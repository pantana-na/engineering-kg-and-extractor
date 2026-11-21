"""OKF v0.2 Knowledge Synthesis Engine.

Transforms extracted domain entities into fully conformant OKF v0.2 concept documents.
"""

from __future__ import annotations

import os
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
    MOCChangeRecord,
    _extract_equipment_base_id,
    derive_canonical_equipment_tag,
    is_nozzle_mark_only,
    sanitize_tag_filename,
)
from extracter_agent.okf.document import OKFDocument


def _slugify(text: str) -> str:
    """Normalize a string to a safe identifier slug."""
    s = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", s).strip("-")


_INST_REGISTER_CACHE: dict[
    tuple[str, int, int, int],
    list[tuple[Path, str, set[str], set[str], set[str]]],
] = {}

_GENERIC_REGISTER_STOPWORDS: set[str] = {
    "cdn",
    "unit",
    "control",
    "instrument",
    "instruments",
    "instrumentation",
    "system",
    "systems",
    "process",
    "section",
    "high",
    "low",
    "alarm",
    "normal",
    "general",
    "local",
    "loop",
    "loops",
    "data",
    "sheet",
    "sheets",
    "register",
    "specification",
    "specifications",
    "summary",
    "table",
    "overview",
    "plant",
    "equipment",
    "monitoring",
    "service",
    "services",
}


def _strip_unit_infix(tag_str: str) -> str:
    """Strip a 2-to-4 digit unit number infix from an ISA tag (e.g., 'uxv-23-1204' -> 'uxv-1204')."""
    return re.sub(r"^([a-z]{1,6})-\d{2,4}-(\d{2,5}[a-z0-9]*)$", r"\1-\2", tag_str)


def _extract_register_primary_keys(raw_text: str) -> set[str]:
    """Extract normalized primary-key instrument tags from Markdown table first columns and level-3 headings."""
    pkeys: set[str] = set()
    isa_tok_re = re.compile(r"\b(?:\d+-)?[a-z]{1,6}-(?:\d{2,4}-)?\d{2,5}[a-z0-9]*\b")

    def _add_tag_variants(tok: str) -> None:
        t = tok.strip().lower()
        if not t:
            return
        pkeys.add(t)
        no_lead = re.sub(r"^\d+-", "", t)
        pkeys.add(no_lead)
        pkeys.add(_strip_unit_infix(no_lead))
        base_loop = re.sub(r"[a-z]+$", "", no_lead)
        if base_loop and len(base_loop) >= 4:
            pkeys.add(base_loop)
            pkeys.add(_strip_unit_infix(base_loop))

    for line in raw_text.splitlines():
        s = line.strip()
        if s.startswith("### "):
            heading_txt = re.sub(r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", s[4:]).strip().lower()
            for tok in isa_tok_re.findall(heading_txt):
                _add_tag_variants(tok)
        elif s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.split("|")[1:-1]]
            if not cells:
                continue
            c0 = re.sub(r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", cells[0]).strip().lower()
            c0 = c0.replace("**", "").replace("`", "").strip()
            if not c0 or c0 in ("tag", "loop", "instrument", "instrument tag", "tag number", "item", "---", ":---"):
                continue
            if re.match(r"^[:\-]+$", c0):
                continue
            base_c0 = c0.split("(")[0].strip()
            if base_c0:
                _add_tag_variants(base_c0)
            for part in re.split(r"[/,;]+", base_c0):
                part_cl = part.strip()
                if part_cl:
                    _add_tag_variants(part_cl)
            for tok in isa_tok_re.findall(c0):
                _add_tag_variants(tok)
    return pkeys


def resolve_bundle_instrument_link(
    inst_tag: str,
    instrument_type: str = "",
    service: str = "",
    bundle_root: Path | None = None,
) -> str | None:
    """Dynamically resolve an instrument loop tag to an existing file in bundle_root/instruments/.

    Prioritizes:
    1. Direct single-instrument concept file match (`<tag>.md`).
    2. Primary-key match in register Markdown tables (first column) and H3 headings.
    3. Specific numbered tag match in register prose (only when the register is domain/prefix compatible).
    4. Empirical ISA prefix frequency across register primary keys + domain token overlap.
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
                raw_text = ""
                content_lower = ""
                fm_meta_str = ""
            stem_tokens = set(re.findall(r"[a-z]{2,}", reg.stem.lower())) - _GENERIC_REGISTER_STOPWORDS
            reg_tokens = (
                set(re.findall(r"[a-z]{2,}", f"{reg.stem} {fm_meta_str}".lower()))
                - _GENERIC_REGISTER_STOPWORDS
            )
            primary_keys = _extract_register_primary_keys(raw_text)
            cached_regs.append((reg, content_lower, reg_tokens, stem_tokens, primary_keys))
        _INST_REGISTER_CACHE[cache_key] = cached_regs

    clean_probe = inst_tag.split("/")[0].split("(")[0].strip().lower()
    stripped_probe = re.sub(r"^\d+-", "", clean_probe)
    no_infix_probe = _strip_unit_infix(stripped_probe)
    range_head_probe = re.split(r"\.\.|~|to", no_infix_probe)[0].strip()

    # Also extract any embedded ISA tag inside parentheses (e.g. 'BL (LT-23-1301)' -> 'lt-23-1301', 'lt-1301')
    embedded_isa_probes: list[str] = []
    for m_emb in re.finditer(r"\b(?:\d+-)?([a-z]{1,6}-(?:\d{2,4}-)?\d{2,5}[a-z0-9]*)\b", inst_tag.lower()):
        emb = m_emb.group(1)
        embedded_isa_probes.append(emb)
        embedded_isa_probes.append(_strip_unit_infix(emb))

    # Only allow fuzzy category fallback onto multi-instrument register files
    single_tag_stem_re = re.compile(r"^(?:\d+-)?(?:[a-z]{1,4}-)?[a-z]{1,6}-\d+[a-z0-9]*$")
    register_candidates = [
        item for item in cached_regs if not single_tag_stem_re.match(item[0].stem.lower())
    ]

    # Strip explicit nozzle mark labels (e.g. 'Nozzle AX (TI)' -> '(TI)') before extracting ISA alpha codes
    tag_for_alpha = re.sub(r"\bnozzle\s+[a-z0-9]{1,4}\b", "", inst_tag.lower()).strip()
    raw_alpha_codes = [
        m.group(1).lower()
        for m in re.finditer(r"\b(?:\d+-)?([a-z]{1,5})(?:[-_\s]+\d|\b)", tag_for_alpha)
        if m.group(1).lower() not in ("high", "low", "ll", "hh", "min", "max", "and", "or", "to", "in", "on", "nozzle", "tap", "taps", "off", "rev", "relief")
    ]
    p_code = raw_alpha_codes[0] if raw_alpha_codes else ""
    if not p_code:
        prefix_match = re.match(r"^(?:\d+-)?([a-z]{1,5})", clean_probe)
        p_code = prefix_match.group(1) if prefix_match else ""
    active_codes = list(dict.fromkeys(raw_alpha_codes or ([p_code] if p_code else [])))

    # Map common ISA instrument letters/codes to semantic engineering domain keywords
    isa_domain_hints: list[str] = []
    probe_and_meta = f"{tag_for_alpha} {instrument_type} {service}".lower()
    for code_tok in active_codes:
        if code_tok in ("bs", "ls", "lsh", "lsl", "lshh", "lsll", "lxshh", "lxsll", "lt", "lxt", "li", "lic", "lg", "lgr", "lcv"):
            isa_domain_hints.extend(["level", "bridle", "float"])
        elif code_tok in ("ro", "fo", "fe", "ft", "fxt", "fi", "fic", "fcv", "fsh", "fsl", "fxsl", "fxsll", "fm"):
            isa_domain_hints.extend(["flow", "orifice", "rotameter", "coriolis"])
        elif code_tok in ("psv", "pzv", "tsv", "pse", "pvrv", "bdv"):
            isa_domain_hints.extend(["relief", "safety", "pressure", "vacuum", "valves"])
        elif code_tok in ("pi", "pt", "pxt", "pic", "pdi", "pdt", "pdic", "pg", "ps", "psh", "psl", "pcv"):
            isa_domain_hints.extend(["pressure", "differential"])
        elif code_tok in ("ti", "tt", "txt", "tic", "te", "tw", "tsh", "tsl", "tshh", "tsll", "txshh", "txsll", "tdt", "tdxt", "tcv", "rtd", "tah", "tal"):
            isa_domain_hints.extend(["temperature", "thermocouple", "thermowell", "rtd"])
        elif code_tok in ("ai", "at", "ay", "aic", "ae", "as", "gc", "ph", "orp"):
            isa_domain_hints.extend(["analyzers", "analyzer", "analytical"])
        elif code_tok in ("sn", "sc", "ss", "sp"):
            isa_domain_hints.extend(["sampling", "sample", "stations"])
        elif code_tok in ("vi", "vt", "ve", "vxt", "vsh", "vshh", "vs"):
            isa_domain_hints.extend(["vibration", "monitoring"])
        elif code_tok in ("xv", "uxv", "uv", "uz", "uy", "uxy", "uc", "hv", "fv", "lv", "pv", "tv", "mov", "sov"):
            isa_domain_hints.extend(["valves", "valve", "interlocks", "esd", "sis"])
        elif code_tok in ("hs", "hss", "mcc"):
            isa_domain_hints.extend(["pump", "motor", "schematics"])

    meta_only_terms: set[str] = (
        set(re.findall(r"[a-z]{2,}", f"{instrument_type} {service}".lower()))
        - _GENERIC_REGISTER_STOPWORDS
    )
    inferred_terms: set[str] = (
        set(re.findall(r"[a-z]{2,}", f"{probe_and_meta} {' '.join(isa_domain_hints)}"))
        - _GENERIC_REGISTER_STOPWORDS
    )

    def _score_register_candidate(
        reg: Path,
        content_lower: str,
        reg_tokens: set[str],
        stem_tokens: set[str],
        primary_keys: set[str],
    ) -> float:
        stem_overlap = len(inferred_terms & stem_tokens)
        unmatched_stem_tokens = len(stem_tokens - inferred_terms)
        meta_overlap = len(inferred_terms & reg_tokens)
        pkey_exact_prefix = (
            max(
                (
                    sum(
                        1
                        for pk in primary_keys
                        if re.match(rf"^(?:\d+-)?{re.escape(c_tok)}[-_0-9]", pk)
                    )
                    for c_tok in active_codes
                ),
                default=0,
            )
            if active_codes
            else 0
        )
        pkey_family_prefix = (
            max(
                (
                    sum(
                        1
                        for pk in primary_keys
                        if re.match(rf"^(?:\d+-)?{re.escape(c_tok[:1])}[a-z]{{0,4}}[-_0-9]", pk)
                    )
                    for c_tok in active_codes
                ),
                default=0,
            )
            if active_codes
            else 0
        )
        prose_prefix_hits = (
            max(
                (
                    len(re.findall(rf"\b(?:\d+-)?{re.escape(c_tok)}[-_0-9]", content_lower))
                    for c_tok in active_codes
                ),
                default=0,
            )
            if active_codes
            else 0
        )
        return (
            (stem_overlap * 15.0)
            - (unmatched_stem_tokens * 2.0)
            + (meta_overlap * 4.0)
            + (pkey_exact_prefix * 8.0)
            + (pkey_family_prefix * 1.5)
            + min(10.0, prose_prefix_hits * 0.5)
        )

    # When caller supplies a numbered tag with zero informative service/type terms (e.g. generic placeholder),
    # only link to a specific register file if the tag literally appears in that register; otherwise fall back to index.md
    if not meta_only_terms and clean_probe and re.search(r"\d{2,}", clean_probe):
        literal_pat = re.compile(rf"(?<![a-z0-9]){re.escape(clean_probe)}(?![a-z0-9])")
        lit_matches: list[tuple[float, Path]] = []
        for reg, content_lower, reg_tokens, stem_tokens, primary_keys in cached_regs:
            if literal_pat.search(content_lower):
                lit_matches.append(
                    (
                        _score_register_candidate(
                            reg, content_lower, reg_tokens, stem_tokens, primary_keys
                        ),
                        reg,
                    )
                )
        if lit_matches:
            lit_matches.sort(key=lambda item: item[0], reverse=True)
            return f"/instruments/{lit_matches[0][1].name}"
        if (inst_dir / "index.md").exists():
            return "/instruments/index.md"
        return f"/instruments/{reg_files[0].name}"

    # Tier 1: Exact Primary-Key match in register tables / H3 headings
    pkey_matches: list[tuple[float, Path]] = []
    all_pkey_probes = [
        p for p in (clean_probe, stripped_probe, no_infix_probe, range_head_probe, *embedded_isa_probes)
        if p and len(p) >= 3
    ]
    for reg, content_lower, reg_tokens, stem_tokens, primary_keys in cached_regs:
        for probe_cand in all_pkey_probes:
            if probe_cand in primary_keys:
                pkey_matches.append(
                    (
                        _score_register_candidate(
                            reg, content_lower, reg_tokens, stem_tokens, primary_keys
                        ),
                        reg,
                    )
                )
                break
    if pkey_matches:
        pkey_matches.sort(key=lambda item: item[0], reverse=True)
        return f"/instruments/{pkey_matches[0][1].name}"

    # Tier 2: Specific numbered tag occurrence in register prose (only when register is domain/prefix compatible)
    if clean_probe and len(clean_probe) >= 4 and re.search(r"\d{2,}", clean_probe):
        prose_matches: list[tuple[float, Path]] = []
        probe_variants = list(dict.fromkeys([clean_probe, stripped_probe, no_infix_probe]))
        probe_pats = [
            re.compile(rf"(?<![a-z0-9]){re.escape(pv)}(?![a-z0-9])")
            for pv in probe_variants
            if pv and len(pv) >= 4
        ]
        for reg, content_lower, reg_tokens, stem_tokens, primary_keys in cached_regs:
            if any(pat.search(content_lower) for pat in probe_pats):
                is_single_reg = single_tag_stem_re.match(reg.stem.lower()) is not None
                stem_overlap = len(inferred_terms & stem_tokens)
                pkey_exact_prefix = (
                    max(
                        (
                            sum(
                                1
                                for pk in primary_keys
                                if re.match(rf"^(?:\d+-)?{re.escape(c_tok)}[-_0-9]", pk)
                            )
                            for c_tok in active_codes
                        ),
                        default=0,
                    )
                    if active_codes
                    else 0
                )
                if is_single_reg or stem_overlap > 0 or pkey_exact_prefix > 0:
                    prose_matches.append(
                        (
                            _score_register_candidate(
                                reg, content_lower, reg_tokens, stem_tokens, primary_keys
                            ),
                            reg,
                        )
                    )
        if prose_matches:
            prose_matches.sort(key=lambda item: item[0], reverse=True)
            return f"/instruments/{prose_matches[0][1].name}"

    # Tier 3: Multi-instrument register scoring by primary-key prefix distribution + domain overlap
    if register_candidates:
        best_reg: Path | None = None
        best_score = 0.0
        for reg, content_lower, reg_tokens, stem_tokens, primary_keys in register_candidates:
            score = _score_register_candidate(
                reg, content_lower, reg_tokens, stem_tokens, primary_keys
            )
            if score > best_score:
                best_score = score
                best_reg = reg

        if best_reg is not None and best_score > 0.0:
            return f"/instruments/{best_reg.name}"
        if (inst_dir / "index.md").exists():
            return "/instruments/index.md"
        return f"/instruments/{register_candidates[0][0].name}"

    if (inst_dir / "index.md").exists():
        return "/instruments/index.md"
    return f"/instruments/{cached_regs[0][0].name}"


_EQUIP_SLUG_RESOLVE_CACHE: dict[tuple[str, int, int, int], dict[str, str | None]] = {}
_EQUIP_DIR_INDEX_CACHE: dict[tuple[str, int, int, int], tuple[dict[str, str], dict[str, str]]] = {}


def _resolve_bundle_equipment_slug(raw_tag: str, bundle_root: Path | None) -> str | None:
    """Resolve an equipment tag token against bundle_root/equipment/*.md using exact stem, alias, or base-ID matching."""
    if bundle_root is None:
        return None
    equip_dir = bundle_root / "equipment"
    if not equip_dir.is_dir():
        return None
    clean = sanitize_tag_filename(raw_tag).upper()
    if not clean:
        return None

    direct = equip_dir / f"{clean}.md"
    if direct.exists():
        return direct.stem

    stems: list[str] = []
    max_child_ns = 0
    with os.scandir(equip_dir) as it:
        for de in it:
            if not de.name.endswith(".md") or de.name in ("index.md", "log.md") or not de.is_file():
                continue
            st_ns = de.stat().st_mtime_ns
            if st_ns > max_child_ns:
                max_child_ns = st_ns
            stems.append(de.name[:-3])

    dir_key = (os.path.abspath(equip_dir), equip_dir.stat().st_mtime_ns, len(stems), max_child_ns)
    memo = _EQUIP_SLUG_RESOLVE_CACHE.setdefault(dir_key, {})
    probe_token = raw_tag.strip()
    if probe_token in memo:
        return memo[probe_token]

    idx_pair = _EQUIP_DIR_INDEX_CACHE.get(dir_key)
    if idx_pair is None:
        by_upper: dict[str, str] = {}
        by_base: dict[str, str] = {}
        for stem in sorted(stems):
            st_up = stem.upper()
            by_upper[st_up] = stem
            b_id = _extract_equipment_base_id(st_up)
            if b_id:
                prev = by_base.get(b_id)
                if prev is None or len(stem) > len(prev):
                    by_base[b_id] = stem
        idx_pair = (by_upper, by_base)
        _EQUIP_DIR_INDEX_CACHE[dir_key] = idx_pair

    by_upper, by_base = idx_pair
    if clean in by_upper:
        memo[probe_token] = by_upper[clean]
        return by_upper[clean]
    base_id = _extract_equipment_base_id(clean)
    if base_id and base_id in by_base:
        memo[probe_token] = by_base[base_id]
        return by_base[base_id]

    alias_cand = derive_canonical_equipment_tag(raw_tag, bundle_root=bundle_root)
    if alias_cand.upper() in by_upper:
        resolved_stem = by_upper[alias_cand.upper()]
        memo[probe_token] = resolved_stem
        return resolved_stem
    alias_file = equip_dir / f"{alias_cand}.md"
    if alias_file.exists():
        memo[probe_token] = alias_file.stem
        return alias_file.stem
    memo[probe_token] = None
    return None


def format_equipment_endpoint_cell(
    raw_endpoint: str | None,
    bundle_root: Path | None,
) -> str:
    """Format an equipment endpoint cell with clickable Markdown links to canonical /equipment/<Slug>.md files."""
    if not raw_endpoint or raw_endpoint.strip() in ("", "—"):
        return "—"
    unlinked = re.sub(r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", raw_endpoint.strip())
    if bundle_root is None or not (bundle_root / "equipment").exists():
        return unlinked

    def _replace_tag(m: re.Match[str]) -> str:
        tok = m.group(0)
        slug = _resolve_bundle_equipment_slug(tok, bundle_root)
        if slug:
            return f"[{tok}](/equipment/{slug}.md)"
        return tok

    return re.sub(
        r"\b(?:[A-Z]{1,4}-\d{3,5}[A-Z0-9]*(?:/[A-Z0-9]+)*)\b",
        _replace_tag,
        unlinked,
    )


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

    clean_func_summary = deduplicate_engineering_prose(entity.function_summary)
    short_description = (
        deduplicate_engineering_prose(clean_func_summary, max_sentences=2)
        or f"{entity.name} in {entity.unit} unit."
    )

    frontmatter: dict[str, Any] = {
        "type": "Equipment Concept",
        "title": f"{entity.tag} — {entity.name}",
        "description": short_description,
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

    if entity.aliases:
        frontmatter["entity_metadata"]["aliases"] = list(dict.fromkeys(entity.aliases))
    if entity.superseded_sources:
        frontmatter["entity_metadata"]["superseded_sources"] = list(
            dict.fromkeys(entity.superseded_sources)
        )
    if entity.removed_instruments:
        frontmatter["entity_metadata"]["removed_instruments"] = list(
            dict.fromkeys(entity.removed_instruments)
        )
    if entity.removed_connections:
        frontmatter["entity_metadata"]["removed_connections"] = list(
            dict.fromkeys(entity.removed_connections)
        )
    if entity.moc_history:
        frontmatter["entity_metadata"]["moc_history"] = [
            m.model_dump() if isinstance(m, MOCChangeRecord) else dict(m)
            for m in entity.moc_history
        ]

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

    if entity.connections:
        frontmatter["entity_metadata"]["connections"] = [
            {
                "stream_id": conn.stream_id,
                "direction": conn.direction,
                "source_tag": re.sub(
                    r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", conn.source_tag or ""
                )
                or None,
                "target_tag": re.sub(
                    r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", conn.target_tag or ""
                )
                or None,
                "line_size": conn.line_size,
                "inline_components": list(conn.inline_components or []),
                "temperature": conn.temperature,
                "pressure": conn.pressure,
                "flow_rate": conn.flow_rate,
                "description": conn.description,
                "source": conn.source,
            }
            for conn in entity.connections
        ]

    body_lines: list[str] = [
        f"# {entity.tag} — {entity.name}",
        "",
        "## Function",
        "",
        clean_func_summary,
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
                "| Stream | Direction | From (Source) | To (Target) | Line Size | Inline Valves / Components | Temp | Pressure | Flow Rate | Description |",
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            ]
        )
        for conn in entity.connections:
            direction_val = conn.direction or "—"
            src_val = format_equipment_endpoint_cell(conn.source_tag, bundle_root)
            tgt_val = format_equipment_endpoint_cell(conn.target_tag, bundle_root)
            lsize_val = conn.line_size or "—"
            inline_val = (
                ", ".join(conn.inline_components) if conn.inline_components else "—"
            )
            t = conn.temperature or "—"
            p = conn.pressure or "—"
            f = conn.flow_rate or "—"
            d = conn.description or "—"
            body_lines.append(
                f"| {conn.stream_id} | {direction_val} | {src_val} | {tgt_val} | {lsize_val} | {inline_val} | {t} | {p} | {f} | {d} |"
            )
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

    # Management of Change (MOC) & Revision History
    if (
        entity.moc_history
        or entity.superseded_sources
        or entity.removed_instruments
        or entity.removed_connections
    ):
        body_lines.extend(
            [
                "## Management of Change (MOC) & Revision History",
                "",
            ]
        )
        if entity.moc_history:
            body_lines.extend(
                [
                    "| MOC / Change ID | Date | Change Type | Summary | Affected Items | Pending Redraft Drawings |",
                    "| :--- | :--- | :--- | :--- | :--- | :--- |",
                ]
            )
            for m in entity.moc_history:
                m_obj = m if isinstance(m, MOCChangeRecord) else MOCChangeRecord(**dict(m))
                aff = ", ".join(m_obj.affected_items) if m_obj.affected_items else "—"
                pend = (
                    ", ".join(m_obj.pending_redraft_drawings)
                    if m_obj.pending_redraft_drawings
                    else "—"
                )
                body_lines.append(
                    f"| {m_obj.moc_id} | {m_obj.date or '—'} | {m_obj.change_type} | {m_obj.summary} | {aff} | {pend} |"
                )
            body_lines.append("")
        if entity.superseded_sources:
            body_lines.append(
                f"- **Superseded Documents Retired:** {', '.join(entity.superseded_sources)}"
            )
        if entity.removed_instruments:
            body_lines.append(
                f"- **Decommissioned / Removed Instruments:** {', '.join(entity.removed_instruments)}"
            )
        if entity.removed_connections:
            body_lines.append(
                f"- **Decommissioned / Removed Process Streams:** {', '.join(entity.removed_connections)}"
            )
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
    s = re.sub(
        r"[_-](?:z\d{1,2}[a-z0-9]*|r\d{1,2}[a-z0-9]*|rev[0-9a-z]+|as[-_]*built|ifc|draft)$",
        "",
        s,
    )
    s = re.sub(r"_(?:[a-oq-y]\d{1,2}[a-z0-9]*)$", "", s)
    if "_" in s and "-" in s.split("_")[0]:
        s = s.split("_")[0]
    m_code = re.search(
        r"\b((?:ps|dwg|pfd|pid|om|sds|sg|std)-[a-z0-9-]+)\b",
        s,
    )
    base = m_code.group(1) if m_code else s
    base = re.sub(
        r"(?:[-_\s]+(?:rev(?:ision)?\.?\s*[a-z0-9]+|z\d{1,2}[a-z0-9]*|r\d{1,2}[a-z0-9]*|as[-_\s]*built|ifc|draft))+$",
        "",
        base,
    )
    return re.sub(r"[^a-z0-9]+", "", base)


def extract_revision_token(src: str) -> str:
    """Extract canonical revision token (e.g. 'AS-BUILT', 'IFC', 'Z1', 'R2', 'A1', 'DRAFT') from a source citation."""
    if not src:
        return ""
    s = src.strip()
    s_up = re.sub(r"_+", " ", s.upper())
    if re.search(r"\bAS[-\s]*BUILT\b", s_up):
        return "AS-BUILT"
    if re.search(r"\b(?:IFC|ISSUED\s+FOR\s+CONSTRUCTION)\b", s_up):
        return "IFC"
    if re.search(r"\b(?:DRAFT|PRELIMINARY|IFR|IFA)\b", s_up):
        return "DRAFT"

    # Match explicit 'Rev Z1', 'Rev. 2', '(Rev A)', 'Rev A2', 'Revision 03'
    m_rev = re.search(
        r"\bREV(?:ISION)?\.?\s*([A-Z]?\d+[A-Z0-9]*|[A-Z])\b",
        s_up,
    )
    if m_rev:
        tok = m_rev.group(1).strip()
        if re.match(r"^\d+$", tok):
            return f"R{int(tok)}"
        return tok

    # Match filename suffix patterns at the end of the stem like '_Z0', '_Z1', '-R2', '_A1'
    stem = s.split("/")[-1].removesuffix(".pdf").removesuffix(".PDF")
    m_suf = re.search(
        r"(?:[_.\-\s(\[])(Z\d{1,2}[A-Z0-9]*|R\d{1,2}[A-Z0-9]*|[A-OQ-Y]\d{1,2}[A-Z0-9]*)[)\]]*$",
        stem.upper(),
    )
    if m_suf:
        return m_suf.group(1).strip()

    return ""


def _parse_revision_rank(rev_tok: str) -> tuple[int, int, str]:
    """Map a canonical revision token to a comparable rank tuple (tier, numeric_ver, sub_suffix).

    Tiers:
      5: AS-BUILT (5, 1) / IFC (5, 0)
      4: Z-series (Z0, Z1, Z2, ...)
      3: Numeric R-series (R0, R1, R2, ...)
      2: Alphabetic / Alphanumeric Preliminary (A, A1, A2, B, B1, ... Y)
      1: DRAFT / PRELIMINARY
      0: Unspecified
    """
    tok = (rev_tok or "").strip().upper()
    if not tok:
        return (0, 0, "")
    if tok == "AS-BUILT":
        return (5, 1, "")
    if tok == "IFC":
        return (5, 0, "")
    if tok in ("DRAFT", "PRELIMINARY", "IFR", "IFA"):
        return (1, 0, "")
    m_z = re.match(r"^Z(\d+)([A-Z0-9]*)$", tok)
    if m_z:
        return (4, int(m_z.group(1)), m_z.group(2))
    m_r = re.match(r"^R(\d+)([A-Z0-9]*)$", tok)
    if m_r:
        return (3, int(m_r.group(1)), m_r.group(2))
    if re.match(r"^\d+$", tok):
        return (3, int(tok), "")
    m_alpha = re.match(r"^([A-OQ-Y])(\d+)?([A-Z0-9]*)$", tok)
    if m_alpha:
        letter_ord = ord(m_alpha.group(1)) - ord("A")
        sub_num = int(m_alpha.group(2)) if m_alpha.group(2) is not None else 0
        return (2, letter_ord * 100 + sub_num, m_alpha.group(3))
    return (0, 0, tok)


def compare_revision_tokens(old_src: str, new_src: str) -> int:
    """Compare revision rank of old_src and new_src.

    Returns:
      +1 if new_src is strictly newer than old_src,
      -1 if new_src is strictly older than old_src,
       0 if equal or if revision order is indeterminate.
    """
    old_tok = extract_revision_token(old_src)
    new_tok = extract_revision_token(new_src)
    if not old_tok or not new_tok:
        return 0
    old_rank = _parse_revision_rank(old_tok)
    new_rank = _parse_revision_rank(new_tok)
    if new_rank > old_rank:
        return 1
    if new_rank < old_rank:
        return -1
    return 0


def _is_strictly_older_same_doc_revision(old_src: str, new_src: str) -> bool:
    """Return True if new_src is a strictly older revision of the same document than old_src.

    Guards against false out-of-order rejection when synthetic or converted citations
    switch between different middle revision numbering schemes (e.g. Z0 -> Rev 1 or -R1 -> Rev B).
    """
    if compare_revision_tokens(old_src, new_src) >= 0:
        return False
    old_tok = extract_revision_token(old_src)
    new_tok = extract_revision_token(new_src)
    old_rank = _parse_revision_rank(old_tok)
    new_rank = _parse_revision_rank(new_tok)
    if old_rank[0] == new_rank[0]:
        return True
    if new_rank[0] == 1 or old_rank[0] == 5:
        return True
    if new_tok.startswith("A") and old_rank[0] in (3, 4):
        return True
    return False


def is_moc_source(src: str, explicit_moc_sources: set[str] | None = None) -> bool:
    """Return True if src is an authoritative Management of Change (MOC / ECN / FCR) document.

    Strictly enforces Boundary Guard #1: only matches explicit moc/ paths, MOC-/ECN-/FCR-
    identifiers, or sources listed in explicit_moc_sources (never standard P&IDs, PFDs, or datasheets).
    """
    if not src:
        return False
    s_clean = src.strip()
    s_low = s_clean.lower()
    if explicit_moc_sources:
        norm_explicit = {x.strip().lower() for x in explicit_moc_sources if x.strip()}
        norm_explicit_base = {
            _normalize_base_source_id(x) for x in explicit_moc_sources if x.strip()
        } - {""}
        for part in [s_low, *[p.strip().lower() for p in s_low.split(";") if p.strip()]]:
            if part in norm_explicit or part.removeprefix("reference/raw/") in norm_explicit:
                return True
            part_base = _normalize_base_source_id(part)
            if part_base and part_base in norm_explicit_base:
                return True

    if re.search(r"(?:^|/|\\)moc(?:/|\\)", s_low):
        return True
    if re.search(
        r"\b(?:moc|ecn|fcr|pcr|dcn)[-_#\s]*(?:\d{2,}|[a-z0-9]{2,}[-_]\d+)",
        s_low,
    ):
        return True
    if re.search(
        r"\b(?:management\s+of\s+change|engineering\s+change\s+notice|field\s+change\s+request)\b",
        s_low,
    ):
        return True
    return False


_PROSE_STOPWORDS: set[str] = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "that",
    "this",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "its",
    "via",
    "which",
    "where",
    "while",
    "during",
    "under",
    "between",
    "through",
    "within",
    "serves",
    "used",
    "designed",
    "provides",
    "operates",
}


def deduplicate_engineering_prose(
    text: str,
    max_sentences: int | None = None,
) -> str:
    """Eliminate exact and near-duplicate sentences in multi-turn engineering prose while preserving 100% of unique tags and numerical facts."""
    if not text or not text.strip():
        return ""
    cleaned = re.sub(r"\s+", " ", text.strip())
    # Protect common engineering abbreviations before sentence splitting
    protected = re.sub(
        r"\b(e\.g|i\.e|wt|vol|deg|ca|approx|fig|no|rev|sh|min|max|abs|atm|vs|st|dr|mr|eq)\.",
        r"\1<DOT>",
        cleaned,
        flags=re.IGNORECASE,
    )
    raw_sentences = [
        s.replace("<DOT>", ".").strip()
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\[⚠️🔄])", protected)
        if s.strip()
    ]
    if not raw_sentences:
        return cleaned

    kept: list[tuple[str, str, set[str], set[str]]] = []
    # Each entry: (sentence_text, norm_str, content_words, eng_facts)
    for sent in raw_sentences:
        norm_s = re.sub(r"[^a-z0-9]+", " ", sent.lower()).strip()
        if not norm_s:
            continue
        words = {
            w
            for w in re.findall(r"[a-z0-9]{2,}", sent.lower())
            if w not in _PROSE_STOPWORDS
        }
        eng_facts = set(
            re.findall(
                r"\b(?:(?:\d+-)?[a-z]{1,4}-\d{3,5}[a-z0-9]*|\d+(?:\.\d+)?%?)\b",
                sent.lower(),
            )
        )

        is_dup = False
        for idx, (k_sent, k_norm, k_words, k_facts) in enumerate(kept):
            if norm_s == k_norm or norm_s in k_norm:
                is_dup = True
                break
            if k_norm in norm_s:
                kept[idx] = (sent, norm_s, words, eng_facts)
                is_dup = True
                break
            if words and k_words:
                min_len = max(1, min(len(words), len(k_words)))
                union_len = max(1, len(words | k_words))
                overlap_ratio = len(words & k_words) / min_len
                jaccard = len(words & k_words) / union_len
                if overlap_ratio >= 0.72 or jaccard >= 0.60:
                    if eng_facts.issubset(k_facts):
                        if (
                            eng_facts == k_facts
                            and len(sent) > len(k_sent)
                            and overlap_ratio >= 0.85
                        ):
                            kept[idx] = (sent, norm_s, words, eng_facts)
                        is_dup = True
                        break
                    if k_facts.issubset(eng_facts) and overlap_ratio >= 0.72:
                        kept[idx] = (sent, norm_s, words, eng_facts)
                        is_dup = True
                        break
        if not is_dup:
            kept.append((sent, norm_s, words, eng_facts))

    selected = [item[0] for item in kept]
    if max_sentences is not None and max_sentences > 0:
        selected = selected[:max_sentences]
    return " ".join(selected).strip()


def _is_same_source_or_revision_update(
    old_src: str,
    new_src: str,
    superseded_sources: set[str] | None = None,
) -> bool:
    """Return True if old_src and new_src refer to the same document (in-place update or newer revision),
    or if old_src is explicitly listed in superseded_sources.
    Returns False if they refer to different documents or different sheets within the same document."""
    if not old_src or not new_src:
        return True
    if old_src.strip().lower() == new_src.strip().lower():
        return True

    if superseded_sources:
        norm_sup = {s.strip().lower() for s in superseded_sources if s.strip()}
        norm_sup_base = {_normalize_base_source_id(s) for s in superseded_sources if s.strip()} - {""}
        old_low = old_src.strip().lower()
        old_base_cand = _normalize_base_source_id(old_src)
        if (
            old_low in norm_sup
            or old_low.removeprefix("reference/raw/") in norm_sup
            or (old_base_cand and old_base_cand in norm_sup_base)
        ):
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
    explicit_moc_sources: set[str] | None = None,
    superseded_sources: set[str] | None = None,
    resolved_topics_out: set[str] | None = None,
) -> tuple[list[EngineeringParameter], list[str]]:
    """Merge two lists of EngineeringParameter.

    Supports:
    - Authoritative MOC overrides (`🔄 MOC PENDING REDRAFT`, zero false `⚠️ CONFLICT` bullets).
    - Deterministic revision ordering (`_is_strictly_older_same_doc_revision`: older revisions never overwrite newer).
    - Explicit `superseded_sources` retirement.
    - Returns `(merged_params, conflict_bullets)` and populates `resolved_topics_out` if provided.
    """
    merged: list[EngineeringParameter] = [p.model_copy(deep=True) for p in existing_params]
    index_by_key: dict[str, int] = {
        p.parameter.strip().lower(): idx for idx, p in enumerate(merged)
    }
    conflicts: list[str] = []
    resolved_topics: set[str] = resolved_topics_out if resolved_topics_out is not None else set()

    for new_p in new_params:
        key = new_p.parameter.strip().lower()
        topic_norm = re.sub(r"[^a-z0-9]+", " ", key).strip()
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

        new_is_moc = is_moc_source(new_src, explicit_moc_sources)
        old_is_moc = is_moc_source(old_src, explicit_moc_sources) or (
            old_p.note is not None and "MOC PENDING REDRAFT" in old_p.note.upper()
        )
        same_or_superseded = _is_same_source_or_revision_update(
            old_src, new_src, superseded_sources=superseded_sources
        )

        if _are_parameter_values_equivalent(old_val, new_val, old_p.note, new_p.note):
            if same_or_superseded:
                if _is_strictly_older_same_doc_revision(old_src, new_src) and not new_is_moc:
                    combined_src = old_src
                else:
                    combined_src = new_src or old_src
                # If a newer revision/document confirms the same value, clear any prior conflict note
                if old_p.note and ":" in old_p.note and "MOC PENDING REDRAFT" not in old_p.note.upper():
                    combined_note = new_p.note
                    if topic_norm:
                        resolved_topics.add(topic_norm)
                else:
                    combined_note = new_p.note or old_p.note
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
            old_u = "" if not old_p.unit or old_p.unit == "—" else f" {old_p.unit}"
            new_u = "" if not new_p.unit or new_p.unit == "—" else f" {new_p.unit}"

            # Case 1: New source is an authoritative MOC / ECN / FCR
            if new_is_moc:
                base_src_display = old_src or "Base Drawing"
                moc_note = f"🔄 MOC PENDING REDRAFT: supersedes {base_src_display} ({old_val}{old_u})"
                if new_p.note and new_p.note.strip() not in moc_note:
                    moc_note = f"{new_p.note.strip()}; {moc_note}"
                comb_src = (
                    f"{new_src}; {old_src}"
                    if old_src and old_src not in new_src
                    else (new_src or old_src or "Engineering Reference Document")
                )
                merged[idx] = EngineeringParameter(
                    parameter=new_p.parameter or old_p.parameter,
                    value=new_val,
                    unit=(new_p.unit if new_p.unit and new_p.unit != "—" else old_p.unit),
                    source=comb_src,
                    note=moc_note,
                )
                if topic_norm:
                    resolved_topics.add(topic_norm)
            # Case 2: Existing value is already governed by an authoritative MOC and an un-redrafted base drawing is re-ingested
            elif old_is_moc and not same_or_superseded:
                existing_note = old_p.note or ""
                redraft_clause = f"supersedes {new_src} ({new_val}{new_u})"
                if new_src and new_src not in existing_note:
                    if "MOC PENDING REDRAFT" in existing_note.upper():
                        existing_note = f"{existing_note}; {redraft_clause}"
                    else:
                        existing_note = f"🔄 MOC PENDING REDRAFT: {redraft_clause}"
                comb_src = (
                    f"{old_src}; {new_src}"
                    if new_src and new_src not in old_src
                    else old_src
                )
                merged[idx] = EngineeringParameter(
                    parameter=old_p.parameter,
                    value=old_val,
                    unit=old_p.unit,
                    source=comb_src,
                    note=existing_note or None,
                )
                if topic_norm:
                    resolved_topics.add(topic_norm)
            # Case 3: Same source document or explicit superseded source
            elif same_or_superseded:
                if _is_strictly_older_same_doc_revision(old_src, new_src):
                    # Out-of-order older revision ingested after newer revision -> retain newer old_p
                    continue
                merged[idx] = new_p.model_copy(deep=True)
                if topic_norm:
                    resolved_topics.add(topic_norm)
            # Case 4: Check if old_src is a semicolon-joined multi-source string where new_src updates one of its constituent documents
            elif ";" in old_src and any(
                _is_same_source_or_revision_update(part.strip(), new_src, superseded_sources=superseded_sources)
                for part in old_src.split(";")
                if part.strip()
            ):
                other_parts = [
                    part.strip()
                    for part in old_src.split(";")
                    if part.strip()
                    and not _is_same_source_or_revision_update(
                        part.strip(), new_src, superseded_sources=superseded_sources
                    )
                ]
                updated_parts = [
                    part.strip()
                    for part in old_src.split(";")
                    if part.strip()
                    and _is_same_source_or_revision_update(
                        part.strip(), new_src, superseded_sources=superseded_sources
                    )
                ]
                if updated_parts and any(_is_strictly_older_same_doc_revision(up, new_src) for up in updated_parts):
                    continue
                comb_src = "; ".join([*other_parts, new_src]) if other_parts else new_src
                merged[idx] = EngineeringParameter(
                    parameter=new_p.parameter or old_p.parameter,
                    value=new_val,
                    unit=(new_p.unit if new_p.unit and new_p.unit != "—" else old_p.unit),
                    source=comb_src or "Engineering Reference Document",
                    note=new_p.note,
                )
                if topic_norm:
                    resolved_topics.add(topic_norm)
            # Case 5: Genuine cross-document / multi-sheet discrepancy
            else:
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

    return merged, conflicts


def _merge_non_destructive_field(
    old_val: str | None,
    new_val: str | None,
    old_src: str | None = None,
    new_src: str | None = None,
    explicit_moc_sources: set[str] | None = None,
    superseded_sources: set[str] | None = None,
) -> str | None:
    """Merge a scalar string attribute across two turns.

    Replaces in-place when updated by an authoritative MOC, explicit superseded source,
    or newer revision of the same document; retains old_val if new_src is an older revision.
    """
    ov = (old_val or "").strip()
    nv = (new_val or "").strip()
    if nv in ("", "—"):
        return old_val
    if ov in ("", "—"):
        return new_val
    if ov == nv or ov in nv:
        return new_val

    osrc = (old_src or "").strip()
    nsrc = (new_src or "").strip()
    if is_moc_source(nsrc, explicit_moc_sources):
        return new_val
    if is_moc_source(osrc, explicit_moc_sources) and not is_moc_source(nsrc, explicit_moc_sources):
        return old_val
    if _is_same_source_or_revision_update(osrc, nsrc, superseded_sources=superseded_sources):
        if _is_strictly_older_same_doc_revision(osrc, nsrc):
            return old_val
        return new_val
    if _is_strictly_older_same_doc_revision(nsrc, osrc):
        return new_val
    if _is_strictly_older_same_doc_revision(osrc, nsrc):
        return old_val
    if nv in ov:
        return old_val
    return f"{nv} ({ov})"


def merge_equipment_entity_with_existing(
    new_entity: EquipmentEntity,
    existing_doc: OKFDocument,
) -> EquipmentEntity:
    """Merge a newly extracted EquipmentEntity with an existing OKFDocument for incremental file-by-file extraction."""
    fm = existing_doc.frontmatter or {}
    body = existing_doc.body or ""
    ent_meta = fm.get("entity_metadata") or {}

    # 0. Extract existing lifecycle metadata (aliases, superseded_sources, removed_instruments, removed_connections, moc_history)
    existing_aliases: list[str] = [
        str(a).strip() for a in (ent_meta.get("aliases") or []) if str(a).strip()
    ]
    existing_tag_meta = str(ent_meta.get("tag") or "").strip()
    if (
        existing_tag_meta
        and new_entity.tag.strip()
        and existing_tag_meta.upper() != new_entity.tag.strip().upper()
    ):
        existing_aliases.append(existing_tag_meta)

    existing_superseded: list[str] = [
        str(s).strip()
        for s in (ent_meta.get("superseded_sources") or [])
        if str(s).strip()
    ]
    all_superseded_list = list(
        dict.fromkeys(existing_superseded + list(new_entity.superseded_sources or []))
    )
    all_superseded_set = set(all_superseded_list)

    existing_removed_insts: list[str] = [
        str(i).strip()
        for i in (ent_meta.get("removed_instruments") or [])
        if str(i).strip()
    ]
    all_removed_insts_list = list(
        dict.fromkeys(existing_removed_insts + list(new_entity.removed_instruments or []))
    )
    removed_inst_keys = {i.strip().upper() for i in all_removed_insts_list if i.strip()}

    existing_removed_conns: list[str] = [
        str(c).strip()
        for c in (ent_meta.get("removed_connections") or [])
        if str(c).strip()
    ]
    all_removed_conns_list = list(
        dict.fromkeys(existing_removed_conns + list(new_entity.removed_connections or []))
    )
    removed_conn_keys = {c.strip().upper() for c in all_removed_conns_list if c.strip()}

    existing_moc_history: list[MOCChangeRecord] = []
    for item in ent_meta.get("moc_history") or []:
        if isinstance(item, MOCChangeRecord):
            existing_moc_history.append(item)
        elif isinstance(item, dict) and item.get("moc_id"):
            existing_moc_history.append(MOCChangeRecord(**item))

    merged_moc_history: list[MOCChangeRecord] = list(existing_moc_history)
    seen_moc_ids = {m.moc_id.strip().upper() for m in merged_moc_history}
    for m in new_entity.moc_history or []:
        m_obj = m if isinstance(m, MOCChangeRecord) else MOCChangeRecord(**dict(m))
        m_key = m_obj.moc_id.strip().upper()
        if m_key not in seen_moc_ids:
            seen_moc_ids.add(m_key)
            merged_moc_history.append(m_obj)
        else:
            for idx, em in enumerate(merged_moc_history):
                if em.moc_id.strip().upper() == m_key:
                    merged_moc_history[idx] = m_obj
                    break

    explicit_moc_sources: set[str] = {
        m.moc_id.strip() for m in merged_moc_history if m.moc_id.strip()
    }
    for s in new_entity.sources or []:
        if is_moc_source(s, explicit_moc_sources):
            explicit_moc_sources.add(s.strip())

    # 1. Extract existing design_data
    existing_design: list[EngineeringParameter] = []
    for cells in _parse_section_table_rows(body, "Design Data"):
        if len(cells) >= 4:
            p_name, val_cell, unit_cell, src_cell = cells[0], cells[1], cells[2], cells[3]
            note_val: str | None = None
            m_note = re.match(r"^([^()]+?)\s+\((.+)\)$", val_cell)
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
            m_note = re.match(r"^([^()]+?)\s+\((.+)\)$", val_cell)
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
    meta_insts = ent_meta.get("instruments") or []
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
                if ikey and ikey not in removed_inst_keys and ikey not in existing_inst_by_key:
                    existing_inst_by_key[ikey] = len(existing_insts)
                    existing_insts.append(inst_obj)

    for cells in _parse_section_table_rows(body, "Instrumentation"):
        if len(cells) >= 7:
            raw_tag_cell = cells[0]
            m_link = re.match(r"^\[([^\]]+)\]\([^)]+\)$", raw_tag_cell)
            clean_tag = (m_link.group(1) if m_link else raw_tag_cell).strip()
            ikey = clean_tag.upper()
            if ikey and ikey not in removed_inst_keys and ikey not in existing_inst_by_key:
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

    # 4. Extract existing connections (union of structured entity_metadata AND Markdown table rows)
    existing_conns: list[ConnectionStream] = []
    existing_conn_by_key: dict[str, int] = {}
    meta_conns = ent_meta.get("connections") or []
    if isinstance(meta_conns, list):
        for item in meta_conns:
            if isinstance(item, dict) and item.get("stream_id"):
                conn_obj = ConnectionStream(
                    stream_id=str(item.get("stream_id", "")),
                    direction=item.get("direction"),
                    source_tag=re.sub(
                        r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", str(item.get("source_tag") or "")
                    )
                    or None,
                    target_tag=re.sub(
                        r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", str(item.get("target_tag") or "")
                    )
                    or None,
                    line_size=item.get("line_size"),
                    inline_components=item.get("inline_components") or [],
                    temperature=item.get("temperature"),
                    pressure=item.get("pressure"),
                    flow_rate=item.get("flow_rate"),
                    description=item.get("description"),
                    source=str(item.get("source") or "Engineering Reference Document"),
                )
                ckey = conn_obj.stream_id.strip().upper()
                if ckey and ckey not in removed_conn_keys and ckey not in existing_conn_by_key:
                    existing_conn_by_key[ckey] = len(existing_conns)
                    existing_conns.append(conn_obj)

    for cells in _parse_section_table_rows(body, "Connections & Stream Summary"):
        if len(cells) >= 10:
            ckey = cells[0].strip().upper()
            if ckey and ckey not in removed_conn_keys and ckey not in existing_conn_by_key:
                existing_conn_by_key[ckey] = len(existing_conns)
                src_clean = re.sub(r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", cells[2]).strip()
                tgt_clean = re.sub(r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", cells[3]).strip()
                existing_conns.append(
                    ConnectionStream(
                        stream_id=cells[0],
                        direction=None if cells[1] == "—" else cells[1],
                        source_tag=None if src_clean in ("", "—") else src_clean,
                        target_tag=None if tgt_clean in ("", "—") else tgt_clean,
                        line_size=None if cells[4] == "—" else cells[4],
                        inline_components=[] if cells[5] == "—" else cells[5],
                        temperature=None if cells[6] == "—" else cells[6],
                        pressure=None if cells[7] == "—" else cells[7],
                        flow_rate=None if cells[8] == "—" else cells[8],
                        description=None if cells[9] == "—" else cells[9],
                        source=(
                            cells[10]
                            if len(cells) >= 11 and cells[10] and cells[10] != "—"
                            else "Engineering Reference Document"
                        ),
                    )
                )
        elif len(cells) >= 5:
            ckey = cells[0].strip().upper()
            if ckey and ckey not in removed_conn_keys and ckey not in existing_conn_by_key:
                existing_conn_by_key[ckey] = len(existing_conns)
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

    # Merge parameters & collect automatic cross-document conflict warnings and resolved topics
    resolved_design_topics: set[str] = set()
    merged_design, design_conflicts = _merge_parameter_lists(
        existing_design,
        new_entity.design_data,
        explicit_moc_sources=explicit_moc_sources,
        superseded_sources=all_superseded_set,
        resolved_topics_out=resolved_design_topics,
    )
    resolved_op_topics: set[str] = set()
    merged_ops, op_conflicts = _merge_parameter_lists(
        existing_ops,
        new_entity.operating_conditions,
        explicit_moc_sources=explicit_moc_sources,
        superseded_sources=all_superseded_set,
        resolved_topics_out=resolved_op_topics,
    )
    all_resolved_topics = resolved_design_topics | resolved_op_topics
    new_conflict_topics = {
        _extract_conflict_topic_key(c)
        for c in (design_conflicts + op_conflicts)
        if _extract_conflict_topic_key(c)
    }

    # Merge instruments by normalized tag with MOC/revision-aware field retention
    merged_insts: list[InstrumentLoop] = [
        i.model_copy(deep=True)
        for i in existing_insts
        if i.tag.strip().upper() not in removed_inst_keys
    ]
    inst_idx: dict[str, int] = {
        i.tag.strip().upper(): idx for idx, i in enumerate(merged_insts)
    }
    for new_i in new_entity.instruments:
        ikey = new_i.tag.strip().upper()
        if ikey in removed_inst_keys:
            continue
        if ikey not in inst_idx:
            inst_idx[ikey] = len(merged_insts)
            merged_insts.append(new_i.model_copy(deep=True))
        else:
            old_i = merged_insts[inst_idx[ikey]]
            old_src = (old_i.source or "").strip()
            new_src = (new_i.source or "").strip()
            if (
                old_src
                and new_src
                and new_src not in old_src
                and not _is_same_source_or_revision_update(
                    old_src, new_src, superseded_sources=all_superseded_set
                )
            ):
                comb_src = f"{new_src}; {old_src}" if is_moc_source(new_src, explicit_moc_sources) else f"{old_src}; {new_src}"
            else:
                comb_src = (
                    old_src
                    if (
                        _is_strictly_older_same_doc_revision(old_src, new_src)
                        and not is_moc_source(new_src, explicit_moc_sources)
                    )
                    else (new_src or old_src)
                )
            merged_insts[inst_idx[ikey]] = InstrumentLoop(
                tag=new_i.tag or old_i.tag,
                service=_merge_non_destructive_field(
                    old_i.service,
                    new_i.service,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                )
                or "",
                instrument_type=_merge_non_destructive_field(
                    old_i.instrument_type,
                    new_i.instrument_type,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                )
                or "",
                location=_merge_non_destructive_field(
                    old_i.location,
                    new_i.location,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                ),
                setpoint_or_range=_merge_non_destructive_field(
                    old_i.setpoint_or_range,
                    new_i.setpoint_or_range,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                ),
                interlock_or_alarm=_merge_non_destructive_field(
                    old_i.interlock_or_alarm,
                    new_i.interlock_or_alarm,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                ),
                source=comb_src or "Engineering Reference Document",
            )

    # Merge connections by normalized stream_id with MOC/revision-aware endpoint replacement
    merged_conns: list[ConnectionStream] = [
        c.model_copy(deep=True)
        for c in existing_conns
        if c.stream_id.strip().upper() not in removed_conn_keys
    ]
    conn_idx: dict[str, int] = {
        c.stream_id.strip().upper(): idx for idx, c in enumerate(merged_conns)
    }
    for new_c in new_entity.connections:
        ckey = new_c.stream_id.strip().upper()
        if ckey in removed_conn_keys:
            continue
        if ckey not in conn_idx:
            conn_idx[ckey] = len(merged_conns)
            merged_conns.append(new_c.model_copy(deep=True))
        else:
            old_c = merged_conns[conn_idx[ckey]]
            old_src = (old_c.source or "").strip()
            new_src = (new_c.source or "").strip()
            is_authoritative_replace = (
                is_moc_source(new_src, explicit_moc_sources)
                or _is_strictly_older_same_doc_revision(new_src, old_src)
                or (
                    bool(all_superseded_set)
                    and _is_same_source_or_revision_update(
                        old_src, new_src, superseded_sources=all_superseded_set
                    )
                    and old_src != new_src
                )
            )
            combined_inline: list[str] = []
            seen_inline: set[str] = set()
            inline_pool = (
                list(new_c.inline_components or [])
                if (is_authoritative_replace and new_c.inline_components)
                else list(old_c.inline_components or []) + list(new_c.inline_components or [])
            )
            for comp in inline_pool:
                comp_clean = comp.strip()
                if comp_clean and comp_clean.upper() not in seen_inline:
                    seen_inline.add(comp_clean.upper())
                    combined_inline.append(comp_clean)

            chosen_conn_src = (
                old_src
                if (
                    _is_strictly_older_same_doc_revision(old_src, new_src)
                    and not is_moc_source(new_src, explicit_moc_sources)
                )
                else (new_c.source or old_c.source or "Engineering Reference Document")
            )
            merged_conns[conn_idx[ckey]] = ConnectionStream(
                stream_id=new_c.stream_id or old_c.stream_id,
                direction=_merge_non_destructive_field(
                    old_c.direction,
                    new_c.direction,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                ),
                source_tag=_merge_non_destructive_field(
                    old_c.source_tag,
                    new_c.source_tag,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                ),
                target_tag=_merge_non_destructive_field(
                    old_c.target_tag,
                    new_c.target_tag,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                ),
                line_size=_merge_non_destructive_field(
                    old_c.line_size,
                    new_c.line_size,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                ),
                inline_components=combined_inline,
                temperature=_merge_non_destructive_field(
                    old_c.temperature,
                    new_c.temperature,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                ),
                pressure=_merge_non_destructive_field(
                    old_c.pressure,
                    new_c.pressure,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                ),
                flow_rate=_merge_non_destructive_field(
                    old_c.flow_rate,
                    new_c.flow_rate,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                ),
                description=_merge_non_destructive_field(
                    old_c.description,
                    new_c.description,
                    old_src,
                    new_src,
                    explicit_moc_sources=explicit_moc_sources,
                    superseded_sources=all_superseded_set,
                ),
                source=chosen_conn_src,
            )

    # Boundary Guard #2: Auto-clear stale '⚠️ CONFLICT — <Topic>:' bullets from existing_hazards
    # ONLY when <Topic> was explicitly resolved in this merge (and did not re-conflict).
    filtered_existing_hazards: list[str] = []
    for eh in existing_hazards:
        t_key = _extract_conflict_topic_key(eh)
        if t_key and t_key in all_resolved_topics and t_key not in new_conflict_topics:
            continue
        filtered_existing_hazards.append(eh)

    # Merge hazards & conflicts (deduplicated by exact text, near-duplicate prose, and conflict topic)
    merged_hazards: list[str] = []
    seen_hazards: set[str] = set()
    seen_conflict_topics: set[str] = set()
    for h in filtered_existing_hazards + new_entity.hazards + design_conflicts + op_conflicts:
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

    # Merge sources (pruning superseded_sources and retaining the highest revision rank per base document ID)
    norm_superseded_exact = {
        s.strip().removeprefix("reference/raw/").lower()
        for s in all_superseded_list
        if s.strip()
    }
    norm_superseded_files = {
        s.strip().split("/")[-1].lower()
        for s in all_superseded_list
        if s.strip()
    }
    merged_sources: list[str] = []
    source_idx_by_base: dict[str, int] = {}
    for s in existing_sources + new_entity.sources:
        s_clean = s.strip().removeprefix("reference/raw/")
        if not s_clean:
            continue
        if (
            s_clean.lower() in norm_superseded_exact
            or s_clean.split("/")[-1].lower() in norm_superseded_files
        ):
            continue
        base_key = _normalize_base_source_id(s_clean) or s_clean.lower()
        if base_key not in source_idx_by_base:
            source_idx_by_base[base_key] = len(merged_sources)
            merged_sources.append(s_clean)
        else:
            prev_s = merged_sources[source_idx_by_base[base_key]]
            if not _is_strictly_older_same_doc_revision(prev_s, s_clean):
                merged_sources[source_idx_by_base[base_key]] = s_clean

    existing_func = _extract_section_text(body, "Function")
    raw_combined_func = new_entity.function_summary or existing_func
    if (
        existing_func
        and new_entity.function_summary
        and existing_func.strip() != new_entity.function_summary.strip()
    ):
        ef_clean = existing_func.strip()
        nf_clean = new_entity.function_summary.strip()
        if ef_clean in nf_clean:
            raw_combined_func = nf_clean
        elif nf_clean in ef_clean:
            raw_combined_func = ef_clean
        else:
            raw_combined_func = f"{ef_clean} {nf_clean}"
    merged_func = deduplicate_engineering_prose(raw_combined_func)

    existing_tags = [
        str(t) for t in (fm.get("tags") or []) if isinstance(t, str) and str(t).strip()
    ]
    merged_aliases = list(
        dict.fromkeys(existing_aliases + [a.strip() for a in (new_entity.aliases or []) if a.strip()])
    )

    return EquipmentEntity(
        tag=new_entity.tag,
        name=new_entity.name,
        equipment_class=new_entity.equipment_class,
        unit=new_entity.unit,
        aliases=merged_aliases,
        function_summary=merged_func,
        design_data=merged_design,
        operating_conditions=merged_ops,
        instruments=merged_insts,
        connections=merged_conns,
        hazards=merged_hazards,
        sources=merged_sources,
        superseded_sources=all_superseded_list,
        removed_instruments=all_removed_insts_list,
        removed_connections=all_removed_conns_list,
        moc_history=merged_moc_history,
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


