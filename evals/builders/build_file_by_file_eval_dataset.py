"""Automated File-by-File (Document-Centric) Evaluation Dataset Builder.

Scans all supported raw engineering documents (.pdf, .xlsx, .xlsm, .csv, .docx,
.png, .jpg, .jpeg, .webp) in reference/raw/ across all 6 subfolders
(data_sheets, operating_manuals, pfd, pid, standards, moc), maps each raw file
to its extracted OKF concepts in build/okf_bundle/, and generates the
evals/datasets/raw_file_by_file_eval.jsonl benchmark dataset with moc ordered last.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from evals.builders.build_wiki_eval_dataset import (
    _extract_instrument_tags,
    _extract_tables,
    _parse_frontmatter,
    is_synthesized_analysis,
)
from extracter_agent.pdf.processor import (
    SUPPORTED_RAW_EXTENSIONS,
    is_supported_raw_file,
)

SUBFOLDER_PRIORITY: dict[str, int] = {
    "data_sheets": 0,
    "operating_manuals": 1,
    "pfd": 2,
    "pid": 3,
    "standards": 4,
    "moc": 5,
}


def _extract_parameters_from_tables(tables: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract parameter/value/unit triples from parsed Markdown tables."""
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
    return parameters


def _index_wiki_ground_truth(wiki_dir: Path) -> list[dict[str, Any]]:
    """Load and index all non-synthesized ground-truth Markdown concepts in reference/wiki/."""
    wiki_entries: list[dict[str, Any]] = []
    for md_file in sorted(wiki_dir.rglob("*.md")):
        if md_file.name.lower() in ("index.md", "log.md"):
            continue
        rel_path = md_file.relative_to(wiki_dir)
        rel_str = str(rel_path).replace("\\", "/")
        if is_synthesized_analysis(rel_str):
            continue
        raw_text = md_file.read_text(encoding="utf-8", errors="replace")
        fm, body = _parse_frontmatter(raw_text)
        tables = _extract_tables(body)
        params = _extract_parameters_from_tables(tables)
        instruments = _extract_instrument_tags(raw_text)
        category = rel_path.parts[0] if len(rel_path.parts) > 1 else "root"
        concept_id = rel_str.removesuffix(".md")
        title = (
            fm.get("name")
            or fm.get("title")
            or md_file.stem.replace("-", " ").title()
        )
        tag = fm.get("tag") or md_file.stem
        wiki_entries.append(
            {
                "concept_id": concept_id,
                "relative_wiki_path": rel_str,
                "category": category,
                "title": str(title),
                "tag": str(tag),
                "frontmatter": fm,
                "raw_text_lower": raw_text.lower(),
                "parameters": params,
                "instruments": instruments,
                "table_count": len(tables),
            }
        )
    return wiki_entries


def build_raw_file_eval_record(
    pdf_path: Path,
    raw_dir: Path,
    wiki_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Construct a file-by-file evaluation test case for a single supported raw file in reference/raw/."""
    rel_to_raw = pdf_path.relative_to(raw_dir)
    subfolder = rel_to_raw.parts[0] if len(rel_to_raw.parts) > 1 else "root"
    rel_repo_path = f"reference/raw/{str(rel_to_raw).replace(chr(92), '/')}"
    filename = pdf_path.name
    stem = pdf_path.stem
    doc_prefix = stem.split("_")[0]

    filename_lower = filename.lower()
    prefix_pattern = re.compile(
        r"(?<![a-z0-9])" + re.escape(doc_prefix.lower()) + r"(?![a-z0-9])"
    )

    matched_entries: list[dict[str, Any]] = []
    for entry in wiki_entries:
        haystack = entry["raw_text_lower"]
        if filename_lower in haystack or prefix_pattern.search(haystack):
            matched_entries.append(entry)

    source_concepts = [
        e["concept_id"] for e in matched_entries if e["category"] == "sources"
    ]
    domain_concepts = [
        e["concept_id"] for e in matched_entries if e["category"] != "sources"
    ]
    affected_concepts = source_concepts + domain_concepts
    affected_categories = sorted({e["category"] for e in matched_entries})

    equipment_tags = sorted(
        {e["tag"] for e in matched_entries if e["category"] == "equipment"}
    )
    instrument_tags: list[str] = []
    seen_inst: set[str] = set()
    for e in matched_entries:
        for inst in e["instruments"]:
            if inst not in seen_inst:
                seen_inst.add(inst)
                instrument_tags.append(inst)

    parameters_sample: list[dict[str, str]] = []
    seen_params: set[str] = set()
    for e in matched_entries:
        for p in e["parameters"]:
            key = f"{p['parameter']}={p['value']}"
            if key not in seen_params:
                seen_params.add(key)
                parameters_sample.append(p)
                if len(parameters_sample) >= 10:
                    break
        if len(parameters_sample) >= 10:
            break

    expected_tools = ["process_raw_pdf_tool"]
    if equipment_tags or subfolder == "data_sheets":
        expected_tools.append("generate_equipment_okf_tool")
    expected_tools.append("generate_okf_concept_tool")

    safe_eval_slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    eval_id = f"eval-raw-{subfolder.replace('_', '-')}-{safe_eval_slug}"

    user_prompt = (
        f"Process raw engineering file {rel_repo_path} and incrementally extract "
        f"and update all affected OKF v0.2 concepts (source summary, equipment, "
        f"instruments, units, hazards, or procedures) in the bundle."
    )

    return {
        "eval_id": eval_id,
        "raw_pdf_path": rel_repo_path,
        "subfolder": subfolder,
        "pdf_filename": filename,
        "file_extension": pdf_path.suffix.lower(),
        "document_code": doc_prefix,
        "category": f"raw_{subfolder}",
        "user_prompt": user_prompt,
        "expected_intent": "GENERATE_OKF_CONCEPT",
        "expected_tool_trajectory": expected_tools,
        "expected_source_concepts": source_concepts,
        "expected_domain_concepts": domain_concepts,
        "expected_affected_concepts": affected_concepts,
        "expected_affected_categories": affected_categories,
        "ground_truth": {
            "raw_pdf_path": rel_repo_path,
            "document_code": doc_prefix,
            "subfolder": subfolder,
            "affected_concept_count": len(affected_concepts),
            "affected_concepts": affected_concepts,
            "equipment_tags": equipment_tags,
            "instrument_tags_sample": instrument_tags[:15],
            "parameters_sample": parameters_sample,
        },
        "verification_rules": {
            "must_ingest_pdf": filename,
            "min_affected_concepts": 1,
            "expected_concepts": affected_concepts,
            "expected_equipment_tags": equipment_tags,
        },
    }


def _raw_file_sort_key(path: Path, raw_dir: Path) -> tuple[int, tuple[str, ...]]:
    """Sort raw files deterministically by SUBFOLDER_PRIORITY (with 'moc' last = 5), then relative path parts."""
    rel_parts = path.relative_to(raw_dir).parts
    subfolder = rel_parts[0] if len(rel_parts) > 1 else "root"
    return (SUBFOLDER_PRIORITY.get(subfolder, 99), rel_parts)


def generate_raw_file_by_file_eval_dataset(
    raw_dir: Path,
    wiki_dir: Path,
    output_jsonl: Path,
) -> dict[str, Any]:
    """Scan all supported raw engineering files in reference/raw/ and generate the file-by-file JSONL dataset."""
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw directory does not exist: {raw_dir}")
    if not wiki_dir.exists():
        raise FileNotFoundError(f"Wiki directory does not exist: {wiki_dir}")

    wiki_entries = _index_wiki_ground_truth(wiki_dir)
    raw_files = sorted(
        (
            p
            for p in raw_dir.rglob("*")
            if p.is_file()
            and is_supported_raw_file(p)
            and p.suffix.lower() in SUPPORTED_RAW_EXTENSIONS
        ),
        key=lambda p: _raw_file_sort_key(p, raw_dir),
    )
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    subfolder_counts: dict[str, int] = {}
    extension_counts: dict[str, int] = {}
    unmapped_files: list[str] = []
    total_concept_links = 0

    for raw_file in raw_files:
        rec = build_raw_file_eval_record(raw_file, raw_dir, wiki_entries)
        records.append(rec)
        sf = rec["subfolder"]
        ext = rec["file_extension"]
        subfolder_counts[sf] = subfolder_counts.get(sf, 0) + 1
        extension_counts[ext] = extension_counts.get(ext, 0) + 1
        n_concepts = len(rec["expected_affected_concepts"])
        total_concept_links += n_concepts
        if n_concepts == 0:
            unmapped_files.append(rec["raw_pdf_path"])

    with open(output_jsonl, "w", encoding="utf-8") as f:
        f.writelines(
            json.dumps(rec, ensure_ascii=False, default=str) + "\n" for rec in records
        )

    return {
        "total_raw_files": len(records),
        "subfolder_distribution": subfolder_counts,
        "extension_distribution": extension_counts,
        "total_concept_links": total_concept_links,
        "unmapped_files_count": len(unmapped_files),
        "unmapped_files": unmapped_files,
        "output_file": str(output_jsonl),
    }


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent.parent
    raw_path = repo_root / "reference" / "raw"
    wiki_path = repo_root / "build" / "okf_bundle"
    dest_path = repo_root / "evals" / "datasets" / "raw_file_by_file_eval.jsonl"
    summary = generate_raw_file_by_file_eval_dataset(raw_path, wiki_path, dest_path)
    print(json.dumps(summary, indent=2, default=str))
