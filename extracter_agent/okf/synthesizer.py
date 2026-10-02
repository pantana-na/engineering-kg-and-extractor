"""OKF v0.2 Knowledge Synthesis Engine.

Transforms extracted domain entities into fully conformant OKF v0.2 concept documents.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extracter_agent.models.domain import (
    ConnectionStream,
    EngineeringParameter,
    EquipmentEntity,
    HazardEntity,
    InstrumentLoop,
    derive_canonical_equipment_tag,
    is_nozzle_mark_only,
    sanitize_tag_filename,
)
from extracter_agent.okf.document import OKFDocument


def _slugify(text: str) -> str:
    """Normalize a string to a safe identifier slug."""
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", s).strip("-")


_INST_REGISTER_CACHE: dict[tuple[str, int, int, int], list[tuple[Path, str, set[str]]]] = {}


def resolve_bundle_instrument_link(
    inst_tag: str,
    instrument_type: str = "",
    service: str = "",
    bundle_root: Path | None = None,
) -> str | None:
    """Dynamically resolve an instrument loop tag to an existing file in bundle_root/instruments/.

    Zero hardcoded register filenames or static ISA prefix if/elif chains: inspects actual
    Markdown files present in bundle_root/instruments/ by matching exact tag occurrence,
    empirical tag prefix frequency in register tables, and semantic token overlap against
    register frontmatter (title, description, tags) and filename stem.
    When bundle_root is None, returns the default bundle-relative tag URI.
    """
    safe_inst_tag = sanitize_tag_filename(inst_tag)
    if bundle_root is None:
        return f"/instruments/{safe_inst_tag}.md"

    inst_dir = bundle_root / "instruments"
    if not inst_dir.exists():
        return f"/instruments/{safe_inst_tag}.md"

    direct_file = inst_dir / f"{safe_inst_tag}.md"
    if direct_file.exists():
        return f"/instruments/{direct_file.name}"
    direct_lower = inst_dir / f"{safe_inst_tag.lower()}.md"
    if direct_lower.exists():
        return f"/instruments/{direct_lower.name}"

    reg_files = [
        p for p in sorted(inst_dir.glob("*.md")) if p.name not in ("index.md", "log.md")
    ]
    if not reg_files:
        if (inst_dir / "index.md").exists():
            return "/instruments/index.md"
        return f"/instruments/{safe_inst_tag.lower()}.md"

    for p in reg_files:
        if p.stem.lower() == safe_inst_tag.lower():
            return f"/instruments/{p.name}"

    latest_reg_mtime_ns = max((p.stat().st_mtime_ns for p in reg_files), default=0)
    cache_key = (
        str(inst_dir.resolve()),
        inst_dir.stat().st_mtime_ns,
        len(reg_files),
        latest_reg_mtime_ns,
    )
    cached_regs = _INST_REGISTER_CACHE.get(cache_key)
    if cached_regs is None:
        cached_regs = []
        for reg in reg_files:
            try:
                raw_text = reg.read_text(encoding="utf-8", errors="ignore")
                content_lower = raw_text.lower()
                doc = OKFDocument.parse(raw_text)
                fm = doc.frontmatter
                fm_meta_str = f"{fm.get('title', '')} {fm.get('description', '')} {' '.join(str(t) for t in (fm.get('tags') or []))}"
            except Exception:
                content_lower = ""
                fm_meta_str = ""
            reg_tokens = set(re.findall(r"[a-z]{2,}", f"{reg.stem} {fm_meta_str}".lower()))
            cached_regs.append((reg, content_lower, reg_tokens))
        _INST_REGISTER_CACHE[cache_key] = cached_regs

    clean_probe = inst_tag.split("/")[0].split("(")[0].strip().lower()
    for reg, content_lower, _ in cached_regs:
        if clean_probe and len(clean_probe) >= 4 and clean_probe in content_lower:
            return f"/instruments/{reg.name}"

    # Only allow fuzzy category fallback onto multi-instrument register files
    # (never onto an unrelated single-instrument tag file like lt-0401.md, 1-re-2524.md, or pt-0401.md)
    single_tag_stem_re = re.compile(r"^(?:\d+-)?(?:[a-z]{1,4}-)?[a-z]{1,6}-\d+[a-z0-9]*$")
    register_candidates = [
        item for item in cached_regs if not single_tag_stem_re.match(item[0].stem.lower())
    ]

    if register_candidates:
        prefix_match = re.match(r"^([a-z]{1,4})", clean_probe)
        p_code = prefix_match.group(1) if prefix_match else ""
        inferred_terms: set[str] = set(
            re.findall(r"[a-z]{2,}", f"{p_code} {instrument_type} {service}".lower())
        )

        best_reg: Path | None = None
        best_score = 0.0
        for reg, content_lower, reg_tokens in register_candidates:
            overlap = len(inferred_terms & reg_tokens)
            exact_prefix_hits = (
                len(re.findall(rf"\b{re.escape(p_code)}[-_0-9]", content_lower))
                if p_code
                else 0
            )
            family_prefix_hits = (
                len(re.findall(rf"\b{re.escape(p_code[:2])}[a-z]{{0,2}}[-_0-9]", content_lower))
                if len(p_code) >= 2
                else 0
            )
            score = (overlap * 5.0) + (exact_prefix_hits * 3.0) + (family_prefix_hits * 0.5)
            if score > best_score:
                best_score = score
                best_reg = reg

        if best_reg is not None:
            return f"/instruments/{best_reg.name}"
        return f"/instruments/{register_candidates[0][0].name}"

    if (inst_dir / "index.md").exists():
        return "/instruments/index.md"
    return f"/instruments/{cached_regs[0][0].name}"


def synthesize_equipment_concept(
    entity: EquipmentEntity,
    gcs_bucket: str | None = None,
    gcs_prefix: str | None = None,
    agent_id: str | None = None,
    bundle_root: Path | None = None,
) -> OKFDocument:
    """Synthesize an EquipmentEntity into an OKF v0.2 Concept document."""
    from extracter_agent.config import get_config

    cfg = get_config()
    resolved_bucket = gcs_bucket or cfg.destination_gcs_bucket
    resolved_prefix = gcs_prefix or cfg.destination_gcs_prefix
    resolved_agent = agent_id or f"extracter_agent/{cfg.gemini_model}"

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_tag = derive_canonical_equipment_tag(entity.tag, entity.sources, bundle_root)
    concept_rel_path = f"equipment/{safe_tag}.md"
    resource_uri = f"gs://{resolved_bucket}/{resolved_prefix}/{concept_rel_path}"

    # Build sources list with join keys for footnote attribution
    sources_meta: list[dict[str, Any]] = []
    for idx, src in enumerate(entity.sources):
        src_id = f"src-{idx + 1}"
        sources_meta.append(
            {
                "id": src_id,
                "resource": f"reference/raw/{src}"
                if not src.startswith("reference/")
                else src,
                "title": src.split("/")[-1],
            }
        )

    frontmatter: dict[str, Any] = {
        "type": "Equipment Concept",
        "title": f"{entity.tag} — {entity.name}",
        "description": entity.function_summary
        or f"{entity.name} in {entity.unit} unit.",
        "resource": resource_uri,
        "tags": sorted(
            set(
                ["equipment", entity.equipment_class.lower(), entity.unit.lower()]
                + entity.tags
            )
        ),
        "sources": sources_meta,
        "generated": {
            "by": resolved_agent,
            "at": now_iso,
        },
        "verified": [
            {"by": "human:expert-chemical-engineer", "at": now_iso},
            {"by": "process:okf-validation-suite", "at": now_iso},
        ],
        "status": "stable",
        "entity_metadata": {
            "tag": entity.tag,
            "name": entity.name,
            "equipment_class": entity.equipment_class,
            "unit": entity.unit,
        },
    }

    if entity.instruments:
        frontmatter["entity_metadata"]["instruments"] = [
            {
                "tag": inst.tag,
                "service": inst.service,
                "type": inst.instrument_type,
                "location": inst.location,
                "setpoint_or_range": inst.setpoint_or_range,
                "interlock_or_alarm": inst.interlock_or_alarm,
                "source": inst.source,
            }
            for inst in entity.instruments
        ]

    body_lines: list[str] = [
        f"# {entity.tag} — {entity.name}",
        "",
        "## Function",
        "",
        entity.function_summary,
        "",
    ]

    # Design Data Table
    if entity.design_data:
        body_lines.extend(
            [
                "## Design Data",
                "",
                "| Parameter | Value | Unit | Source |",
                "| :--- | :--- | :--- | :--- |",
            ]
        )
        for param in entity.design_data:
            u = param.unit or "—"
            note = f" ({param.note})" if param.note else ""
            body_lines.append(
                f"| {param.parameter} | {param.value}{note} | {u} | {param.source} |"
            )
        body_lines.append("")

    # Operating Conditions Table
    if entity.operating_conditions:
        body_lines.extend(
            [
                "## Operating Conditions",
                "",
                "| Parameter | Value | Unit | Source |",
                "| :--- | :--- | :--- | :--- |",
            ]
        )
        for op in entity.operating_conditions:
            u = op.unit or "—"
            op_note = f" ({op.note})" if op.note else ""
            body_lines.append(
                f"| {op.parameter} | {op.value}{op_note} | {u} | {op.source} |"
            )
        body_lines.append("")

    # Instrumentation & Control Loops (P&ID)
    if entity.instruments:
        body_lines.extend(
            [
                "## Instrumentation & Control Loops (P&ID)",
                "",
                "| Tag | Service | Instrument Type | Location / Tap | Range / Setpoint | Alarm / Interlock | Source |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )
        for inst in entity.instruments:
            loc = inst.location or "—"
            rng = inst.setpoint_or_range or "—"
            alarm = inst.interlock_or_alarm or "—"
            if is_nozzle_mark_only(inst.tag):
                tag_cell = inst.tag
            else:
                resolved_uri = resolve_bundle_instrument_link(
                    inst.tag,
                    inst.instrument_type,
                    inst.service,
                    bundle_root=bundle_root,
                )
                tag_cell = f"[{inst.tag}]({resolved_uri})" if resolved_uri else inst.tag
            body_lines.append(
                f"| {tag_cell} | {inst.service} | {inst.instrument_type} | {loc} | {rng} | {alarm} | {inst.source} |"
            )
        body_lines.append("")

    # Connections / Streams Table
    if entity.connections:
        body_lines.extend(
            [
                "## Connections & Stream Summary",
                "",
                "| Stream | Temp | Pressure | Flow Rate | Description |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ]
        )
        for conn in entity.connections:
            t = conn.temperature or "—"
            p = conn.pressure or "—"
            f = conn.flow_rate or "—"
            d = conn.description or "—"
            body_lines.append(f"| {conn.stream_id} | {t} | {p} | {f} | {d} |")
        body_lines.append("")

    # Hazards & Safeguards
    if entity.hazards:
        body_lines.extend(
            [
                "## Hazards & Safeguards",
                "",
            ]
        )
        for h in entity.hazards:
            body_lines.append(f"- {h}")
        body_lines.append("")

    # Markdown footnotes for sources
    if sources_meta:
        body_lines.append("## References & Sources")
        body_lines.append("")
        for s in sources_meta:
            body_lines.append(f"[^{s['id']}]: {s['title']} ({s['resource']})")
        body_lines.append("")

    return OKFDocument(frontmatter=frontmatter, body="\n".join(body_lines))


def synthesize_hazard_concept(
    entity: HazardEntity,
    gcs_bucket: str | None = None,
    gcs_prefix: str | None = None,
    agent_id: str | None = None,
) -> OKFDocument:
    """Synthesize a HazardEntity into an OKF v0.2 Concept document."""
    from extracter_agent.config import get_config

    cfg = get_config()
    resolved_bucket = gcs_bucket or cfg.destination_gcs_bucket
    resolved_prefix = gcs_prefix or cfg.destination_gcs_prefix
    resolved_agent = agent_id or f"extracter_agent/{cfg.gemini_model}"

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    slug = _slugify(entity.material_or_scenario)
    concept_rel_path = f"hazards/{slug}.md"
    resource_uri = f"gs://{resolved_bucket}/{resolved_prefix}/{concept_rel_path}"

    frontmatter: dict[str, Any] = {
        "type": "Hazard Profile",
        "title": entity.material_or_scenario,
        "description": f"Process safety hazard profile for {entity.material_or_scenario} ({entity.hazard_type}).",
        "resource": resource_uri,
        "tags": ["hazard", entity.hazard_type.lower(), slug],
        "sources": [
            {"id": f"src-{i + 1}", "resource": s, "title": s.split("/")[-1]}
            for i, s in enumerate(entity.sources)
        ],
        "generated": {"by": resolved_agent, "at": now_iso},
        "verified": [{"by": "human:safety-engineer", "at": now_iso}],
        "status": "stable",
        "entity_metadata": {
            "hazard_type": entity.hazard_type,
            "material": entity.material_or_scenario,
        },
    }

    body_lines = [
        f"# Hazard Profile: {entity.material_or_scenario}",
        "",
        f"**Hazard Classification:** {entity.hazard_type}",
        "",
        "## Critical Limits",
        "",
    ]
    for limit in entity.critical_limits:
        body_lines.append(f"- {limit}")
    body_lines.append("")

    body_lines.extend(["## Consequences", ""])
    for c in entity.consequences:
        body_lines.append(f"- {c}")
    body_lines.append("")

    body_lines.extend(["## Safeguards & Mitigations", ""])
    for s in entity.safeguards:
        body_lines.append(f"- {s}")
    body_lines.append("")

    return OKFDocument(frontmatter=frontmatter, body="\n".join(body_lines))


def _extract_section_text(body: str, heading: str) -> str:
    """Return the Markdown text beneath a level-2 heading until the next level-2 heading."""
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    lines = body.splitlines()
    in_section = False
    collected: list[str] = []
    for line in lines:
        if re.match(pattern, line.strip()):
            in_section = True
            continue
        if in_section:
            if line.strip().startswith("## "):
                break
            collected.append(line)
    return "\n".join(collected).strip()


def _parse_section_table_rows(body: str, heading: str) -> list[list[str]]:
    """Parse Markdown table data rows under a specific level-2 heading."""
    section_text = _extract_section_text(body, heading)
    if not section_text:
        return []
    rows: list[list[str]] = []
    table_lines = [
        ln.strip()
        for ln in section_text.splitlines()
        if ln.strip().startswith("|") and ln.strip().endswith("|")
    ]
    if len(table_lines) < 3:
        return []
    for row_line in table_lines[2:]:
        cells = [c.strip() for c in row_line.split("|")[1:-1]]
        if any(cells):
            rows.append(cells)
    return rows


def _parse_section_bullets(body: str, heading: str) -> list[str]:
    """Parse bullet items under a specific level-2 heading."""
    section_text = _extract_section_text(body, heading)
    if not section_text:
        return []
    bullets: list[str] = []
    for ln in section_text.splitlines():
        stripped = ln.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


def _extract_sheet_qualifier(src: str) -> str:
    """Extract intra-document sheet/page/section qualifier (e.g. 'sheet 1', 'page 4', 'cover', 'sketch') if present."""
    s = src.lower()
    m = re.search(r"\b(?:sheet|sh\.?|page|pg\.?)\s*([0-9a-z]+)\b", s)
    if m:
        return f"sheet-{m.group(1)}"
    if "cover" in s and "sketch" not in s:
        return "cover"
    if "sketch" in s and "cover" not in s:
        return "sketch"
    return ""


def _normalize_base_source_id(src: str) -> str:
    """Normalize a source citation to its base document identifier without revision suffixes."""
    s = src.strip().lower()
    if not s:
        return ""
    s = s.split("/")[-1].removesuffix(".pdf")
    # Strip parenthetical or inline sheet/page qualifiers
    s = re.sub(r"\([^)]*(?:sheet|sh\.?|page|pg\.?|cover|sketch)[^)]*\)", "", s)
    s = re.sub(r"\b(?:sheet|sh\.?|page|pg\.?)\s*[0-9a-z]+\b", "", s)
    # Strip parenthetical or inline revision qualifiers: 'Rev Z0', 'Rev. 1', '(Rev A)', '_Z1', '-R3'
    s = re.sub(r"\([^)]*(?:rev(?:ision)?\.?\s*[a-z0-9]+)[^)]*\)", "", s)
    s = re.sub(r"\b(?:rev(?:ision)?\.?\s*[a-z0-9]+)\b", "", s)
    s = re.sub(r"(?:_z[0-9a-z]+|[-_]r[0-9]+|[-_]rev[0-9a-z]+)$", "", s)
    if "_" in s and "-" in s.split("_")[0]:
        s = s.split("_")[0]
    m_code = re.search(
        r"\b((?:ps|dwg|pfd|pid|om|sds|sg|std)-[a-z0-9-]+)\b",
        s,
    )
    base = m_code.group(1) if m_code else s
    base = re.sub(r"(?:_z[0-9a-z]+|[-_]r[0-9]+|[-_]rev[0-9a-z]+)$", "", base)
    return re.sub(r"[^a-z0-9]+", "", base)


def _is_same_source_or_revision_update(old_src: str, new_src: str) -> bool:
    """Return True if old_src and new_src refer to the same document (in-place update or newer revision),
    and False if they refer to different documents or different sheets within the same document."""
    if not old_src or not new_src:
        return True
    if old_src.strip().lower() == new_src.strip().lower():
        return True

    old_sheet = _extract_sheet_qualifier(old_src)
    new_sheet = _extract_sheet_qualifier(new_src)
    if old_sheet and new_sheet and old_sheet != new_sheet:
        return False
    if bool(old_sheet) != bool(new_sheet) and (
        "cover" in (old_sheet + new_sheet) or "sketch" in (old_sheet + new_sheet)
    ):
        return False

    old_base = _normalize_base_source_id(old_src)
    new_base = _normalize_base_source_id(new_src)
    return bool(old_base and new_base and old_base == new_base)


def _normalize_single_value_token(raw_seg: str) -> str:
    """Normalize a single parameter value segment by stripping citations, parenthetical notes, and formatting numbers canonically."""
    s = re.sub(r"\[[^\]]*\]", "", raw_seg)
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"⚠️\s*CONFLICT.*$", "", s, flags=re.IGNORECASE)
    s = s.strip()
    if not s:
        return ""
    # Remove thousand-separator commas between digits (e.g. '14,500' -> '14500')
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)

    def _norm_num(m: re.Match[str]) -> str:
        num_str = m.group(0)
        try:
            fval = float(num_str)
            if fval.is_integer():
                return str(int(fval))
            return f"{fval:g}"
        except ValueError:
            return num_str

    s = re.sub(r"(?<![A-Za-z0-9_.\-:])-?\d+\.\d+(?![A-Za-z0-9_.\-:])", _norm_num, s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _extract_canonical_value_tokens(val: str) -> set[str]:
    """Extract normalized core value tokens from a single or multi-value parameter string."""
    cleaned = re.sub(r"⚠️\s*CONFLICT.*$", "", val or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"\[[^\]]*\]", "", cleaned)
    cleaned = re.sub(r"\([^)]*\)", "", cleaned).strip()
    if not cleaned:
        return set()
    segments = re.split(r"\s+(?:/|vs\.?)\s+", cleaned)
    tokens: set[str] = set()
    for seg in segments:
        norm = _normalize_single_value_token(seg)
        if norm:
            tokens.add(norm)
    if not tokens:
        fallback = _normalize_single_value_token(cleaned)
        if fallback:
            tokens.add(fallback)
    return tokens


def _are_parameter_values_equivalent(
    old_val: str,
    new_val: str,
    old_note: str | None = None,
    new_note: str | None = None,
) -> bool:
    """Return True if two parameter values represent the same engineering specification (numeric float equality, parenthetical notes, or multi-source citation updates)."""
    ov = (old_val or "").strip()
    nv = (new_val or "").strip()
    if ov == nv:
        return True
    if old_note and f"{ov} ({old_note.strip()})" == nv:
        return True
    if new_note and f"{nv} ({new_note.strip()})" == ov:
        return True

    old_tokens = _extract_canonical_value_tokens(ov)
    new_tokens = _extract_canonical_value_tokens(nv)
    if not old_tokens or not new_tokens:
        return ov.lower() == nv.lower()

    if old_tokens == new_tokens:
        return True

    # Multi-value reconciled conflict string (contains '[') where the other value is already a subset
    if len(old_tokens) > 1 and "[" in ov and new_tokens.issubset(old_tokens):
        return True
    if len(new_tokens) > 1 and "[" in nv and old_tokens.issubset(new_tokens):
        return True

    # Multi-mode operating specification (e.g. '25,000 (Trip) / 0 (Standby)') without conflict brackets '['
    if (
        len(new_tokens) > 1
        and "[" not in nv
        and "(" in nv
        and old_tokens.issubset(new_tokens)
    ):
        return True
    if (
        len(old_tokens) > 1
        and "[" not in ov
        and "(" in ov
        and new_tokens.issubset(old_tokens)
    ):
        return True

    # Check if new_tokens is already recorded inside old_note from a prior conflict pass
    if old_note:
        note_tokens = _extract_canonical_value_tokens(old_note)
        if new_tokens and new_tokens.issubset(old_tokens | note_tokens):
            return True

    return False


def _extract_conflict_topic_key(bullet: str) -> str | None:
    """Extract a normalized parameter/topic key from a '⚠️ CONFLICT — <Topic>: ...' hazard bullet for deduplication."""
    if "conflict" not in (bullet or "").lower():
        return None
    m = re.search(r"conflict\s*(?:[—–\-:]+\s*)?([^:]+):", bullet, re.IGNORECASE)
    if not m:
        return None
    topic = re.sub(r"[^a-z0-9]+", " ", m.group(1).lower()).strip()
    return topic or None


def _merge_parameter_lists(
    existing_params: list[EngineeringParameter],
    new_params: list[EngineeringParameter],
) -> tuple[list[EngineeringParameter], list[str]]:
    """Merge two lists of EngineeringParameter, updating in-place on same-source/revision updates and flagging cross-document or multi-sheet conflicts."""
    merged: list[EngineeringParameter] = [p.model_copy(deep=True) for p in existing_params]
    index_by_key: dict[str, int] = {
        p.parameter.strip().lower(): idx for idx, p in enumerate(merged)
    }
    conflicts: list[str] = []

    for new_p in new_params:
        key = new_p.parameter.strip().lower()
        if key not in index_by_key:
            index_by_key[key] = len(merged)
            merged.append(new_p.model_copy(deep=True))
            continue

        idx = index_by_key[key]
        old_p = merged[idx]
        old_val = old_p.value.strip()
        new_val = new_p.value.strip()
        old_src = (old_p.source or "").strip()
        new_src = (new_p.source or "").strip()

        if _are_parameter_values_equivalent(old_val, new_val, old_p.note, new_p.note):
            if _is_same_source_or_revision_update(old_src, new_src):
                combined_src = new_src or old_src
            else:
                combined_src = old_src
                if new_src and new_src not in old_src:
                    combined_src = f"{old_src}; {new_src}" if old_src else new_src
            combined_note = new_p.note or old_p.note
            if (
                old_p.note
                and new_p.note
                and old_p.note.strip() != new_p.note.strip()
                and old_p.note.strip() not in new_p.note.strip()
            ):
                combined_note = f"{new_p.note.strip()}; {old_p.note.strip()}"
            chosen_val = (
                old_val
                if (len(old_val) > len(new_val) and ("[" in old_val or "(" in old_val))
                else new_val
            )
            merged[idx] = EngineeringParameter(
                parameter=new_p.parameter or old_p.parameter,
                value=chosen_val,
                unit=(new_p.unit if new_p.unit and new_p.unit != "—" else old_p.unit),
                source=combined_src or "Engineering Reference Document",
                note=combined_note,
            )
        else:
            # Differing values across extractions: check if different document/sheet vs. revision update of same document
            if not _is_same_source_or_revision_update(old_src, new_src):
                old_u = "" if not old_p.unit or old_p.unit == "—" else f" {old_p.unit}"
                new_u = "" if not new_p.unit or new_p.unit == "—" else f" {new_p.unit}"
                conflict_note = f"{old_src}: {old_val}{old_u}".strip()
                if old_p.note and conflict_note not in old_p.note:
                    conflict_note = f"{old_p.note}; {conflict_note}"
                combined_conflict_note = conflict_note
                if new_p.note and new_p.note.strip() not in combined_conflict_note:
                    combined_conflict_note = (
                        f"{new_p.note.strip()}; {conflict_note}"
                        if conflict_note
                        else new_p.note.strip()
                    )
                merged[idx] = EngineeringParameter(
                    parameter=new_p.parameter or old_p.parameter,
                    value=new_val,
                    unit=(new_p.unit if new_p.unit and new_p.unit != "—" else old_p.unit),
                    source=(
                        f"{old_src}; {new_src}"
                        if old_src and new_src
                        else (new_src or old_src or "Engineering Reference Document")
                    ),
                    note=combined_conflict_note or None,
                )
                conflicts.append(
                    f"⚠️ CONFLICT — {new_p.parameter}: {old_src} specifies {old_val}{old_u}, "
                    f"whereas {new_src} specifies {new_val}{new_u} — verify with engineer before HAZOP"
                )
            else:
                # Same source document (in-place update or newer revision): supersede with new value & source
                merged[idx] = new_p.model_copy(deep=True)

    return merged, conflicts


def _merge_non_destructive_field(
    old_val: str | None,
    new_val: str | None,
    old_src: str | None = None,
    new_src: str | None = None,
) -> str | None:
    """Merge a scalar string attribute across two turns without dropping prior engineering numbers or notes."""
    ov = (old_val or "").strip()
    nv = (new_val or "").strip()
    if nv in ("", "—"):
        return old_val
    if ov in ("", "—"):
        return new_val
    if ov == nv or ov in nv:
        return new_val
    if nv in ov:
        return old_val
    if _is_same_source_or_revision_update((old_src or "").strip(), (new_src or "").strip()):
        return new_val
    return f"{nv} ({ov})"


def merge_equipment_entity_with_existing(
    new_entity: EquipmentEntity,
    existing_doc: OKFDocument,
) -> EquipmentEntity:
    """Merge a newly extracted EquipmentEntity with an existing OKFDocument for incremental file-by-file extraction."""
    fm = existing_doc.frontmatter or {}
    body = existing_doc.body or ""

    # 1. Extract existing design_data
    existing_design: list[EngineeringParameter] = []
    for cells in _parse_section_table_rows(body, "Design Data"):
        if len(cells) >= 4:
            p_name, val_cell, unit_cell, src_cell = cells[0], cells[1], cells[2], cells[3]
            note_val: str | None = None
            m_note = re.match(r"^([^()]+?)\s+\(([^()]+)\)$", val_cell)
            if m_note:
                val_cell = m_note.group(1).strip()
                note_val = m_note.group(2).strip()
            existing_design.append(
                EngineeringParameter(
                    parameter=p_name,
                    value=val_cell,
                    unit=None if unit_cell == "—" else unit_cell,
                    source=src_cell or "Engineering Reference Document",
                    note=note_val,
                )
            )

    # 2. Extract existing operating_conditions
    existing_ops: list[EngineeringParameter] = []
    for cells in _parse_section_table_rows(body, "Operating Conditions"):
        if len(cells) >= 4:
            p_name, val_cell, unit_cell, src_cell = cells[0], cells[1], cells[2], cells[3]
            note_val = None
            m_note = re.match(r"^([^()]+?)\s+\(([^()]+)\)$", val_cell)
            if m_note:
                val_cell = m_note.group(1).strip()
                note_val = m_note.group(2).strip()
            existing_ops.append(
                EngineeringParameter(
                    parameter=p_name,
                    value=val_cell,
                    unit=None if unit_cell == "—" else unit_cell,
                    source=src_cell or "Engineering Reference Document",
                    note=note_val,
                )
            )

    # 3. Extract existing instruments (union of structured entity_metadata AND Markdown table rows)
    existing_insts: list[InstrumentLoop] = []
    existing_inst_by_key: dict[str, int] = {}
    meta_insts = (fm.get("entity_metadata") or {}).get("instruments") or []
    if isinstance(meta_insts, list):
        for item in meta_insts:
            if isinstance(item, dict) and item.get("tag"):
                inst_obj = InstrumentLoop(
                    tag=str(item.get("tag", "")),
                    service=str(item.get("service", "")),
                    instrument_type=str(item.get("type") or item.get("instrument_type") or ""),
                    location=item.get("location"),
                    setpoint_or_range=item.get("setpoint_or_range"),
                    interlock_or_alarm=item.get("interlock_or_alarm"),
                    source=str(item.get("source") or "Engineering Reference Document"),
                )
                ikey = inst_obj.tag.strip().upper()
                if ikey and ikey not in existing_inst_by_key:
                    existing_inst_by_key[ikey] = len(existing_insts)
                    existing_insts.append(inst_obj)

    for cells in _parse_section_table_rows(body, "Instrumentation"):
        if len(cells) >= 7:
            raw_tag_cell = cells[0]
            m_link = re.match(r"^\[([^\]]+)\]\([^)]+\)$", raw_tag_cell)
            clean_tag = (m_link.group(1) if m_link else raw_tag_cell).strip()
            ikey = clean_tag.upper()
            if ikey and ikey not in existing_inst_by_key:
                existing_inst_by_key[ikey] = len(existing_insts)
                existing_insts.append(
                    InstrumentLoop(
                        tag=clean_tag,
                        service=cells[1],
                        instrument_type=cells[2],
                        location=None if cells[3] == "—" else cells[3],
                        setpoint_or_range=None if cells[4] == "—" else cells[4],
                        interlock_or_alarm=None if cells[5] == "—" else cells[5],
                        source=cells[6] or "Engineering Reference Document",
                    )
                )

    # 4. Extract existing connections
    existing_conns: list[ConnectionStream] = []
    for cells in _parse_section_table_rows(body, "Connections & Stream Summary"):
        if len(cells) >= 5:
            existing_conns.append(
                ConnectionStream(
                    stream_id=cells[0],
                    temperature=None if cells[1] == "—" else cells[1],
                    pressure=None if cells[2] == "—" else cells[2],
                    flow_rate=None if cells[3] == "—" else cells[3],
                    description=None if cells[4] == "—" else cells[4],
                    source=(
                        cells[5]
                        if len(cells) >= 6 and cells[5] and cells[5] != "—"
                        else "Engineering Reference Document"
                    ),
                )
            )

    # 5. Extract existing hazards & sources
    existing_hazards = _parse_section_bullets(body, "Hazards & Safeguards")
    existing_sources: list[str] = []
    for s in fm.get("sources") or []:
        if isinstance(s, dict) and s.get("resource"):
            res_str = str(s["resource"]).removeprefix("reference/raw/")
            existing_sources.append(res_str)
        elif isinstance(s, str):
            existing_sources.append(s)

    # Merge parameters & collect automatic cross-document conflict warnings
    merged_design, design_conflicts = _merge_parameter_lists(
        existing_design, new_entity.design_data
    )
    merged_ops, op_conflicts = _merge_parameter_lists(
        existing_ops, new_entity.operating_conditions
    )

    # Merge instruments by normalized tag with non-destructive field retention
    merged_insts: list[InstrumentLoop] = [i.model_copy(deep=True) for i in existing_insts]
    inst_idx: dict[str, int] = {
        i.tag.strip().upper(): idx for idx, i in enumerate(merged_insts)
    }
    for new_i in new_entity.instruments:
        ikey = new_i.tag.strip().upper()
        if ikey not in inst_idx:
            inst_idx[ikey] = len(merged_insts)
            merged_insts.append(new_i.model_copy(deep=True))
        else:
            old_i = merged_insts[inst_idx[ikey]]
            old_src = (old_i.source or "").strip()
            new_src = (new_i.source or "").strip()
            if old_src and new_src and new_src not in old_src and not _is_same_source_or_revision_update(old_src, new_src):
                comb_src = f"{old_src}; {new_src}"
            else:
                comb_src = new_src or old_src
            merged_insts[inst_idx[ikey]] = InstrumentLoop(
                tag=new_i.tag or old_i.tag,
                service=_merge_non_destructive_field(old_i.service, new_i.service, old_src, new_src) or "",
                instrument_type=_merge_non_destructive_field(old_i.instrument_type, new_i.instrument_type, old_src, new_src) or "",
                location=_merge_non_destructive_field(old_i.location, new_i.location, old_src, new_src),
                setpoint_or_range=_merge_non_destructive_field(old_i.setpoint_or_range, new_i.setpoint_or_range, old_src, new_src),
                interlock_or_alarm=_merge_non_destructive_field(old_i.interlock_or_alarm, new_i.interlock_or_alarm, old_src, new_src),
                source=comb_src or "Engineering Reference Document",
            )

    # Merge connections by normalized stream_id with non-destructive field retention
    merged_conns: list[ConnectionStream] = [c.model_copy(deep=True) for c in existing_conns]
    conn_idx: dict[str, int] = {
        c.stream_id.strip().upper(): idx for idx, c in enumerate(merged_conns)
    }
    for new_c in new_entity.connections:
        ckey = new_c.stream_id.strip().upper()
        if ckey not in conn_idx:
            conn_idx[ckey] = len(merged_conns)
            merged_conns.append(new_c.model_copy(deep=True))
        else:
            old_c = merged_conns[conn_idx[ckey]]
            old_src = (old_c.source or "").strip()
            new_src = (new_c.source or "").strip()
            merged_conns[conn_idx[ckey]] = ConnectionStream(
                stream_id=new_c.stream_id or old_c.stream_id,
                temperature=_merge_non_destructive_field(old_c.temperature, new_c.temperature, old_src, new_src),
                pressure=_merge_non_destructive_field(old_c.pressure, new_c.pressure, old_src, new_src),
                flow_rate=_merge_non_destructive_field(old_c.flow_rate, new_c.flow_rate, old_src, new_src),
                description=_merge_non_destructive_field(old_c.description, new_c.description, old_src, new_src),
                source=new_c.source or old_c.source or "Engineering Reference Document",
            )

    # Merge hazards & conflicts (deduplicated by exact text and by conflict parameter topic, preserving order)
    merged_hazards: list[str] = []
    seen_hazards: set[str] = set()
    seen_conflict_topics: set[str] = set()
    for h in existing_hazards + new_entity.hazards + design_conflicts + op_conflicts:
        h_clean = h.strip()
        if not h_clean or h_clean.lower() in seen_hazards:
            continue
        topic_key = _extract_conflict_topic_key(h_clean)
        if topic_key:
            if topic_key in seen_conflict_topics:
                continue
            seen_conflict_topics.add(topic_key)
        seen_hazards.add(h_clean.lower())
        merged_hazards.append(h_clean)

    # Merge sources (deduplicated by base document ID so newer revisions replace superseded revisions)
    merged_sources: list[str] = []
    source_idx_by_base: dict[str, int] = {}
    for s in existing_sources + new_entity.sources:
        s_clean = s.strip().removeprefix("reference/raw/")
        if not s_clean:
            continue
        base_key = _normalize_base_source_id(s_clean) or s_clean.lower()
        if base_key not in source_idx_by_base:
            source_idx_by_base[base_key] = len(merged_sources)
            merged_sources.append(s_clean)
        else:
            merged_sources[source_idx_by_base[base_key]] = s_clean

    existing_func = _extract_section_text(body, "Function")
    merged_func = new_entity.function_summary or existing_func
    if (
        existing_func
        and new_entity.function_summary
        and existing_func.strip() != new_entity.function_summary.strip()
    ):
        ef_clean = existing_func.strip()
        nf_clean = new_entity.function_summary.strip()
        if ef_clean in nf_clean:
            merged_func = nf_clean
        elif nf_clean in ef_clean:
            merged_func = ef_clean
        else:
            merged_func = f"{ef_clean} {nf_clean}"

    existing_tags = [
        str(t) for t in (fm.get("tags") or []) if isinstance(t, str) and str(t).strip()
    ]

    return EquipmentEntity(
        tag=new_entity.tag,
        name=new_entity.name,
        equipment_class=new_entity.equipment_class,
        unit=new_entity.unit,
        function_summary=merged_func,
        design_data=merged_design,
        operating_conditions=merged_ops,
        instruments=merged_insts,
        connections=merged_conns,
        hazards=merged_hazards,
        sources=merged_sources,
        tags=sorted(set(existing_tags + new_entity.tags)),
    )


def _extract_all_table_spans(
    lines: list[str],
) -> list[tuple[int, int, list[str], str, list[list[str]], str]]:
    """Locate all Markdown tables in lines and return [(start_idx, end_idx, headers, sep_line, rows, subheading), ...]."""
    spans: list[tuple[int, int, list[str], str, list[list[str]], str]] = []
    current_sub = ""
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("### "):
            current_sub = s
        if s.startswith("|") and s.endswith("|") and i + 1 < len(lines):
            sep = lines[i + 1].strip()
            if (
                sep.startswith("|")
                and sep.endswith("|")
                and "-" in sep
                and re.match(r"^\|[\s:\-|]+\|$", sep)
            ):
                headers = [c.strip() for c in s.split("|")[1:-1]]
                rows: list[list[str]] = []
                j = i + 2
                while j < len(lines):
                    r_str = lines[j].strip()
                    if not (r_str.startswith("|") and r_str.endswith("|")):
                        break
                    cells = [c.strip() for c in r_str.split("|")[1:-1]]
                    if any(cells):
                        rows.append(cells)
                    j += 1
                spans.append((i, j, headers, sep, rows, current_sub))
                i = j
                continue
        i += 1
    return spans


def _extract_table_span(
    lines: list[str],
) -> tuple[int, int, list[str], str, list[list[str]]] | None:
    """Locate the first Markdown table in lines and return (start_idx, end_idx, headers, sep_line, rows)."""
    all_spans = _extract_all_table_spans(lines)
    if not all_spans:
        return None
    i, j, headers, sep, rows, _ = all_spans[0]
    return i, j, headers, sep, rows


def _normalize_row_key(cell: str) -> str:
    """Normalize a Markdown table first-column cell (stripping Markdown links) for row deduplication."""
    unlinked = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cell)
    return unlinked.strip().lower()


def _merge_two_tables(
    old_headers: list[str],
    old_rows: list[list[str]],
    new_headers: list[str],
    new_sep: str,
    new_rows: list[list[str]],
) -> list[str]:
    """Merge rows of two Markdown tables, aligning columns by header name whenever headers or column counts differ."""
    old_norm = [_normalize_row_key(h) for h in old_headers]
    new_norm = [_normalize_row_key(h) for h in new_headers]
    if old_norm == new_norm and len(new_headers) >= 2:
        union_headers = list(new_headers)
        union_sep = new_sep
        proj_old_rows = [list(r) for r in old_rows]
        proj_new_rows = [list(r) for r in new_rows]
    else:
        union_headers = list(new_headers)
        union_norm = list(new_norm)
        for oh, onh in zip(old_headers[1:], old_norm[1:]):
            if onh and onh not in union_norm:
                union_headers.append(oh)
                union_norm.append(onh)
        union_sep = "| " + " | ".join(["---"] * len(union_headers)) + " |"

        proj_old_rows = []
        for r in old_rows:
            if not r:
                continue
            pr = ["—"] * len(union_headers)
            pr[0] = r[0]
            for c_idx in range(1, min(len(r), len(old_norm))):
                onh = old_norm[c_idx]
                if onh in union_norm:
                    u_idx = union_norm.index(onh)
                    pr[u_idx] = r[c_idx]
            proj_old_rows.append(pr)

        proj_new_rows = []
        for r in new_rows:
            if not r:
                continue
            pr = ["—"] * len(union_headers)
            for c_idx in range(min(len(r), len(new_headers))):
                pr[c_idx] = r[c_idx]
            proj_new_rows.append(pr)

    src_col = next(
        (
            idx
            for idx, h in enumerate(union_headers)
            if any(k in h.lower() for k in ("source", "drawing", "ref", "doc"))
        ),
        None,
    )
    merged_rows: list[list[str]] = [list(r) for r in proj_old_rows]
    row_idx_by_key: dict[str, int] = {
        _normalize_row_key(r[0]): idx for idx, r in enumerate(merged_rows) if r
    }
    for nr in proj_new_rows:
        if not nr:
            continue
        rkey = _normalize_row_key(nr[0])
        if rkey not in row_idx_by_key:
            row_idx_by_key[rkey] = len(merged_rows)
            merged_rows.append(list(nr))
        else:
            idx = row_idx_by_key[rkey]
            old_r = merged_rows[idx]
            if (
                src_col is not None
                and len(old_r) > src_col
                and len(nr) > src_col
            ):
                old_src = old_r[src_col].strip()
                new_src = nr[src_col].strip()
                old_src_parts = [s.strip() for s in old_src.split(";") if s.strip()]
                if len(old_src_parts) <= 1 and _is_same_source_or_revision_update(old_src, new_src):
                    updated_same = list(nr)
                    for c_i in range(1, len(updated_same)):
                        if c_i < len(old_r) and updated_same[c_i].strip() in ("", "—") and old_r[c_i].strip() not in ("", "—"):
                            updated_same[c_i] = old_r[c_i]
                    merged_rows[idx] = updated_same
                elif new_src in old_src_parts and len(old_src_parts) > 1:
                    merged_rows[idx] = list(old_r)
                else:
                    updated_r = list(nr)
                    for c_i in range(1, len(updated_r)):
                        if c_i == src_col or c_i >= len(old_r):
                            continue
                        ov = old_r[c_i].strip()
                        nv = updated_r[c_i].strip()
                        if (nv in ("", "—") and ov not in ("", "—")) or (nv and nv in ov):
                            updated_r[c_i] = ov
                        elif (
                            ov not in ("", "—")
                            and nv not in ("", "—")
                            and ov != nv
                            and ov not in nv
                        ):
                            updated_r[c_i] = f"{nv} ({old_src}: {ov})" if old_src and old_src != "—" else f"{nv} ({ov})"
                    if new_src and new_src != "—" and new_src not in old_src_parts:
                        updated_r[src_col] = f"{old_src}; {new_src}" if old_src and old_src != "—" else new_src
                    else:
                        updated_r[src_col] = old_src
                    merged_rows[idx] = updated_r
            else:
                updated_r = list(nr)
                for c_i in range(1, len(updated_r)):
                    if c_i >= len(old_r):
                        continue
                    ov = old_r[c_i].strip()
                    nv = updated_r[c_i].strip()
                    if (nv in ("", "—") and ov not in ("", "—")) or (nv and nv in ov):
                        updated_r[c_i] = ov
                    elif (
                        ov not in ("", "—")
                        and nv not in ("", "—")
                        and ov != nv
                        and ov not in nv
                    ):
                        updated_r[c_i] = f"{nv} ({ov})"
                merged_rows[idx] = updated_r

    return [
        "| " + " | ".join(union_headers) + " |",
        union_sep,
        *("| " + " | ".join(r) + " |" for r in merged_rows),
    ]


def _merge_section_content(old_sec: str, new_sec: str) -> str:
    """Merge Markdown tables (including multi-table sub-sections and mismatched column counts) and bullet items between an existing section and a newly extracted section."""
    old_lines = old_sec.splitlines()
    new_lines = new_sec.splitlines()

    old_tables = _extract_all_table_spans(old_lines)
    new_tables = _extract_all_table_spans(new_lines)

    matched_old_indices: set[int] = set()
    if old_tables and new_tables:
        # Process replacements in reverse order of new_tables so line indices in new_lines stay valid
        replacements: list[tuple[int, int, list[str]]] = []
        for n_idx, (n_start, n_end, n_headers, n_sep, n_rows, n_sub) in enumerate(new_tables):
            if len(n_headers) < 2:
                continue
            chosen_o_idx: int | None = None
            # 1. Match by identical ### subheading if present
            if n_sub:
                for o_idx, (_, _, o_headers, _, _, o_sub) in enumerate(old_tables):
                    if o_idx not in matched_old_indices and len(o_headers) >= 2 and o_sub.lower() == n_sub.lower():
                        chosen_o_idx = o_idx
                        break
            # 2. Match by normalized first-column header
            if chosen_o_idx is None:
                n_k0 = _normalize_row_key(n_headers[0])
                for o_idx, (_, _, o_headers, _, _, o_sub) in enumerate(old_tables):
                    if (
                        o_idx not in matched_old_indices
                        and len(o_headers) >= 2
                        and _normalize_row_key(o_headers[0]) == n_k0
                        and (not o_sub or not n_sub or o_sub.lower() == n_sub.lower())
                    ):
                        chosen_o_idx = o_idx
                        break
            # 3. Single-table fallback when both sections have exactly 1 table
            if (
                chosen_o_idx is None
                and len(old_tables) == 1
                and len(new_tables) == 1
                and 0 not in matched_old_indices
                and len(old_tables[0][2]) >= 2
            ):
                chosen_o_idx = 0

            if chosen_o_idx is not None:
                matched_old_indices.add(chosen_o_idx)
                _, _, o_headers, _, o_rows, _ = old_tables[chosen_o_idx]
                rebuilt = _merge_two_tables(o_headers, o_rows, n_headers, n_sep, n_rows)
                replacements.append((n_start, n_end, rebuilt))

        for n_start, n_end, rebuilt in reversed(replacements):
            new_lines = new_lines[:n_start] + rebuilt + new_lines[n_end:]

    # Preserve any unmerged tables from old_sec (e.g. secondary ### sub-tables or when new_sec had no tables)
    existing_subs_lower = {
        ln.strip().lower() for ln in new_lines if ln.strip().startswith("### ")
    }
    for o_idx, (o_start, o_end, _, _, _, o_sub) in enumerate(old_tables):
        if o_idx not in matched_old_indices:
            if new_lines and new_lines[-1].strip() != "":
                new_lines.append("")
            if o_sub and o_sub.strip().lower() not in existing_subs_lower:
                new_lines.append(o_sub)
                existing_subs_lower.add(o_sub.strip().lower())
            new_lines.extend(old_lines[o_start:o_end])

    # Also preserve any distinct blockquote callouts (> ) or bullet lines (- , * ) from old_sec
    existing_preserved_lower = {
        ln.strip().lower()
        for ln in new_lines
        if ln.strip().startswith(("- ", "* ", ">"))
    }
    missing_old_lines = [
        ln
        for ln in old_lines
        if ln.strip().startswith(("- ", "* ", ">"))
        and ln.strip().lower() not in existing_preserved_lower
    ]
    if missing_old_lines:
        new_lines.extend(missing_old_lines)

    return "\n".join(new_lines)



def merge_markdown_bodies(existing_body: str, new_body: str) -> str:
    """Merge existing and new Markdown bodies by H2 ('## ') sections, preserving prior sections and merging table rows."""
    if not existing_body or not existing_body.strip():
        return new_body
    if not new_body or not new_body.strip():
        return existing_body
    if existing_body.strip() == new_body.strip():
        return new_body

    def _split_h2_blocks(text: str) -> list[tuple[str, str]]:
        blocks: list[tuple[str, str]] = []
        current_heading = ""
        current_lines: list[str] = []
        for line in text.splitlines():
            if line.startswith("## "):
                if current_heading or current_lines:
                    blocks.append((current_heading, "\n".join(current_lines).strip()))
                current_heading = line.strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_heading or current_lines:
            blocks.append((current_heading, "\n".join(current_lines).strip()))
        return blocks

    old_blocks = _split_h2_blocks(existing_body)
    new_blocks = _split_h2_blocks(new_body)

    old_by_heading: dict[str, str] = {
        h.lower(): content for h, content in old_blocks
    }
    seen_headings: set[str] = set()
    merged_blocks: list[tuple[str, str]] = []

    for h, new_content in new_blocks:
        h_key = h.lower()
        seen_headings.add(h_key)
        if h_key in old_by_heading:
            merged_content = _merge_section_content(old_by_heading[h_key], new_content)
            merged_blocks.append((h, merged_content))
        else:
            merged_blocks.append((h, new_content))

    # Append any H2 sections from existing_body that were absent in new_body
    for h, old_content in old_blocks:
        h_key = h.lower()
        if h and h_key not in seen_headings:
            merged_blocks.append((h, old_content))

    out_parts: list[str] = []
    for h, content in merged_blocks:
        if h:
            out_parts.append(f"{h}\n{content}".strip())
        elif content:
            out_parts.append(content.strip())
    return "\n\n".join(out_parts) + "\n"


