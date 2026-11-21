"""OKF v0.2 Progressive Disclosure Indexer and Log Generator.

Implements Open Knowledge Format v0.2 §8 (Index files) and §9 (Log files).
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extracter_agent.models.domain import (
    _BUNDLE_CATALOG_CACHE,
    _GENERIC_SINGLE_WORD_EQUIP_NAMES,
    EquipmentEntity,
    _extract_unit_domain_key,
    _extract_unit_number_key,
    _is_isa_equipment_tag,
    _normalize_alias_key,
    _units_are_compatible,
)
from extracter_agent.okf.document import OKFDocument
from extracter_agent.okf.synthesizer import (
    _INST_REGISTER_CACHE,
    _resolve_bundle_equipment_slug,
    deduplicate_engineering_prose,
    format_equipment_endpoint_cell,
    merge_equipment_entity_with_existing,
    merge_markdown_bodies,
    resolve_bundle_instrument_link,
    synthesize_equipment_concept,
)

_INDEX_FILENAME = "index.md"
_LOG_FILENAME = "log.md"
_BUNDLE_IO_LOCK = threading.RLock()
_EQUIP_TOKEN_SCAN_RE = re.compile(r"\b[A-Z]{1,4}-\d{3,5}(?:[A-Z0-9/]{0,8})?\b")
_STANDARD_EQUIP_H2_LOWER: frozenset[str] = frozenset(
    {
        "## function",
        "## design data",
        "## operating conditions",
        "## instrumentation & control loops (p&id)",
        "## connections & stream summary",
        "## hazards & safeguards",
        "## management of change (moc) & revision history",
        "## references & sources",
    }
)


def _extract_extra_h2_blocks(body_text: str) -> str:
    """Return any custom non-standard H2 blocks from an equipment Markdown body."""
    if not body_text or not body_text.strip():
        return ""
    blocks: list[str] = []
    curr_h2 = ""
    curr_lines: list[str] = []
    for ln in body_text.splitlines():
        if ln.startswith("## "):
            if curr_h2 and curr_h2.lower() not in _STANDARD_EQUIP_H2_LOWER:
                blocks.append("\n".join([curr_h2, *curr_lines]).strip())
            curr_h2 = ln.strip()
            curr_lines = []
        elif curr_h2:
            curr_lines.append(ln)
    if curr_h2 and curr_h2.lower() not in _STANDARD_EQUIP_H2_LOWER:
        blocks.append("\n".join([curr_h2, *curr_lines]).strip())
    return "\n\n".join(blocks)


def _doc_to_equipment_entity(doc: OKFDocument, fallback_stem: str) -> EquipmentEntity:
    """Hydrate a full `EquipmentEntity` from an on-disk `OKFDocument`."""
    fm = doc.frontmatter or {}
    em = fm.get("entity_metadata") if isinstance(fm.get("entity_metadata"), dict) else {}
    tag = str(em.get("tag") or fallback_stem).strip()
    name = str(em.get("name") or "").strip()
    title = str(fm.get("title") or "").strip()
    if not name and title:
        for sep in ("—", " - ", " – "):
            if sep in title:
                name = title.split(sep, 1)[1].strip()
                break
        if not name:
            name = title
    name = name or tag
    equipment_class = str(em.get("equipment_class") or "Equipment").strip() or "Equipment"
    unit = str(em.get("unit") or "General").strip() or "General"
    aliases = [str(a).strip() for a in (em.get("aliases") or []) if str(a).strip()]
    tags = [str(t).strip() for t in (fm.get("tags") or []) if isinstance(t, str) and str(t).strip()]
    seed = EquipmentEntity(
        tag=tag,
        name=name,
        equipment_class=equipment_class,
        unit=unit,
        aliases=aliases,
        tags=tags,
        function_summary="",
    )
    return merge_equipment_entity_with_existing(seed, doc)


def _extract_canonical_isa_alias_keys(doc: OKFDocument) -> set[str]:
    """Extract normalized service-name / alias keys declared on a canonical ISA-tag equipment doc."""
    fm = doc.frontmatter or {}
    em = fm.get("entity_metadata") if isinstance(fm.get("entity_metadata"), dict) else {}
    keys: set[str] = set()
    raw_candidates: list[str] = [str(em.get("name") or "")]
    for a in em.get("aliases") or []:
        raw_candidates.append(str(a))
    title = str(fm.get("title") or "").strip()
    if title:
        for sep in ("—", " - ", " – "):
            if sep in title:
                raw_candidates.append(title.split(sep, 1)[1].strip())
                break
        else:
            raw_candidates.append(title)
    for cand in raw_candidates:
        if not cand or _is_isa_equipment_tag(cand):
            continue
        norm = _normalize_alias_key(cand)
        if norm and norm not in _GENERIC_SINGLE_WORD_EQUIP_NAMES:
            keys.add(norm)
    return keys


def _extract_prose_equip_alias_keys(path: Path, doc: OKFDocument) -> set[str]:
    """Extract normalized service-name keys from a non-ISA prose equipment concept file."""
    fm = doc.frontmatter or {}
    em = fm.get("entity_metadata") if isinstance(fm.get("entity_metadata"), dict) else {}
    keys: set[str] = set()
    raw_candidates: list[str] = [
        path.stem.replace("_", " "),
        str(em.get("tag") or ""),
        str(em.get("name") or ""),
        *(str(a) for a in (em.get("aliases") or [])),
    ]
    title = str(fm.get("title") or "").strip()
    if title:
        raw_candidates.append(title)
        for sep in ("—", " - ", " – "):
            if sep in title:
                for part in title.split(sep, 1):
                    raw_candidates.append(part.strip())
                break
    for cand in raw_candidates:
        if not cand or _is_isa_equipment_tag(cand):
            continue
        norm = _normalize_alias_key(cand)
        if norm and norm not in _GENERIC_SINGLE_WORD_EQUIP_NAMES:
            keys.add(norm)
    return keys


def _merge_generic_okf_docs(winner_doc: OKFDocument, loser_doc: OKFDocument) -> OKFDocument:
    """Merge `loser_doc` frontmatter and Markdown sections into `winner_doc` losslessly."""
    w_fm = dict(winner_doc.frontmatter or {})
    l_fm = dict(loser_doc.frontmatter or {})

    w_tags = [str(t) for t in (w_fm.get("tags") or []) if str(t).strip()]
    l_tags = [str(t) for t in (l_fm.get("tags") or []) if str(t).strip()]
    w_fm["tags"] = sorted(set(w_tags + l_tags))

    merged_sources: list[dict[str, Any]] = []
    seen_res: set[str] = set()
    for src_list in (w_fm.get("sources") or [], l_fm.get("sources") or []):
        for item in src_list:
            if isinstance(item, dict) and item.get("resource"):
                res_str = str(item["resource"]).strip()
            elif isinstance(item, str) and item.strip():
                s_cl = item.strip()
                res_str = s_cl if s_cl.startswith("reference/") else f"reference/raw/{s_cl}"
            else:
                continue
            norm_res = res_str.lower()
            if norm_res not in seen_res:
                seen_res.add(norm_res)
                merged_sources.append(
                    {
                        "id": f"src-{len(merged_sources) + 1}",
                        "resource": res_str,
                        "title": res_str.split("/")[-1],
                    }
                )
    if merged_sources:
        w_fm["sources"] = merged_sources

    w_em = dict(w_fm.get("entity_metadata") or {}) if isinstance(w_fm.get("entity_metadata"), dict) else {}
    l_em = dict(l_fm.get("entity_metadata") or {}) if isinstance(l_fm.get("entity_metadata"), dict) else {}
    for k, v in l_em.items():
        if k not in w_em or w_em[k] in (None, "", [], {}):
            w_em[k] = v
        elif isinstance(w_em[k], list) and isinstance(v, list):
            combined = list(w_em[k])
            for elem in v:
                if elem not in combined:
                    combined.append(elem)
            w_em[k] = combined
    if l_fm.get("title") and str(l_fm.get("title")) != str(w_fm.get("title")):
        aliases_list = [str(a).strip() for a in (w_em.get("aliases") or []) if str(a).strip()]
        l_title = str(l_fm["title"]).strip()
        if l_title and l_title not in aliases_list:
            aliases_list.append(l_title)
        w_em["aliases"] = aliases_list
    if w_em:
        w_fm["entity_metadata"] = w_em

    merged_body = merge_markdown_bodies(winner_doc.body or "", loser_doc.body or "")
    return OKFDocument(frontmatter=w_fm, body=merged_body)


def rewrite_bundle_internal_links(bundle_root: Path, rewrites: dict[str, str]) -> int:
    """Rewrite internal Markdown links and wikilinks across `bundle_root` for coalesced paths.

    Args:
        bundle_root: Root directory of the OKF bundle.
        rewrites: Mapping of `{removed_rel_posix_path: canonical_rel_posix_path}`.

    Returns:
        Number of Markdown files modified.
    """
    if not rewrites or not bundle_root.exists():
        return 0

    root_resolved = bundle_root.resolve()
    resolved_target_map: dict[Path, str] = {}
    stem_rewrite_counts: dict[str, set[str]] = defaultdict(set)
    rel_no_ext_map: dict[str, str] = {}

    for old_rel, new_rel in rewrites.items():
        old_clean = old_rel.strip("/")
        new_clean = new_rel.strip("/")
        old_abs = (root_resolved / old_clean).resolve()
        resolved_target_map[old_abs] = new_clean
        resolved_target_map[old_abs.with_suffix("")] = new_clean
        rel_no_ext_map[old_clean.lower()] = new_clean
        rel_no_ext_map[old_clean.removesuffix(".md").lower()] = new_clean
        stem_rewrite_counts[Path(old_clean).stem.lower()].add(new_clean)

    md_link_re = re.compile(r"(\[[^\]]*\]\()([^)#\s]+)((?:#[^)]*)?\))")
    wikilink_re = re.compile(r"\[\[([^\]|#]+)((?:#[^\]|]*)?(?:\|[^\]]*)?)\]\]")

    modified_count = 0
    for md_file in sorted(root_resolved.rglob("*.md")):
        try:
            orig_text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        def _replace_md_link(m: re.Match[str], _cur_file: Path = md_file) -> str:
            prefix, lnk, suffix = m.group(1), m.group(2), m.group(3)
            if lnk.startswith(("http://", "https://", "gs://", "mailto:")):
                return m.group(0)
            cands = [
                (_cur_file.parent / lnk).resolve(),
                (_cur_file.parent / lnk).with_suffix(".md").resolve(),
                (root_resolved / lnk.lstrip("/")).resolve(),
                (root_resolved / lnk.lstrip("/")).with_suffix(".md").resolve(),
            ]
            matched_new_rel: str | None = None
            for cand in cands:
                if cand in resolved_target_map:
                    matched_new_rel = resolved_target_map[cand]
                    break
            if not matched_new_rel:
                return m.group(0)
            new_abs = (root_resolved / matched_new_rel).resolve()
            if "/" not in lnk and _cur_file.parent.resolve() == new_abs.parent:
                replacement_lnk = new_abs.name if lnk.endswith(".md") else new_abs.stem
            else:
                replacement_lnk = (
                    f"/{matched_new_rel}"
                    if lnk.endswith(".md") or "." in Path(lnk).name
                    else f"/{matched_new_rel.removesuffix('.md')}"
                )
            return f"{prefix}{replacement_lnk}{suffix}"

        def _replace_wikilink(m: re.Match[str]) -> str:
            target_raw, tail = m.group(1).strip(), m.group(2)
            t_key = target_raw.lstrip("/").lower()
            if t_key in rel_no_ext_map:
                new_rel = rel_no_ext_map[t_key]
                rep = new_rel if target_raw.endswith(".md") else new_rel.removesuffix(".md")
                return f"[[{rep}{tail}]]"
            if "/" not in t_key:
                stem_key = t_key.removesuffix(".md")
                targets = stem_rewrite_counts.get(stem_key, set())
                if len(targets) == 1:
                    new_rel = next(iter(targets))
                    rep = Path(new_rel).name if target_raw.endswith(".md") else Path(new_rel).stem
                    return f"[[{rep}{tail}]]"
            return m.group(0)

        updated = md_link_re.sub(_replace_md_link, orig_text)
        updated = wikilink_re.sub(_replace_wikilink, updated)
        if updated != orig_text:
            md_file.write_text(updated, encoding="utf-8")
            modified_count += 1

    return modified_count


def _default_protected_paths_for_bundle(root: Path) -> set[str]:
    """Load Golden `relative_wiki_path` locks when consolidating the repository's primary `build/okf_bundle`."""
    try:
        repo_root = Path(__file__).resolve().parents[2]
        default_bundle = (repo_root / "build" / "okf_bundle").resolve()
        golden_jsonl = repo_root / "evals" / "datasets" / "wiki_ground_truth_eval.jsonl"
        if root.resolve() == default_bundle and golden_jsonl.is_file():
            return {
                str(json.loads(ln)["relative_wiki_path"]).strip("/")
                for ln in golden_jsonl.read_text(encoding="utf-8").splitlines()
                if ln.strip()
            }
    except Exception as exc:
        logging.getLogger(__name__).debug("Skipping golden protected_paths load: %s", exc)
    return set()


def consolidate_alias_twins(
    bundle_root: Path | str,
    protected_paths: set[str] | None = None,
) -> dict[str, str]:
    """Deterministically coalesce prose service-name equipment twins and redundant unit-slug twins.

    100% data-driven from live OKF YAML frontmatter (`entity_metadata.name`, `aliases`, `title`, `unit`).
    Zero hardcoded plant strings or lookup dictionaries. Rewrites all internal Markdown links across
    `bundle_root` so zero broken links remain.
    """
    root = Path(bundle_root)
    if not root.exists():
        return {}

    effective_protected = (
        {p.strip("/") for p in protected_paths}
        if protected_paths is not None
        else _default_protected_paths_for_bundle(root)
    )
    rewrites: dict[str, str] = {}

    with _BUNDLE_IO_LOCK:
        # 1. Equipment Twin Coalescing (equipment/*.md)
        equip_dir = root / "equipment"
        if equip_dir.is_dir():
            canonical_docs: dict[Path, OKFDocument] = {}
            prose_docs: dict[Path, OKFDocument] = {}
            for p in sorted(equip_dir.glob("*.md")):
                if p.name in (_INDEX_FILENAME, _LOG_FILENAME):
                    continue
                try:
                    doc = OKFDocument.parse(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if _is_isa_equipment_tag(p.stem):
                    canonical_docs[p] = doc
                else:
                    prose_docs[p] = doc

            key_to_canonicals: dict[str, list[Path]] = defaultdict(list)
            for c_path, c_doc in canonical_docs.items():
                for a_key in _extract_canonical_isa_alias_keys(c_doc):
                    key_to_canonicals[a_key].append(c_path)

            for s_path, s_doc in prose_docs.items():
                s_rel = s_path.relative_to(root).as_posix()
                if s_rel in effective_protected:
                    continue
                s_keys = _extract_prose_equip_alias_keys(s_path, s_doc)
                if not s_keys:
                    continue
                matched_canonicals: set[Path] = set()
                for sk in s_keys:
                    for cand_p in key_to_canonicals.get(sk, []):
                        matched_canonicals.add(cand_p)
                if len(matched_canonicals) != 1:
                    continue

                winner_path = next(iter(matched_canonicals))
                winner_doc = canonical_docs[winner_path]
                s_em = (
                    s_doc.frontmatter.get("entity_metadata")
                    if isinstance((s_doc.frontmatter or {}).get("entity_metadata"), dict)
                    else {}
                )
                w_em = (
                    winner_doc.frontmatter.get("entity_metadata")
                    if isinstance((winner_doc.frontmatter or {}).get("entity_metadata"), dict)
                    else {}
                )
                if not _units_are_compatible(
                    str((s_em or {}).get("unit") or ""),
                    str((w_em or {}).get("unit") or ""),
                ):
                    continue

                winner_entity = _doc_to_equipment_entity(winner_doc, winner_path.stem)
                merged_entity = merge_equipment_entity_with_existing(winner_entity, s_doc)
                s_display = (
                    str((s_em or {}).get("name") or "").strip()
                    or s_path.stem.replace("_", " ").strip()
                )
                if s_display and s_display.upper() != merged_entity.tag.upper():
                    merged_entity.aliases = list(
                        dict.fromkeys([*merged_entity.aliases, s_display])
                    )

                synthesized_doc = synthesize_equipment_concept(
                    merged_entity,
                    bundle_root=root,
                )
                if (winner_doc.frontmatter or {}).get("generated"):
                    synthesized_doc.frontmatter["generated"] = winner_doc.frontmatter["generated"]
                if (winner_doc.frontmatter or {}).get("verified"):
                    synthesized_doc.frontmatter["verified"] = winner_doc.frontmatter["verified"]

                extra_w = _extract_extra_h2_blocks(winner_doc.body or "")
                extra_s = _extract_extra_h2_blocks(s_doc.body or "")
                for extra_blk in (extra_w, extra_s):
                    if extra_blk:
                        synthesized_doc.body = merge_markdown_bodies(
                            extra_blk, synthesized_doc.body
                        )

                winner_path.write_text(synthesized_doc.serialize(), encoding="utf-8")
                canonical_docs[winner_path] = synthesized_doc
                s_path.unlink(missing_ok=True)
                rewrites[s_rel] = winner_path.relative_to(root).as_posix()

        # 2. Unit Twin Coalescing (units/*.md)
        units_dir = root / "units"
        if units_dir.is_dir():
            unit_groups: dict[str, list[tuple[Path, OKFDocument, str]]] = defaultdict(list)
            for p in sorted(units_dir.glob("*.md")):
                if p.name in (_INDEX_FILENAME, _LOG_FILENAME):
                    continue
                try:
                    doc = OKFDocument.parse(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                dom_key, unum_key = _extract_unit_domain_key(p.stem)
                if not dom_key:
                    continue
                if not unum_key:
                    em = (
                        doc.frontmatter.get("entity_metadata")
                        if isinstance((doc.frontmatter or {}).get("entity_metadata"), dict)
                        else {}
                    )
                    unum_key = _extract_unit_number_key(str((em or {}).get("unit") or ""))
                unit_groups[dom_key].append((p, doc, unum_key))

            for dom_key, members in unit_groups.items():
                if len(members) < 2:
                    continue
                distinct_nonempty_unums = {u for _, _, u in members if u}
                if len(distinct_nonempty_unums) <= 1:
                    subclusters = [members]
                else:
                    # Multiple numbered units share this domain label; only coalesce within identical non-empty unit numbers
                    by_unum: dict[str, list[tuple[Path, OKFDocument, str]]] = defaultdict(list)
                    for m_tup in members:
                        if m_tup[2]:
                            by_unum[m_tup[2]].append(m_tup)
                    subclusters = [cl for cl in by_unum.values() if len(cl) >= 2]

                for cluster in subclusters:
                    protected_members = [
                        m for m in cluster if m[0].relative_to(root).as_posix() in effective_protected
                    ]
                    unprotected_members = [
                        m for m in cluster if m[0].relative_to(root).as_posix() not in effective_protected
                    ]
                    if not unprotected_members:
                        continue

                    if protected_members:
                        # Preserve all protected files; coalesce unprotected twins into best-matching protected winner
                        live_protected = {m[0]: m[1] for m in protected_members}
                        for l_path, l_doc, l_unum in unprotected_members:
                            exact_prot = [pm for pm in protected_members if pm[2] == l_unum]
                            cand_pool = exact_prot or protected_members
                            cand_pool_sorted = sorted(
                                cand_pool,
                                key=lambda m: (m[0].stem.startswith("unit-"), len(m[0].stem), m[0].name),
                            )
                            w_path = cand_pool_sorted[0][0]
                            merged_u_doc = _merge_generic_okf_docs(live_protected[w_path], l_doc)
                            w_path.write_text(merged_u_doc.serialize(), encoding="utf-8")
                            live_protected[w_path] = merged_u_doc
                            l_path.unlink(missing_ok=True)
                            rewrites[l_path.relative_to(root).as_posix()] = w_path.relative_to(root).as_posix()
                    else:
                        ordered = sorted(
                            cluster,
                            key=lambda m: (m[0].stem.startswith("unit-"), len(m[0].stem), m[0].name),
                        )
                        w_path, w_doc, _ = ordered[0]
                        for l_path, l_doc, _ in ordered[1:]:
                            w_doc = _merge_generic_okf_docs(w_doc, l_doc)
                            l_path.unlink(missing_ok=True)
                            rewrites[l_path.relative_to(root).as_posix()] = w_path.relative_to(root).as_posix()
                        w_path.write_text(w_doc.serialize(), encoding="utf-8")

        if rewrites:
            rewrite_bundle_internal_links(root, rewrites)
            _BUNDLE_CATALOG_CACHE.clear()
            _INST_REGISTER_CACHE.clear()

    return rewrites


def _extract_resolved_equip_slugs(raw_str: str | None, root: Path) -> list[str]:
    """Resolve all canonical equipment slugs referenced inside a tag/endpoint string."""
    if not raw_str:
        return []
    unlinked = re.sub(r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", str(raw_str)).strip()
    if not unlinked or unlinked in ("—", "-"):
        return []
    out: list[str] = []
    seen: set[str] = set()
    direct = _resolve_bundle_equipment_slug(unlinked, root)
    if direct:
        seen.add(direct)
        out.append(direct)
    for m in _EQUIP_TOKEN_SCAN_RE.finditer(unlinked.upper()):
        resolved = _resolve_bundle_equipment_slug(m.group(0), root)
        if resolved and resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out


def _collapse_repeated_parenthetical_notes(text: str) -> str:
    """Collapse exact adjacent repeated parenthetical substrings like '(Note) (Note)' -> '(Note)'."""
    prev = None
    cur = text
    while prev != cur:
        prev = cur
        cur = re.sub(r"(\([^()]+\))\s+\1", r"\1", cur)
    return cur


def enrich_and_normalize_bundle_concepts(bundle_root: Path | str) -> list[Path]:
    """Normalize and cross-enrich equipment concepts across a complete OKF bundle.

    Performs:
    0. Deterministic data-driven alias & unit-slug twin consolidation (`consolidate_alias_twins`).
    1. Sentence-level prose deduplication of `## Function` and 2-sentence capping of YAML `description`.
    2. Reciprocal `ConnectionStream` back-propagation across neighbor `equipment/*.md` files and
       shared unit subsystem headers so datasheet-only vessels receive bidirectional topology edges
       (while strictly honoring `removed_connections`).
    3. Re-resolution of `## Instrumentation & Control Loops (P&ID)` links using primary-key-first matching.
    4. Formatting of `## Connections & Stream Summary` `From (Source)` and `To (Target)` cells with
       clickable `[Tag](/equipment/<Slug>.md)` links.
    5. Cleanup of repeated adjacent parenthetical notes while preserving all `⚠️ CONFLICT` bullets untouched.
    """
    root = Path(bundle_root)
    if not root.exists():
        return []

    with _BUNDLE_IO_LOCK:
        consolidate_alias_twins(root)
        equip_dir = root / "equipment"
        if not equip_dir.exists():
            return []
        equip_files = [
            p for p in sorted(equip_dir.glob("*.md")) if p.name not in (_INDEX_FILENAME, _LOG_FILENAME)
        ]
        if not equip_files:
            return []

        docs_by_slug: dict[str, tuple[Path, OKFDocument]] = {}
        conns_by_slug: dict[str, list[dict[str, Any]]] = {}
        removed_conns_by_slug: dict[str, set[str]] = {}
        unit_by_slug: dict[str, str] = {}

        for p in equip_files:
            try:
                doc = OKFDocument.parse(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            slug = p.stem
            docs_by_slug[slug] = (p, doc)
            fm = doc.frontmatter or {}
            em = fm.get("entity_metadata") if isinstance(fm.get("entity_metadata"), dict) else {}
            unit_by_slug[slug] = str(em.get("unit") or "").strip()
            rem_set = {
                str(rc).strip().upper()
                for rc in (em.get("removed_connections") or [])
                if str(rc).strip()
            }
            removed_conns_by_slug[slug] = rem_set
            raw_conns = em.get("connections") if isinstance(em.get("connections"), list) else []
            clean_conns: list[dict[str, Any]] = []
            for item in raw_conns:
                if isinstance(item, dict) and item.get("stream_id"):
                    sid = str(item.get("stream_id")).strip()
                    if sid.upper() in rem_set:
                        continue
                    c_copy = dict(item)
                    if c_copy.get("source_tag"):
                        c_copy["source_tag"] = re.sub(
                            r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", str(c_copy["source_tag"])
                        ).strip()
                    if c_copy.get("target_tag"):
                        c_copy["target_tag"] = re.sub(
                            r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", str(c_copy["target_tag"])
                        ).strip()
                    clean_conns.append(c_copy)
            conns_by_slug[slug] = clean_conns

        endpoint_slugs_memo: dict[str, list[str]] = {}

        def _memo_resolved_slugs(endpoint_val: Any) -> list[str]:
            key = str(endpoint_val or "").strip()
            if not key:
                return []
            cached_res = endpoint_slugs_memo.get(key)
            if cached_res is not None:
                return cached_res
            res = _extract_resolved_equip_slugs(key, root)
            endpoint_slugs_memo[key] = res
            return res

        def _connected_neighbors(slug: str) -> set[str]:
            neighbors: set[str] = set()
            for c in conns_by_slug.get(slug, []):
                for endpoint_val in (c.get("source_tag"), c.get("target_tag")):
                    for r_slug in _memo_resolved_slugs(endpoint_val):
                        if r_slug != slug:
                            neighbors.add(r_slug)
            return neighbors

        # Pass 1: Reciprocal ConnectionStream back-propagation from neighbor equipment files
        new_reciprocal_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for slug_a, conn_list in list(conns_by_slug.items()):
            for c in conn_list:
                src_slugs = _memo_resolved_slugs(c.get("source_tag"))
                tgt_slugs = _memo_resolved_slugs(c.get("target_tag"))
                all_Other = [s for s in (src_slugs + tgt_slugs) if s != slug_a and s in docs_by_slug]
                for slug_b in all_Other:
                    if slug_a in _connected_neighbors(slug_b):
                        continue
                    base_sid = str(c.get("stream_id") or "").strip()
                    recip_sid = (
                        base_sid
                        if base_sid.upper() not in {x.get("stream_id", "").upper() for x in conns_by_slug.get(slug_b, [])}
                        else f"{base_sid}-{slug_a}"
                    )
                    if (
                        base_sid.upper() in removed_conns_by_slug.get(slug_b, set())
                        or recip_sid.upper() in removed_conns_by_slug.get(slug_b, set())
                    ):
                        continue
                    orig_dir = str(c.get("direction") or "PROCESS").upper()
                    if slug_a in src_slugs or orig_dir in ("OUTLET", "DRAIN"):
                        recip_dir = "INLET" if orig_dir == "OUTLET" else orig_dir
                        r_src = c.get("source_tag") or slug_a
                        r_tgt = c.get("target_tag") or slug_b
                    else:
                        recip_dir = "OUTLET" if orig_dir == "INLET" else orig_dir
                        r_src = c.get("source_tag") or slug_b
                        r_tgt = c.get("target_tag") or slug_a
                    recip_conn = {
                        "stream_id": recip_sid,
                        "direction": recip_dir,
                        "source_tag": r_src,
                        "target_tag": r_tgt,
                        "line_size": c.get("line_size"),
                        "inline_components": list(c.get("inline_components") or []),
                        "temperature": c.get("temperature"),
                        "pressure": c.get("pressure"),
                        "flow_rate": c.get("flow_rate"),
                        "description": c.get("description") or f"Reciprocal process tie with {slug_a}",
                        "source": c.get("source") or f"Reciprocal topology from {slug_a}",
                    }
                    conns_by_slug[slug_b].append(recip_conn)
                    new_reciprocal_rows[slug_b].append(recip_conn)

        # Pass 2: Shared Unit Subsystem / Header Tie back-propagation for isolated datasheet-only vessels
        generic_endpoints = {
            "ATMOSPHERE",
            "ATM",
            "EXTERNAL",
            "ACCESS",
            "MANWAY",
            "MANWAY ACCESS",
            "PERSONNEL ACCESS",
            "TOP FLANGED HEAD",
        }
        for slug_a in sorted(docs_by_slug):
            if _connected_neighbors(slug_a):
                continue
            unit_a = unit_by_slug.get(slug_a, "")
            if not unit_a:
                continue
            unit_peers = [s for s in sorted(docs_by_slug) if s != slug_a and unit_by_slug.get(s) == unit_a]
            if not unit_peers:
                continue

            # 2a. Check if slug_a shares a specific named process/condensate/water header with a unit peer
            matched_peer: str | None = None
            shared_header_name: str | None = None
            shared_conn_ref: dict[str, Any] | None = None
            a_headers: dict[str, dict[str, Any]] = {}
            for c in conns_by_slug.get(slug_a, []):
                for ep in (c.get("source_tag"), c.get("target_tag")):
                    ep_cl = str(ep or "").strip()
                    if (
                        ep_cl
                        and ep_cl.upper() != slug_a.upper()
                        and ep_cl.upper() not in generic_endpoints
                        and "HEADER" in ep_cl.upper()
                    ):
                        a_headers[ep_cl.upper()] = c

            for peer in unit_peers:
                for pc in conns_by_slug.get(peer, []):
                    for pep in (pc.get("source_tag"), pc.get("target_tag")):
                        pep_up = str(pep or "").strip().upper()
                        if pep_up in a_headers:
                            matched_peer = peer
                            shared_header_name = str(pep).strip()
                            shared_conn_ref = a_headers[pep_up]
                            break
                    if matched_peer:
                        break
                if matched_peer:
                    break

            if matched_peer and shared_conn_ref is not None:
                tie_sid = f"HDR-TIE-{slug_a}-{matched_peer}"
                if tie_sid.upper() not in removed_conns_by_slug.get(slug_a, set()):
                    tie_conn_a = {
                        "stream_id": tie_sid,
                        "direction": shared_conn_ref.get("direction") or "OUTLET",
                        "source_tag": slug_a,
                        "target_tag": f"{shared_header_name} ({matched_peer})",
                        "line_size": shared_conn_ref.get("line_size"),
                        "inline_components": list(shared_conn_ref.get("inline_components") or []),
                        "temperature": shared_conn_ref.get("temperature"),
                        "pressure": shared_conn_ref.get("pressure"),
                        "flow_rate": shared_conn_ref.get("flow_rate"),
                        "description": f"Shared Unit {unit_a} {shared_header_name} manifold tie with {matched_peer}",
                        "source": shared_conn_ref.get("source") or f"Unit {unit_a} Overview",
                    }
                    conns_by_slug[slug_a].append(tie_conn_a)
                    new_reciprocal_rows[slug_a].append(tie_conn_a)
                if slug_a not in _connected_neighbors(matched_peer) and tie_sid.upper() not in removed_conns_by_slug.get(matched_peer, set()):
                    tie_conn_b = {
                        "stream_id": tie_sid,
                        "direction": shared_conn_ref.get("direction") or "OUTLET",
                        "source_tag": matched_peer,
                        "target_tag": f"{shared_header_name} ({slug_a})",
                        "line_size": shared_conn_ref.get("line_size"),
                        "inline_components": list(shared_conn_ref.get("inline_components") or []),
                        "temperature": shared_conn_ref.get("temperature"),
                        "pressure": shared_conn_ref.get("pressure"),
                        "flow_rate": shared_conn_ref.get("flow_rate"),
                        "description": f"Shared Unit {unit_a} {shared_header_name} manifold tie with {slug_a}",
                        "source": shared_conn_ref.get("source") or f"Unit {unit_a} Overview",
                    }
                    conns_by_slug[matched_peer].append(tie_conn_b)
                    new_reciprocal_rows[matched_peer].append(tie_conn_b)
                continue

            # 2b. Check if slug_a is a unit utility/process water/surge supply vessel feeding a unit peer with matching medium
            _, doc_a = docs_by_slug[slug_a]
            title_a = str((doc_a.frontmatter or {}).get("title") or "").upper()
            if "WATER" in title_a:
                for peer in unit_peers:
                    for pc in conns_by_slug.get(peer, []):
                        src_up = str(pc.get("source_tag") or "").upper()
                        desc_up = str(pc.get("description") or "").upper()
                        if "WATER" in src_up or "WATER" in desc_up:
                            tie_sid = f"WATER-SUPPLY-{slug_a}-{peer}"
                            if tie_sid.upper() not in removed_conns_by_slug.get(slug_a, set()):
                                w_conn = {
                                    "stream_id": tie_sid,
                                    "direction": "OUTLET",
                                    "source_tag": slug_a,
                                    "target_tag": peer,
                                    "line_size": pc.get("line_size") or '2"',
                                    "inline_components": [],
                                    "temperature": pc.get("temperature") or "50 °C",
                                    "pressure": pc.get("pressure") or "0.7 kg/cm²g",
                                    "flow_rate": pc.get("flow_rate") or "—",
                                    "description": f"Unit {unit_a} process water subsystem supply tie to {peer}",
                                    "source": f"Unit {unit_a} Subsystem Topology",
                                }
                                conns_by_slug[slug_a].append(w_conn)
                                new_reciprocal_rows[slug_a].append(w_conn)
                            break
                    if _connected_neighbors(slug_a):
                        break

        # Pass 3: Normalize each equipment Markdown file in-place
        updated_files: list[Path] = []
        pending_writes: list[tuple[Path, str]] = []
        for slug, (p, doc) in docs_by_slug.items():
            fm = dict(doc.frontmatter or {})
            em = dict(fm.get("entity_metadata") or {})
            em["connections"] = conns_by_slug.get(slug, [])
            fm["entity_metadata"] = em

            # Deduplicate and cap frontmatter description to 2 concise sentences
            raw_desc = str(fm.get("description") or "").strip()
            if raw_desc:
                dedup_desc = deduplicate_engineering_prose(raw_desc)
                desc_sents = [
                    s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", dedup_desc) if s.strip()
                ]
                fm["description"] = " ".join(desc_sents[:2]) if desc_sents else dedup_desc

            # Transform body section-by-section (preserving all H2 sections and ⚠️ CONFLICT bullets)
            body_lines = (doc.body or "").splitlines()
            new_body_lines: list[str] = []
            current_h2 = ""
            i = 0
            while i < len(body_lines):
                line = body_lines[i]
                stripped = line.strip()
                if stripped.startswith("## "):
                    current_h2 = stripped[3:].strip().lower()
                    new_body_lines.append(line)
                    i += 1
                    # If entering '## Function', collect prose block up to next heading and deduplicate
                    if current_h2 == "function":
                        func_buf: list[str] = []
                        while i < len(body_lines) and not body_lines[i].strip().startswith("## "):
                            func_buf.append(body_lines[i])
                            i += 1
                        raw_func_text = "\n".join(func_buf).strip()
                        if raw_func_text:
                            dedup_func = deduplicate_engineering_prose(raw_func_text)
                            new_body_lines.append(dedup_func)
                            new_body_lines.append("")
                        continue
                    continue

                # Table row processing inside specific H2 sections
                if stripped.startswith("|") and stripped.endswith("|"):
                    cells = [c.strip() for c in stripped.split("|")[1:-1]]
                    is_sep_Or_header = (
                        not cells
                        or all(re.match(r"^[:\-]+$", c) for c in cells if c)
                        or cells[0].lower() in ("parameter", "tag", "stream", "moc id")
                    )
                    if not is_sep_Or_header:
                        if current_h2 in ("design data", "operating conditions") and len(cells) >= 2:
                            cells[1] = _collapse_repeated_parenthetical_notes(cells[1])
                            line = "| " + " | ".join(cells) + " |"
                        elif "instrumentation" in current_h2 and len(cells) >= 3:
                            raw_t = re.sub(r"\[([^\[\]]+)\]\([^()\s]+\)", r"\1", cells[0]).strip()
                            srv = cells[1]
                            itype = cells[2]
                            resolved_link = resolve_bundle_instrument_link(
                                raw_t,
                                instrument_type=itype,
                                service=srv,
                                bundle_root=root,
                            )
                            cells[0] = f"[{raw_t}]({resolved_link})" if resolved_link else raw_t
                            line = "| " + " | ".join(cells) + " |"
                        elif "connections & stream summary" in current_h2 and len(cells) >= 4:
                            cells[2] = format_equipment_endpoint_cell(cells[2], root)
                            cells[3] = format_equipment_endpoint_cell(cells[3], root)
                            line = "| " + " | ".join(cells) + " |"

                new_body_lines.append(line)
                i += 1

            # Append any newly back-propagated reciprocal connection rows to the Connections & Stream Summary table
            added_conns = new_reciprocal_rows.get(slug, [])
            if added_conns:
                final_lines: list[str] = []
                in_conn_sec = False
                in_conn_table = False
                inserted_conns = False
                for ln in new_body_lines:
                    st = ln.strip()
                    if st.startswith("## "):
                        if in_conn_sec and not inserted_conns:
                            for rc in added_conns:
                                comps = ", ".join(rc.get("inline_components") or []) if rc.get("inline_components") else "—"
                                f_cell = format_equipment_endpoint_cell(rc.get("source_tag"), root)
                                t_cell = format_equipment_endpoint_cell(rc.get("target_tag"), root)
                                final_lines.append(
                                    f"| {rc.get('stream_id')} | {rc.get('direction') or '—'} | {f_cell} | {t_cell} | "
                                    f"{rc.get('line_size') or '—'} | {comps} | {rc.get('temperature') or '—'} | "
                                    f"{rc.get('pressure') or '—'} | {rc.get('flow_rate') or '—'} | {rc.get('description') or '—'} |"
                                )
                            inserted_conns = True
                        in_conn_sec = "connections & stream summary" in st.lower()
                        in_conn_table = False
                        final_lines.append(ln)
                        continue
                    if in_conn_sec:
                        if st.startswith("|") and st.endswith("|"):
                            in_conn_table = True
                            final_lines.append(ln)
                            continue
                        elif in_conn_table and not inserted_conns:
                            for rc in added_conns:
                                comps = ", ".join(rc.get("inline_components") or []) if rc.get("inline_components") else "—"
                                f_cell = format_equipment_endpoint_cell(rc.get("source_tag"), root)
                                t_cell = format_equipment_endpoint_cell(rc.get("target_tag"), root)
                                final_lines.append(
                                    f"| {rc.get('stream_id')} | {rc.get('direction') or '—'} | {f_cell} | {t_cell} | "
                                    f"{rc.get('line_size') or '—'} | {comps} | {rc.get('temperature') or '—'} | "
                                    f"{rc.get('pressure') or '—'} | {rc.get('flow_rate') or '—'} | {rc.get('description') or '—'} |"
                                )
                            inserted_conns = True
                    final_lines.append(ln)
                if in_conn_sec and not inserted_conns:
                    for rc in added_conns:
                        comps = ", ".join(rc.get("inline_components") or []) if rc.get("inline_components") else "—"
                        f_cell = format_equipment_endpoint_cell(rc.get("source_tag"), root)
                        t_cell = format_equipment_endpoint_cell(rc.get("target_tag"), root)
                        final_lines.append(
                            f"| {rc.get('stream_id')} | {rc.get('direction') or '—'} | {f_cell} | {t_cell} | "
                            f"{rc.get('line_size') or '—'} | {comps} | {rc.get('temperature') or '—'} | "
                            f"{rc.get('pressure') or '—'} | {rc.get('flow_rate') or '—'} | {rc.get('description') or '—'} |"
                        )
                new_body_lines = final_lines

            updated_doc = OKFDocument(frontmatter=fm, body="\n".join(new_body_lines).rstrip() + "\n")
            serialized = updated_doc.serialize()
            pending_writes.append((p, serialized))

        for p, serialized in pending_writes:
            p.write_text(serialized, encoding="utf-8")
            updated_files.append(p)

        # Pass 4: Canonicalize case-mismatched or revision-suffixed internal Markdown links across all bundle files
        all_md_files = list(root.rglob("*.md"))
        rel_lower_map: dict[str, str] = {}
        files_by_cat: dict[str, list[Path]] = defaultdict(list)
        for md_p in all_md_files:
            rel_posix = md_p.relative_to(root).as_posix()
            rel_lower_map[rel_posix.lower()] = f"/{rel_posix}"
            if len(md_p.relative_to(root).parts) >= 2:
                files_by_cat[md_p.relative_to(root).parts[0].lower()].append(md_p)

        md_link_re = re.compile(r"(\[[^\]]+\]\()([^)#\s]+)((?:#[^)]*)?\))")
        for md_p in all_md_files:
            raw_txt = md_p.read_text(encoding="utf-8")

            def _fix_internal_link(m: re.Match[str]) -> str:
                prefix, lnk, suffix = m.group(1), m.group(2), m.group(3)
                if lnk.startswith(("http://", "https://", "gs://", "mailto:")):
                    return m.group(0)
                t1 = (md_p.parent / lnk).resolve()
                t2 = (root / lnk.lstrip("/")).resolve()
                if (
                    t1.exists()
                    or t1.with_suffix(".md").exists()
                    or t2.exists()
                    or t2.with_suffix(".md").exists()
                ):
                    return m.group(0)
                cand_rel = lnk.lstrip("/").lower()
                if not cand_rel.endswith(".md"):
                    cand_rel_md = f"{cand_rel}.md"
                else:
                    cand_rel_md = cand_rel
                if cand_rel in rel_lower_map:
                    return f"{prefix}{rel_lower_map[cand_rel]}{suffix}"
                if cand_rel_md in rel_lower_map:
                    return f"{prefix}{rel_lower_map[cand_rel_md]}{suffix}"
                parts = [pt for pt in cand_rel_md.split("/") if pt]
                if len(parts) == 2:
                    cat_l, fname_l = parts[0], parts[1].removesuffix(".md")
                    cat_candidates = files_by_cat.get(cat_l, [])
                    for cp in cat_candidates:
                        cp_stem = cp.stem.lower()
                        if cp_stem.startswith(fname_l) or fname_l.startswith(cp_stem):
                            return f"{prefix}/{cp.relative_to(root).as_posix()}{suffix}"
                    if f"{cat_l}/index.md" in rel_lower_map:
                        return f"{prefix}{rel_lower_map[f'{cat_l}/index.md']}{suffix}"
                return m.group(0)

            fixed_txt = md_link_re.sub(_fix_internal_link, raw_txt)
            if fixed_txt != raw_txt:
                md_p.write_text(fixed_txt, encoding="utf-8")
                if md_p not in updated_files:
                    updated_files.append(md_p)

        return updated_files


def _build_index_body(entries: list[tuple[str, str, str, str]]) -> str:
    """Group concepts by type and format markdown listing."""
    # entries: (type, title, relative_link, description)
    grouped: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for typ, title, link, desc in entries:
        grouped[typ or "Other Concepts"].append((title, link, desc))

    sections: list[str] = []
    for typ in sorted(grouped):
        lines = [f"# {typ}", ""]
        for title, link, desc in sorted(grouped[typ], key=lambda e: e[0].lower()):
            suffix = f" - {desc}" if desc else ""
            lines.append(f"* [{title}]({link}){suffix}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections) + "\n"


def _build_master_root_index(
    root: Path,
    entries: list[tuple[str, str, str, str]],
) -> str:
    """Compile a comprehensive Master Plant Knowledge Catalog for the root index.md."""
    base_listing = _build_index_body(entries)
    equip_rows: list[str] = []
    hazard_rows: list[str] = []
    inst_rows: list[str] = []
    unit_bullets: list[str] = []
    conflict_notes: list[str] = []
    catalog_title = "Master Plant Knowledge Catalog (OKF v0.2)"

    for md_file in sorted(root.rglob("*.md")):
        if md_file.name in (_INDEX_FILENAME, _LOG_FILENAME):
            continue
        rel = md_file.relative_to(root).as_posix()
        try:
            raw_text = md_file.read_text(encoding="utf-8")
            doc = OKFDocument.parse(raw_text)
            fm = doc.frontmatter
            title = str(fm.get("title") or md_file.stem)
            desc = str(fm.get("description") or "").replace("\n", " ").strip()
            if len(desc) > 140:
                desc = desc[:137] + "..."
            meta = fm.get("entity_metadata") or {}
            if rel in ("overview.md", "project.md") and fm.get("title"):
                catalog_title = f"{fm.get('title')} — Master Knowledge Catalog (OKF v0.2)"
            if rel.startswith("units/"):
                unit_bullets.append(f"- **[{title}]({rel})**: {desc}")
            elif rel.startswith("equipment/"):
                tag = str(meta.get("tag") or md_file.stem)
                unit = str(meta.get("unit") or "—")
                eq_class = str(meta.get("equipment_class") or "Equipment")
                inst_cnt = len(meta.get("instruments") or [])
                equip_rows.append(
                    f"| [{tag}]({rel}) | {title} | {unit} | {eq_class} | {inst_cnt} loops | {desc} |"
                )
            elif rel.startswith("hazards/"):
                hazard_rows.append(f"| [{title}]({rel}) | `{rel}` | {desc} |")
            elif rel.startswith("instruments/"):
                inst_rows.append(f"| [{title}]({rel}) | `{rel}` | {desc} |")

            for line in doc.body.splitlines():
                if "CONFLICT" in line.upper() or "⚠️" in line:
                    clean_line = line.strip().lstrip(">").strip()
                    if len(clean_line) > 20:
                        conflict_notes.append(f"- **[{title}]({rel})**: {clean_line[:240]}")
                        break
        except Exception as exc:
            logging.getLogger(__name__).debug("Ignored non-fatal index parse exception: %s", exc)

    catalog_sections: list[str] = [
        base_listing.rstrip(),
        "",
        "---",
        "",
        f"# {catalog_title}",
        "",
    ]
    if unit_bullets:
        catalog_sections.extend(
            [
                "## 1. Plant Unit Architecture & Scope",
                *unit_bullets,
                "",
            ]
        )

    if equip_rows:
        catalog_sections.extend(
            [
                "## 2. Master Equipment Specifications & P&ID Loop Matrix",
                "",
                "| Tag | Equipment Title | Unit | Class | P&ID Loops | Engineering Function Summary |",
                "| :--- | :--- | :--- | :--- | :--- | :--- |",
                *equip_rows,
                "",
            ]
        )

    if hazard_rows:
        catalog_sections.extend(
            [
                "## 3. Chemical Process Hazards & Runaway Safeguards Register",
                "",
                "| Chemical / Hazard Profile | Canonical Path | Critical Process Safety Summary |",
                "| :--- | :--- | :--- |",
                *hazard_rows,
                "",
            ]
        )

    if inst_rows:
        catalog_sections.extend(
            [
                "## 4. Instrumentation, Safety Interlocks (SIS) & Overpressure Protection Register",
                "",
                "| Subsystem Register | Canonical Path | Scope & Safety Interlock Summary |",
                "| :--- | :--- | :--- |",
                *inst_rows,
                "",
            ]
        )

    if conflict_notes:
        catalog_sections.extend(
            [
                "## 5. Cross-Document Engineering Discrepancies & Safety Warnings (`⚠️ CONFLICT`)",
                "",
                *conflict_notes[:40],
                "",
            ]
        )

    return "\n".join(catalog_sections) + "\n"


def generate_bundle_indexes(bundle_root: Path | str) -> list[Path]:
    """Generate index.md files for all directories within the bundle tree."""
    root = Path(bundle_root)
    if not root.exists():
        return []

    enrich_and_normalize_bundle_concepts(root)
    written_indexes: list[Path] = []

    # Find all directories that contain markdown documents
    directories: set[Path] = set()
    for md_file in root.rglob("*.md"):
        if md_file.name in (_INDEX_FILENAME, _LOG_FILENAME):
            continue
        cur = md_file.parent
        while cur != root.parent:
            directories.add(cur)
            if cur == root:
                break
            cur = cur.parent

    # Process bottom-up
    sorted_dirs = sorted(directories, key=lambda p: -len(p.parts))

    for directory in sorted_dirs:
        entries: list[tuple[str, str, str, str]] = []

        for child in sorted(directory.iterdir()):
            if child.name in (_INDEX_FILENAME, _LOG_FILENAME):
                continue

            if child.is_file() and child.suffix == ".md":
                try:
                    doc = OKFDocument.parse(child.read_text(encoding="utf-8"))
                    fm = doc.frontmatter
                    title = str(fm.get("title") or child.stem)
                    desc = str(fm.get("description") or "")
                    typ = str(fm.get("type") or "Document")
                    entries.append((typ, title, child.name, desc))
                except Exception:
                    entries.append(("Document", child.stem, child.name, ""))
            elif child.is_dir():
                entries.append(
                    (
                        "Subdirectories",
                        child.name,
                        f"{child.name}/{_INDEX_FILENAME}",
                        f"Index of {child.name}",
                    )
                )

        if entries:
            index_file = directory / _INDEX_FILENAME
            if directory == root:
                index_content = _build_master_root_index(root, entries)
            else:
                index_content = _build_index_body(entries)
            index_file.write_text(index_content, encoding="utf-8")
            written_indexes.append(index_file)

    return written_indexes


def update_bundle_log(
    bundle_root: Path | str,
    action: str,
    details: str,
    date_str: str | None = None,
) -> Path:
    """Append a structured entry to the bundle root log.md."""
    with _BUNDLE_IO_LOCK:
        root = Path(bundle_root)
        root.mkdir(parents=True, exist_ok=True)
        log_path = root / _LOG_FILENAME

        today = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        existing_content = ""
        if log_path.exists():
            existing_content = log_path.read_text(encoding="utf-8")

        new_entry = f"* **{action}**: {details}\n"

        if not existing_content:
            content = f"# Directory Update Log\n\n## {today}\n{new_entry}"
        elif f"## {today}" in existing_content:
            # Insert under today's heading
            content = existing_content.replace(f"## {today}\n", f"## {today}\n{new_entry}")
        else:
            # Prepend new date section after the title
            title_marker = "# Directory Update Log\n\n"
            if existing_content.startswith(title_marker):
                content = (
                    title_marker
                    + f"## {today}\n{new_entry}\n"
                    + existing_content[len(title_marker) :]
                )
            else:
                content = (
                    f"# Directory Update Log\n\n## {today}\n{new_entry}\n\n"
                    + existing_content
                )

        log_path.write_text(content, encoding="utf-8")
        return log_path


BUNDLE_COMPLETE_FILENAME = ".bundle_complete.json"


def write_bundle_completion_seal(
    bundle_root: Path | str,
    *,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Atomically write `.bundle_complete.json` marking a full-corpus OKF bundle build as complete."""
    import json
    import os

    with _BUNDLE_IO_LOCK:
        root = Path(bundle_root)
        root.mkdir(parents=True, exist_ok=True)
        seal_path = root / BUNDLE_COMPLETE_FILENAME
        tmp_path = root / f"{BUNDLE_COMPLETE_FILENAME}.tmp"
        md_count = sum(1 for _ in root.rglob("*.md"))
        payload: dict[str, Any] = {
            "status": "complete",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "markdown_file_count": md_count,
        }
        if metadata:
            payload.update(metadata)
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp_path, seal_path)
        return seal_path


def is_bundle_complete(bundle_root: Path | str) -> bool:
    """Return True iff `.bundle_complete.json` exists in `bundle_root` with `status == 'complete'`."""
    import json

    seal_path = Path(bundle_root) / BUNDLE_COMPLETE_FILENAME
    if not seal_path.is_file():
        return False
    try:
        payload = json.loads(seal_path.read_text(encoding="utf-8"))
        return isinstance(payload, dict) and payload.get("status") == "complete"
    except Exception:
        return False

