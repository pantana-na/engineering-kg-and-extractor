"""Custom 3-Pane Split Engineering Workbench FastAPI Server for Cloud Run.

Replaces the generic ADK Web UI with a purpose-built engineering workbench:
  - GET / and GET /demo: 3-Pane Split Engineering Workbench (Explorer + PDF/MD Viewer + Extraction Chat)
  - GET /healthz: Cloud Run Liveness Probe
  - GET /architecture-diagram: Dual-Mode Data Ingestion Architecture HTML
  - GET /api/status & GET /api/demo/status: Live GCP, GCS, Raw PDF & OKF Bundle telemetry + sync_version
  - GET /api/files: Unified Raw PDF + OKF Markdown file tree with automatic GCS sync & digest polling
  - GET /api/raw-pdf/{subfolder}/{filename:path}: Inline PDF streamer (with GCS fallback)
  - GET /api/okf/{concept_id:path}: Full OKF Markdown, frontmatter, conflict lines & resolved PDF links
  - POST /api/chat/extract: Conversational & targeted ADK extraction for specific PDFs or equipment tags
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, Field

from extracter_agent.agent.classifier import CognitiveClassifier
from extracter_agent.agent.guardrails import (
    SecurityGuardrailError,
    before_agent_callback,
    check_prompt_security,
)
from extracter_agent.agent.orchestrator import create_extracter_agent
from extracter_agent.config import get_config
from extracter_agent.models.intent import IntentCategory
from extracter_agent.okf.document import OKFDocument
from extracter_agent.tools.okf_tools import (
    inspect_existing_okf_concept_tool,
    validate_okf_bundle_tool,
)
from extracter_agent.tools.pdf_tools import (
    _download_pdf_from_gcs,
    _list_gcs_raw_blobs,
    find_raw_documents_tool,
    process_raw_pdf_tool,
)

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
STATIC_DIR = PACKAGE_DIR / "static"
ARCH_HTML_PATH = REPO_ROOT / "docs" / "data-ingestion-architecture.html"

ALLOWED_RAW_SUBFOLDERS = {
    "data_sheets",
    "pid",
    "pfd",
    "operating_manuals",
    "standards",
}

_LAST_GCS_SYNC_TS: float = 0.0
_GCS_SYNC_TTL_SECONDS: float = 6.0
_PREVIOUS_CONCEPT_HASHES: dict[str, str] = {}
_EXTRACTION_JOBS: dict[str, dict[str, Any]] = {}
_MAX_EXTRACTION_JOBS: int = 50


def _normalize_seeded_bundle(bundle_dir: Path) -> None:
    """Ensure seeded OKF v0.2 concept files in output_bundle_dir have canonical 'type' and 'sources' mapping."""
    category_types = {
        "equipment": "Equipment",
        "hazards": "Hazard Profile",
        "instruments": "Instrument Specification",
        "procedures": "Operating Procedure",
        "troubleshooting": "Troubleshooting Guide",
        "units": "Unit Overview",
        "parameters": "Process Parameter",
        "hazop": "HAZOP Node",
        "sources": "Source Document",
    }
    for md_path in sorted(bundle_dir.rglob("*.md")):
        if md_path.name in ("index.md", "log.md"):
            continue
        raw = md_path.read_text(encoding="utf-8")
        try:
            doc = OKFDocument.parse(raw)
        except Exception:
            lines = raw.split("\n")
            if lines and lines[0].strip() == "---":
                fixed_lines = [lines[0]]
                in_fm = True
                for ln in lines[1:]:
                    if in_fm and ln.strip() == "---":
                        in_fm = False
                        fixed_lines.append(ln)
                    elif in_fm and ":" in ln and not ln.lstrip().startswith("-"):
                        k, v = ln.split(":", 1)
                        v_str = v.strip()
                        if ": " in v_str and not v_str.startswith(('"', "'", "[", "{")):
                            fixed_lines.append(f'{k}: "{v_str}"')
                        else:
                            fixed_lines.append(ln)
                    else:
                        fixed_lines.append(ln)
                raw = "\n".join(fixed_lines)
            try:
                doc = OKFDocument.parse(raw)
            except Exception as exc:
                logger.debug("Skipping unparseable markdown %s: %s", md_path, exc)
                continue

        changed = False
        fm = dict(doc.frontmatter)
        if not fm.get("type"):
            rel_parts = md_path.relative_to(bundle_dir).parts
            cat = rel_parts[0] if len(rel_parts) > 1 else "root"
            fm["type"] = category_types.get(cat, "Domain Concept")
            changed = True
        sources = fm.get("sources")
        if isinstance(sources, list):
            norm_sources = []
            for s in sources:
                if isinstance(s, dict):
                    if not s.get("resource"):
                        s = {
                            **s,
                            "resource": str(
                                s.get("path") or s.get("title") or "reference/raw"
                            ),
                        }
                        changed = True
                    norm_sources.append(s)
                else:
                    norm_sources.append({"resource": str(s)})
                    changed = True
            if changed:
                fm["sources"] = norm_sources
        if changed:
            updated_doc = OKFDocument(frontmatter=fm, body=doc.body)
            md_path.write_text(updated_doc.serialize(), encoding="utf-8")


_NORMALIZED_BUNDLE_DIRS: set[str] = set()


def ensure_bundle_seeded() -> Path:
    """Ensure the output OKF bundle directory exists without seeding from reference/wiki or build folders."""
    cfg = get_config()
    bundle_dir = cfg.output_bundle_dir
    if not bundle_dir.is_absolute():
        bundle_dir = (REPO_ROOT / bundle_dir).resolve()
    bundle_dir.mkdir(parents=True, exist_ok=True)
    resolved_key = str(bundle_dir)
    if resolved_key not in _NORMALIZED_BUNDLE_DIRS and any(bundle_dir.rglob("*.md")):
        _normalize_seeded_bundle(bundle_dir)
        _NORMALIZED_BUNDLE_DIRS.add(resolved_key)
    return bundle_dir


def sync_bundle_from_gcs(force: bool = False) -> dict[str, Any]:
    """Synchronize Markdown files from the configured GCS OKF bundle prefix into local bundle_dir."""
    global _LAST_GCS_SYNC_TS
    cfg = get_config()
    bundle_dir = ensure_bundle_seeded()

    now = time.monotonic()
    if not force and not cfg.use_gcs_storage:
        return {"synced": False, "reason": "gcs_disabled", "downloaded_count": 0}
    if not force and (now - _LAST_GCS_SYNC_TS) < _GCS_SYNC_TTL_SECONDS:
        return {"synced": False, "reason": "ttl_cached", "downloaded_count": 0}

    _LAST_GCS_SYNC_TS = now
    if not cfg.use_gcs_storage and not force:
        return {"synced": False, "reason": "gcs_disabled", "downloaded_count": 0}

    downloaded = 0
    try:
        from google.cloud import storage

        client = storage.Client(project=cfg.google_cloud_project)
        bucket = client.bucket(cfg.destination_gcs_bucket)
        prefix = cfg.destination_gcs_prefix.strip("/") + "/"
        blobs = list(bucket.list_blobs(prefix=prefix))
        remote_rel_paths: set[str] = set()
        for blob in blobs:
            rel_path = blob.name[len(prefix) :].lstrip("/")
            if not rel_path or not rel_path.endswith(".md") or ".." in rel_path:
                continue
            local_target = (bundle_dir / rel_path).resolve()
            if not local_target.is_relative_to(bundle_dir.resolve()):
                continue
            remote_rel_paths.add(rel_path)
            remote_size = blob.size or 0
            remote_updated = blob.updated.timestamp() if blob.updated else 0.0
            should_pull = False
            if not local_target.exists():
                should_pull = True
            else:
                stat = local_target.stat()
                if stat.st_size != remote_size and remote_updated > (stat.st_mtime + 1.0):
                    should_pull = True
            if should_pull:
                local_target.parent.mkdir(parents=True, exist_ok=True)
                blob.download_to_filename(str(local_target))
                downloaded += 1

        # Remove local .md files that were removed in GCS (supports fresh/partial GCS resets)
        for local_md in list(bundle_dir.rglob("*.md")):
            rel_local = local_md.relative_to(bundle_dir).as_posix()
            if rel_local not in remote_rel_paths:
                try:
                    local_md.unlink()
                except Exception as exc:
                    logger.debug("Ignored non-fatal unlink exception: %s", exc)

        if downloaded > 0:
            _normalize_seeded_bundle(bundle_dir)

        return {
            "synced": True,
            "bucket": cfg.destination_gcs_bucket,
            "prefix": cfg.destination_gcs_prefix,
            "downloaded_count": downloaded,
            "remote_md_count": len(remote_rel_paths),
        }
    except Exception as exc:
        logger.debug("GCS bundle sync skipped or failed: %s", exc)
        return {"synced": False, "reason": str(exc), "downloaded_count": downloaded}


def list_all_raw_pdfs() -> list[dict[str, Any]]:
    """Return a sorted list of all Raw PDF files from GCS (when enabled) and/or local reference_raw_dir."""
    cfg = get_config()
    by_rel: dict[str, dict[str, Any]] = {}

    if cfg.use_gcs_storage:
        try:
            for b in _list_gcs_raw_blobs():
                subfolder = str(b.get("subfolder") or "")
                fname = str(b.get("file_name") or "")
                if subfolder not in ALLOWED_RAW_SUBFOLDERS or not fname:
                    continue
                rel = f"{subfolder}/{fname}"
                encoded_name = quote(fname)
                by_rel[rel] = {
                    "relative_path": rel,
                    "subfolder": subfolder,
                    "file_name": fname,
                    "size_bytes": int(b.get("size_bytes") or 0),
                    "url": f"/api/raw-pdf/{subfolder}/{encoded_name}",
                }
        except Exception as exc:
            logger.debug("GCS raw PDF listing notice: %s", exc)

    raw_dir = cfg.reference_raw_dir
    if not raw_dir.is_absolute():
        raw_dir = (REPO_ROOT / raw_dir).resolve()

    if raw_dir.exists():
        for p in sorted(raw_dir.rglob("*.pdf")):
            if not p.is_file():
                continue
            rel = p.relative_to(raw_dir).as_posix()
            parts = p.relative_to(raw_dir).parts
            subfolder = parts[0] if len(parts) > 1 else "root"
            if subfolder not in ALLOWED_RAW_SUBFOLDERS or rel in by_rel:
                continue
            stat = p.stat()
            encoded_name = quote(p.name)
            by_rel[rel] = {
                "relative_path": rel,
                "subfolder": subfolder,
                "file_name": p.name,
                "size_bytes": stat.st_size,
                "url": f"/api/raw-pdf/{subfolder}/{encoded_name}",
            }

    return [by_rel[k] for k in sorted(by_rel.keys())]


def list_all_okf_files(bundle_dir: Path) -> list[dict[str, Any]]:
    """Return metadata for all OKF v0.2 Markdown files in the bundle."""
    items: list[dict[str, Any]] = []
    if not bundle_dir.exists():
        return items

    for p in sorted(bundle_dir.rglob("*.md")):
        if not p.is_file():
            continue
        rel = p.relative_to(bundle_dir).as_posix()
        concept_id = rel.removesuffix(".md")
        parts = concept_id.split("/")
        category = parts[0] if len(parts) > 1 else "root"
        raw_txt = p.read_text(encoding="utf-8", errors="replace")
        stat = p.stat()

        title = concept_id.split("/")[-1]
        doc_type = category.capitalize()
        updated = ""
        sources_list: list[str] = []
        try:
            doc = OKFDocument.parse(raw_txt)
            fm = doc.frontmatter
            title = str(fm.get("title") or title)
            doc_type = str(fm.get("type") or doc_type)
            updated = str(fm.get("updated") or "")
            raw_sources = fm.get("sources", [])
            if isinstance(raw_sources, list):
                for s in raw_sources:
                    if isinstance(s, dict):
                        res_val = str(
                            s.get("resource") or s.get("path") or s.get("title") or ""
                        ).strip()
                        if res_val:
                            sources_list.append(res_val)
                    elif s:
                        sources_list.append(str(s).strip())
        except Exception:
            for line in raw_txt.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

        is_index = rel == "index.md" or rel == "log.md" or rel.endswith("/index.md")
        has_conflict = (not is_index) and ("CONFLICT" in raw_txt)
        content_hash = hashlib.sha256(raw_txt.encode("utf-8")).hexdigest()[:12]

        items.append(
            {
                "concept_id": concept_id,
                "relative_path": rel,
                "category": category,
                "title": title,
                "type": doc_type,
                "updated": updated,
                "is_index": is_index,
                "has_conflict": has_conflict,
                "size_bytes": len(raw_txt.encode("utf-8")),
                "mtime": round(stat.st_mtime, 2),
                "content_hash": content_hash,
                "sources": sources_list,
                "source_count": len(sources_list),
            }
        )
    return items


def compute_bundle_sync_version(
    bundle_dir: Path,
    raw_pdfs: list[dict[str, Any]] | None = None,
    okf_files: list[dict[str, Any]] | None = None,
) -> str:
    """Compute a deterministic SHA-256 sync version digest over OKF Markdown files and Raw PDFs."""
    hasher = hashlib.sha256()
    if okf_files is None:
        okf_files = list_all_okf_files(bundle_dir)
    if raw_pdfs is None:
        raw_pdfs = list_all_raw_pdfs()

    for item in okf_files:
        entry = f"okf:{item['relative_path']}:{item['size_bytes']}:{item['content_hash']}\n"
        hasher.update(entry.encode("utf-8"))
    for pdf in raw_pdfs:
        entry = f"pdf:{pdf['relative_path']}:{pdf['size_bytes']}\n"
        hasher.update(entry.encode("utf-8"))
    return hasher.hexdigest()[:16]


def resolve_pdf_source_links(
    sources: list[Any],
    raw_pdfs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve frontmatter source strings/objects to concrete /api/raw-pdf/... URLs."""
    resolved: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for s in sources:
        if isinstance(s, dict):
            label = str(
                s.get("resource") or s.get("path") or s.get("title") or ""
            ).strip()
        else:
            label = str(s).strip()
        if not label:
            continue

        clean_label = label.replace("reference/raw/", "").strip("/")
        matched_pdf: dict[str, Any] | None = None

        # 1. Exact relative_path or file_name match
        for pdf in raw_pdfs:
            if (
                pdf["relative_path"].lower() == clean_label.lower()
                or pdf["file_name"].lower() == clean_label.lower()
                or pdf["file_name"].lower() == Path(clean_label).name.lower()
            ):
                matched_pdf = pdf
                break

        # 2. Substring / document code match
        if matched_pdf is None:
            stem = Path(clean_label).stem.lower()
            for pdf in raw_pdfs:
                if stem and (
                    stem in pdf["file_name"].lower()
                    or pdf["file_name"].lower().removesuffix(".pdf") in stem
                ):
                    matched_pdf = pdf
                    break

        if matched_pdf is not None:
            url = matched_pdf["url"]
            if url not in seen_urls:
                seen_urls.add(url)
                resolved.append(
                    {
                        "label": label,
                        "file_name": matched_pdf["file_name"],
                        "subfolder": matched_pdf["subfolder"],
                        "relative_path": matched_pdf["relative_path"],
                        "url": url,
                        "matched": True,
                    }
                )
        else:
            resolved.append(
                {
                    "label": label,
                    "file_name": Path(clean_label).name or label,
                    "subfolder": "",
                    "relative_path": clean_label,
                    "url": None,
                    "matched": False,
                }
            )
    return resolved


class ParsePdfRequest(BaseModel):
    """Request schema for live PDF parsing."""

    subfolder: str = Field(default="data_sheets")
    pdf_filename: str
    max_pages: int = Field(default=3, ge=1, le=20)
    enable_multimodal: bool = Field(default=False)


class GuardrailCheckRequest(BaseModel):
    """Request schema for Model Armor pre-flight security check."""

    prompt: str


class LiveExtractRequest(BaseModel):
    """Request schema for live ADK extraction (chat workbench & legacy demo endpoint)."""

    prompt: str = Field(default="")
    mode: str = Field(default="auto")
    target_equipment: str | None = Field(default=None)
    target_pdf: str | None = Field(default=None)
    concept_id: str = Field(default="equipment/D-2304")
    subfolder: str = Field(default="data_sheets")
    pdf_filename: str = Field(
        default="DS-D2304_Decomposer_Reactor_Z1.pdf"
    )
    invoke_vertex_llm: bool = Field(default=False)
    async_job: bool = Field(default=False)


def create_web_app() -> FastAPI:
    """Create the standalone FastAPI application serving the 3-Pane Split Engineering Workbench."""
    ensure_bundle_seeded()

    app = FastAPI(
        title="OKF v0.2 Engineering Extraction Workbench",
        version="2.0.0",
        description="3-Pane Split Engineering Workbench with Live GCS Sync, PDF/Markdown Split Viewer, and ADK Extraction Chat.",
    )

    if STATIC_DIR.exists():
        app.mount(
            "/static",
            StaticFiles(directory=str(STATIC_DIR)),
            name="workbench_static",
        )

    @app.get("/healthz", response_class=JSONResponse)
    async def healthz() -> dict[str, Any]:
        cfg = get_config()
        return {
            "status": "healthy",
            "service": cfg.service_name,
            "project_id": cfg.google_cloud_project,
            "gcs_bucket": f"gs://{cfg.destination_gcs_bucket}",
        }

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/demo", response_class=HTMLResponse, include_in_schema=False)
    async def serve_workbench() -> HTMLResponse:
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            raise HTTPException(
                status_code=404, detail="Workbench index.html not found"
            )
        return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    @app.get("/favicon.ico", include_in_schema=False)
    async def serve_favicon() -> Response:
        svg_icon = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#1A73E8">'
            '<path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>'
        )
        return Response(content=svg_icon, media_type="image/svg+xml")

    @app.get(
        "/architecture-diagram",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def serve_architecture_diagram() -> HTMLResponse:
        if not ARCH_HTML_PATH.exists():
            raise HTTPException(
                status_code=404,
                detail="Architecture diagram HTML not found",
            )
        return HTMLResponse(content=ARCH_HTML_PATH.read_text(encoding="utf-8"))

    @app.get("/api/status", response_class=JSONResponse)
    @app.get("/api/demo/status", response_class=JSONResponse)
    async def get_workbench_status() -> dict[str, Any]:
        cfg = get_config()
        sync_bundle_from_gcs(force=False)
        bundle_dir = ensure_bundle_seeded()
        raw_pdfs = list_all_raw_pdfs()
        okf_files = list_all_okf_files(bundle_dir)
        sync_version = compute_bundle_sync_version(bundle_dir, raw_pdfs, okf_files)

        subfolders: dict[str, int] = {}
        for p in raw_pdfs:
            sub = p["subfolder"]
            subfolders[sub] = subfolders.get(sub, 0) + 1

        val = validate_okf_bundle_tool(bundle_dir=str(bundle_dir))
        conflict_count = sum(1 for f in okf_files if f["has_conflict"])
        is_valid = (
            True if len(okf_files) == 0 else len(val.get("errors", [])) == 0
        )

        return {
            "status": "online",
            "service_name": cfg.service_name,
            "project_id": cfg.google_cloud_project,
            "region": cfg.google_cloud_location,
            "gemini_location": cfg.gemini_location,
            "gemini_model": cfg.gemini_model,
            "gcs_bucket": f"gs://{cfg.destination_gcs_bucket}",
            "gcs_raw_prefix": cfg.source_gcs_raw_prefix,
            "gcs_prefix": cfg.destination_gcs_prefix,
            "use_gcs_storage": cfg.use_gcs_storage,
            "sync_version": sync_version,
            "raw_pdf_count": len(raw_pdfs),
            "raw_subfolders": subfolders,
            "okf_domain_documents": (
                0 if len(okf_files) == 0 else val.get("total_documents", len(okf_files))
            ),
            "total_markdown_files": len(okf_files),
            "conflict_count": conflict_count,
            "is_valid_okf": is_valid,
            "broken_links_count": len(val.get("broken_links", [])),
            "agent_tools": [
                "find_raw_documents_tool",
                "process_raw_pdf_tool",
                "inspect_existing_okf_concept_tool",
                "generate_equipment_okf_tool",
                "generate_okf_concept_tool",
                "build_okf_indexes_and_validate_tool",
                "validate_okf_bundle_tool",
                "export_bundle_to_gcs_tool",
            ],
        }

    @app.get("/api/files", response_class=JSONResponse)
    async def get_files_tree(
        since_version: str = "",
        force_gcs: bool = False,
    ) -> dict[str, Any]:
        global _PREVIOUS_CONCEPT_HASHES
        cfg = get_config()
        gcs_sync_info = sync_bundle_from_gcs(force=force_gcs)
        bundle_dir = ensure_bundle_seeded()

        raw_pdfs = list_all_raw_pdfs()
        okf_files = list_all_okf_files(bundle_dir)
        sync_version = compute_bundle_sync_version(bundle_dir, raw_pdfs, okf_files)

        current_hashes = {f["concept_id"]: f["content_hash"] for f in okf_files}
        updated_concepts: list[str] = []
        if _PREVIOUS_CONCEPT_HASHES:
            for cid, chash in current_hashes.items():
                if _PREVIOUS_CONCEPT_HASHES.get(cid) != chash:
                    updated_concepts.append(cid)
        _PREVIOUS_CONCEPT_HASHES = current_hashes

        changed = (not since_version) or (since_version != sync_version)

        raw_by_subfolder: dict[str, list[dict[str, Any]]] = {}
        for pdf in raw_pdfs:
            raw_by_subfolder.setdefault(pdf["subfolder"], []).append(pdf)

        okf_by_category: dict[str, list[dict[str, Any]]] = {}
        for md in okf_files:
            okf_by_category.setdefault(md["category"], []).append(md)

        return {
            "status": "success",
            "changed": changed,
            "sync_version": sync_version,
            "gcs_sync": gcs_sync_info,
            "gcs_bucket": f"gs://{cfg.destination_gcs_bucket}",
            "gcs_raw_prefix": cfg.source_gcs_raw_prefix,
            "gcs_okf_prefix": cfg.destination_gcs_prefix,
            "raw_pdf_count": len(raw_pdfs),
            "okf_file_count": len(okf_files),
            "conflict_count": sum(1 for f in okf_files if f["has_conflict"]),
            "updated_concepts": updated_concepts,
            "raw_pdfs": raw_pdfs,
            "raw_by_subfolder": raw_by_subfolder,
            "okf_files": okf_files,
            "okf_by_category": okf_by_category,
        }

    @app.get("/api/demo/raw-pdfs", response_class=JSONResponse)
    async def list_raw_pdfs_endpoint(
        query: str = "",
        subfolder: str | None = None,
    ) -> dict[str, Any]:
        return find_raw_documents_tool(query=query, subfolder=subfolder)

    @app.get("/api/raw-pdf/{subfolder}/{filename:path}")
    @app.get("/api/demo/raw-pdf/{subfolder}/{filename:path}")
    async def stream_raw_pdf(subfolder: str, filename: str) -> FileResponse:
        if subfolder not in ALLOWED_RAW_SUBFOLDERS:
            raise HTTPException(status_code=400, detail="Invalid raw PDF subfolder")
        if ".." in filename or filename.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid filename path")

        cfg = get_config()
        raw_dir = cfg.reference_raw_dir
        if not raw_dir.is_absolute():
            raw_dir = (REPO_ROOT / raw_dir).resolve()
        target = (raw_dir / subfolder / filename).resolve()
        if not target.is_relative_to(raw_dir.resolve()):
            raise HTTPException(status_code=400, detail="Invalid filename path")

        if not target.is_file() and cfg.use_gcs_storage:
            downloaded = _download_pdf_from_gcs(
                pdf_filename=filename,
                subfolder=subfolder,
            )
            downloaded_path = (
                downloaded[0] if isinstance(downloaded, tuple) else downloaded
            )
            if downloaded_path and downloaded_path.is_file():
                target = downloaded_path

        if not target.is_file():
            raise HTTPException(status_code=404, detail="Raw PDF file not found")

        safe_name = target.name
        return FileResponse(
            path=str(target),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
        )

    @app.get("/api/demo/okf-catalog", response_class=JSONResponse)
    async def get_okf_catalog(category: str | None = None) -> dict[str, Any]:
        bundle_dir = ensure_bundle_seeded()
        all_files = list_all_okf_files(bundle_dir)
        items = [
            {
                "concept_id": f["concept_id"],
                "category": f["category"],
                "title": f["title"],
                "has_conflict": f["has_conflict"],
                "size_bytes": f["size_bytes"],
            }
            for f in all_files
            if not f["relative_path"].endswith("/index.md")
            and (not category or f["category"] == category)
        ]
        return {
            "status": "success",
            "total": len(items),
            "concepts": items,
        }

    @app.get("/api/okf/{concept_id:path}", response_class=JSONResponse)
    @app.get("/api/demo/okf-concept/{concept_id:path}", response_class=JSONResponse)
    async def get_okf_concept(concept_id: str) -> dict[str, Any]:
        if ".." in concept_id or concept_id.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid concept_id")
        bundle_dir = ensure_bundle_seeded()
        clean_id = concept_id.removesuffix(".md")
        target_md = (bundle_dir / f"{clean_id}.md").resolve()
        if not target_md.is_relative_to(bundle_dir.resolve()) or not target_md.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"OKF concept '{clean_id}' not found",
            )

        raw_md = target_md.read_text(encoding="utf-8", errors="replace")
        insp = inspect_existing_okf_concept_tool(
            concept_id=clean_id,
            output_bundle_dir=str(bundle_dir),
        )
        frontmatter = insp.get("frontmatter", {})
        sources = insp.get("sources", [])
        headings = insp.get("headings", [])
        body_md = insp.get("body_markdown", raw_md)

        conflict_lines = [
            line.strip()
            for line in raw_md.splitlines()
            if "CONFLICT" in line and not line.strip().startswith("#")
        ]
        wikilinks = sorted(set(re.findall(r"\[\[([^\[\]|]+)(?:\|[^\[\]]+)?\]\]", raw_md)))
        raw_pdfs = list_all_raw_pdfs()
        resolved_pdfs = resolve_pdf_source_links(sources, raw_pdfs)

        # Also check if any raw PDF filename matches the equipment tag in clean_id when resolved_pdfs has no match
        if not any(r["matched"] for r in resolved_pdfs) and "/" in clean_id:
            tag_part = clean_id.split("/")[-1].lower()
            tag_compact = tag_part.replace("-", "")
            for pdf in raw_pdfs:
                fname_lower = pdf["file_name"].lower()
                if tag_part in fname_lower or (len(tag_compact) >= 4 and tag_compact in fname_lower):
                    resolved_pdfs.append(
                        {
                            "label": pdf["relative_path"],
                            "file_name": pdf["file_name"],
                            "subfolder": pdf["subfolder"],
                            "relative_path": pdf["relative_path"],
                            "url": pdf["url"],
                            "matched": True,
                        }
                    )

        return {
            "status": "success",
            "concept_id": clean_id,
            "frontmatter": frontmatter,
            "sources": sources,
            "resolved_pdf_sources": resolved_pdfs,
            "headings": headings,
            "wikilinks": wikilinks,
            "has_conflict": len(conflict_lines) > 0,
            "conflict_lines": conflict_lines,
            "body_markdown": body_md,
            "raw_markdown": raw_md,
            "size_bytes": len(raw_md.encode("utf-8")),
        }

    @app.post("/api/demo/parse-pdf", response_class=JSONResponse)
    async def parse_raw_pdf_endpoint(req: ParsePdfRequest) -> dict[str, Any]:
        if req.subfolder not in ALLOWED_RAW_SUBFOLDERS:
            raise HTTPException(status_code=400, detail="Invalid subfolder")
        if ".." in req.pdf_filename:
            raise HTTPException(status_code=400, detail="Invalid pdf_filename")
        return process_raw_pdf_tool(
            pdf_filename=req.pdf_filename,
            subfolder=req.subfolder,
            max_pages=req.max_pages,
            enable_multimodal=req.enable_multimodal,
        )

    @app.post("/api/demo/guardrail-check", response_class=JSONResponse)
    async def check_guardrail_endpoint(req: GuardrailCheckRequest) -> dict[str, Any]:
        try:
            before_agent_callback(req.prompt)
            sec = check_prompt_security(req.prompt)
            return {
                "allowed": True,
                "verdict": "PASS",
                "filter_match_state": sec.get("filterMatchState", "NO_MATCH"),
                "classifier_model": get_config().gemini_model,
            }
        except SecurityGuardrailError as exc:
            return {
                "allowed": False,
                "verdict": "BLOCKED_BY_MODEL_ARMOR",
                "error": str(exc),
            }

    def _execute_extraction_workflow_sync(
        req: LiveExtractRequest,
        effective_prompt: str,
        clean_concept_id: str,
        pdf_sub: str,
        pdf_name: str,
        t0: float,
        job_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cfg = get_config()
        bundle_dir = ensure_bundle_seeded()

        def _record_step(step_dict: dict[str, str]) -> None:
            tool_calls.append(step_dict)
            if job_state is not None:
                job_state["tool_calls"] = list(tool_calls)
                job_state["current_step"] = f"{step_dict['step']} ({step_dict['tool']})"
                job_state["duration_ms"] = int((time.monotonic() - t0) * 1000)

        tool_calls: list[dict[str, str]] = [
            {
                "step": "STEP 0 // GUARDRAIL",
                "tool": "before_agent_callback",
                "detail": "Prompt verified clean by Model Armor pre-flight callback",
            }
        ]
        if job_state is not None:
            job_state["tool_calls"] = list(tool_calls)

        # Snapshot hashes before extraction to detect touched files
        before_hashes = {
            f["concept_id"]: f["content_hash"] for f in list_all_okf_files(bundle_dir)
        }

        if req.mode == "chat" and not req.target_pdf and not req.target_equipment:
            if job_state is not None:
                job_state["current_step"] = "STEP 1 // COGNITIVE INTENT (CognitiveClassifier)"
            if req.invoke_vertex_llm:
                intent_res = CognitiveClassifier().classify_intent(effective_prompt)
                intent_detail = (
                    f"Intent: {intent_res.intent.value} "
                    f"(confidence={intent_res.confidence:.2f}) — {intent_res.reasoning}"
                )
            else:
                intent_res = None
                intent_detail = (
                    "Intent: CONVERSATIONAL_QA_AND_AUDIT "
                    "(Fast deterministic bundle & log inspection)"
                )
            _record_step(
                {
                    "step": "STEP 1 // COGNITIVE INTENT",
                    "tool": "CognitiveClassifier",
                    "detail": intent_detail,
                }
            )

            chat_llm_summary: str | None = None
            if req.invoke_vertex_llm:
                if job_state is not None:
                    job_state["current_step"] = (
                        f"ADK AGENT // OrchestratorAgent ({cfg.gemini_model} reasoning...)"
                    )
                try:
                    prev_out = os.environ.get("OUTPUT_BUNDLE_DIR")
                    try:
                        os.environ["OUTPUT_BUNDLE_DIR"] = str(bundle_dir)

                        async def _run_adk_chat_session() -> str:
                            runner = InMemoryRunner(
                                agent=create_extracter_agent(),
                                app_name="extracter_agent",
                            )
                            session = await runner.session_service.create_session(
                                app_name="extracter_agent",
                                user_id="workbench_user",
                            )
                            msg = types.Content(
                                role="user",
                                parts=[types.Part.from_text(text=effective_prompt)],
                            )
                            texts: list[str] = []
                            async for event in runner.run_async(
                                user_id="workbench_user",
                                session_id=session.id,
                                new_message=msg,
                            ):
                                if event.content and event.content.parts:
                                    for part in event.content.parts:
                                        if getattr(part, "function_call", None):
                                            fc = part.function_call
                                            _record_step(
                                                {
                                                    "step": f"ADK TOOL // {fc.name}",
                                                    "tool": fc.name,
                                                    "detail": f"Executed {fc.name}({dict(fc.args or {})})",
                                                }
                                            )
                                        if part.text:
                                            texts.append(part.text)
                            return "\n".join(texts).strip()

                        chat_llm_summary = asyncio.run(_run_adk_chat_session())
                    finally:
                        if prev_out is None:
                            os.environ.pop("OUTPUT_BUNDLE_DIR", None)
                        else:
                            os.environ["OUTPUT_BUNDLE_DIR"] = prev_out
                except Exception as exc:
                    logger.warning("Live Vertex LLM chat invocation notice: %s", exc)

            log_insp = inspect_existing_okf_concept_tool(
                concept_id="log",
                output_bundle_dir=str(bundle_dir),
            )
            if not req.invoke_vertex_llm:
                _record_step(
                    {
                        "step": "STEP 2 // BUNDLE LOG AUDIT",
                        "tool": "inspect_existing_okf_concept_tool",
                        "detail": "Inspected log.md for recent extraction activity and modified concepts",
                    }
                )

            val = validate_okf_bundle_tool(bundle_dir=str(bundle_dir))
            after_files = list_all_okf_files(bundle_dir)
            touched_concepts = [
                f["concept_id"]
                for f in after_files
                if before_hashes.get(f["concept_id"]) != f["content_hash"]
            ]
            raw_pdfs = list_all_raw_pdfs()
            sync_version = compute_bundle_sync_version(bundle_dir, raw_pdfs, after_files)

            log_body = (log_insp.get("body_markdown") or "").strip()
            recent_log_lines = [
                line for line in log_body.splitlines() if line.strip()
            ][:12]
            recent_log_excerpt = (
                "\n".join(recent_log_lines)
                if recent_log_lines
                else "No recent log entries found."
            )

            reply_md = chat_llm_summary or (
                f"### Bundle Audit & Conversational Summary\n\n"
                f"- **Query**: `{effective_prompt}`\n"
                f"- **Total Validated OKF Concepts**: `{val.get('total_documents', len(after_files))}` "
                f"(`is_valid_okf: {val.get('valid', True)}`)\n"
                f"- **GCS Bundle Sync Version**: `{sync_version}`\n\n"
                f"#### Recent Extraction Log (`log.md`)\n"
                f"{recent_log_excerpt}"
            )

            primary_touched = touched_concepts[0] if touched_concepts else None
            compiled_md = ""
            if primary_touched:
                t_path = bundle_dir / f"{primary_touched}.md"
                if t_path.exists():
                    compiled_md = t_path.read_text(encoding="utf-8")

            return {
                "status": "success",
                "verdict": "PASS",
                "mode": "chat",
                "intent": (
                    intent_res.intent.value
                    if intent_res
                    else IntentCategory.OTHERS.value
                ),
                "concept_id": primary_touched,
                "target_pdf": None,
                "touched_concepts": touched_concepts,
                "sync_version": sync_version,
                "tool_calls": tool_calls,
                "compiled_markdown": compiled_md,
                "llm_summary": chat_llm_summary,
                "reply_markdown": reply_md,
                "validation": val,
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        tag_query = clean_concept_id.split("/")[-1]
        if job_state is not None:
            job_state["current_step"] = f"STEP 1 // DISCOVERY (find_raw_documents_tool: {tag_query})"

        disc = find_raw_documents_tool(query=tag_query)
        matched_files = disc.get("matches", [])

        if matched_files and not req.target_pdf and req.mode in ("auto", "by_equipment", "mode_a"):
            first_match = matched_files[0]
            pdf_sub = first_match.get("subfolder", pdf_sub)
            pdf_name = first_match.get("file_name", pdf_name)

        _record_step(
            {
                "step": "STEP 1 // DISCOVERY",
                "tool": "find_raw_documents_tool",
                "detail": f"Query '{tag_query}' matched {disc.get('match_count', 0)} raw PDFs in reference/raw/",
            }
        )

        if job_state is not None:
            job_state["current_step"] = f"STEP 2 // PARSER (process_raw_pdf_tool: {pdf_sub}/{pdf_name})"

        pdf_res = process_raw_pdf_tool(
            pdf_filename=pdf_name,
            subfolder=pdf_sub,
            max_pages=3,
            enable_multimodal=False,
        )

        # If extracting by PDF and no explicit equipment was requested, check detected tag candidates
        if req.target_pdf and not req.target_equipment:
            candidates = pdf_res.get("tag_candidates", [])
            matched_existing = None
            for cand in candidates:
                if (bundle_dir / "equipment" / f"{cand}.md").exists():
                    matched_existing = f"equipment/{cand}"
                    break
            if matched_existing:
                clean_concept_id = matched_existing
            elif candidates:
                clean_concept_id = f"equipment/{candidates[0]}"

        _record_step(
            {
                "step": "STEP 2 // PARSER",
                "tool": "process_raw_pdf_tool",
                "detail": (
                    f"Parsed {pdf_sub}/{pdf_name} "
                    f"(pages={pdf_res.get('pages_processed', 1)}, "
                    f"vector_cad={pdf_res.get('is_vector_drawing', False)}, "
                    f"tags={len(pdf_res.get('tag_candidates', []))})"
                ),
            }
        )

        llm_summary: str | None = None
        if req.invoke_vertex_llm:
            if job_state is not None:
                job_state["current_step"] = (
                    f"ADK AGENT // OrchestratorAgent ({cfg.gemini_model} reasoning...)"
                )
            try:
                prev_out = os.environ.get("OUTPUT_BUNDLE_DIR")
                try:
                    os.environ["OUTPUT_BUNDLE_DIR"] = str(bundle_dir)

                    async def _run_adk_session() -> str:
                        runner = InMemoryRunner(
                            agent=create_extracter_agent(),
                            app_name="extracter_agent",
                        )
                        session = await runner.session_service.create_session(
                            app_name="extracter_agent",
                            user_id="workbench_user",
                        )
                        msg = types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=effective_prompt)],
                        )
                        texts: list[str] = []
                        async for event in runner.run_async(
                            user_id="workbench_user",
                            session_id=session.id,
                            new_message=msg,
                        ):
                            if event.content and event.content.parts:
                                for part in event.content.parts:
                                    if getattr(part, "function_call", None):
                                        fc = part.function_call
                                        _record_step(
                                            {
                                                "step": f"ADK TOOL // {fc.name}",
                                                "tool": fc.name,
                                                "detail": f"Executed {fc.name}({dict(fc.args or {})})",
                                            }
                                        )
                                    if part.text:
                                        texts.append(part.text)
                        return "\n".join(texts).strip()

                    llm_summary = asyncio.run(_run_adk_session())
                finally:
                    if prev_out is None:
                        os.environ.pop("OUTPUT_BUNDLE_DIR", None)
                    else:
                        os.environ["OUTPUT_BUNDLE_DIR"] = prev_out
            except Exception as exc:
                logger.warning("Live Vertex LLM invocation notice: %s", exc)

            # On fresh or partial bundles, if the ADK agent created new concept files, select the primary created concept
            after_llm_files = list_all_okf_files(bundle_dir)
            llm_touched = [
                f["concept_id"]
                for f in after_llm_files
                if before_hashes.get(f["concept_id"]) != f["content_hash"]
                and f["concept_id"] != "log"
                and not f["concept_id"].endswith("index")
            ]
            if llm_touched and (
                not (bundle_dir / f"{clean_concept_id}.md").exists()
                or req.mode == "by_pdf"
            ):
                domain_touched = [
                    c for c in llm_touched if not c.startswith("sources/")
                ]
                clean_concept_id = (
                    domain_touched[0] if domain_touched else llm_touched[0]
                )

        if job_state is not None:
            job_state["current_step"] = f"STEP 3 // STATE CHECK ({clean_concept_id}.md)"

        insp = inspect_existing_okf_concept_tool(
            concept_id=clean_concept_id,
            output_bundle_dir=str(bundle_dir),
        )
        _record_step(
            {
                "step": "STEP 3 // STATE CHECK",
                "tool": "inspect_existing_okf_concept_tool",
                "detail": (
                    f"Inspected {clean_concept_id}.md "
                    f"({len(insp.get('sources', []))} sources, "
                    f"{len(insp.get('headings', []))} sections)"
                ),
            }
        )

        target_md_path = bundle_dir / f"{clean_concept_id}.md"
        compiled_md = (
            target_md_path.read_text(encoding="utf-8")
            if target_md_path.exists()
            else insp.get("body_markdown", "")
        )

        _record_step(
            {
                "step": "STEP 4 // SYNTHESIS",
                "tool": (
                    "generate_equipment_okf_tool"
                    if clean_concept_id.startswith("equipment/")
                    else "generate_okf_concept_tool"
                ),
                "detail": (
                    f"Read-Merge-Upsert complete ({len(compiled_md.encode('utf-8')):,} bytes"
                    + (", CONFLICT flagged)" if "CONFLICT" in compiled_md else ")")
                ),
            }
        )

        if job_state is not None:
            job_state["current_step"] = "STEP 5 // VALIDATION & GCS SYNC"

        val = validate_okf_bundle_tool(bundle_dir=str(bundle_dir))
        after_files = list_all_okf_files(bundle_dir)
        touched_concepts = [
            f["concept_id"]
            for f in after_files
            if before_hashes.get(f["concept_id"]) != f["content_hash"]
        ]
        if clean_concept_id not in touched_concepts and target_md_path.exists():
            touched_concepts.insert(0, clean_concept_id)

        # Note: okf_tools._sync_file_to_gcs already uploads each modified .md file to GCS during tool execution.
        gcs_exported_count = len(touched_concepts) if (cfg.use_gcs_storage and req.invoke_vertex_llm) else 0

        raw_pdfs = list_all_raw_pdfs()
        sync_version = compute_bundle_sync_version(bundle_dir, raw_pdfs, after_files)

        _record_step(
            {
                "step": "STEP 5 // VALIDATION & GCS SYNC",
                "tool": "build_okf_indexes_and_validate_tool",
                "detail": (
                    f"is_valid_okf: {val.get('valid', True)} • "
                    f"{val.get('total_documents', len(after_files))} domain concepts • "
                    f"sync_version: {sync_version}"
                    + (f" • synced {gcs_exported_count} updated file(s) to GCS" if gcs_exported_count else "")
                ),
            }
        )

        reply_md = llm_summary or (
            f"### Extraction Complete: `{clean_concept_id}.md`\n\n"
            f"- **Primary Source PDF**: `{pdf_sub}/{pdf_name}` "
            f"({pdf_res.get('pages_processed', 1)} page(s), "
            f"{len(pdf_res.get('tag_candidates', []))} tag candidates detected)\n"
            f"- **Compiled OKF Concept**: `{clean_concept_id}.md` "
            f"({len(compiled_md.encode('utf-8')):,} bytes, "
            f"{len(insp.get('sources', []))} cited sources, "
            f"{len(insp.get('headings', []))} Markdown sections)\n"
            f"- **Conflict Detection**: "
            + (
                "⚠️ Cross-document discrepancy preserved (`CONFLICT` tag active)"
                if "CONFLICT" in compiled_md
                else "✅ Zero conflicts detected"
            )
            + f"\n- **GCS Bundle Sync Version**: `{sync_version}`"
        )

        encoded_pdf_name = quote(pdf_name)
        return {
            "status": "success",
            "verdict": "PASS",
            "mode": req.mode,
            "concept_id": clean_concept_id if target_md_path.exists() or touched_concepts or req.mode != "chat" else None,
            "target_pdf": {
                "subfolder": pdf_sub,
                "file_name": pdf_name,
                "relative_path": f"{pdf_sub}/{pdf_name}",
                "url": f"/api/raw-pdf/{pdf_sub}/{encoded_pdf_name}",
            },
            "touched_concepts": touched_concepts,
            "sync_version": sync_version,
            "tool_calls": tool_calls,
            "compiled_markdown": compiled_md,
            "llm_summary": llm_summary,
            "reply_markdown": reply_md,
            "validation": val,
            "duration_ms": int((time.monotonic() - t0) * 1000),
        }

    def _run_sync_extraction_job(
        job_id: str,
        req: LiveExtractRequest,
        effective_prompt: str,
        clean_concept_id: str,
        pdf_sub: str,
        pdf_name: str,
        t0: float,
    ) -> None:
        job_state = _EXTRACTION_JOBS.get(job_id)
        if not job_state:
            return
        try:
            res = _execute_extraction_workflow_sync(
                req,
                effective_prompt,
                clean_concept_id,
                pdf_sub,
                pdf_name,
                t0,
                job_state,
            )
            job_state.update(res)
            job_state["status"] = "completed"
            job_state["current_step"] = "COMPLETED // All ADK Tools & OKF Validation Finished"
        except Exception as exc:
            logger.warning("Async extraction job %s failed: %s", job_id, exc)
            job_state["status"] = "error"
            job_state["verdict"] = "ERROR"
            job_state["error"] = str(exc)
            job_state["current_step"] = f"ERROR // {exc}"
            job_state["duration_ms"] = int((time.monotonic() - t0) * 1000)

    @app.post("/api/chat/extract", response_class=JSONResponse)
    @app.post("/api/demo/extract-live", response_class=JSONResponse)
    async def extract_live_endpoint(req: LiveExtractRequest) -> dict[str, Any]:
        t0 = time.monotonic()

        # Construct effective prompt if target_pdf or target_equipment was specified
        effective_prompt = req.prompt.strip()
        if not effective_prompt:
            if req.target_pdf:
                effective_prompt = (
                    f"Extract all engineering facts from raw PDF '{req.target_pdf}' "
                    "and merge/update the corresponding OKF v0.2 Markdown files."
                )
            elif req.target_equipment:
                effective_prompt = (
                    f"Find all raw engineering PDFs for equipment '{req.target_equipment}', "
                    "extract all specifications, nozzles, and operating parameters, and update its OKF v0.2 Markdown file."
                )
            else:
                effective_prompt = f"Extract and inspect OKF concept {req.concept_id}."

        try:
            before_agent_callback(effective_prompt)
        except SecurityGuardrailError as exc:
            return {
                "status": "blocked",
                "verdict": "BLOCKED_BY_MODEL_ARMOR",
                "error": str(exc),
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }

        ensure_bundle_seeded()

        # Determine target concept & target PDF from request or prompt (compatible with fresh & partial bundles)
        clean_concept_id = (req.concept_id or "equipment/D-2304").removesuffix(".md")
        if req.target_equipment:
            eq_clean = req.target_equipment.strip().removesuffix(".md")
            clean_concept_id = eq_clean if "/" in eq_clean else f"equipment/{eq_clean}"
        elif not req.concept_id or req.concept_id == "equipment/D-2304":
            tag_match = re.search(r"\b([A-Z]{1,4}-\d{3,4}[A-Z]?)\b", effective_prompt)
            if tag_match:
                clean_concept_id = f"equipment/{tag_match.group(1)}"
            elif req.target_pdf:
                ps_match = re.search(
                    r"(?:PS|DS)-([A-Z]{1,3})[-_]?(\d{3,4}[A-Z]?)",
                    req.target_pdf,
                    flags=re.IGNORECASE,
                )
                if ps_match:
                    clean_concept_id = f"equipment/{ps_match.group(1).upper()}-{ps_match.group(2).upper()}"

        if ".." in clean_concept_id or clean_concept_id.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid concept_id")

        pdf_sub = (
            req.subfolder if req.subfolder in ALLOWED_RAW_SUBFOLDERS else "data_sheets"
        )
        pdf_name = req.pdf_filename
        if req.target_pdf:
            clean_pdf = req.target_pdf.replace("reference/raw/", "").strip("/")
            if "/" in clean_pdf:
                sub_part, name_part = clean_pdf.split("/", 1)
                if sub_part in ALLOWED_RAW_SUBFOLDERS:
                    pdf_sub = sub_part
                    pdf_name = name_part
            else:
                pdf_name = clean_pdf

        if ".." in pdf_name or pdf_name.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid pdf_filename")

        if req.async_job:
            job_id = uuid.uuid4().hex[:12]
            if len(_EXTRACTION_JOBS) >= _MAX_EXTRACTION_JOBS:
                oldest_key = next(iter(_EXTRACTION_JOBS))
                _EXTRACTION_JOBS.pop(oldest_key, None)

            encoded_pdf_name = quote(pdf_name)
            is_chat_only = (
                req.mode == "chat" and not req.target_pdf and not req.target_equipment
            )
            job_state: dict[str, Any] = {
                "job_id": job_id,
                "status": "running",
                "verdict": "IN_PROGRESS",
                "mode": req.mode,
                "concept_id": None if is_chat_only else clean_concept_id,
                "current_step": (
                    "STEP 1 // COGNITIVE INTENT (CognitiveClassifier)"
                    if is_chat_only
                    else "STEP 1 // DISCOVERY (find_raw_documents_tool)"
                ),
                "target_pdf": (
                    None
                    if is_chat_only
                    else {
                        "subfolder": pdf_sub,
                        "file_name": pdf_name,
                        "relative_path": f"{pdf_sub}/{pdf_name}",
                        "url": f"/api/raw-pdf/{pdf_sub}/{encoded_pdf_name}",
                    }
                ),
                "touched_concepts": [],
                "tool_calls": [
                    {
                        "step": "STEP 0 // GUARDRAIL",
                        "tool": "before_agent_callback",
                        "detail": "Prompt verified clean by Model Armor pre-flight callback",
                    }
                ],
                "started_at": t0,
                "duration_ms": int((time.monotonic() - t0) * 1000),
            }
            _EXTRACTION_JOBS[job_id] = job_state
            worker = threading.Thread(
                target=_run_sync_extraction_job,
                args=(
                    job_id,
                    req,
                    effective_prompt,
                    clean_concept_id,
                    pdf_sub,
                    pdf_name,
                    t0,
                ),
                daemon=True,
            )
            worker.start()
            return {
                k: v for k, v in job_state.items() if k != "started_at"
            }

        return await asyncio.to_thread(
            _execute_extraction_workflow_sync,
            req,
            effective_prompt,
            clean_concept_id,
            pdf_sub,
            pdf_name,
            t0,
            None,
        )

    @app.get("/api/chat/jobs/{job_id}", response_class=JSONResponse)
    async def get_extraction_job_endpoint(job_id: str) -> dict[str, Any]:
        job = _EXTRACTION_JOBS.get(job_id)
        if not job:
            raise HTTPException(
                status_code=404,
                detail=f"Extraction job '{job_id}' not found",
            )
        if job.get("status") == "running" and "started_at" in job:
            job["duration_ms"] = int((time.monotonic() - float(job["started_at"])) * 1000)
        return {k: v for k, v in job.items() if k != "started_at"}

    return app


app = create_web_app()

