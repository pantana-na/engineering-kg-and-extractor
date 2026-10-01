"""Automated Evaluation Dataset Builder from Extracted OKF Bundle.

Ingests verified chemical engineering Markdown documents in build/okf_bundle/
and constructs a comprehensive evaluation dataset.
Strictly adheres to Spec-Driven Development, ADK evaluation criteria, and zero hardcoding standards.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml


class _SafeLoader(yaml.SafeLoader):
    pass


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and body from Markdown."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    raw_yaml = parts[1].strip()
    body = parts[2].strip()

    try:
        data = yaml.load(raw_yaml, Loader=_SafeLoader)  # nosec B506
        return data if isinstance(data, dict) else {}, body
    except Exception:
        return {}, body


def _extract_tables(markdown_text: str) -> list[dict[str, Any]]:
    """Extract structured markdown tables from body text."""
    tables: list[dict[str, Any]] = []
    lines = markdown_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and line.endswith("|") and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            # Check for header separator e.g. |---|---| or | :--- | :--- |
            if re.match(r"^\|(\s*:?-+:?\s*\|)+$", next_line):
                headers = [c.strip() for c in line.split("|")[1:-1]]
                rows: list[list[str]] = []
                i += 2
                while (
                    i < len(lines)
                    and lines[i].strip().startswith("|")
                    and lines[i].strip().endswith("|")
                ):
                    row_cells = [c.strip() for c in lines[i].split("|")[1:-1]]
                    if any(row_cells):
                        rows.append(row_cells)
                    i += 1
                if rows:
                    tables.append({"headers": headers, "rows": rows})
                continue
        i += 1
    return tables


def _extract_wiki_links(text: str) -> list[str]:
    """Extract Obsidian-style [[target]] and markdown [title](target) links."""
    obsidian_links = re.findall(r"\[\[(.*?)\]\]", text)
    clean_links = [l.split("|")[0].strip() for l in obsidian_links]
    md_links = re.findall(r"\[.*?\]\((/?[a-zA-Z0-9_\-./]+(?:\.md)?)\)", text)
    all_links = sorted(set(clean_links + md_links))
    return all_links


def _extract_instrument_tags(text: str) -> list[str]:
    """Find instrument tags matching ISA patterns, e.g. TI-0404, FT-0401A, PSV-23-0401A."""
    pattern = r"\b(?:[A-Z]{2,4}-(?:\d{2}-)?\d{3,4}[A-Z]*(?:/[A-Z]+)*)\b"
    found = re.findall(pattern, text)
    excluded_prefixes = ("DWG-", "PS-", "SA-", "REV-", "STD-", "FIG-")
    valid = [t for t in found if not any(t.startswith(p) for p in excluded_prefixes)]
    return sorted(set(valid))


def build_wiki_eval_record(file_path: Path, wiki_root: Path) -> dict[str, Any]:
    """Construct an individual evaluation test case from a wiki markdown document."""
    rel_path = file_path.relative_to(wiki_root)
    parts = rel_path.parts

    category = parts[0] if len(parts) > 1 else "root"
    stem = file_path.stem

    raw_content = file_path.read_text(encoding="utf-8", errors="replace")
    frontmatter, body = _parse_frontmatter(raw_content)

    # Title derivation
    title = frontmatter.get("name") or frontmatter.get("title")
    if not title:
        h1_match = re.search(r"^#\s+(.*)$", body, re.MULTILINE)
        title = (
            h1_match.group(1).strip() if h1_match else stem.replace("-", " ").title()
        )

    # Target entity tag
    target_tag = frontmatter.get("tag") or stem

    # Unit derivation
    unit = frontmatter.get("unit") or "CDN"

    # Sources derivation
    sources_meta = frontmatter.get("sources") or []
    if isinstance(sources_meta, str):
        sources_meta = [sources_meta]
    elif not isinstance(sources_meta, list):
        sources_meta = []

    # Search body for source citations if empty
    if not sources_meta:
        body_sources = re.findall(
            r"(?:Source|Drawing|P&ID|DWG)\s*[:\-]?\s*([0-9A-Z\-_\.]+(?:\.pdf)?)",
            body,
            re.IGNORECASE,
        )
        sources_meta = sorted(set(body_sources))[:5]

    # Tables extraction
    tables = _extract_tables(body)

    # Instruments & cross-links
    instruments = _extract_instrument_tags(raw_content)
    cross_links = _extract_wiki_links(raw_content)

    # Key parameters from tables
    parameters: list[dict[str, str]] = []
    for t in tables:
        headers_lower = [h.lower() for h in t["headers"]]
        if any(
            k in headers_lower
            for k in ("parameter", "property", "item", "service", "tag")
        ):
            param_col = next(
                (
                    i
                    for i, h in enumerate(headers_lower)
                    if h in ("parameter", "property", "item")
                ),
                0,
            )
            val_col = next(
                (
                    i
                    for i, h in enumerate(headers_lower)
                    if h in ("value", "calibrated range", "set pressure", "setpoint")
                ),
                1 if len(t["headers"]) > 1 else 0,
            )
            unit_col = next(
                (i for i, h in enumerate(headers_lower) if "unit" in h), None
            )

            for row in t["rows"]:
                if len(row) > max(param_col, val_col):
                    p_name = row[param_col]
                    p_val = row[val_col]
                    p_unit = (
                        row[unit_col]
                        if unit_col is not None and len(row) > unit_col
                        else ""
                    )
                    if p_name and p_val and p_name != "—":
                        parameters.append(
                            {"parameter": p_name, "value": p_val, "unit": p_unit}
                        )

    # Determine expected intent & tools
    if category == "equipment":
        expected_intent = "GENERATE_OKF_CONCEPT"
        expected_tools = [
            "process_raw_pdf_tool",
            "generate_equipment_okf_tool",
            "validate_okf_bundle_tool",
        ]
        prompt = f"Extract verified equipment concept for {title} (Tag: {target_tag}) from reference/raw and synthesize into OKF v0.2."
    elif category == "instruments":
        expected_intent = "GENERATE_OKF_CONCEPT"
        expected_tools = [
            "process_raw_pdf_tool",
            "generate_okf_concept_tool",
            "validate_okf_bundle_tool",
        ]
        prompt = f"Extract instrumentation register for {title} ({unit} section) including setpoints and SIS interlocks into OKF v0.2."
    elif category == "hazards":
        expected_intent = "GENERATE_OKF_CONCEPT"
        expected_tools = [
            "process_raw_pdf_tool",
            "generate_okf_concept_tool",
            "validate_okf_bundle_tool",
        ]
        prompt = f"Extract chemical process hazard profile for {title} including critical runaway limits and safeguards into OKF v0.2."
    elif category == "hazop":
        expected_intent = "GENERATE_OKF_CONCEPT"
        expected_tools = [
            "process_raw_pdf_tool",
            "generate_okf_concept_tool",
            "validate_okf_bundle_tool",
        ]
        prompt = f"Extract HAZOP study matrix for {title} ({unit}) with deviation causes, consequences, and safeguards into OKF v0.2."
    elif category == "root" and stem in ("index", "log"):
        expected_intent = "BUILD_OKF_BUNDLE"
        expected_tools = ["build_okf_indexes_and_validate_tool"]
        prompt = f"Compile progressive disclosure OKF v0.2 bundle index and log for {title} ({rel_path})."
    else:
        expected_intent = "GENERATE_OKF_CONCEPT"
        expected_tools = ["process_raw_pdf_tool", "generate_okf_concept_tool"]
        prompt = f"Extract process technical document for {title} ({rel_path}) into OKF v0.2 format."

    return {
        "eval_id": f"eval-{category}-{stem}",
        "relative_wiki_path": str(rel_path),
        "category": category,
        "target_tag": target_tag,
        "title": title,
        "unit": unit,
        "user_prompt": prompt,
        "expected_intent": expected_intent,
        "expected_tool_trajectory": expected_tools,
        "source_files": sources_meta,
        "ground_truth": {
            "title": title,
            "tag": target_tag,
            "category": category,
            "unit": unit,
            "frontmatter": frontmatter,
            "parameter_count": len(parameters),
            "parameters_sample": parameters[:10],
            "table_count": len(tables),
            "instrument_tags_found": instruments[:15],
            "associated_wiki_links": cross_links[:15],
            "content_length_chars": len(raw_content),
        },
        "verification_rules": {
            "min_table_count": 1 if tables else 0,
            "required_source_citations": sources_meta[:3],
            "target_instruments": instruments[:5],
            "key_parameters": [p["parameter"] for p in parameters[:5]],
        },
    }


# Patterns identifying human-synthesized post-extraction HAZOP analysis (not directly extracted from raw)
SYNTHESIZED_HAZOP_PATTERNS = (
    "hazop/nodes/",
    "hazop/action-register.md",
    "hazop/interlock-esd-summary.md",
    "hazop/examples/",
    "hazop/templates/",
)


def is_synthesized_analysis(rel_path_str: str) -> bool:
    """Check if a file is post-extraction human engineering synthesis rather than raw document extraction."""
    norm_path = rel_path_str.replace("\\", "/")
    return any(pattern in norm_path for pattern in SYNTHESIZED_HAZOP_PATTERNS)


def generate_all_wiki_eval_dataset(
    wiki_dir: Path,
    output_jsonl: Path,
    filter_synthesized: bool = True,
) -> dict[str, Any]:
    """Scan reference/wiki/ and generate complete JSONL evaluation dataset, filtering out synthesized analyses."""
    if not wiki_dir.exists():
        raise FileNotFoundError(f"Wiki directory does not exist: {wiki_dir}")

    md_files = sorted(wiki_dir.rglob("*.md"))
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    filtered_out: list[str] = []

    for md_file in md_files:
        rel_path = md_file.relative_to(wiki_dir)
        rel_str = str(rel_path)
        if filter_synthesized and is_synthesized_analysis(rel_str):
            filtered_out.append(rel_str)
            continue
        record = build_wiki_eval_record(md_file, wiki_dir)
        records.append(record)
        cat = record["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    with open(output_jsonl, "w", encoding="utf-8") as f:
        f.writelines(
            json.dumps(rec, ensure_ascii=False, default=str) + "\n" for rec in records
        )

    return {
        "total_records": len(records),
        "filtered_synthesized_count": len(filtered_out),
        "filtered_files": filtered_out,
        "output_file": str(output_jsonl),
        "category_distribution": category_counts,
    }


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent.parent
    wiki_path = repo_root / "reference" / "wiki"
    dest_path = repo_root / "evals" / "datasets" / "wiki_ground_truth_eval.jsonl"
    result = generate_all_wiki_eval_dataset(wiki_path, dest_path)
    print(json.dumps(result, indent=2, default=str))
