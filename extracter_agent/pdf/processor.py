"""PDF processing pipeline for chemical engineering documents.

Extracts text, metadata, and structural sections from raw engineering PDFs.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Any

import pypdf


class PDFProcessingError(Exception):
    """Raised when a PDF cannot be parsed or processed."""


def extract_pdf_pages(file_path: Path | str) -> list[dict[str, Any]]:
    """Extract text and metadata from each page of a PDF document.

    Args:
        file_path: Path to the PDF file.

    Returns:
        A list of dictionaries, each containing page_number (1-indexed), text,
        char_count, and word_count.
    """
    path = Path(file_path)
    if not path.exists():
        raise PDFProcessingError(f"PDF file does not exist: {path}")

    try:
        reader = pypdf.PdfReader(str(path))
    except Exception as e:
        raise PDFProcessingError(f"Failed to read PDF {path}: {e}") from e

    pages: list[dict[str, Any]] = []
    for idx, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as e:
            text = f"[Extraction error on page {idx + 1}: {e}]"

        pages.append(
            {
                "page_number": idx + 1,
                "text": text,
                "char_count": len(text),
                "word_count": len(text.split()),
            }
        )

    return pages


def get_pdf_metadata(file_path: Path | str) -> dict[str, Any]:
    """Retrieve document-level metadata and summary metrics."""
    path = Path(file_path)
    if not path.exists():
        raise PDFProcessingError(f"PDF file does not exist: {path}")

    try:
        reader = pypdf.PdfReader(str(path))
        meta = reader.metadata or {}
        total_pages = len(reader.pages)
        return {
            "file_name": path.name,
            "file_size_bytes": path.stat().st_size,
            "page_count": total_pages,
            "title": getattr(meta, "title", None) or path.stem,
            "author": getattr(meta, "author", None),
            "creator": getattr(meta, "creator", None),
        }
    except Exception as e:
        raise PDFProcessingError(f"Error extracting metadata from {path}: {e}") from e


def chunk_document_text(
    pages: list[dict[str, Any]],
    max_chunk_size: int = 4000,
    overlap: int = 400,
) -> list[dict[str, Any]]:
    """Chunk page texts into bounded segments preserving page attribution.

    Args:
        pages: List of page dictionaries from extract_pdf_pages.
        max_chunk_size: Maximum characters per chunk.
        overlap: Character overlap between contiguous chunks.

    Returns:
        List of chunks with text, start_page, end_page, and chunk_index.
    """
    if not pages:
        return []

    chunks: list[dict[str, Any]] = []
    current_text: list[str] = []
    current_pages: list[int] = []
    current_len = 0

    for page in pages:
        page_num = page["page_number"]
        page_text = page["text"].strip()
        if not page_text:
            continue

        if current_len + len(page_text) > max_chunk_size and current_text:
            combined = "\n\n".join(current_text)
            chunks.append(
                {
                    "chunk_index": len(chunks) + 1,
                    "text": combined,
                    "start_page": current_pages[0],
                    "end_page": current_pages[-1],
                    "char_count": len(combined),
                }
            )
            # Apply overlap from tail of combined text
            overlap_text = combined[-overlap:] if overlap > 0 else ""
            current_text = [overlap_text, page_text] if overlap_text else [page_text]
            current_pages = [page_num]
            current_len = sum(len(t) for t in current_text)
        else:
            current_text.append(page_text)
            current_pages.append(page_num)
            current_len += len(page_text)

    if current_text:
        combined = "\n\n".join(current_text)
        chunks.append(
            {
                "chunk_index": len(chunks) + 1,
                "text": combined,
                "start_page": current_pages[0],
                "end_page": current_pages[-1],
                "char_count": len(combined),
            }
        )

    return chunks


def extract_equipment_tag_candidates(text: str) -> list[str]:
    """Extract likely equipment tag candidates matching standard plant tag patterns.

    Identifies alphanumeric plant equipment tags matching <PREFIX>-<NUMBER><SUFFIX>
    or multi-segment unit-prefixed tags (<UNIT>-<SYSTEM>-<TYPE>-<NUMBER><SUFFIX>).
    Used as candidate hints for model reasoning; does NOT replace cognitive routing.
    """
    pattern = r"\b((?:\d+-[A-Z]{1,4}-)?[A-Z]{1,4}-\d{1,5}[A-Z]{0,6})\b"
    matches = re.findall(pattern, text)
    # Preserve order, deduplicate
    seen: set[str] = set()
    unique: list[str] = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            unique.append(m)
    return unique


def is_vector_drawing(file_path: Path | str) -> bool:
    """Determine if a PDF is an AutoCAD or vector drawing lacking text streams."""
    path = Path(file_path)
    if not path.exists():
        return False
    try:
        reader = pypdf.PdfReader(str(path))
        if not reader.pages:
            return False
        total_text = "".join(p.extract_text() or "" for p in reader.pages[:3]).strip()
        return len(total_text) == 0
    except Exception:
        return False


def search_raw_documents(
    query: str,
    raw_dir: Path | str,
    subfolder: str | None = None,
) -> list[dict[str, Any]]:
    """Search reference/raw directory for PDF documents matching a query or entity tag."""
    base = Path(raw_dir)
    target = base / subfolder if subfolder else base
    if not target.exists():
        return []

    results: list[tuple[int, dict[str, Any]]] = []
    q_lower = query.lower().strip()
    q_compact = re.sub(r"[^a-z0-9]", "", q_lower)
    tokens = [
        t.lower().strip()
        for t in re.split(r"[\s\-_]+", query)
        if len(t.strip()) >= 2
    ]

    for pdf in target.rglob("*.pdf"):
        name_lower = pdf.name.lower()
        name_compact = re.sub(r"[^a-z0-9]", "", name_lower)
        is_exact = bool(
            (q_lower and q_lower in name_lower)
            or (len(q_compact) >= 3 and q_compact in name_compact)
        )
        if is_exact or any(tok in name_lower for tok in tokens):
            try:
                rel = pdf.relative_to(base)
            except ValueError:
                rel = pdf
            subf = pdf.parent.name if pdf.parent != base else "root"
            priority = 0 if is_exact else 1
            results.append(
                (
                    priority,
                    {
                        "file_name": pdf.name,
                        "subfolder": subf,
                        "relative_path": str(rel),
                        "size_bytes": pdf.stat().st_size,
                    },
                )
            )

    results.sort(key=lambda x: (x[0], x[1]["subfolder"], x[1]["file_name"]))
    return [item[1] for item in results]


def extract_pdf_multimodal_part(file_path: Path | str) -> Any:
    """Create a google.genai types.Part representation for multimodal PDF processing."""
    path = Path(file_path)
    if not path.exists():
        raise PDFProcessingError(f"PDF file does not exist: {path}")

    from google.genai import types

    pdf_bytes = path.read_bytes()
    return types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")


def _build_multimodal_prompt(
    prompt_hint: str | None = None,
) -> str:
    """Construct a general, domain-agnostic multimodal extraction prompt."""
    base_prompt = (
        "Exhaustively extract all technical specifications, diagrams, and tables from this engineering document without summarizing or omitting columns:\n"
        "- All primary and auxiliary equipment items, package sub-components, and spare suffixes, along with titles, plant sections, and document metadata.\n"
        "- Complete mechanical and geometrical dimensions for both overall assemblies and individual sub-sections or stages, supports, and internal components.\n"
        "- All design and operating ratings (pressures including vacuum ratings, temperatures, materials of construction, corrosion allowances, driver ratings, nominal and design-margin heat duties, flow rates, liquid levels, physical properties, and stream compositions). Carefully verify decimal points across title blocks and tables, and retain both values whenever a drawing title block and a specification table disagree.\n"
        "- Complete nozzle schedules and every process, utility, cooling/chilled water, seal flush, vent, and drain piping line designation with origins, destinations, and off-page continuation arrow drawing identifiers along drawing borders.\n"
        "- Complete instrumentation and control loops across the entire drawing or package (including transmitters, controllers, control/block/relief valves, in-line sight flow indicators / sight glasses, restriction orifices, and local gauges or switches on auxiliary skids). Never collapse stacked or multi-function loops into a single tag; if different measured variables share the same loop number, list every function separately.\n"
        "- Complete row-by-row and column-by-column transcription of all tables (process/mechanical data sheets, instrument/valve/relief sizing tables including operating liquid/vapor specific gravities, capillary fill densities, orifice areas, Cv values, and required/rated relief capacities, heat and material stream balance tables including molar flows, molecular weights, and trace components, physical/chemical property tables, occupational exposure limits retaining all printed unit representations including parenthetical units, transport classifications, risk matrices, and operating schedules).\n"
        "- All safety instrumented systems, interlocks, trip setpoints, alarms, engineering notes, elevation requirements, and cross-document discrepancies."
    )
    if prompt_hint:
        base_prompt = f"{base_prompt}\nFocus especially on: {prompt_hint}"
    return base_prompt


def _compute_multimodal_cache_digest(pdf_bytes: bytes, prompt_text: str) -> str:
    """Compute a deterministic 24-hex SHA-256 cache digest over both PDF bytes and the resolved prompt."""
    hasher = hashlib.sha256()
    hasher.update(pdf_bytes)
    hasher.update(b"\x00PROMPT_V4\x00")
    hasher.update(prompt_text.encode("utf-8"))
    return hasher.hexdigest()[:24]


def _extract_single_pdf_window_multimodal(
    pdf_bytes: bytes,
    cache_key_name: str,
    prompt_hint: str | None = None,
) -> str:
    """Run or fetch cached Gemini multimodal extraction for a single PDF or page-window byte stream."""
    import tempfile
    import time

    from google import genai
    from google.genai import types

    from extracter_agent.config import get_config

    cfg = get_config()
    base_prompt = _build_multimodal_prompt(prompt_hint=prompt_hint)
    pdf_sha = _compute_multimodal_cache_digest(pdf_bytes, base_prompt)
    cache_dir = Path(tempfile.gettempdir()) / "extracter_multimodal_cache_v4"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{cache_key_name}_{pdf_sha}.md"

    if cache_file.exists() and cache_file.stat().st_size > 100:
        return cache_file.read_text(encoding="utf-8")

    if cfg.use_gcs_storage:
        try:
            from google.cloud import storage

            st_client = storage.Client(project=cfg.google_cloud_project)
            bucket = st_client.bucket(cfg.destination_gcs_bucket)
            cache_blob = bucket.blob(f"cache/multimodal_v4/{cache_key_name}_{pdf_sha}.md")
            if cache_blob.exists():
                cached_text = cache_blob.download_as_text(encoding="utf-8")
                if len(cached_text) > 100:
                    cache_file.write_text(cached_text, encoding="utf-8")
                    return cached_text
        except Exception as exc:
            logging.getLogger(__name__).debug("Ignored non-fatal exception: %s", exc)

    http_opts = types.HttpOptions(
        retry_options=types.HttpRetryOptions(
            attempts=5,
            initial_delay=2.0,
            exp_base=2.0,
            http_status_codes=[429, 500, 502, 503, 504],
        )
    )
    use_vertex = (
        os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() in ("true", "1")
        or os.getenv("GOOGLE_GENAI_USE_ENTERPRISE", "").lower() in ("true", "1")
    )
    part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

    last_err: Exception | None = None
    gen_cfg = types.GenerateContentConfig(
        max_output_tokens=65536,
        temperature=0.0,
    )
    for attempt in range(3):
        try:
            if use_vertex:
                client = genai.Client(
                    vertexai=True,
                    project=cfg.google_cloud_project,
                    location=cfg.gemini_location,
                    http_options=http_opts,
                )
            else:
                client = genai.Client(http_options=http_opts)
            resp = client.models.generate_content(
                model=cfg.gemini_model,
                contents=[part, base_prompt],
                config=gen_cfg,
            )
            text_out = resp.text or ""
            if len(text_out) > 100:
                try:
                    cache_file.write_text(text_out, encoding="utf-8")
                    if cfg.use_gcs_storage:
                        from google.cloud import storage

                        st_client = storage.Client(project=cfg.google_cloud_project)
                        bucket = st_client.bucket(cfg.destination_gcs_bucket)
                        bucket.blob(
                            f"cache/multimodal_v4/{cache_key_name}_{pdf_sha}.md"
                        ).upload_from_string(text_out, content_type="text/markdown")
                except Exception as exc:
                    logging.getLogger(__name__).debug("Ignored non-fatal exception: %s", exc)
            return text_out
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2.0 * (2**attempt))
    return f"[Multimodal extraction error: {last_err}]"


def extract_pdf_multimodal_summary(
    file_path: Path | str,
    prompt_hint: str | None = None,
    window_size: int = 4,
    page_query: str | None = None,
    start_page: int = 1,
    max_pages: int = 150,
) -> str:
    """Extract chemical engineering technical content using Gemini multimodal vision.

    Eliminates the single-call multimodal output bottleneck on multi-sheet packages:
    - Automatically adapts to 1-2 page windowing (`window_size=2`) on landscape vector CAD drawings (`is_vector_drawing(path)`) while keeping `window_size=4` for portrait text/table PDFs.
    - Supports `start_page`, `max_pages`, and `page_query` filtering across multi-page documents.
    - For single-sheet or <= effective_window PDFs, executes a single cached call keyed by `(pdf_bytes, prompt)` SHA-256.
    - For multi-sheet PDFs (> effective_window pages, up to 150 pages), slices pages into effective_window batches via
      pypdf.PdfWriter, executes windows concurrently (up to 4 parallel workers) with max_output_tokens=65536,
      and caches each window deterministically under extracter_multimodal_cache_v4 / cache/multimodal_v4/.
    """
    import io
    from concurrent.futures import ThreadPoolExecutor

    path = Path(file_path)
    if not path.exists():
        raise PDFProcessingError(f"PDF file does not exist: {path}")

    effective_window = max(1, window_size)
    pdf_bytes = path.read_bytes()

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(reader.pages)
    except Exception:
        total_pages = 1
        reader = None

    # Adaptive 1-2 page windowing for landscape vector CAD drawings (P&IDs / PFDs)
    if reader is not None and total_pages > 1 and window_size == 4:
        try:
            first_mb = reader.pages[0].mediabox
            is_landscape = float(first_mb.width) > float(first_mb.height)
        except Exception:
            is_landscape = False
        if is_landscape and is_vector_drawing(path):
            effective_window = 2

    has_page_slice = start_page > 1 or max_pages < total_pages
    if reader is None or (
        total_pages <= effective_window
        and not (page_query and page_query.strip())
        and not has_page_slice
    ):
        return _extract_single_pdf_window_multimodal(
            pdf_bytes=pdf_bytes,
            cache_key_name=path.stem,
            prompt_hint=prompt_hint,
        )

    # Multi-sheet PDF (> effective_window pages): build page windows across all sheets up to 150 pages
    if total_pages <= 150:
        target_indices = list(range(total_pages))
    else:
        # For 300+ page prose operating manuals, extract TOC + low-text/diagram pages
        target_indices = list(range(min(effective_window * 2, total_pages)))
        for idx in range(effective_window * 2, total_pages):
            try:
                txt_len = len((reader.pages[idx].extract_text() or "").strip())
            except Exception:
                txt_len = 0
            if txt_len < 1300:
                target_indices.append(idx)
        target_indices = target_indices[: effective_window * 8]

    if has_page_slice:
        start_idx = max(0, start_page - 1)
        end_idx = start_idx + max(1, max_pages)
        target_indices = [idx for idx in target_indices if start_idx <= idx < end_idx]

    if page_query and page_query.strip() and reader is not None:
        q_tokens = [
            t.lower() for t in re.split(r"[\s,;]+", page_query.strip()) if len(t) >= 2
        ]
        if q_tokens:
            matched_indices: list[int] = []
            for idx in target_indices:
                try:
                    p_txt = (reader.pages[idx].extract_text() or "").lower()
                except Exception:
                    p_txt = ""
                if any(qt in p_txt for qt in q_tokens):
                    matched_indices.append(idx)
            if matched_indices:
                target_indices = matched_indices

    windows: list[list[int]] = [
        target_indices[i : i + effective_window]
        for i in range(0, len(target_indices), effective_window)
    ]

    prepared_windows: list[tuple[int, int, bytes, str]] = []
    for win_indices in windows:
        start_p = win_indices[0] + 1
        end_p = win_indices[-1] + 1
        try:
            writer = pypdf.PdfWriter()
            for p_idx in win_indices:
                writer.add_page(reader.pages[p_idx])
            buf = io.BytesIO()
            writer.write(buf)
            win_bytes = buf.getvalue()
        except Exception:
            win_bytes = pdf_bytes

        win_hint = (
            f"{prompt_hint} (Pages {start_p}-{end_p} of {total_pages}: exhaustively transcribe every sheet, table row, column, tag, and numerical value in this page window without summarizing)"
            if prompt_hint
            else f"Exhaustively transcribe all tables, columns, instrument tags, nozzles, and specifications on pages {start_p}-{end_p} of {total_pages} without summarizing"
        )
        prepared_windows.append((start_p, end_p, win_bytes, win_hint))

    def _run_window(item: tuple[int, int, bytes, str]) -> str:
        s_p, e_p, w_bytes, w_hint = item
        w_text = _extract_single_pdf_window_multimodal(
            pdf_bytes=w_bytes,
            cache_key_name=f"{path.stem}_p{s_p}-{e_p}",
            prompt_hint=w_hint,
        )
        return f"### [Pages {s_p}–{e_p} of {total_pages}]\n{w_text}"

    if len(prepared_windows) == 1:
        window_outputs = [_run_window(prepared_windows[0])]
    else:
        with ThreadPoolExecutor(max_workers=min(4, len(prepared_windows))) as pool:
            window_outputs = list(pool.map(_run_window, prepared_windows))

    return "\n\n".join(window_outputs)




