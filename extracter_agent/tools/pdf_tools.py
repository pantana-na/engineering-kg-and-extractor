"""ADK FunctionTools for PDF document processing.

Strictly complies with Rule 11 (FunctionTool docstring contracts, type safety).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from google.cloud import storage

from extracter_agent.config import get_config
from extracter_agent.pdf.processor import (
    extract_equipment_tag_candidates,
    extract_pdf_multimodal_summary,
    extract_pdf_pages,
    get_pdf_metadata,
    is_vector_drawing,
    search_raw_documents,
)

_GCS_RAW_BLOBS_CACHE: list[dict[str, Any]] | None = None
_GCS_RAW_CACHE_DIR = Path(tempfile.gettempdir()) / "extracter_gcs_raw_cache"


def _compute_file_md5_b64(path: Path) -> str:
    """Compute base64-encoded MD5 digest matching Google Cloud Storage blob.md5_hash."""
    return base64.b64encode(
        hashlib.md5(path.read_bytes(), usedforsecurity=False).digest()
    ).decode("ascii")


def _list_gcs_raw_blobs(force_refresh: bool = False) -> list[dict[str, Any]]:
    """List and cache raw PDF object metadata from Google Cloud Storage."""
    global _GCS_RAW_BLOBS_CACHE
    if not force_refresh and _GCS_RAW_BLOBS_CACHE is not None:
        return _GCS_RAW_BLOBS_CACHE

    cfg = get_config()
    client = storage.Client(project=cfg.google_cloud_project)
    bucket = client.bucket(cfg.destination_gcs_bucket)
    prefix = cfg.source_gcs_raw_prefix.strip("/") + "/"
    items: list[dict[str, Any]] = []
    for blob in bucket.list_blobs(prefix=prefix):
        if blob.name.lower().endswith(".pdf"):
            rel_under_raw = blob.name[len(prefix) :]
            parts = rel_under_raw.split("/")
            sub = parts[0] if len(parts) > 1 else ""
            fname = parts[-1]
            raw_md5 = getattr(blob, "md5_hash", None)
            items.append(
                {
                    "file_name": fname,
                    "subfolder": sub,
                    "relative_path": f"reference/raw/{rel_under_raw}",
                    "blob_name": blob.name,
                    "gcs_uri": f"gs://{cfg.destination_gcs_bucket}/{blob.name}",
                    "size_bytes": blob.size or 0,
                    "md5_hash": raw_md5 if isinstance(raw_md5, str) else None,
                    "updated": str(getattr(blob, "updated", "") or ""),
                }
            )
    if items:
        _GCS_RAW_BLOBS_CACHE = items
    return items


def _match_pdf_candidate(
    pdf_filename: str,
    subfolder: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve a target PDF filename or citation against candidate metadata with strict drawing-code boundary rules.

    Prevents base numeric drawing codes (e.g. '0012') from colliding with alpha-suffixed
    sibling drawings (e.g. '0012A') that sort earlier in ASCII order ('A' < '_'), and
    supports shortened citations where middle title words are omitted (e.g. '<CODE>_Z1.pdf').
    """
    if not candidates:
        return None

    clean_name = Path(pdf_filename).name.strip()
    clean_lower = clean_name.lower()
    clean_stem = Path(clean_name).stem.strip()
    clean_stem_lower = clean_stem.lower()
    norm_target = re.sub(r"[^a-z0-9]", "", clean_lower)

    # Leading document/drawing code before first underscore (e.g. 'PID-23-0013')
    query_code = clean_stem_lower.split("_")[0].strip()
    query_tokens = [
        t for t in re.split(r"[^a-z0-9]+", clean_stem_lower) if len(t) >= 2
    ]

    def _subfolder_Pool(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not subfolder:
            return pool
        scoped = [c for c in pool if c.get("subfolder") == subfolder]
        return scoped if scoped else pool

    ordered_pools = (
        [[c for c in candidates if c.get("subfolder") == subfolder], candidates]
        if subfolder
        else [candidates]
    )

    # 1. Exact filename match
    for pool in ordered_pools:
        for c in pool:
            if c["file_name"].lower() == clean_lower:
                return c

    # 2. Exact leading document-code prefix match (before '_')
    if len(query_code) >= 3:
        for pool in ordered_pools:
            prefix_matches: list[tuple[int, str, dict[str, Any]]] = []
            for c in pool:
                c_stem_lower = Path(c["file_name"]).stem.lower()
                c_code = c_stem_lower.split("_")[0].strip()
                if c_code == query_code:
                    c_tokens = set(re.split(r"[^a-z0-9]+", c_stem_lower))
                    extra_overlap = sum(1 for qt in query_tokens if qt in c_tokens)
                    prefix_matches.append((extra_overlap, c["file_name"].lower(), c))
            if prefix_matches:
                prefix_matches.sort(key=lambda item: (item[0], item[1]))
                return prefix_matches[-1][2]

    # 3. Alphanumeric boundary match on query_code or clean_stem_lower
    # Ensures '0012' matches '...-0012_...' and NEVER '...-0012a_...'
    for probe in (clean_stem_lower, query_code):
        if len(probe) < 3:
            continue
        boundary_pat = re.compile(rf"(?<![a-z0-9]){re.escape(probe)}(?![a-z0-9])")
        for pool in ordered_pools:
            boundary_matches: list[tuple[int, str, dict[str, Any]]] = []
            for c in pool:
                c_stem_lower = Path(c["file_name"]).stem.lower()
                if boundary_pat.search(c_stem_lower):
                    c_tokens = set(re.split(r"[^a-z0-9]+", c_stem_lower))
                    overlap = sum(1 for qt in query_tokens if qt in c_tokens)
                    boundary_matches.append((overlap, c["file_name"].lower(), c))
            if boundary_matches:
                boundary_matches.sort(key=lambda item: (item[0], item[1]))
                return boundary_matches[-1][2]

    # 4. All query tokens present as exact tokens in candidate stem
    if query_tokens:
        for pool in ordered_pools:
            token_matches: list[tuple[int, dict[str, Any]]] = []
            for c in pool:
                c_tokens = {
                    t for t in re.split(r"[^a-z0-9]+", Path(c["file_name"]).stem.lower()) if t
                }
                if all(qt in c_tokens for qt in query_tokens):
                    token_matches.append((-len(c["file_name"]), c))
            if token_matches:
                token_matches.sort(key=lambda item: item[0], reverse=True)
                return token_matches[0][1]

    # 5. Substring / normalized alphanumeric fallback
    for pool in _subfolder_Pool(candidates), candidates:
        for c in pool:
            if clean_lower in c["file_name"].lower():
                return c
        for c in pool:
            if norm_target and norm_target in re.sub(r"[^a-z0-9]", "", c["file_name"].lower()):
                return c

    return None


def _download_pdf_from_gcs(
    pdf_filename: str,
    subfolder: str,
    force_refresh: bool = False,
) -> tuple[Path | None, str | None]:
    """Download a raw PDF from GCS into the local temporary cache directory with size and MD5 verification."""
    cfg = get_config()
    blobs = _list_gcs_raw_blobs(force_refresh=force_refresh)
    matched_blob = _match_pdf_candidate(pdf_filename, subfolder, blobs)

    if not matched_blob:
        return None, None

    dest_path = _GCS_RAW_CACHE_DIR / matched_blob["relative_path"]
    needs_download = not dest_path.exists() or dest_path.stat().st_size == 0
    if not needs_download:
        expected_size = matched_blob.get("size_bytes") or 0
        expected_md5 = matched_blob.get("md5_hash")
        if (expected_size > 0 and dest_path.stat().st_size != expected_size) or (
            isinstance(expected_md5, str)
            and expected_md5
            and _compute_file_md5_b64(dest_path) != expected_md5
        ):
            needs_download = True

    if needs_download:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        client = storage.Client(project=cfg.google_cloud_project)
        bucket = client.bucket(cfg.destination_gcs_bucket)
        bucket.blob(matched_blob["blob_name"]).download_to_filename(str(dest_path))

    return dest_path, matched_blob["gcs_uri"]


def find_raw_documents_tool(
    query: str,
    subfolder: str | None = None,
) -> dict[str, Any]:
    """Search and discover raw engineering technical documents in Google Cloud Storage (reference/raw/).

    When to use:
        - When discovering raw PDF files for an equipment tag, drawing number,
          or document category (e.g. data_sheets, pid, pfd) before starting extraction.
        - Example: find_raw_documents_tool(query="<EQUIPMENT_TAG>")

    When NOT to use:
        - Do NOT use for already processed Markdown files in reference/wiki/.
        - Do NOT use for general chat inquiries.
        - Do NOT attempt to modify or delete reference files.

    Args:
        query: Equipment tag, document code, or keyword to search.
        subfolder: Optional subdirectory to scope search (data_sheets, pid, pfd, operating_manuals, standards).

    Returns:
        A dictionary containing matched files, counts, GCS URIs, and relative paths.
    """
    cfg = get_config()
    if cfg.use_gcs_storage:
        try:
            blobs = _list_gcs_raw_blobs()
            if blobs:
                q_compact = re.sub(r"[^a-z0-9]", "", query.lower())
                tokens = [
                    re.sub(r"[^a-z0-9]", "", t.lower())
                    for t in query.split()
                    if len(re.sub(r"[^a-z0-9]", "", t.lower())) >= 2
                ]
                scored_matches: list[tuple[int, str, str, dict[str, Any]]] = []
                for b in blobs:
                    if subfolder and b["subfolder"] != subfolder:
                        continue
                    fname_compact = re.sub(r"[^a-z0-9]", "", b["file_name"].lower())
                    haystack = re.sub(
                        r"[^a-z0-9]", "", f"{b['subfolder']} {b['file_name']}".lower()
                    )
                    is_exact = bool(len(q_compact) >= 3 and q_compact in fname_compact)
                    if is_exact or not tokens or any(tok in haystack for tok in tokens):
                        scored_matches.append(
                            (0 if is_exact else 1, b["subfolder"], b["file_name"], b)
                        )
                scored_matches.sort(key=lambda item: (item[0], item[1], item[2]))
                gcs_matches = [item[3] for item in scored_matches]
                return {
                    "status": "success",
                    "source_storage": "gcs",
                    "gcs_bucket": f"gs://{cfg.destination_gcs_bucket}/{cfg.source_gcs_raw_prefix}",
                    "query": query,
                    "subfolder": subfolder or "all",
                    "match_count": len(gcs_matches),
                    "matches": gcs_matches,
                }
        except Exception as exc:
            logging.getLogger(__name__).debug("Ignored non-fatal exception: %s", exc)

    raw_dir = cfg.reference_raw_dir
    results = search_raw_documents(query=query, raw_dir=raw_dir, subfolder=subfolder)
    return {
        "status": "success",
        "source_storage": "local",
        "query": query,
        "subfolder": subfolder or "all",
        "match_count": len(results),
        "matches": results,
    }


def _select_document_pages(
    pages: list[dict[str, Any]],
    max_pages: int = 150,
    start_page: int = 1,
    page_query: str | None = None,
) -> list[dict[str, Any]]:
    """Select up to max_pages from pages, supporting start_page, page_query filtering, and high-density chapter sampling for very large manuals."""
    start_idx = max(0, start_page - 1)
    candidates = [dict(p) for p in pages[start_idx:]]
    if not candidates:
        return []

    if page_query and page_query.strip():
        q_tokens = [
            t.lower() for t in re.split(r"[\s,;]+", page_query.strip()) if len(t) >= 2
        ]
        if q_tokens:
            matched = [
                p
                for idx, p in enumerate(candidates)
                if idx < 3 or any(qt in p.get("text", "").lower() for qt in q_tokens)
            ]
            if matched:
                return matched[:max_pages]

    if len(candidates) <= max_pages or max_pages < 50:
        return candidates[:max_pages]

    # For very large documents (> max_pages, e.g. 388-page operating manuals):
    # Retain leading TOC/index pages (first 14 pages) + highest engineering-density pages in page order
    lead_count = min(14, max_pages // 4)
    lead_pages = candidates[:lead_count]
    remaining_budget = max(0, max_pages - lead_count)
    tail_Pool = candidates[lead_count:]

    scored_tail: list[tuple[int, int, dict[str, Any]]] = []
    for p in tail_Pool:
        txt = p.get("text", "")
        digit_density = len(re.findall(r"\b\d+(?:\.\d+)?\b", txt))
        line_density = len([ln for ln in txt.splitlines() if ln.strip()])
        score = digit_density * 2 + min(20, line_density // 3)
        scored_tail.append((score, p["page_number"], p))

    scored_tail.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    selected_tail = sorted(
        (item[2] for item in scored_tail[:remaining_budget]),
        key=lambda p: p["page_number"],
    )
    return lead_pages + selected_tail


def process_raw_pdf_tool(
    pdf_filename: str,
    subfolder: str = "data_sheets",
    max_pages: int = 150,
    enable_multimodal: bool = True,
    start_page: int = 1,
    page_query: str | None = None,
) -> dict[str, Any]:
    """Extract text, tables, and document metadata from a raw engineering PDF in GCS (reference/raw/).

    When to use:
        - When ingesting process data sheets, P&IDs, PFDs, standards, or operating manuals
          from the reference/raw directory in GCS to extract chemical engineering knowledge.
        - Example: process_raw_pdf_tool("<PROCESS_DATA_SHEET>.pdf", "data_sheets")

    When NOT to use:
        - Do NOT use for already processed Markdown files in reference/wiki/.
        - Do NOT use for general conversational queries unrelated to document ingestion.
        - Do NOT attempt to modify or delete the source PDF file.

    Args:
        pdf_filename: The filename or relative path of the PDF.
        subfolder: The subdirectory under reference/raw (e.g. data_sheets, pid, pfd, operating_manuals, standards).
        max_pages: Maximum pages to process (default: 150, covering full multi-sheet datasheets, 136-page valve packages, and standards).
        enable_multimodal: Whether to run Gemini multimodal vision for vector drawings, data sheets, or scanned tables (default: True).
        start_page: 1-indexed starting page number (default: 1).
        page_query: Optional keyword filter to prioritize specific sections or tags within large manuals.

    Returns:
        A dictionary containing metadata, source GCS URI, extracted pages, vector drawing status, and identified equipment tag candidates.
    """
    cfg = get_config()
    raw_dir = cfg.reference_raw_dir
    target_path: Path | None = None
    source_gcs_uri: str | None = None

    if cfg.use_gcs_storage:
        try:
            target_path, source_gcs_uri = _download_pdf_from_gcs(pdf_filename, subfolder)
        except Exception:
            target_path = None

    if target_path is None:
        if (raw_dir / subfolder / pdf_filename).exists():
            target_path = raw_dir / subfolder / pdf_filename
        elif (raw_dir / pdf_filename).exists():
            target_path = raw_dir / pdf_filename
        elif Path(pdf_filename).exists():
            target_path = Path(pdf_filename)
        else:
            local_candidates = [
                {
                    "file_name": p.name,
                    "subfolder": p.parent.name if p.parent != raw_dir else "",
                    "path": p,
                }
                for p in sorted(raw_dir.rglob("*.pdf"))
            ]
            matched_local = _match_pdf_candidate(pdf_filename, subfolder, local_candidates)
            if matched_local is not None:
                target_path = matched_local["path"]
            else:
                return {
                    "status": "error",
                    "error": f"PDF file not found in GCS or {raw_dir}: {pdf_filename}",
                    "pages": [],
                }

    try:
        meta = get_pdf_metadata(target_path)
        pages = extract_pdf_pages(target_path)
        limited_pages = _select_document_pages(
            pages=pages,
            max_pages=max_pages,
            start_page=start_page,
            page_query=page_query,
        )

        full_text = " ".join(p["text"] for p in limited_pages)
        has_native_text = len(full_text.strip()) > 0
        # Check if drawing is an AutoCAD vector graphic with empty text stream
        is_vector = is_vector_drawing(target_path)

        # Universal multimodal visual analysis when enable_multimodal is True:
        # 1. Vector drawings or documents with minimal native text (<100 chars)
        # 2. All other documents with native text (extracting embedded tables, sketches, and structured rows)
        multimodal_text = None
        if enable_multimodal and (is_vector or len(full_text.strip()) < 100):
            mm_kwargs: dict[str, Any] = {
                "prompt_hint": f"Extract complete engineering data for drawing {target_path.stem}",
            }
            if is_vector:
                mm_kwargs["window_size"] = 2
            if page_query:
                mm_kwargs["page_query"] = page_query
            if start_page > 1 or max_pages < 150:
                mm_kwargs["start_page"] = start_page
                mm_kwargs["max_pages"] = max_pages
            try:
                multimodal_text = extract_pdf_multimodal_summary(target_path, **mm_kwargs)
            except TypeError:
                multimodal_text = extract_pdf_multimodal_summary(
                    target_path,
                    prompt_hint=f"Extract complete engineering data for drawing {target_path.stem}",
                )
            limited_pages.append(
                {
                    "page_number": len(limited_pages) + 1,
                    "text": f"[Multimodal Visual Interpretation of {target_path.name}]:\n{multimodal_text}",
                    "char_count": len(multimodal_text),
                    "word_count": len(multimodal_text.split()),
                }
            )
            full_text = f"{full_text}\n{multimodal_text}"
        elif enable_multimodal:
            mm_kwargs = {
                "prompt_hint": f"Extract all technical tables, diagrams, and specifications from {target_path.stem}",
            }
            if page_query:
                mm_kwargs["page_query"] = page_query
            if start_page > 1 or max_pages < 150:
                mm_kwargs["start_page"] = start_page
                mm_kwargs["max_pages"] = max_pages
            try:
                multimodal_text = extract_pdf_multimodal_summary(target_path, **mm_kwargs)
            except TypeError:
                multimodal_text = extract_pdf_multimodal_summary(
                    target_path,
                    prompt_hint=f"Extract all technical tables, diagrams, and specifications from {target_path.stem}",
                )
            injected_once = False
            for p in limited_pages:
                if len(p["text"].strip()) < 50:
                    if not injected_once:
                        p["text"] = f"[Multimodal Visual Extraction of {target_path.name} Tables]:\n{multimodal_text}"
                        injected_once = True
                    else:
                        p["text"] = f"[Page {p['page_number']}: Raster table included in Multimodal Visual Extraction above]"
                    p["char_count"] = len(p["text"])
                    p["word_count"] = len(p["text"].split())
            if not injected_once and limited_pages and multimodal_text:
                last_p = limited_pages[-1]
                last_p["text"] = (
                    f"{last_p['text']}\n\n[Multimodal Visual Extraction of {target_path.name} Tables]:\n{multimodal_text}"
                )
                last_p["char_count"] = len(last_p["text"])
                last_p["word_count"] = len(last_p["text"].split())
            full_text = f"{full_text}\n{multimodal_text}"

        # Extract tag candidates from both text and filename
        combined_text = f"{target_path.stem} {full_text}"
        tag_candidates = extract_equipment_tag_candidates(combined_text)

        rel_path = (
            str(target_path.resolve().relative_to(Path.cwd().resolve()))
            if target_path.resolve().is_relative_to(Path.cwd().resolve())
            else f"{cfg.source_gcs_raw_prefix}/{target_path.parent.name}/{target_path.name}"
        )

        multimodal_analysis_out = (
            f"[Multimodal extraction completed ({len(multimodal_text)} chars); "
            f"full transcription is populated in `pages` above to prevent payload duplication.]\n\n"
            f"{multimodal_text[:4000]}..."
            if multimodal_text and len(multimodal_text) > 16000
            else multimodal_text
        )

        return {
            "status": "success",
            "source_storage": "gcs" if source_gcs_uri else "local",
            "source_gcs_uri": source_gcs_uri
            or f"gs://{cfg.destination_gcs_bucket}/{rel_path}",
            "file_name": target_path.name,
            "subfolder": target_path.parent.name,
            "relative_path": rel_path,
            "metadata": meta,
            "is_vector_drawing": is_vector,
            "has_text_stream": has_native_text,
            "multimodal_ready": True,
            "multimodal_analysis": multimodal_analysis_out,
            "pages_processed": len(limited_pages),
            "total_pages": meta["page_count"],
            "tag_candidates": tag_candidates,
            "pages": limited_pages,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to process PDF {target_path}: {e}",
            "pages": [],
        }


