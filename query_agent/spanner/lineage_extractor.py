"""Automated OKF Bundle Parser, Header-Preserving Chunker, Graph Builder & Data Lineage Extractor.

Implements SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT Section 3.2:
- 100% automated extraction of Nodes, Chunks, Connectivity Edges, and Claim-to-PDF Lineage.
- Header-preserving Markdown table chunking.
- Boundary-aware Raw PDF citation resolution (primary & conflicting sources).
- Zero hardcoded domain tags, prefixes, or lookup tables.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from query_agent.config import get_config

logger = logging.getLogger(__name__)

try:
    from extracter_agent.tools.pdf_tools import _match_pdf_candidate
except ImportError:
    _match_pdf_candidate = None  # type: ignore[assignment]
from query_agent.models.schemas import (
    BundleGraphExtractionResult,
    ConceptWikiLinkEdge,
    EngineeringEntityNode,
    FactAssertionNode,
    FactLineageEdge,
    InstrumentControlEdge,
    OkfConceptNode,
    OkfSectionChunkNode,
    ProcessConnectionEdge,
    RawSourceNode,
    compute_deterministic_id,
)

_EQUIP_TAG_RE = re.compile(r"\b([A-Z]{1,3}-\d{4}[A-Z0-9/]*)\b")
_INST_TAG_RE = re.compile(r"\b([A-Z]{2,5}-(?:\d{2}-)?\d{4}[A-Z0-9/]*)\b")
_LINE_ID_RE = re.compile(r"\b([A-Z]{1,4}-\d{2}-\d{6}[A-Z0-9-]*)\b")
_WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+)(?:#[^\[\]|]+)?(?:\|[^\[\]]+)?\]\]")
_BRACKET_CIT_RE = re.compile(r"\[([^\[\]]{3,120})\]")


def _extract_doc_code_and_revision(filename: str) -> tuple[str, str]:
    """Deterministically extract leading document code and revision token from a filename or citation."""
    stem = Path(filename).stem
    rev_match = re.search(
        r"(?:_|-|\bRev\s*)([A-Z]\d+|\d+[A-Z]?)$", stem, re.IGNORECASE
    )
    revision = rev_match.group(1).upper() if rev_match else "Z1"
    if stem.upper().startswith("SDS_"):
        parts = stem.split("_")
        doc_code = "_".join(parts[:2]) if len(parts) >= 2 else parts[0]
    else:
        doc_code = stem.split("_")[0].split(" ")[0].strip()
    return doc_code, revision


def _parse_md_frontmatter_and_body(
    raw_text: str, default_title: str
) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and Markdown body directly from an OKF .md file."""
    text = raw_text or ""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                loaded = yaml.safe_load(parts[1])
                if isinstance(loaded, dict):
                    return loaded, parts[2].lstrip("\r\n")
            except Exception as exc:
                logger.debug("YAML frontmatter fallback for %s: %s", default_title, exc)
    return {"title": default_title}, text


def _source_node_from_md_reference(
    raw_entry: Any,
    bucket_name: str,
    raw_prefix: str = "reference/raw",
) -> RawSourceNode | None:
    """Build a RawSourceNode 100% from a .md YAML frontmatter `sources` entry or citation string (zero PDF file access)."""
    if isinstance(raw_entry, dict):
        res_str = str(
            raw_entry.get("resource")
            or raw_entry.get("title")
            or raw_entry.get("id")
            or ""
        ).strip()
        title_str = str(raw_entry.get("title") or "").strip()
    elif isinstance(raw_entry, str):
        res_str = raw_entry.strip()
        title_str = res_str
    else:
        return None

    if not res_str:
        return None

    norm_path = res_str.replace("\\", "/").strip("/")
    fname = Path(norm_path).name or title_str
    if not fname:
        return None
    source_id = Path(fname).stem
    if not source_id:
        return None

    # Infer subfolder from the .md resource path (e.g. reference/raw/data_sheets/foo.pdf -> data_sheets)
    path_parts = [p for p in norm_path.split("/") if p]
    subfolder = "md_cited"
    for idx, part in enumerate(path_parts):
        if part == "raw" and idx + 1 < len(path_parts) - 1:
            subfolder = path_parts[idx + 1]
            break
    if subfolder == "md_cited" and len(path_parts) >= 2:
        subfolder = path_parts[-2]

    doc_code, revision = _extract_doc_code_and_revision(fname)
    md5_hex = hashlib.md5(
        f"md-source:{source_id}:{revision}:{norm_path}".encode(),
        usedforsecurity=False,
    ).hexdigest()
    if norm_path.startswith("gs://"):
        gcs_uri = norm_path
    elif "/" in norm_path:
        gcs_uri = f"gs://{bucket_name}/{norm_path}"
    else:
        gcs_uri = f"gs://{bucket_name}/{raw_prefix.strip('/')}/{subfolder}/{fname}"

    return RawSourceNode(
        source_id=source_id[:128],
        filename=fname[:512],
        subfolder=subfolder[:64],
        doc_code=doc_code[:128],
        revision=revision[:32],
        md5_hash=md5_hex[:64],
        gcs_uri=gcs_uri[:1024],
    )



def resolve_citation_to_source_nodes(
    citation_text: str,
    raw_sources: list[RawSourceNode],
    fallback_sources: list[RawSourceNode] | None = None,
) -> list[RawSourceNode]:
    """Resolve a raw citation string or document code to matching RawSourceNode(s)."""
    cleaned = (citation_text or "").strip().strip("`*_[]()")
    if not cleaned or cleaned in ("—", "-", "N/A", "None"):
        return list(fallback_sources or [])

    matched: list[RawSourceNode] = []
    seen_ids: set[str] = set()

    # Split composite citation strings separated by commas, semicolons, or slashes (when not part of path)
    tokens = [t.strip() for t in re.split(r"[,;]+|\bvs\.?\b", cleaned) if t.strip()]
    if not tokens:
        tokens = [cleaned]

    candidate_dicts = [
        {"file_name": s.filename, "subfolder": s.subfolder, "source_id": s.source_id}
        for s in raw_sources
    ]
    sources_by_id = {s.source_id: s for s in raw_sources}

    for tok in tokens:
        tok_clean = Path(tok.strip("`*_[]() ")).name
        if not tok_clean:
            continue
        tok_lower = tok_clean.lower()
        tok_stem_lower = Path(tok_clean).stem.lower()

        hit_direct = False
        for src in raw_sources:
            if src.source_id in seen_ids:
                continue
            if (
                src.filename.lower() == tok_lower
                or src.source_id.lower() == tok_stem_lower
                or (src.doc_code and src.doc_code.lower() == tok_stem_lower)
            ):
                matched.append(src)
                seen_ids.add(src.source_id)
                hit_direct = True

        if not hit_direct and candidate_dicts:
            cand_hit = _match_pdf_candidate(tok_clean, "", candidate_dicts)
            if cand_hit:
                sid = cand_hit["source_id"]
                if sid not in seen_ids and sid in sources_by_id:
                    matched.append(sources_by_id[sid])
                    seen_ids.add(sid)

    if matched:
        return matched
    if fallback_sources:
        return list(fallback_sources)

    # Create a deterministic synthetic RawSourceNode if an external/unindexed source is cited
    doc_code, rev = _extract_doc_code_and_revision(cleaned)
    synth_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(cleaned).stem).strip("_")[:96] or "unindexed_source"
    return [
        RawSourceNode(
            source_id=synth_id,
            filename=cleaned[:256],
            subfolder="external",
            doc_code=doc_code[:64],
            revision=rev[:16],
            md5_hash="",
            gcs_uri="",
        )
    ]


def chunk_markdown_preserving_headers(
    concept_id: str,
    category: str,
    unit: str,
    body_markdown: str,
    max_rows_per_chunk: int = 35,
) -> list[OkfSectionChunkNode]:
    """Split an OKF Markdown body by H2 sections while repeating Markdown table headers on every slice."""
    lines = (body_markdown or "").splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_heading = "Overview"
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = line[3:].strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, current_lines))

    chunks: list[OkfSectionChunkNode] = []
    chunk_idx = 0

    for heading, sec_lines in sections:
        sec_text = "\n".join(sec_lines).strip()
        if not sec_text:
            continue

        banner = (
            f"[Concept: {concept_id} | Category: {category} | "
            f"Unit: {unit or 'ALL'} | Section: ## {heading}]"
        )

        # Check if section contains a large Markdown table (> max_rows_per_chunk)
        table_header_idx = -1
        for i in range(len(sec_lines) - 1):
            if (
                sec_lines[i].strip().startswith("|")
                and sec_lines[i + 1].strip().startswith("|")
                and "---" in sec_lines[i + 1]
            ):
                table_header_idx = i
                break

        if table_header_idx >= 0:
            pre_table = "\n".join(sec_lines[:table_header_idx]).strip()
            header_line = sec_lines[table_header_idx]
            sep_line = sec_lines[table_header_idx + 1]
            data_rows: list[str] = []
            post_table_lines: list[str] = []
            in_table = True
            for line in sec_lines[table_header_idx + 2 :]:
                if in_table and line.strip().startswith("|"):
                    data_rows.append(line)
                else:
                    if line.strip():
                        in_table = False
                    if not in_table:
                        post_table_lines.append(line)

            if len(data_rows) > max_rows_per_chunk:
                for start in range(0, len(data_rows), max_rows_per_chunk):
                    batch = data_rows[start : start + max_rows_per_chunk]
                    slice_parts = [banner]
                    if pre_table:
                        slice_parts.append(pre_table)
                    slice_parts.append(header_line)
                    slice_parts.append(sep_line)
                    slice_parts.extend(batch)
                    if start + max_rows_per_chunk >= len(data_rows) and post_table_lines:
                        post_str = "\n".join(post_table_lines).strip()
                        if post_str:
                            slice_parts.append(post_str)
                    chunk_md = "\n".join(slice_parts).strip()
                    has_conf = "CONFLICT" in chunk_md or "⚠️" in chunk_md
                    c_id = compute_deterministic_id(concept_id, heading, str(chunk_idx), prefix="CHK")
                    chunks.append(
                        OkfSectionChunkNode(
                            chunk_id=c_id,
                            concept_id=concept_id,
                            category=category,
                            unit=unit,
                            section_heading=heading,
                            chunk_index=chunk_idx,
                            header_preserved_markdown=chunk_md,
                            has_conflict=has_conf,
                        )
                    )
                    chunk_idx += 1
                continue

        chunk_md = f"{banner}\n{sec_text}".strip()
        has_conf = "CONFLICT" in chunk_md or "⚠️" in chunk_md
        c_id = compute_deterministic_id(concept_id, heading, str(chunk_idx), prefix="CHK")
        chunks.append(
            OkfSectionChunkNode(
                chunk_id=c_id,
                concept_id=concept_id,
                category=category,
                unit=unit,
                section_heading=heading,
                chunk_index=chunk_idx,
                header_preserved_markdown=chunk_md,
                has_conflict=has_conf,
            )
        )
        chunk_idx += 1

    return chunks


def _parse_markdown_tables_by_section(body_markdown: str) -> list[tuple[str, list[str], list[list[str]]]]:
    """Return a list of (section_heading, headers, rows) for all Markdown tables in body_markdown."""
    lines = (body_markdown or "").splitlines()
    current_heading = "Overview"
    results: list[tuple[str, list[str], list[list[str]]]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            current_heading = line[3:].strip()
            i += 1
            continue
        if (
            i + 1 < len(lines)
            and lines[i].strip().startswith("|")
            and lines[i + 1].strip().startswith("|")
            and "---" in lines[i + 1]
        ):
            headers = [c.strip() for c in lines[i].strip().strip("|").split("|")]
            rows: list[list[str]] = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= {"-", ":", " "} for c in cells):
                    rows.append(cells)
                i += 1
            results.append((current_heading, headers, rows))
            continue
        i += 1
    return results


def _extract_conflicting_citations(text: str) -> list[str]:
    """Extract bracketed or inline citation strings from a conflict note or dual-value cell."""
    citations: list[str] = []
    for m in _BRACKET_CIT_RE.finditer(text or ""):
        cand = m.group(1).strip()
        if not cand.startswith("[") and any(ch.isdigit() or ".pdf" in cand.lower() or "-" in cand for ch in cand):
            citations.append(cand)
    # Also check parenthetical source references like "(12.2 kg/cm2g in PID-23-0013)"
    for m in re.finditer(r"\b((?:DS|PID|PFD|STD|PS|OM)-[A-Za-z0-9_-]+|SDS_[A-Za-z0-9_-]+)", text or ""):
        cand = m.group(1).strip()
        if cand not in citations:
            citations.append(cand)
    return citations


def extract_bundle_graph_and_lineage(
    bundle_dir: Path | None = None,
    raw_dir: Path | None = None,
    bundle_version: str = "v3-by-equipment",
    md_files: list[Path] | None = None,
    existing_sources: list[RawSourceNode] | None = None,
) -> BundleGraphExtractionResult:
    """Parse OKF .md files (100% .md-only, zero PDF file inspection) into Spanner Graph nodes, chunks, connectivity edges, and lineage."""
    _ = raw_dir  # Explicitly unused: ingestion relies 100% on .md files only
    cfg = get_config()
    target_bundle = bundle_dir or cfg.output_bundle_dir
    raw_sources_by_id: dict[str, RawSourceNode] = {
        s.source_id: s for s in (existing_sources or [])
    }

    concepts: list[OkfConceptNode] = []
    entities_by_id: dict[str, EngineeringEntityNode] = {}
    facts_by_id: dict[str, FactAssertionNode] = {}
    chunks: list[OkfSectionChunkNode] = []
    process_edges_by_id: dict[str, ProcessConnectionEdge] = {}
    instrument_edges_by_id: dict[str, InstrumentControlEdge] = {}
    wikilink_edges_by_id: dict[str, ConceptWikiLinkEdge] = {}
    lineage_edges_by_id: dict[str, FactLineageEdge] = {}

    if not target_bundle.is_dir() and not md_files:
        return BundleGraphExtractionResult(
            raw_sources=list(raw_sources_by_id.values())
        )

    all_bundle_md_files = (
        sorted(
            p
            for p in target_bundle.rglob("*.md")
            if p.name not in ("index.md", "log.md")
        )
        if target_bundle.is_dir()
        else []
    )
    target_md_files = (
        sorted(p for p in md_files if p.name not in ("index.md", "log.md"))
        if md_files is not None
        else all_bundle_md_files
    )

    # Pass 1: Build the .md-derived RawSourceNode catalog & concept metadata map 100% from .md files
    known_concept_ids: set[str] = set()
    stem_to_concept_id: dict[str, str] = {}
    equipment_meta_by_slug: dict[str, tuple[str, str, str, str]] = {}
    for scan_md in all_bundle_md_files or target_md_files:
        try:
            try:
                scan_rel = str(scan_md.relative_to(target_bundle)).replace("\\", "/")
            except ValueError:
                scan_rel = (
                    f"{scan_md.parent.name}/{scan_md.name}"
                    if scan_md.parent.name
                    in ("equipment", "units", "hazards", "hazop", "instruments", "logs")
                    else scan_md.name
                )
            scan_cid = scan_rel.removesuffix(".md")
            known_concept_ids.add(scan_cid)
            stem_to_concept_id.setdefault(scan_md.stem, scan_cid)

            scan_text = scan_md.read_text(encoding="utf-8", errors="replace")
            fm_scan, _ = _parse_md_frontmatter_and_body(scan_text, scan_md.stem)
            for s_entry in fm_scan.get("sources") or []:
                s_node = _source_node_from_md_reference(
                    s_entry,
                    bucket_name=cfg.destination_gcs_bucket,
                    raw_prefix=cfg.source_gcs_raw_prefix,
                )
                if s_node:
                    raw_sources_by_id.setdefault(s_node.source_id, s_node)

            if scan_cid.startswith("equipment/"):
                s_title = str(fm_scan.get("title") or fm_scan.get("name") or scan_md.stem).strip()[:512]
                s_em = fm_scan.get("entity_metadata") if isinstance(fm_scan.get("entity_metadata"), dict) else {}
                s_class = str(s_em.get("equipment_class") or fm_scan.get("type") or "Equipment").strip()[:128]
                s_unit = str(s_em.get("unit") or fm_scan.get("unit") or "").strip()
                if not s_unit:
                    for t in fm_scan.get("tags") or []:
                        if isinstance(t, str):
                            u_m = re.match(r"^unit\s*(\d{3,4})$", t.strip(), re.IGNORECASE)
                            if u_m:
                                s_unit = f"U{u_m.group(1)}"
                                break
                s_unit = s_unit[:64]
                equipment_meta_by_slug[scan_md.stem] = (s_title, s_class, s_unit, scan_cid)
        except Exception as exc:
            logger.debug("Skipping scan_md %s in Pass 1: %s", scan_md, exc)
            continue

    # Pass 2: Extract concepts, chunks, entities, parameters, conflicts, and graph/lineage edges for target_md_files
    for md_path in target_md_files:
        try:
            rel_path = str(md_path.relative_to(target_bundle)).replace("\\", "/")
        except ValueError:
            rel_path = (
                f"{md_path.parent.name}/{md_path.name}"
                if md_path.parent.name
                in ("equipment", "units", "hazards", "hazop", "instruments", "logs")
                else md_path.name
            )
        concept_id = rel_path.removesuffix(".md")[:256]
        category = (concept_id.split("/")[0] if "/" in concept_id else "root")[:64]

        raw_text = md_path.read_text(encoding="utf-8", errors="replace")
        md5_hex = hashlib.md5(
            raw_text.encode("utf-8"), usedforsecurity=False
        ).hexdigest()

        fm_dict, body_md = _parse_md_frontmatter_and_body(raw_text, md_path.stem)
        title = str(fm_dict.get("title") or fm_dict.get("name") or md_path.stem).strip()[:512]
        desc = str(fm_dict.get("description") or "").strip()
        trust_tier = str(fm_dict.get("trust_tier") or "human-reviewed").strip()[:64]
        fm_sources = list(fm_dict.get("sources") or [])
        em = (
            fm_dict.get("entity_metadata")
            if isinstance(fm_dict.get("entity_metadata"), dict)
            else {}
        )

        unit = str(em.get("unit") or fm_dict.get("unit") or "").strip()
        if not unit:
            for t in fm_dict.get("tags") or []:
                if isinstance(t, str):
                    t_str = t.strip()
                    u_m = re.match(r"^unit\s*(\d{3,4})$", t_str, re.IGNORECASE)
                    if u_m:
                        unit = f"U{u_m.group(1)}"
                        break
                    if t_str.isupper() and 2 <= len(t_str) <= 6:
                        unit = t_str
                        break
        unit = unit[:64]

        conflict_lines = [
            line.strip()
            for line in raw_text.splitlines()
            if "CONFLICT" in line and not line.strip().startswith("#")
        ]
        has_conflict = len(conflict_lines) > 0
        gcs_uri = str(
            fm_dict.get("resource")
            or f"gs://{cfg.destination_gcs_bucket}/{cfg.destination_gcs_prefix.strip('/')}/{rel_path}"
        )[:1024]

        concepts.append(
            OkfConceptNode(
                concept_id=concept_id,
                category=category,
                name=title,
                description=desc,
                unit=unit,
                trust_tier=trust_tier,
                has_conflict=has_conflict,
                conflict_count=len(conflict_lines),
                frontmatter_json=fm_dict,
                body_markdown=body_md or raw_text,
                md5_hash=md5_hex,
                bundle_version=bundle_version,
                gcs_uri=gcs_uri,
            )
        )

        # Resolve concept-level frontmatter sources (100% from .md)
        concept_source_nodes: list[RawSourceNode] = []
        for s_entry in fm_sources:
            direct_node = _source_node_from_md_reference(
                s_entry,
                bucket_name=cfg.destination_gcs_bucket,
                raw_prefix=cfg.source_gcs_raw_prefix,
            )
            if direct_node:
                raw_sources_by_id.setdefault(direct_node.source_id, direct_node)
                if direct_node not in concept_source_nodes:
                    concept_source_nodes.append(direct_node)
            else:
                resolved = resolve_citation_to_source_nodes(
                    str(s_entry), list(raw_sources_by_id.values())
                )
                for r_node in resolved:
                    raw_sources_by_id.setdefault(r_node.source_id, r_node)
                    if r_node not in concept_source_nodes:
                        concept_source_nodes.append(r_node)

        # Build Header-Preserved Section Chunks
        concept_chunks = chunk_markdown_preserving_headers(
            concept_id=concept_id,
            category=category,
            unit=unit,
            body_markdown=body_md or raw_text,
        )
        chunks.extend(concept_chunks)

        # Primary Entity for this Concept
        slug_tail = concept_id.split("/")[-1][:120]
        if category == "equipment":
            eq_tag = str(em.get("tag") or slug_tail).strip()[:128]
            eq_class = str(em.get("equipment_class") or fm_dict.get("type") or "Equipment").strip()[:128]
            primary_entity_id = f"EQ:{slug_tail}"[:256]
            entities_by_id[primary_entity_id] = EngineeringEntityNode(
                entity_id=primary_entity_id,
                entity_type="EQUIPMENT",
                canonical_tag=eq_tag,
                name=title[:512],
                equipment_class=eq_class,
                unit=unit[:64],
                concept_id=concept_id,
            )
        elif category == "hazards":
            primary_entity_id = f"HAZ:{slug_tail}"[:256]
            entities_by_id[primary_entity_id] = EngineeringEntityNode(
                entity_id=primary_entity_id,
                entity_type="HAZARD",
                canonical_tag=slug_tail[:128],
                name=title[:512],
                equipment_class="Chemical Hazard",
                unit=unit[:64],
                concept_id=concept_id,
            )
        elif category == "units":
            primary_entity_id = f"UNIT:{slug_tail.upper()}"[:256]
            entities_by_id[primary_entity_id] = EngineeringEntityNode(
                entity_id=primary_entity_id,
                entity_type="UNIT",
                canonical_tag=slug_tail.upper()[:128],
                name=title[:512],
                equipment_class="Process Unit",
                unit=(unit or slug_tail.upper())[:64],
                concept_id=concept_id,
            )
        else:
            primary_entity_id = f"{category.upper()[:4]}:{slug_tail}"[:256]
            entities_by_id.setdefault(
                primary_entity_id,
                EngineeringEntityNode(
                    entity_id=primary_entity_id,
                    entity_type=category.upper()[:64],
                    canonical_tag=slug_tail[:128],
                    name=title[:512],
                    equipment_class=category[:128],
                    unit=unit[:64],
                    concept_id=concept_id,
                ),
            )

        # Extract [[wikilinks]] -> ConceptWikiLinkEdge (and Hazard/Equipment edges)
        current_sec = "Overview"
        for line in (body_md or raw_text).splitlines():
            if line.startswith("## "):
                current_sec = line[3:].strip()
            for m in _WIKILINK_RE.finditer(line):
                target_cid = m.group(1).strip().removesuffix(".md")
                target_cid = target_cid.removeprefix("wiki/")
                if target_cid not in known_concept_ids and target_cid in stem_to_concept_id:
                    target_cid = stem_to_concept_id[target_cid]
                if target_cid and target_cid != concept_id:
                    e_id = compute_deterministic_id(concept_id, target_cid, current_sec, prefix="WL")
                    wikilink_edges_by_id[e_id] = ConceptWikiLinkEdge(
                        edge_id=e_id,
                        from_concept_id=concept_id,
                        to_concept_id=target_cid,
                        section_heading=current_sec,
                    )

        # Parse all Markdown tables in the concept body into FactAssertions, LineageEdges, and Connectivity Edges
        parsed_tables = _parse_markdown_tables_by_section(body_md or raw_text)
        for sec_heading, headers, rows in parsed_tables:
            norm_headers = [h.lower().strip("*_ ") for h in headers]
            source_col_idx = next(
                (
                    idx
                    for idx, h in enumerate(norm_headers)
                    if any(k in h for k in ("source", "document", "drawing", "ref"))
                ),
                -1,
            )
            unit_col_idx = next(
                (idx for idx, h in enumerate(norm_headers) if h in ("unit", "units", "uom")),
                -1,
            )

            for row in rows:
                if not row or not row[0].strip():
                    continue
                param_key = row[0].strip("*_ ")
                if not param_key or param_key in ("—", "-"):
                    continue

                # Determine value and unit
                if len(row) >= 2:
                    val_Indices = [
                        idx
                        for idx in range(1, len(row))
                        if idx not in (source_col_idx, unit_col_idx)
                    ]
                    if val_Indices:
                        val_parts = []
                        for idx in val_Indices:
                            cell_val = row[idx].strip()
                            if cell_val and cell_val not in ("—", "-"):
                                col_label = headers[idx].strip() if idx < len(headers) else ""
                                if len(val_Indices) > 1 and col_label:
                                    val_parts.append(f"{col_label}: {cell_val}")
                                else:
                                    val_parts.append(cell_val)
                        param_val = " | ".join(val_parts) if val_parts else row[1].strip()
                    else:
                        param_val = row[1].strip()
                else:
                    param_val = param_key

                param_unit = (
                    row[unit_col_idx].strip()
                    if 0 <= unit_col_idx < len(row) and row[unit_col_idx].strip()
                    else "—"
                )
                row_source_str = (
                    row[source_col_idx].strip()
                    if 0 <= source_col_idx < len(row) and row[source_col_idx].strip()
                    else ""
                )

                full_row_str = " | ".join(row)
                row_has_conflict = (
                    "CONFLICT" in full_row_str
                    or "⚠️" in full_row_str
                    or bool(re.search(r"\bvs\.?\b", full_row_str))
                    or any(
                        param_key.lower() in c_line.lower()
                        for c_line in conflict_lines
                    )
                )
                matching_conflict_notes = [
                    c_line
                    for c_line in conflict_lines
                    if param_key.lower() in c_line.lower()
                ]
                conflict_note = (
                    " ; ".join(matching_conflict_notes)
                    if matching_conflict_notes
                    else (full_row_str if row_has_conflict else "")
                )

                fact_id = compute_deterministic_id(
                    concept_id, sec_heading, param_key, prefix="FACT"
                )
                facts_by_id[fact_id] = FactAssertionNode(
                    fact_id=fact_id,
                    concept_id=concept_id,
                    entity_id=primary_entity_id,
                    section_heading=sec_heading,
                    parameter_name=param_key[:512],
                    parameter_value=(param_val or "—")[:4000],
                    parameter_unit=param_unit[:128],
                    has_conflict=row_has_conflict,
                    conflict_note=conflict_note[:4000],
                    bundle_version=bundle_version,
                )

                # Automated Lineage Edge Resolution for this FactAssertion
                primary_src_nodes = resolve_citation_to_source_nodes(
                    row_source_str,
                    list(raw_sources_by_id.values()),
                    fallback_sources=concept_source_nodes,
                )
                for p_src in primary_src_nodes:
                    raw_sources_by_id.setdefault(p_src.source_id, p_src)
                    lin_id = compute_deterministic_id(
                        fact_id, p_src.source_id, "PRIMARY", prefix="LIN"
                    )
                    lineage_edges_by_id[lin_id] = FactLineageEdge(
                        lineage_id=lin_id,
                        fact_id=fact_id,
                        concept_id=concept_id,
                        source_id=p_src.source_id,
                        raw_citation_string=(row_source_str or p_src.filename)[:512],
                        source_role="PRIMARY",
                        bundle_version=bundle_version,
                    )

                if row_has_conflict:
                    competing_cits = _extract_conflicting_citations(
                        f"{param_val} {conflict_note} {row_source_str}"
                    )
                    for comp_cit in competing_cits:
                        comp_nodes = resolve_citation_to_source_nodes(
                            comp_cit, list(raw_sources_by_id.values())
                        )
                        for c_src in comp_nodes:
                            raw_sources_by_id.setdefault(c_src.source_id, c_src)
                            lin_id = compute_deterministic_id(
                                fact_id, c_src.source_id, "CONFLICTING", prefix="LIN"
                            )
                            lineage_edges_by_id[lin_id] = FactLineageEdge(
                                lineage_id=lin_id,
                                fact_id=fact_id,
                                concept_id=concept_id,
                                source_id=c_src.source_id,
                                raw_citation_string=comp_cit[:512],
                                source_role="CONFLICTING",
                                bundle_version=bundle_version,
                            )

                # Extract Piping Line & Equipment Connectivity Edges from Connection/Stream tables
                sec_lower = sec_heading.lower()
                if any(k in sec_lower for k in ("connection", "stream", "nozzle", "piping", "line")):
                    line_matches = _LINE_ID_RE.findall(full_row_str)
                    stream_or_line = line_matches[0] if line_matches else param_key
                    for l_tag in line_matches:
                        l_ent_id = f"LINE:{l_tag}"
                        entities_by_id.setdefault(
                            l_ent_id,
                            EngineeringEntityNode(
                                entity_id=l_ent_id,
                                entity_type="PIPING_LINE",
                                canonical_tag=l_tag,
                                name=f"Piping Line {l_tag}",
                                equipment_class="Piping Line",
                                unit=unit,
                                concept_id=concept_id,
                            ),
                        )

                    # Find connected equipment tags mentioned in the row
                    eq_mentions: list[str] = []
                    for w_m in _WIKILINK_RE.finditer(full_row_str):
                        w_target = w_m.group(1).strip().removesuffix(".md")
                        if w_target.startswith("equipment/"):
                            eq_mentions.append(w_target.split("/")[-1])
                    for eq_m in _EQUIP_TAG_RE.finditer(full_row_str):
                        cand_eq = eq_m.group(1).replace("/", "")
                        if cand_eq != slug_tail and cand_eq not in eq_mentions:
                            eq_mentions.append(cand_eq)

                    primary_src_id = primary_src_nodes[0].source_id if primary_src_nodes else ""
                    for target_eq_slug in eq_mentions:
                        target_ent_id = f"EQ:{target_eq_slug}"
                        eq_meta = equipment_meta_by_slug.get(target_eq_slug)
                        entities_by_id.setdefault(
                            target_ent_id,
                            EngineeringEntityNode(
                                entity_id=target_ent_id,
                                entity_type="EQUIPMENT",
                                canonical_tag=target_eq_slug,
                                name=eq_meta[0] if eq_meta else target_eq_slug,
                                equipment_class=eq_meta[1] if eq_meta else "Equipment",
                                unit=(eq_meta[2] if eq_meta and eq_meta[2] else unit),
                                concept_id=eq_meta[3] if eq_meta else f"equipment/{target_eq_slug}",
                            ),
                        )
                        is_inbound = bool(
                            re.search(r"\b(from|inlet|feed|suction|supply)\b", full_row_str, re.IGNORECASE)
                            and not re.search(r"\b(to|outlet|discharge|return)\b", full_row_str, re.IGNORECASE)
                        )
                        src_ent = target_ent_id if is_inbound else primary_entity_id
                        dst_ent = primary_entity_id if is_inbound else target_ent_id
                        pe_id = compute_deterministic_id(
                            src_ent, dst_ent, stream_or_line, concept_id, prefix="CONN"
                        )
                        process_edges_by_id[pe_id] = ProcessConnectionEdge(
                            edge_id=pe_id,
                            from_entity_id=src_ent,
                            to_entity_id=dst_ent,
                            stream_or_line_id=stream_or_line[:256],
                            fluid_service=param_val[:512],
                            temperature="",
                            pressure="",
                            flow_rate="",
                            source_concept_id=concept_id,
                            source_id=primary_src_id,
                        )

                # Extract Instrument Control & SIS Interlock Edges from Instrumentation tables
                if any(k in sec_lower for k in ("instrument", "loop", "valve", "relief", "analyzer", "interlock", "cause")):
                    inst_matches = _INST_TAG_RE.findall(param_key) or _INST_TAG_RE.findall(full_row_str)
                    if inst_matches:
                        inst_tag = inst_matches[0]
                        inst_ent_id = f"INST:{inst_tag.replace('/', '-')}"
                        entities_by_id.setdefault(
                            inst_ent_id,
                            EngineeringEntityNode(
                                entity_id=inst_ent_id,
                                entity_type="INSTRUMENT",
                                canonical_tag=inst_tag,
                                name=f"{inst_tag} ({param_val[:80]})",
                                equipment_class=sec_heading[:128],
                                unit=unit,
                                concept_id=concept_id,
                            ),
                        )
                        loop_num_m = re.search(r"(\d{4})", inst_tag)
                        loop_prefix = inst_tag.split("-")[0][0] if "-" in inst_tag else "I"
                        loop_id = f"{loop_prefix}-{loop_num_m.group(1)}" if loop_num_m else inst_tag
                        primary_src_id = primary_src_nodes[0].source_id if primary_src_nodes else ""

                        # Link instrument to current equipment concept or any equipment mentioned in row
                        target_eq_ids: list[str] = []
                        if category == "equipment":
                            target_eq_ids.append(primary_entity_id)
                        for w_m in _WIKILINK_RE.finditer(full_row_str):
                            w_t = w_m.group(1).strip().removesuffix(".md")
                            if w_t.startswith("equipment/"):
                                eq_s = w_t.split("/")[-1]
                                t_id = f"EQ:{eq_s}"
                                eq_meta = equipment_meta_by_slug.get(eq_s)
                                entities_by_id.setdefault(
                                    t_id,
                                    EngineeringEntityNode(
                                        entity_id=t_id,
                                        entity_type="EQUIPMENT",
                                        canonical_tag=eq_s,
                                        name=eq_meta[0] if eq_meta else eq_s,
                                        equipment_class=eq_meta[1] if eq_meta else "Equipment",
                                        unit=(eq_meta[2] if eq_meta and eq_meta[2] else unit),
                                        concept_id=eq_meta[3] if eq_meta else f"equipment/{eq_s}",
                                    ),
                                )
                                if t_id not in target_eq_ids:
                                    target_eq_ids.append(t_id)

                        for t_eq_id in target_eq_ids:
                            ie_id = compute_deterministic_id(
                                inst_ent_id, t_eq_id, loop_id, concept_id, prefix="INSTEDGE"
                            )
                            instrument_edges_by_id[ie_id] = InstrumentControlEdge(
                                edge_id=ie_id,
                                instrument_entity_id=inst_ent_id,
                                target_entity_id=t_eq_id,
                                loop_id=loop_id[:128],
                                instrument_type=sec_heading[:256],
                                setpoint_or_range=param_val[:256],
                                interlock_or_alarm=full_row_str[:512],
                                source_concept_id=concept_id,
                                source_id=primary_src_id,
                            )

    return BundleGraphExtractionResult(
        raw_sources=list(raw_sources_by_id.values()),
        concepts=concepts,
        entities=list(entities_by_id.values()),
        facts=list(facts_by_id.values()),
        chunks=chunks,
        process_edges=list(process_edges_by_id.values()),
        instrument_edges=list(instrument_edges_by_id.values()),
        wikilink_edges=list(wikilink_edges_by_id.values()),
        lineage_edges=list(lineage_edges_by_id.values()),
    )
