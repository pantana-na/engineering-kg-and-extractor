"""Domain entity models for chemical engineering assets and hazard evaluations.

Models align with verified domain extractions in reference/wiki/.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


def sanitize_tag_filename(tag: str) -> str:
    """Sanitize an equipment or instrument tag for safe filesystem markdown filenames.

    Examples:
        'TK-101A/B/C' -> 'TK-101ABC'
        'P-101A/B' -> 'P-101AB'
        'TI-101 / TAH-101' -> 'TI-101_TAH-101'
        'LT-101 (N1)' -> 'LT-101'
    """
    cleaned = tag.strip()
    # Strip parenthetical nozzle/location remarks such as '(Y02)'
    cleaned = re.sub(r"\s*\([^)]*\)", "", cleaned).strip()
    # Replace ' / ' (paired tags) with '_' and strip direct unit slashes ('A/B/C' -> 'ABC')
    cleaned = re.sub(r"\s+[/\\]\s+", "_", cleaned)
    cleaned = re.sub(r"[/\\]+", "", cleaned)
    cleaned = re.sub(r"[^\w\-]+", "_", cleaned)
    return cleaned.strip("_") or "UNTAGGED"


def is_nozzle_mark_only(tag: str) -> bool:
    """Return True if a tag entry represents a datasheet nozzle mark rather than a P&ID instrument tag."""
    t = tag.strip()
    if t.lower().startswith("nozzle "):
        return True
    return bool(re.match(r"^[A-Z]\d{2}\b", t))


_ISA_EQUIP_TAG_RE = re.compile(
    r"^(?:[A-Z]{1,5}-\d{2,5}[A-Z0-9_-]*|\d+-[A-Z]{1,5}-\d{2,5}[A-Z0-9_-]*|[A-Z]{1,4}-\d{2}-\d{3,5}[A-Z0-9_-]*)$"
)

_GENERIC_SINGLE_WORD_EQUIP_NAMES: frozenset[str] = frozenset(
    {
        "equipment",
        "untagged",
        "unknown",
        "general",
        "system",
        "unit",
        "plant",
        "process",
        "item",
        "asset",
    }
)


def _is_isa_equipment_tag(tag_or_stem: str) -> bool:
    """Return True iff `tag_or_stem` conforms to a numbered plant/ISA equipment tag pattern."""
    cleaned = sanitize_tag_filename(tag_or_stem).upper()
    if not cleaned or cleaned == "UNTAGGED":
        return False
    return bool(_ISA_EQUIP_TAG_RE.match(cleaned))


def _singularize_alias_token(token: str) -> str:
    """Deterministically singularize lowercase alphabetic English plural nouns of length >= 5."""
    t = token.lower()
    if len(t) < 5 or not t.isalpha():
        return t
    if len(t) >= 6 and t.endswith("ies"):
        return f"{t[:-3]}y"
    if t.endswith(("ches", "shes", "xes", "zes", "ses")):
        return t[:-2]
    if t.endswith("s") and not t.endswith(("ss", "us", "is", "as", "os")):
        return t[:-1]
    return t


def _normalize_alias_key(text: str) -> str:
    """Normalize an equipment service name or alias into a canonical singularized comparison key."""
    if not text:
        return ""
    unlinked = re.sub(r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", str(text))
    unparen = re.sub(r"\s*\([^)]*\)", " ", unlinked)
    tokens = [
        _singularize_alias_token(tok)
        for tok in re.findall(r"[a-z0-9]+", unparen.lower())
        if tok
    ]
    return " ".join(tokens)


def _extract_unit_number_key(unit_str: str) -> str:
    """Extract canonical numeric plant unit code (normalizing 4-digit 'XX00' section numbers to 'XX')."""
    if not unit_str:
        return ""
    s = str(unit_str).strip().lower()
    m_pref = re.search(r"\bunit[-_\s]*(\d{2,4})\b", s)
    raw_num = m_pref.group(1) if m_pref else ""
    if not raw_num and re.fullmatch(r"\d{2,4}", s):
        raw_num = s
    if not raw_num:
        m_any = re.search(r"(?<![\d-])(\d{2,4})(?![\d-])", s)
        if m_any:
            cand = m_any.group(1)
            if not cand.startswith(("19", "202")):
                raw_num = cand
    if len(raw_num) == 4 and raw_num.endswith("00"):
        return raw_num[:2]
    return raw_num


def _units_are_compatible(unit_a: str, unit_b: str) -> bool:
    """Return True when neither unit specifies a conflicting numeric plant unit code."""
    ka = _extract_unit_number_key(unit_a)
    kb = _extract_unit_number_key(unit_b)
    return not ka or not kb or ka == kb


def _extract_unit_domain_key(slug_or_id: str) -> tuple[str, str]:
    """Extract `(core_domain_key, unit_number_key)` from a `units/*` slug or concept ID."""
    stem = slug_or_id.removesuffix(".md").split("/")[-1].lower().strip("-")
    if not stem:
        return "", ""
    unit_num = ""
    m_lead = re.match(r"^unit-(\d{2,4})-(.+)$", stem)
    if m_lead:
        unit_num = _extract_unit_number_key(m_lead.group(1))
        stem = m_lead.group(2)
    else:
        m_trail = re.match(r"^(.+)-unit-(\d{2,4})$", stem)
        if m_trail:
            unit_num = _extract_unit_number_key(m_trail.group(2))
            stem = m_trail.group(1)

    if re.fullmatch(r"unit-\d{2,4}", stem) or re.fullmatch(r"\d{2,4}", stem):
        return "", _extract_unit_number_key(stem)

    prev = None
    cur = stem
    while prev != cur:
        prev = cur
        cur = re.sub(r"^(?:unit|section)-", "", cur)
        cur = re.sub(r"-(?:unit|section|overview|summary)$", "", cur)
    cur = cur.strip("-")
    return cur, unit_num


_C_YAML_LOADER: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _parse_frontmatter_head(head_text: str) -> dict[str, Any]:
    """Safely parse YAML frontmatter from the leading bytes of an OKF Markdown file."""
    if not head_text.startswith("---"):
        return {}
    end_idx = head_text.find("\n---", 3)
    if end_idx == -1:
        return {}
    yaml_block = head_text[3:end_idx]
    try:
        parsed = yaml.load(yaml_block, Loader=_C_YAML_LOADER)  # nosec B506
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _equipment_catalog_alias_keys(item: dict[str, Any]) -> set[str]:
    """Return normalized service-name / alias keys declared on a catalog equipment item."""
    keys: set[str] = set()
    for candidate in (
        item.get("entity_name") or "",
        *(item.get("aliases") or []),
    ):
        norm = _normalize_alias_key(str(candidate))
        if norm and norm not in _GENERIC_SINGLE_WORD_EQUIP_NAMES and not _is_isa_equipment_tag(str(candidate)):
            keys.add(norm)
    title = str(item.get("title") or "").strip()
    if title:
        for sep in ("—", " - ", " – "):
            if sep in title:
                rhs = title.split(sep, 1)[1].strip()
                norm_rhs = _normalize_alias_key(rhs)
                if norm_rhs and norm_rhs not in _GENERIC_SINGLE_WORD_EQUIP_NAMES and not _is_isa_equipment_tag(rhs):
                    keys.add(norm_rhs)
                break
        else:
            if not _is_isa_equipment_tag(title):
                norm_t = _normalize_alias_key(title)
                if norm_t and norm_t not in _GENERIC_SINGLE_WORD_EQUIP_NAMES:
                    keys.add(norm_t)
    return keys


_BUNDLE_CATALOG_CACHE: dict[tuple[str, int, int, int], list[dict[str, Any]]] = {}
_BUNDLE_EQUIP_ALIAS_MAP_CACHE: dict[tuple[str, int, int, int], dict[str, str | None]] = {}


def _scan_bundle_md_entries(root_str: str) -> tuple[list[tuple[str, str, str, str]], int]:
    """Fast os.scandir recursive scan returning sorted `(rel_posix, abs_path, name, stem)` and max child `st_mtime_ns`."""
    import os

    found: list[tuple[str, str, str, str]] = []
    max_mtime_ns = 0
    stack: list[tuple[str, str]] = [(root_str, "")]
    while stack:
        abs_dir, rel_prefix = stack.pop()
        try:
            with os.scandir(abs_dir) as it:
                for de in it:
                    if de.is_dir(follow_symlinks=False):
                        sub_rel = f"{rel_prefix}/{de.name}" if rel_prefix else de.name
                        stack.append((de.path, sub_rel))
                    elif de.name.endswith(".md") and de.is_file(follow_symlinks=False):
                        st_ns = de.stat(follow_symlinks=False).st_mtime_ns
                        if st_ns > max_mtime_ns:
                            max_mtime_ns = st_ns
                        rel_posix = f"{rel_prefix}/{de.name}" if rel_prefix else de.name
                        found.append((rel_posix, de.path, de.name, de.name[:-3]))
        except OSError:
            continue
    found.sort(key=lambda item: item[0])
    return found, max_mtime_ns


def _iter_bundle_catalog(bundle_root: Path | None = None) -> list[dict[str, Any]]:
    """Dynamically inspect existing OKF concept files in the output bundle directory."""
    import os
    from extracter_agent.config import get_config

    cfg = get_config()
    root = bundle_root or cfg.output_bundle_dir
    if not root or not root.exists():
        return []

    abs_root = os.path.abspath(root)
    md_entries, latest_child_mtime_ns = _scan_bundle_md_entries(abs_root)
    cache_key = (
        abs_root,
        os.stat(abs_root).st_mtime_ns,
        len(md_entries),
        latest_child_mtime_ns,
    )
    cached = _BUNDLE_CATALOG_CACHE.get(cache_key)
    if cached is not None:
        return cached

    equip_catalog, equip_alias_map = _get_equipment_catalog_and_aliases(Path(abs_root))
    equip_by_id: dict[str, dict[str, Any]] = {
        str(item["concept_id"]): item for item in equip_catalog
    }

    catalog: list[dict[str, Any]] = []
    for rel, fpath, fname, stem in md_entries:
        if fname in ("index.md", "log.md") and rel != "index.md":
            continue
        stem_id = rel[:-3]
        if stem_id in equip_by_id:
            catalog.append(equip_by_id[stem_id])
            continue
        category = stem_id.split("/", 1)[0] if "/" in stem_id else "root"
        try:
            with open(fpath, encoding="utf-8", errors="ignore") as fp:
                head = fp.read(3500)
        except Exception:
            head = ""
        fm = _parse_frontmatter_head(head)
        em = fm.get("entity_metadata") if isinstance(fm.get("entity_metadata"), dict) else {}
        raw_aliases = em.get("aliases") if isinstance(em.get("aliases"), list) else []
        entry: dict[str, Any] = {
            "concept_id": stem_id,
            "category": category,
            "stem": stem,
            "stem_upper": stem.upper(),
            "head_lower": head.lower(),
            "title": str(fm.get("title") or ""),
            "entity_tag": str(em.get("tag") or ""),
            "entity_name": str(em.get("name") or ""),
            "entity_unit": str(em.get("unit") or ""),
            "aliases": [str(a).strip() for a in raw_aliases if str(a).strip()],
        }
        catalog.append(entry)

    _BUNDLE_CATALOG_CACHE[cache_key] = catalog
    _BUNDLE_EQUIP_ALIAS_MAP_CACHE[cache_key] = dict(equip_alias_map)
    return catalog


_EQUIP_ONLY_CATALOG_CACHE: dict[
    tuple[str, int, int, int],
    tuple[list[dict[str, Any]], dict[str, str | None]],
] = {}


def _get_equipment_catalog_and_aliases(
    bundle_root: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str | None]]:
    """Fast os.scandir-backed equipment-only catalog and O(1) unique prose alias map."""
    import os
    from extracter_agent.config import get_config

    cfg = get_config()
    root = bundle_root or cfg.output_bundle_dir
    if not root:
        return [], {}
    equip_dir = Path(root) / "equipment"
    if not equip_dir.is_dir():
        return [], {}

    entries_meta: list[tuple[str, str, int]] = []
    max_ns = 0
    with os.scandir(equip_dir) as it:
        for de in it:
            if not de.name.endswith(".md") or de.name in ("index.md", "log.md") or not de.is_file():
                continue
            st_ns = de.stat().st_mtime_ns
            if st_ns > max_ns:
                max_ns = st_ns
            entries_meta.append((de.name[:-3], de.path, st_ns))

    cache_key = (
        os.path.abspath(equip_dir),
        equip_dir.stat().st_mtime_ns,
        len(entries_meta),
        max_ns,
    )
    cached_pair = _EQUIP_ONLY_CATALOG_CACHE.get(cache_key)
    if cached_pair is not None:
        return cached_pair

    entries_meta.sort(key=lambda x: x[0])
    c_loader: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    equip_catalog: list[dict[str, Any]] = []
    alias_hits: dict[str, list[str]] = {}

    for stem, fpath, _ in entries_meta:
        try:
            with open(fpath, encoding="utf-8", errors="ignore") as fp:
                head = fp.read(3500)
        except Exception:
            head = ""
        fm: dict[str, Any] = {}
        if head.startswith("---"):
            end_idx = head.find("\n---", 3)
            if end_idx != -1:
                try:
                    parsed = yaml.load(head[3:end_idx], Loader=c_loader)  # nosec B506
                    if isinstance(parsed, dict):
                        fm = parsed
                except Exception:
                    fm = {}
        em = fm.get("entity_metadata") if isinstance(fm.get("entity_metadata"), dict) else {}
        raw_aliases = em.get("aliases") if isinstance(em.get("aliases"), list) else []
        is_isa = _is_isa_equipment_tag(stem)
        entry: dict[str, Any] = {
            "concept_id": f"equipment/{stem}",
            "category": "equipment",
            "stem": stem,
            "stem_upper": stem.upper(),
            "head_lower": head.lower(),
            "title": str(fm.get("title") or ""),
            "entity_tag": str(em.get("tag") or ""),
            "entity_name": str(em.get("name") or ""),
            "entity_unit": str(em.get("unit") or ""),
            "aliases": [str(a).strip() for a in raw_aliases if str(a).strip()],
            "is_isa_tag": is_isa,
            "base_id": _extract_equipment_base_id(stem),
        }
        if is_isa:
            a_keys = _equipment_catalog_alias_keys(entry)
            entry["alias_keys"] = a_keys
            for ak in a_keys:
                alias_hits.setdefault(ak, []).append(stem)
        else:
            entry["alias_keys"] = set()
        equip_catalog.append(entry)

    alias_map: dict[str, str | None] = {
        ak: stems[0] if len(stems) == 1 else None
        for ak, stems in alias_hits.items()
    }
    res_pair = (equip_catalog, alias_map)
    _EQUIP_ONLY_CATALOG_CACHE[cache_key] = res_pair
    return res_pair


def _extract_equipment_base_id(tag_str: str) -> str:
    """Extract canonical '<PREFIX>-<DIGITS>' base equipment identifier."""
    cleaned = sanitize_tag_filename(tag_str).upper()
    m = re.match(r"^([A-Z]{1,4})[-_]?(\d{3,4})", cleaned)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return cleaned


def derive_canonical_equipment_tag(
    tag: str,
    source_files: list[str] | None = None,
    bundle_root: Path | None = None,
) -> str:
    """Derive the canonical equipment filename tag dynamically from source document metadata and bundle catalog.

    Zero hardcoded equipment tag literals. Enforces strict base equipment ID isolation so shared P&IDs,
    operating manuals, or connected vessel datasheets never cause cross-entity filename collisions.
    """
    safe = sanitize_tag_filename(tag)
    safe_upper = safe.upper()
    req_base = _extract_equipment_base_id(safe)
    catalog, alias_map = _get_equipment_catalog_and_aliases(bundle_root)

    # 1. Extract PS-<TAG> candidates from source_files that share the same base equipment ID
    ps_candidates: list[str] = []
    for src in source_files or []:
        m = re.search(
            r"(?:PS|DS)-([A-Z]{1,3})[-_]?(\d{4}[A-Z]*)(?=[_\-\s.]|$)",
            src,
            flags=re.IGNORECASE,
        )
        if m:
            cand = f"{m.group(1).upper()}-{m.group(2).upper()}"
            if _extract_equipment_base_id(cand) == req_base:
                ps_candidates.append(cand)

    for ps_tag in ps_candidates:
        if any(c.get("stem_upper", c["stem"].upper()) == ps_tag for c in catalog):
            return ps_tag

    if bundle_root is None and ps_candidates and re.search(r"\d[A-Z]{2}$", safe):
        if any(" a_b " in (s or "").lower() for s in (source_files or [])):
            return ps_candidates[0]

    # 2. Exact stem match in bundle catalog
    for c in catalog:
        if c.get("stem_upper", c["stem"].upper()) == safe_upper:
            return str(c["stem"])

    # 3. Match existing catalog file only if it shares the exact same base equipment ID
    #    and explicitly declares this exact equipment tag in its frontmatter or dedicated PS-<TAG>
    ps_code_match = re.match(r"^([A-Z]{1,4})-(\d{3,4})$", req_base)
    dedicated_ps_token = (
        f"ps-{ps_code_match.group(1).lower()}{ps_code_match.group(2)}"
        if ps_code_match
        else ""
    )
    raw_tag_lower = tag.strip().lower()
    for c in catalog:
        c_base = c.get("base_id") or _extract_equipment_base_id(str(c["stem"]))
        if c_base != req_base:
            continue
        head = c["head_lower"]
        if raw_tag_lower and (
            re.search(
                rf"(?:^|\n)\s*tag:\s*['\"]?{re.escape(raw_tag_lower)}['\"]?\s*(?:\n|$)",
                head,
            )
            or f"title: {raw_tag_lower} " in head
        ):
            return str(c["stem"])
        if dedicated_ps_token and dedicated_ps_token in head:
            return str(c["stem"])

    # 3b. Prose service-name -> unique Canonical ISA Tag resolution via O(1) cached frontmatter index
    if not _is_isa_equipment_tag(safe):
        probe_key = _normalize_alias_key(tag)
        if probe_key and probe_key not in _GENERIC_SINGLE_WORD_EQUIP_NAMES:
            winner = alias_map.get(probe_key)
            if winner:
                return winner

    # 4. When no catalog entry exists yet, only use PS-<TAG> candidate over a 2-unit paired tag
    #    if the PS-<TAG> candidate is at least as specific (e.g. PS-C101AB) or the source title explicitly embeds ' A_B '
    if ps_candidates and re.search(r"\d[A-Z]{2}$", safe):
        has_inline_ab = any(" a_b " in (s or "").lower() for s in (source_files or []))
        if len(ps_candidates[0]) >= len(safe) or has_inline_ab:
            return ps_candidates[0]

    return safe


_BOILERPLATE_SLUG_TOKENS: frozenset[str] = frozenset(
    {
        "cdn",
        "unit",
        "section",
        "plant",
        "train",
        "ii",
        "acme",
        "demo",
        "complex",
        "ds",
        "std",
        "23",
        "2300",
        "20",
        "21",
        "22",
        "25",
        "ps",
        "sds",
        "psi",
        "om",
        "pfd",
        "pid",
        "dwg",
        "sg",
        "mp",
        "oems",
        "batch",
        "2026",
        "2015",
        "06",
        "14",
        "16",
        "r1",
        "r2",
        "r3",
        "r4",
        "z0",
        "z1",
        "rev",
        "as",
        "built",
        "final",
        "process",
        "data",
        "sheet",
        "sheets",
        "datasheet",
        "datasheets",
        "instrument",
        "instruments",
        "instrumentation",
        "register",
        "master",
        "procedure",
        "procedures",
        "operating",
        "operations",
        "operation",
        "hazop",
        "leadership",
        "training",
        "course",
        "module",
        "chapter",
        "table",
        "checklist",
        "readiness",
        "guide",
        "standard",
        "study",
        "overview",
        "summary",
        "specification",
        "profile",
        "hazard",
        "chemical",
        "safety",
        "system",
        "architecture",
        "control",
    }
)


def _extract_distinct_id_tokens(tokens: set[str]) -> set[str]:
    """Extract document numbers, chapter numbers, CAS segments, or equipment codes that distinguish concepts."""
    ids: set[str] = set()
    for t in tokens:
        if t in _BOILERPLATE_SLUG_TOKENS:
            continue
        if re.match(r"^(?:r\d+|rev\d*[a-z]*|z\d+)$", t):
            continue
        if any(ch.isdigit() for ch in t):
            ids.add(t)
    return ids


def derive_canonical_concept_id(
    concept_id: str,
    concept_type: str = "",
    title: str = "",
    sources: list[str] | None = None,
    entity_metadata: dict[str, Any] | None = None,
    bundle_root: Path | None = None,
) -> str:
    """Dynamically resolve the canonical OKF concept_id path from bundle catalog metadata and structural rules.

    Zero static lookup dictionaries or plant-specific hardcoded strings.
    """
    clean_id = concept_id.removesuffix(".md").strip("/")
    if not clean_id:
        return "index"

    # Normalize parenthetical qualifiers and whitespace in the candidate slug
    parts = [p for p in clean_id.split("/") if p]
    norm_parts: list[str] = []
    for idx, part in enumerate(parts):
        cleaned_part = re.sub(r"\s*\([^)]*\)", "", part).strip()
        if idx == len(parts) - 1 and parts[0].lower() != "sources":
            cleaned_part = re.sub(r"[^\w\-]+", "-", cleaned_part.lower()).strip("-")
        else:
            cleaned_part = re.sub(r"[^\w\-.]+", "-", cleaned_part).strip("-")
        if cleaned_part:
            norm_parts.append(cleaned_part)

    normalized_id = "/".join(norm_parts) if norm_parts else clean_id

    if normalized_id.lower().startswith("equipment/"):
        raw_tag = clean_id.split("/")[-1]
        return f"equipment/{derive_canonical_equipment_tag(raw_tag, sources, bundle_root)}"

    req_cat = norm_parts[0].lower() if len(norm_parts) > 1 else "root"
    raw_slug = norm_parts[-1].lower() if norm_parts else clean_id.lower()
    core_slug = re.sub(
        r"-(?:process-hazard-profile|chemical-hazard-profile|hazard-profile|process-hazard|hazard|profile|register|specification|procedure|overview|architecture|summary)$",
        "",
        raw_slug,
    ).strip("-")
    if core_slug.startswith(f"{req_cat}-") and len(core_slug) > len(req_cat) + 1:
        core_slug = core_slug.removeprefix(f"{req_cat}-")
    core_id = f"{req_cat}/{core_slug}" if len(norm_parts) > 1 and core_slug else normalized_id

    catalog = _iter_bundle_catalog(bundle_root)
    if not catalog:
        return core_id

    # 1. Exact case-insensitive match against existing bundle concept (prioritizing core_id first)
    for cand_exact in (core_id.lower(), normalized_id.lower(), clean_id.lower()):
        for item in catalog:
            if item["concept_id"].lower() == cand_exact:
                return str(item["concept_id"])

    # 1b. Unit domain-slug coalescing (before _BOILERPLATE_SLUG_TOKENS strips 'unit'/'section' domain tokens)
    if req_cat == "units":
        req_dom, req_unum = _extract_unit_domain_key(raw_slug)
        if not req_unum and isinstance(entity_metadata, dict):
            req_unum = _extract_unit_number_key(str(entity_metadata.get("unit") or ""))
        if req_dom:
            unit_matches: list[dict[str, Any]] = []
            for item in catalog:
                if str(item["category"]).lower() != "units":
                    continue
                item_dom, item_unum = _extract_unit_domain_key(str(item["stem"]))
                if not item_unum:
                    item_unum = _extract_unit_number_key(str(item.get("entity_unit") or ""))
                if item_dom == req_dom and _units_are_compatible(req_unum, item_unum):
                    unit_matches.append(item)
            if len(unit_matches) == 1:
                return str(unit_matches[0]["concept_id"])
            if len(unit_matches) > 1:
                exact_unum = [
                    m
                    for m in unit_matches
                    if _extract_unit_domain_key(str(m["stem"]))[1] == req_unum
                ]
                pool = exact_unum or unit_matches
                pool_sorted = sorted(pool, key=lambda m: (len(str(m["stem"])), str(m["concept_id"])))
                return str(pool_sorted[0]["concept_id"])

    # 2. Match by target category + boilerplate-free domain token specificity + identifier guard
    slug_tokens = set(re.findall(r"[a-z0-9]{2,}", core_slug.lower()))
    core_slug_tokens = slug_tokens - _BOILERPLATE_SLUG_TOKENS
    slug_id_tokens = _extract_distinct_id_tokens(slug_tokens)

    query_tokens = (
        set(re.findall(r"[a-z0-9]{2,}", f"{core_slug} {title} {concept_type}".lower()))
        - _BOILERPLATE_SLUG_TOKENS
        - {"md", "okf", "pdf", "extract", "document", "concept"}
    )
    src_tokens = [Path(s).stem.lower() for s in (sources or []) if s and len(Path(s).stem) >= 4]

    best_id: str | None = None
    best_score = 0.0
    for item in catalog:
        item_cat = str(item["category"]).lower()
        if item_cat != req_cat and not (
            req_cat in ("root", "standards") and item_cat in ("root", "sources", "hazop")
        ):
            continue

        item_stem_tokens = set(re.findall(r"[a-z0-9]{2,}", str(item["stem"]).lower()))
        if not item_stem_tokens:
            continue

        core_item_tokens = item_stem_tokens - _BOILERPLATE_SLUG_TOKENS
        item_id_tokens = _extract_distinct_id_tokens(item_stem_tokens)

        # Guard A: Never merge two concepts that carry different numeric/code identifiers
        # (e.g., '0003' vs '0004', 'ch1' vs 'ch2', '98-82-8' vs '98-86-2', 'std-pha-001' vs unnumbered chapter)
        if slug_id_tokens != item_id_tokens:
            continue

        # Guard B: Direct strict-subset guard between requested tokens and catalog item tokens
        if (
            item_cat == req_cat
            and slug_tokens
            and (slug_tokens < item_stem_tokens or item_stem_tokens < slug_tokens)
        ):
            continue
        if (
            item_cat == req_cat
            and core_slug_tokens
            and core_item_tokens
            and (core_slug_tokens < core_item_tokens or core_item_tokens < core_slug_tokens)
        ):
            continue

        # Guard C: For same-category concepts, require high Jaccard similarity (>= 0.65)
        # on non-boilerplate domain tokens so shared unit/batch tokens ('cdn', 'batch', 'ps', 'sds') never cause collisions
        if item_cat == req_cat:
            if not core_slug_tokens or not core_item_tokens:
                continue
            core_jaccard = len(core_slug_tokens & core_item_tokens) / max(
                1, len(core_slug_tokens | core_item_tokens)
            )
            if core_jaccard < 0.65:
                continue
        else:
            effective_s = core_slug_tokens or slug_tokens
            effective_i = core_item_tokens or item_stem_tokens
            core_jaccard = (
                len(effective_s & effective_i) / max(1, len(effective_s | effective_i))
                if effective_s
                else 0.0
            )
            if core_jaccard == 0.0:
                continue

        effective_item = core_item_tokens or item_stem_tokens
        overlap = len(query_tokens & effective_item) / max(1, len(effective_item))
        if overlap == 0.0 and core_jaccard < 1.0:
            continue

        specificity_bonus = 0.25 * len((core_slug_tokens or slug_tokens) & effective_item)
        src_bonus = min(0.35, sum(0.25 for st in src_tokens if st in item["head_lower"]))
        cat_bonus = 0.25 if item_cat == req_cat else 0.0
        score = overlap + (core_jaccard * 0.5) + specificity_bonus + src_bonus + cat_bonus

        if score > best_score and score >= 0.75:
            best_score = score
            best_id = str(item["concept_id"])

    return best_id or core_id




class EngineeringParameter(BaseModel):
    parameter: str
    value: str
    unit: str | None = None
    source: str = Field(default="Engineering Reference Document")
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_parameter_dict(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        param = out.get("parameter") or out.get("name") or out.get("property") or "Parameter"
        val = out.get("value")
        if val is None:
            val = out.get("val")
        if val is None:
            val = "—"
        out["parameter"] = str(param).strip() or "Parameter"
        out["value"] = str(val).strip() or "—"
        if out.get("unit") is not None:
            out["unit"] = str(out["unit"]).strip()
        out["source"] = str(out.get("source") or "Engineering Reference Document").strip()
        if out.get("note") is not None:
            out["note"] = str(out["note"]).strip()
        return out


class ConnectionStream(BaseModel):
    stream_id: str = Field(default="Process Connection")
    direction: str | None = Field(
        default=None,
        description="Topological edge direction relative to this equipment (e.g. INLET, OUTLET, BYPASS, VENT, DRAIN, RELIEF, RECIRC, UTILITY)",
    )
    source_tag: str | None = Field(
        default=None,
        description="Canonical upstream equipment tag or boundary source node ID for Spanner Graph edge (e.g. P-12, F-33, RWST)",
    )
    target_tag: str | None = Field(
        default=None,
        description="Canonical downstream equipment tag or boundary target node ID for Spanner Graph edge (e.g. F-33, DM-8, WLD DR 218)",
    )
    line_size: str | None = Field(
        default=None,
        description="Printed pipe diameter or reducer/expander transition (e.g. 4\", 1\"x4\", 3/4\")",
    )
    inline_components: list[str] = Field(
        default_factory=list,
        description="Ordered inline valves, check valves, control valves, restriction orifices, or flow elements along this connection edge",
    )
    temperature: str | None = None
    pressure: str | None = None
    flow_rate: str | None = None
    description: str | None = None
    source: str = Field(default="Engineering Reference Document")

    @model_validator(mode="before")
    @classmethod
    def _normalize_connection_dict(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        raw_sid = (
            out.get("stream_id")
            or out.get("stream")
            or out.get("nozzle")
            or out.get("line_id")
            or out.get("id")
            or out.get("name")
        )
        direction = str(out.get("direction") or "").strip().upper() or None
        source_tag = str(out.get("source_tag") or out.get("from_tag") or out.get("from") or "").strip() or None
        target_tag = str(out.get("target_tag") or out.get("to_tag") or out.get("to") or "").strip() or None
        line_size = str(out.get("line_size") or out.get("size") or "").strip() or None
        desc = str(out.get("description") or "").strip() or None

        if not raw_sid or not str(raw_sid).strip():
            size_prefix = f"{line_size} " if line_size and line_size not in ("—", "-") else ""
            if direction == "INLET" and source_tag:
                raw_sid = f"{size_prefix}Inlet from {source_tag}".strip()
            elif direction and target_tag and direction != "INLET":
                raw_sid = f"{size_prefix}{direction.title()} to {target_tag}".strip()
            elif source_tag and target_tag:
                dir_prefix = f"{direction}: " if direction else ""
                raw_sid = f"{dir_prefix}{source_tag} -> {target_tag}".strip()
            elif direction and desc:
                raw_sid = f"{direction}: {desc[:48]}".strip()
            elif desc:
                raw_sid = desc[:60]
            else:
                raw_sid = "Process Connection"

        out["stream_id"] = str(raw_sid).strip() or "Process Connection"
        out["direction"] = direction
        out["source_tag"] = source_tag
        out["target_tag"] = target_tag
        out["line_size"] = line_size
        out["description"] = desc
        for k in ("temperature", "pressure", "flow_rate"):
            if out.get(k) is not None:
                out[k] = str(out[k]).strip()
        out["source"] = str(out.get("source") or "Engineering Reference Document").strip()
        return out

    @field_validator("inline_components", mode="before")
    @classmethod
    def _normalize_inline_components(cls, val: Any) -> list[str]:
        if val is None:
            return []
        if isinstance(val, str):
            cleaned = val.strip()
            if not cleaned or cleaned in ("—", "-", "None", "N/A"):
                return []
            return [
                tok.strip()
                for tok in re.split(r"[,;]+|\s*->\s*|\s*→\s*", cleaned)
                if tok.strip() and tok.strip() not in ("—", "-")
            ]
        if isinstance(val, (list, tuple, set)):
            out: list[str] = []
            for item in val:
                s = str(item).strip()
                if s and s not in ("—", "-", "None"):
                    out.append(s)
            return out
        return [str(val).strip()]


class InstrumentLoop(BaseModel):
    tag: str = Field(
        default="INST", description="Unique instrument loop tag from P&ID or datasheet"
    )
    service: str = Field(
        default="Process Instrumentation",
        description="Process service or functional description",
    )
    instrument_type: str = Field(
        default="Process Instrument",
        description="Physical or functional instrument type (e.g. RTD, DP Transmitter, PSV)",
    )
    location: str | None = Field(
        default=None, description="Physical installation location or nozzle tap point"
    )
    setpoint_or_range: str | None = Field(
        default=None, description="Calibrated range or operational setpoint"
    )
    interlock_or_alarm: str | None = Field(
        default=None, description="Associated DCS alarm or SIS/ESD trip action"
    )
    source: str = Field(
        default="Engineering Reference Document",
        description="Engineering drawing or datasheet citation",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_instrument_dict(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        tag = out.get("tag") or out.get("instrument_tag") or out.get("loop_id") or out.get("id") or "INST"
        out["tag"] = str(tag).strip() or "INST"
        out["service"] = str(
            out.get("service") or out.get("description") or out.get("function") or "Process Instrumentation"
        ).strip()
        out["instrument_type"] = str(
            out.get("instrument_type") or out.get("type") or "Process Instrument"
        ).strip()
        for k in ("location", "setpoint_or_range", "interlock_or_alarm"):
            if out.get(k) is not None:
                out[k] = str(out[k]).strip()
        out["source"] = str(out.get("source") or "Engineering Reference Document").strip()
        return out


class MOCChangeRecord(BaseModel):
    moc_id: str = Field(..., description="MOC, ECN, or FCR identifier or filename")
    date: str = Field(default="", description="Approval or implementation date (YYYY-MM-DD)")
    change_type: str = Field(
        default="PARAMETER_OVERRIDE",
        description="PARAMETER_OVERRIDE, TOPOLOGY_ REROUTE, INSTRUMENT_CHANGE, DECOMMISSION, or REVISION_UPDATE",
    )
    summary: str = Field(..., description="Engineering description of the authorized modification")
    affected_items: list[str] = Field(
        default_factory=list,
        description="List of modified parameters, stream IDs, or instrument loop tags",
    )
    pending_redraft_drawings: list[str] = Field(
        default_factory=list,
        description="Base drawings/datasheets overridden by this MOC that are awaiting master redraft",
    )


class EquipmentEntity(BaseModel):
    tag: str = Field(..., description="Unique equipment plant identifier tag")
    name: str = Field(..., description="Descriptive equipment title")
    equipment_class: str = Field(
        ..., description="Equipment class (e.g. Column, Heat Exchanger, Pump, Vessel)"
    )
    unit: str = Field(..., description="Plant unit or process section code")
    aliases: list[str] = Field(
        default_factory=list,
        description="Prior equipment tags, superseded train identifiers, or alternate tag aliases",
    )
    tags: list[str] = Field(default_factory=list)
    function_summary: str
    design_data: list[EngineeringParameter] = Field(default_factory=list)
    operating_conditions: list[EngineeringParameter] = Field(default_factory=list)
    instruments: list[InstrumentLoop] = Field(
        default_factory=list,
        description="P&ID instrumentation, transmitters, and control/safety loops associated with this equipment",
    )
    connections: list[ConnectionStream] = Field(default_factory=list)
    hazards: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    superseded_sources: list[str] = Field(
        default_factory=list,
        description="Document filenames or revision citations retired/superseded by newer revisions or MOCs",
    )
    removed_instruments: list[str] = Field(
        default_factory=list,
        description="Instrument loop tags decommissioned or removed by a newer drawing revision or MOC",
    )
    removed_connections: list[str] = Field(
        default_factory=list,
        description="Stream or piping line IDs decommissioned or removed by a newer drawing revision or MOC",
    )
    moc_history: list[MOCChangeRecord] = Field(
        default_factory=list,
        description="Chronological log of Management of Change (MOC) and Engineering Change Notices (ECN)",
    )



class HazardEntity(BaseModel):
    material_or_scenario: str
    hazard_type: str  # Thermal Runaway, Toxicity, Flammability, Overpressure
    critical_limits: list[str] = Field(default_factory=list)
    safeguards: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class HazopNode(BaseModel):
    node_id: str
    node_name: str
    unit: str
    deviations: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class InstrumentEntity(BaseModel):
    tag: str
    service: str
    unit: str
    instrument_type: str
    normal_value: str | None = None
    alarm_high: str | None = None
    alarm_low: str | None = None
    interlock_action: str | None = None
    sources: list[str] = Field(default_factory=list)
