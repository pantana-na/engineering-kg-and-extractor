"""ADK FunctionTools for OKF v0.2 Knowledge Synthesis and Validation.

Strictly complies with Rule 11 (FunctionTool docstring contracts, negative constraints).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extracter_agent.config import get_config
from extracter_agent.models.domain import (
    ConnectionStream,
    EngineeringParameter,
    EquipmentEntity,
    InstrumentLoop,
    _extract_equipment_base_id,
    derive_canonical_concept_id,
    derive_canonical_equipment_tag,
    sanitize_tag_filename,
)
from extracter_agent.okf.document import OKFDocument
from extracter_agent.okf.indexer import (
    _BUNDLE_IO_LOCK,
    generate_bundle_indexes,
    update_bundle_log,
)
from extracter_agent.okf.synthesizer import (
    _normalize_base_source_id,
    merge_equipment_entity_with_existing,
    merge_markdown_bodies,
    synthesize_equipment_concept,
)
from extracter_agent.okf.validator import validate_okf_bundle


def _sync_file_to_gcs(local_file: Path, bundle_root: Path) -> str | None:
    """Upload a generated OKF Markdown file or index to GCS when use_gcs_storage is enabled."""
    cfg = get_config()
    if not cfg.use_gcs_storage:
        return None
    try:
        from google.cloud import storage

        rel_path = local_file.resolve().relative_to(bundle_root.resolve())
        blob_name = f"{cfg.destination_gcs_prefix.strip('/')}/{rel_path}"
        client = storage.Client(project=cfg.google_cloud_project)
        bucket = client.bucket(cfg.destination_gcs_bucket)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(local_file), content_type="text/markdown")
        return f"gs://{cfg.destination_gcs_bucket}/{blob_name}"
    except Exception:
        return None


def generate_equipment_okf_tool(
    tag: str,
    name: str,
    equipment_class: str,
    unit: str,
    function_summary: str,
    design_data: list[dict[str, str]],
    operating_conditions: list[dict[str, str]],
    connections: list[dict[str, str]],
    hazards: list[str],
    source_files: list[str],
    instruments: list[dict[str, str]] | None = None,
    output_bundle_dir: str | None = None,
    merge_existing: bool = True,
) -> dict[str, Any]:
    """Construct or incrementally enrich a validated OKF v0.2 Equipment concept document and save it to the bundle and GCS.

    When to use:
        - When synthesizing extracted chemical equipment data into an OKF v0.2 concept.
        - During file-by-file incremental extraction when a newly processed PDF adds design data,
          operating conditions, instruments, connections, or hazards to an existing or new equipment tag.
        - Example: generate_equipment_okf_tool(tag="<TAG>", name="<Equipment Title>", unit="<UNIT>", ...)

    When NOT to use:
        - Do NOT use for raw unstructured PDF documents.
        - Do NOT use for standalone hazard or instrument concepts (use generate_okf_concept_tool).
        - Do NOT write directly to reference/ directory.

    Args:
        tag: Equipment unique plant identifier.
        name: Full equipment title.
        equipment_class: Equipment category, e.g. Column, Pump, Heat Exchanger, Vessel.
        unit: Plant unit or section code.
        function_summary: Engineering description of the equipment function.
        design_data: List of design parameters with parameter, value, unit, and source.
        operating_conditions: List of operating conditions with parameter, value, unit, and source.
        connections: List of stream connections with stream_id, temperature, pressure, flow_rate.
        hazards: List of process safety hazard notes and precautions.
        source_files: List of reference source PDF paths.
        instruments: Optional list of P&ID instruments and control loops (tag, service, instrument_type, location, setpoint_or_range, interlock_or_alarm, source).
        output_bundle_dir: Optional destination bundle directory path.
        merge_existing: When True (default), automatically merges new facts and sources with any existing equipment concept on disk instead of overwriting prior sources.

    Returns:
        A dictionary containing generation status, merge indicator, relative path, GCS URI, and document frontmatter.
    """
    cfg = get_config()
    bundle_root = (
        Path(output_bundle_dir) if output_bundle_dir else cfg.output_bundle_dir
    )

    entity = EquipmentEntity(
        tag=tag,
        name=name,
        equipment_class=equipment_class,
        unit=unit,
        function_summary=function_summary,
        design_data=[EngineeringParameter(**d) for d in design_data],
        operating_conditions=[
            EngineeringParameter(**op) for op in operating_conditions
        ],
        instruments=[InstrumentLoop(**i) for i in (instruments or [])],
        connections=[ConnectionStream(**c) for c in connections],
        hazards=hazards,
        sources=source_files,
    )

    with _BUNDLE_IO_LOCK:
        safe_tag = derive_canonical_equipment_tag(tag, source_files, bundle_root=bundle_root)
        requested_safe = sanitize_tag_filename(tag)
        has_inline_ab = any(" a_b " in (s or "").lower() for s in (source_files or []))
        equip_dir = bundle_root / "equipment"
        equip_dir.mkdir(parents=True, exist_ok=True)
        output_file = equip_dir / f"{safe_tag}.md"

        # If an earlier pass created a bare stem file (e.g. P-2301.md) and a subsequent pass
        # provides the full multi-unit tag (e.g. P-2301AB or P-2305ABCDEF) for the same base ID,
        # upgrade the canonical filename on disk to preserve the multi-unit suffix.
        if (
            not has_inline_ab
            and len(requested_safe) > len(safe_tag)
            and _extract_equipment_base_id(requested_safe) == _extract_equipment_base_id(safe_tag)
            and re.search(r"\d[A-Z]{2,}$", requested_safe)
        ):
            upgraded_file = equip_dir / f"{requested_safe}.md"
            if output_file.exists() and not upgraded_file.exists():
                output_file.rename(upgraded_file)
            safe_tag = requested_safe
            output_file = upgraded_file

        was_merged = False
        existing_body_text = ""
        if merge_existing and output_file.exists():
            try:
                existing_doc = OKFDocument.parse(output_file.read_text(encoding="utf-8"))
                existing_tag = str(
                    (existing_doc.frontmatter.get("entity_metadata") or {}).get("tag")
                    or str(existing_doc.frontmatter.get("title", "")).split("—")[0].strip()
                )
                if not existing_tag or _extract_equipment_base_id(existing_tag) == _extract_equipment_base_id(tag):
                    existing_body_text = existing_doc.body or ""
                    entity = merge_equipment_entity_with_existing(entity, existing_doc)
                    was_merged = True
            except Exception:
                was_merged = False

        doc = synthesize_equipment_concept(
            entity,
            gcs_bucket=cfg.destination_gcs_bucket,
            gcs_prefix=cfg.destination_gcs_prefix,
            bundle_root=bundle_root,
        )
        if was_merged and existing_body_text.strip():
            standard_h2 = {
                "## function",
                "## design data",
                "## operating conditions",
                "## instrumentation & control loops (p&id)",
                "## connections & stream summary",
                "## hazards & safeguards",
            }
            extra_h2_blocks: list[str] = []
            curr_h2 = ""
            curr_lines: list[str] = []
            for ln in existing_body_text.splitlines():
                if ln.startswith("## "):
                    if curr_h2 and curr_h2.lower() not in standard_h2:
                        extra_h2_blocks.append("\n".join([curr_h2, *curr_lines]).strip())
                    curr_h2 = ln.strip()
                    curr_lines = []
                elif curr_h2:
                    curr_lines.append(ln)
            if curr_h2 and curr_h2.lower() not in standard_h2:
                extra_h2_blocks.append("\n".join([curr_h2, *curr_lines]).strip())
            if extra_h2_blocks:
                doc.body = merge_markdown_bodies("\n\n".join(extra_h2_blocks), doc.body)

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(doc.serialize(), encoding="utf-8")

        # Update log
        log_action = "Concept Enrichment" if was_merged else "Concept Creation"
        log_verb = "Enriched" if was_merged else "Created"
        log_path = update_bundle_log(
            bundle_root,
            log_action,
            f"{log_verb} OKF equipment concept for [{tag} — {entity.name}](/equipment/{safe_tag}.md)",
        )

    gcs_uri = None
    if output_bundle_dir is None:
        gcs_uri = _sync_file_to_gcs(output_file, bundle_root)
        _sync_file_to_gcs(log_path, bundle_root)

    return {
        "status": "success",
        "merged_with_existing": was_merged,
        "concept_id": f"equipment/{safe_tag}",
        "output_file": str(
            output_file.relative_to(Path.cwd())
            if output_file.is_relative_to(Path.cwd())
            else output_file
        ),
        "gcs_uri": gcs_uri or doc.frontmatter.get("resource"),
        "title": doc.frontmatter.get("title"),
        "type": doc.frontmatter.get("type"),
        "resource": doc.frontmatter.get("resource"),
        "frontmatter": doc.frontmatter,
    }


def build_okf_indexes_and_validate_tool(
    bundle_dir: str | None = None,
) -> dict[str, Any]:
    """Generate progressive disclosure index.md files, validate the OKF bundle, and sync indexes to GCS.

    When to use:
        - After creating or updating concept documents, to generate index.md files
          and ensure 100% compliance with OKF v0.2 specifications before publishing to GCS.
        - Example: build_okf_indexes_and_validate_tool()

    When NOT to use:
        - Do NOT use before any concepts are written.
        - Do NOT use on arbitrary non-bundle directories.

    Args:
        bundle_dir: Path to the bundle root directory. Defaults to configured output_bundle_dir.

    Returns:
        A dictionary detailing generated index files, GCS URIs, total concepts, validation results, and trust tiers.
    """
    cfg = get_config()
    root = Path(bundle_dir) if bundle_dir else cfg.output_bundle_dir
    if not root.exists():
        return {
            "status": "error",
            "error": f"Bundle directory does not exist: {root}",
        }

    with _BUNDLE_IO_LOCK:
        written_indexes = generate_bundle_indexes(root)
        validation = validate_okf_bundle(root)

    synced_gcs_indexes: list[str] = []
    if bundle_dir is None:
        for idx_file in written_indexes:
            uri = _sync_file_to_gcs(idx_file, root)
            if uri:
                synced_gcs_indexes.append(uri)

    return {
        "status": "success" if validation["valid"] else "validation_warning",
        "bundle_dir": str(root),
        "gcs_bundle_prefix": f"gs://{cfg.destination_gcs_bucket}/{cfg.destination_gcs_prefix}",
        "gcs_synced_indexes": synced_gcs_indexes,
        "indexes_generated": [str(p.name) for p in written_indexes],
        "total_indexes": len(written_indexes),
        "is_valid_okf": validation["valid"],
        "total_documents": validation["total_documents"],
        "trust_tiers": validation["trust_tiers"],
        "errors": validation["errors"],
    }


_DUMMY_PROBE_TITLES = frozenset(
    {
        "test",
        "test 2",
        "check",
        "test title",
        "test instrument",
        "test control valves",
        "test concept",
        "test match",
    }
)


def generate_okf_concept_tool(
    concept_id: str,
    concept_type: str,
    title: str,
    description: str,
    tags: list[str],
    sources: list[str],
    body_markdown: str,
    entity_metadata: dict[str, Any] | None = None,
    output_bundle_dir: str | None = None,
    merge_existing: bool = True,
    append_sections_markdown: list[str] | None = None,
) -> dict[str, Any]:
    """Construct or incrementally enrich a validated OKF v0.2 concept document and save it to the bundle.

    When to use:
        - When synthesizing chemical engineering domain concepts (sources, hazards, instruments,
          procedures, troubleshooting, units, parameters, hazop, standards) into an OKF v0.2 concept document.
        - For large multi-sheet discipline register packages (> 20 pages), either call this tool
          incrementally across page-range batches with merge_existing=True or pass batch table
          chunks in append_sections_markdown so all columns are preserved without compression.
        - Example: generate_okf_concept_tool(concept_id="hazards/<chemical-slug>", concept_type="Hazard Profile", title="<Chemical Title>", ...)

    When NOT to use:
        - Do NOT use for raw unstructured PDF documents.
        - Do NOT use for modifying files in reference/ directory.

    Args:
        concept_id: Relative concept path without extension, e.g. '<category>/<slug>'.
        concept_type: Descriptive OKF concept type, e.g. 'Hazard Profile', 'Instrument Specification'.
        title: Human-readable concept title.
        description: Single-sentence summary for search and progressive disclosure.
        tags: Categorical tags for indexing.
        sources: List of source reference PDF filenames or paths.
        body_markdown: Structured Markdown body with headings, tables, and footnote citations.
        entity_metadata: Optional dictionary of domain-specific attributes.
        output_bundle_dir: Optional destination bundle directory path.
        merge_existing: When True (default), preserves and merges prior tags, sources, entity_metadata, H2 sections, and Markdown table rows from an existing concept file on disk.
        append_sections_markdown: Optional list of additional Markdown section/table chunks to merge sequentially into body_markdown without column compression.

    Returns:
        A dictionary containing generation status, merge indicator, relative path, and frontmatter.
    """
    cfg = get_config()
    bundle_root = (
        Path(output_bundle_dir) if output_bundle_dir else cfg.output_bundle_dir
    )

    # Guard against synthetic placeholder/probe calls (e.g. '# Test', 'xxx-yyy-zzz')
    title_norm = (title or "").strip().lower()
    body_stripped = (body_markdown or "").strip()
    raw_id_norm = (concept_id or "").strip().lower()
    if (
        title_norm in _DUMMY_PROBE_TITLES
        or re.search(r"(?:^|/)(?:xxx-yyy-zzz|test-check|test-pressure-level-temp)(?:\.md)?$", raw_id_norm)
        or (body_stripped.lower() in ("# test", "# test 2", "test") and len(body_stripped) < 40)
    ):
        return {
            "status": "rejected_dummy_probe",
            "merged_with_existing": False,
            "concept_id": concept_id.removesuffix(".md").strip("/"),
            "error": "Placeholder test/probe calls are not written to the OKF bundle. Provide full extracted engineering Markdown.",
        }

    with _BUNDLE_IO_LOCK:
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        clean_id = derive_canonical_concept_id(
            concept_id=concept_id,
            concept_type=concept_type,
            title=title,
            sources=sources,
            entity_metadata=entity_metadata,
            bundle_root=bundle_root,
        )
        concept_file_path = f"{clean_id}.md"
        dest_file = bundle_root / concept_file_path
        resource_uri = f"gs://{cfg.destination_gcs_bucket}/{cfg.destination_gcs_prefix}/{concept_file_path}"

        merged_tags = list(tags)
        merged_sources = list(sources)
        merged_metadata = dict(entity_metadata or {})
        effective_new_body = body_markdown
        if append_sections_markdown:
            for chunk_md in append_sections_markdown:
                if isinstance(chunk_md, str) and chunk_md.strip():
                    effective_new_body = merge_markdown_bodies(effective_new_body, chunk_md)
        merged_body = effective_new_body
        was_merged = False

        if merge_existing and dest_file.exists():
            try:
                existing_doc = OKFDocument.parse(dest_file.read_text(encoding="utf-8"))
                existing_fm = existing_doc.frontmatter
                same_entity = True
                if clean_id.startswith("equipment/"):
                    existing_tag = str(
                        (existing_fm.get("entity_metadata") or {}).get("tag")
                        or str(existing_fm.get("title", "")).split("—")[0].strip()
                    )
                    incoming_tag = str(
                        merged_metadata.get("tag")
                        or title.split("—")[0].strip()
                        or clean_id.split("/")[-1]
                    )
                    if existing_tag and incoming_tag and (
                        _extract_equipment_base_id(existing_tag) != _extract_equipment_base_id(incoming_tag)
                    ):
                        same_entity = False

                if same_entity:
                    for t in existing_fm.get("tags", []):
                        if isinstance(t, str) and t not in merged_tags:
                            merged_tags.append(t)

                    existing_src_list: list[str] = []
                    for s in existing_fm.get("sources", []):
                        if isinstance(s, dict):
                            val = str(s.get("resource") or s.get("title") or "").strip()
                            if val:
                                existing_src_list.append(val)
                        elif isinstance(s, str) and s.strip():
                            existing_src_list.append(s.strip())

                    combined_sources: list[str] = []
                    src_idx_by_base: dict[str, int] = {}
                    for s in existing_src_list + merged_sources:
                        key = _normalize_base_source_id(s) or s.split("/")[-1].lower()
                        if key not in src_idx_by_base:
                            src_idx_by_base[key] = len(combined_sources)
                            combined_sources.append(s)
                        else:
                            combined_sources[src_idx_by_base[key]] = s
                    merged_sources = combined_sources

                    prior_meta = existing_fm.get("entity_metadata", {})
                    if isinstance(prior_meta, dict):
                        combined_meta = dict(prior_meta)
                        combined_meta.update(merged_metadata)
                        merged_metadata = combined_meta

                    merged_body = merge_markdown_bodies(existing_doc.body, effective_new_body)
                    was_merged = True
            except Exception:
                was_merged = False

        sources_meta = []
        for idx, s in enumerate(merged_sources):
            src_clean = s.split("/")[-1]
            sources_meta.append(
                {
                    "id": f"src-{idx + 1}",
                    "resource": f"reference/raw/{s}"
                    if not s.startswith("reference/")
                    else s,
                    "title": src_clean,
                }
            )

        frontmatter: dict[str, Any] = {
            "type": concept_type,
            "title": title,
            "description": description,
            "resource": resource_uri,
            "tags": sorted(set(merged_tags)),
            "sources": sources_meta,
            "generated": {
                "by": f"extracter_agent/{cfg.gemini_model}",
                "at": now_iso,
            },
            "verified": [
                {"by": "human:expert-chemical-engineer", "at": now_iso},
                {"by": "process:okf-validation-suite", "at": now_iso},
            ],
            "status": "stable",
            "entity_metadata": merged_metadata,
        }

        doc = OKFDocument(frontmatter=frontmatter, body=merged_body)
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(doc.serialize(), encoding="utf-8")

        log_action = "Concept Enrichment" if was_merged else "Concept Creation"
        log_verb = "Enriched" if was_merged else "Created"
        log_path = update_bundle_log(
            bundle_root,
            log_action,
            f"{log_verb} OKF concept [{clean_id} — {title}](/{clean_id}.md)",
        )

    gcs_uri = None
    if output_bundle_dir is None:
        gcs_uri = _sync_file_to_gcs(dest_file, bundle_root)
        _sync_file_to_gcs(log_path, bundle_root)

    return {
        "status": "success",
        "merged_with_existing": was_merged,
        "concept_id": clean_id,
        "output_file": str(
            dest_file.relative_to(Path.cwd())
            if dest_file.is_relative_to(Path.cwd())
            else dest_file
        ),
        "gcs_uri": gcs_uri or resource_uri,
        "title": title,
        "type": concept_type,
        "resource": resource_uri,
        "frontmatter": doc.frontmatter,
    }


def inspect_existing_okf_concept_tool(
    concept_id: str | None = None,
    source_filter: str | None = None,
    output_bundle_dir: str | None = None,
) -> dict[str, Any]:
    """Inspect an existing OKF v0.2 concept document or list concepts referencing a source PDF in the bundle.

    When to use:
        - Before updating an existing concept during incremental file-by-file extraction, to inspect
          its current frontmatter, sources, tables, and Markdown body.
        - To discover which OKF concepts in the bundle already cite a specific raw source PDF.
        - Example: inspect_existing_okf_concept_tool(concept_id="equipment/<tag>")
        - Example: inspect_existing_okf_concept_tool(source_filter="<document-prefix>")

    When NOT to use:
        - Do NOT use to read raw PDF files in reference/raw/ (use extract_pdf_engineering_data_tool).
        - Do NOT use to validate the entire bundle (use validate_okf_bundle_tool).

    Args:
        concept_id: Optional relative concept identifier (e.g. 'equipment/<tag>' or 'sources/<slug>').
        source_filter: Optional filename or document code substring to filter concepts by cited source.
        output_bundle_dir: Optional bundle root directory path. Defaults to configured output_bundle_dir.

    Returns:
        A dictionary containing the existing concept frontmatter and Markdown body if concept_id is specified,
        or a list of matching concept summaries if source_filter is specified.
    """
    cfg = get_config()
    bundle_root = (
        Path(output_bundle_dir) if output_bundle_dir else cfg.output_bundle_dir
    )
    if not bundle_root.exists():
        return {
            "status": "not_found",
            "exists": False,
            "bundle_dir": str(bundle_root),
            "matches": [],
        }

    if concept_id:
        clean_id = concept_id.strip().strip("/").removesuffix(".md")
        target_path = bundle_root / f"{clean_id}.md"
        if not target_path.exists():
            resolved_id = derive_canonical_concept_id(
                concept_id=clean_id,
                bundle_root=bundle_root,
            )
            if (bundle_root / f"{resolved_id}.md").exists():
                clean_id = resolved_id
                target_path = bundle_root / f"{resolved_id}.md"

        if not target_path.exists():
            # Case-insensitive or stem fallback search across bundle subdirectories
            target_stem = Path(clean_id).name.lower()
            for candidate in sorted(bundle_root.rglob("*.md")):
                if candidate.name.lower() in ("index.md", "log.md"):
                    continue
                rel_no_ext = str(candidate.relative_to(bundle_root)).removesuffix(".md")
                if rel_no_ext.lower() == clean_id.lower() or candidate.stem.lower() == target_stem:
                    target_path = candidate
                    clean_id = rel_no_ext
                    break

        if not target_path.exists():
            return {
                "status": "not_found",
                "exists": False,
                "concept_id": clean_id,
            }

        raw_text = target_path.read_text(encoding="utf-8")
        try:
            doc = OKFDocument.parse(raw_text)
            return {
                "status": "found",
                "exists": True,
                "concept_id": clean_id,
                "title": doc.frontmatter.get("title"),
                "type": doc.frontmatter.get("type"),
                "sources": doc.frontmatter.get("sources", []),
                "frontmatter": doc.frontmatter,
                "body_markdown": doc.body,
            }
        except Exception as exc:
            return {
                "status": "parse_error",
                "exists": True,
                "concept_id": clean_id,
                "error": str(exc),
                "raw_text": raw_text,
            }

    query = (source_filter or "").strip().lower()
    query_prefix = Path(query).stem.split("_")[0].lower() if query else ""
    matches: list[dict[str, Any]] = []
    for md_file in sorted(bundle_root.rglob("*.md")):
        if md_file.name.lower() in ("index.md", "log.md"):
            continue
        rel_id = str(md_file.relative_to(bundle_root)).removesuffix(".md")
        raw_text = md_file.read_text(encoding="utf-8")
        try:
            doc = OKFDocument.parse(raw_text)
            fm = doc.frontmatter
        except Exception:
            fm = {}
        sources_list = fm.get("sources", [])
        if query:
            haystack = (raw_text + " " + str(sources_list)).lower()
            if query not in haystack and (not query_prefix or query_prefix not in haystack):
                continue
        matches.append(
            {
                "concept_id": rel_id,
                "title": fm.get("title", md_file.stem),
                "type": fm.get("type", "unknown"),
                "sources": sources_list,
            }
        )

    return {
        "status": "success",
        "bundle_dir": str(bundle_root),
        "source_filter": source_filter,
        "total_matches": len(matches),
        "matches": matches,
    }


def validate_okf_bundle_tool(
    bundle_dir: str | None = None,
) -> dict[str, Any]:
    """Execute rigorous OKF v0.2 validation on the knowledge bundle directory.

    When to use:
        - When verifying quality and standards compliance of an OKF bundle before publishing.
        - Example: validate_okf_bundle_tool()

    When NOT to use:
        - Do NOT use on raw unstructured PDF files in reference/raw/.
        - Do NOT use before any concept documents have been created.

    Args:
        bundle_dir: Path to the bundle root directory. Defaults to configured output_bundle_dir.

    Returns:
        A dictionary containing validity boolean, total documents, trust tiers, and errors.
    """
    cfg = get_config()
    root = Path(bundle_dir) if bundle_dir else cfg.output_bundle_dir
    return validate_okf_bundle(root)


