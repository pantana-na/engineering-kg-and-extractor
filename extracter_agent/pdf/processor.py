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
        "- All primary and auxiliary equipment items, package sub-components, sumps, protective chambers, expansion pieces, and spare suffixes, along with titles, plant sections, and document metadata.\n"
        "- When a landscape engineering drawing is provided as 7 multi-scale images (Image 1: Full-Sheet Overview [0-100% X, 0-100% Y] followed by 6 overlapping high-resolution 3x2 regional zooms: Image 2 Top-Left [0-45% X, 0-55% Y], Image 3 Top-Center Bridge [28-72% X, 0-55% Y], Image 4 Top-Right [55-100% X, 0-55% Y], Image 5 Bottom-Left [0-45% X, 45-100% Y], Image 6 Bottom-Center Bridge [28-72% X, 45-100% Y], Image 7 Bottom-Right [55-100% X, 45-100% Y]), perform a strict 2-stage analysis: First, use Image 1 (Full-Sheet Overview) and the Center Bridge zooms (Images 3 and 6) to trace every continuous horizontal and vertical piping header end-to-end across all drawing grid columns and rows (including lines passing through wall sleeves or pipe tunnels) from the true upstream equipment nozzle to the true downstream equipment nozzle or boundary termination. Second, use the 6 high-resolution regional zooms to verify every 6-pt equipment tag, valve number, arrowhead direction, nozzle reducer size, drain header destination, and instrument bubble digit.\n"
        "- Transcribe the exact verbatim tag printed inside or beside each equipment symbol, valve, and instrument bubble without guessing or extrapolating sequential tag numbers, and transcribe any printed status modifier (such as NON-FUNCTIONAL, SPARE, or FUTURE) verbatim. When a drawing General Note specifies a default system prefix, explicitly record both the verbatim printed symbol tag and the full General-Note-prefixed tag; however, if a printed tag already begins with an explicit system prefix, retain its printed prefix as-is and NEVER double-prefix it.\n"
        "- Complete mechanical and geometrical dimensions for both overall assemblies and individual sub-sections or stages, supports, and internal components.\n"
        "- All design and operating ratings (pressures including vacuum ratings, temperatures, materials of construction, corrosion allowances, driver ratings, nominal and design-margin heat duties, flow rates, liquid levels, physical properties, and stream compositions). Carefully verify decimal points across title blocks and tables, and retain both values whenever a drawing title block and a specification table disagree.\n"
        "- Complete nozzle schedules and a structured, Spanner-Graph-ready connectivity breakdown for EVERY equipment item covering every process, utility, cooling/chilled water, seal flush, bypass, vent, relief, and drain piping line. For each connection, explicitly identify: (a) `stream_id`, (b) `direction` (`INLET`, `OUTLET`, `BYPASS`, `VENT`, `DRAIN`, `RELIEF`, `RECIRC`, or `UTILITY`), (c) `source_tag` (exact canonical upstream equipment tag or boundary origin), (d) `target_tag` (exact canonical downstream equipment tag or boundary destination), (e) `line_size` (printed nominal diameter and reducer/expander transitions), and (f) `inline_components` (ordered list of all inline valves, check valves, control valves, restriction orifices, and flow elements along that pipe path). Enforce strict P&ID topological rules:\n"
        "  * Cross-Sheet Line Continuity & Zero False Proximity Attachment: Follow long perimeter, tunnel, and return headers continuously from corner elbow to corner elbow across the sheet width. Never attach a passing header (or its inline valves, relief valves, or chemical/makeup tie-ins) to an equipment item merely because the pipe runs underneath or beside that equipment symbol—only attribute a pipe to an equipment item if a physical nozzle line or tee actually touches the equipment symbol.\n"
        "  * Nozzle Line-Size Verification, Unique Valve Per Branch & Bypass Tee Tracing: Check the printed pipe diameter and reducer/expander cone at every filter, demineralizer, vessel, and heat exchanger nozzle (bottom head vs. top head vs. upper/lower side shell). Never confuse a small 3/4\" or 1/2\" top-head vent, drain, or differential-pressure tap (routing to WLD DR, FLR, or PDIS-*) with the main 4\"/3\" process inlet or outlet nozzle. Each distinct nozzle branch on a vessel (Main Inlet, Main Outlet, Full-Flow Bypass, Top-Head Vent, and Bottom-Head Drain) has its own unique valve tag—NEVER reuse the same valve number for both a vessel's inlet and its top vent, or for both a vessel's bottom drain and its main process outlet. Inspect the valve label directly on each individual branch.\n"
        "  * True Flow Direction via Arrowheads & Check Valves: Never assume flow goes from pump to filter or left to right by default (a filter may sit on the suction side of a pump). Determine suction vs. discharge strictly from inline flow arrowheads, check valve symbol orientation (flow always exits a pump discharge in the direction the check valve points), and pump discharge pressure gauge (PI-*) placement.\n"
        "  * Relief Valves + Open Drains vs. Restriction Orifices: Never conflate an open equipment drain funnel label (DR <num>) and a relief valve setpoint (SET @ <pressure> PSIG) into a Restriction Orifice (RO-<num>). An angled spring-loaded valve symbol with SET @ <pressure> PSIG discharging to DR <num> is a Relief Valve (V* / PSV-*), whereas a Restriction Orifice (RO-*) is an inline orifice plate symbol with no pressure setpoint.\n"
        "- Complete instrumentation and control loops across the entire drawing or package (including transmitters, controllers, control/block/relief valves, in-line sight flow indicators / sight glasses, restriction orifices, and local gauges or switches on auxiliary skids). For every instrument bubble, trace its thin physical leader line or impulse tap to the exact pipe line, guard pipe, sump, or equipment body it touches—never attribute an instrument bubble to an adjacent piece of equipment merely because the bubble is printed nearby in 2D space. Carefully distinguish digits `8` vs `6` inside circular instrument bubbles where the horizontal dividing line touches the bottom of the digits, and verify that temperature indicators (`TI-*`) do not borrow the loop number of adjacent flow/hand control valves (`FCV-*` / `HCV-*`). Never collapse stacked or multi-function loops into a single tag; if different measured variables share the same loop number, list every function separately. If an instrument or valve loop number in a General Note differs from the graphic bubble on the flow path, record both numbers and note the discrepancy.\n"
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
    hasher.update(b"\x00PROMPT_V8_SPANNER_GRAPH_3X2\x00")
    hasher.update(prompt_text.encode("utf-8"))
    return hasher.hexdigest()[:24]


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Pack a standard PNG chunk (length + type + data + CRC32)."""
    import struct
    import zlib

    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def _encode_raw_crop_as_png(
    raw: bytes,
    w: int,
    h: int,
    bpp: int,
    color_type: int,
    x0: int,
    y0: int,
    cw: int,
    ch: int,
    pal_bytes: bytes | None = None,
) -> bytes:
    """Encode a rectangular sub-region (or full image) of raw pixel bytes into a valid PNG byte stream."""
    import struct
    import zlib

    row_stride = w * bpp
    col_start = x0 * bpp
    col_end = (x0 + cw) * bpp
    scanlines = b"".join(
        b"\x00" + raw[y * row_stride + col_start : y * row_stride + col_end]
        for y in range(y0, y0 + ch)
    )
    chunks = [
        b"\x89PNG\r\n\x1a\n",
        _png_chunk(b"IHDR", struct.pack(">IIBBBBB", cw, ch, 8, color_type, 0, 0, 0)),
    ]
    if color_type == 3 and pal_bytes is not None:
        chunks.append(_png_chunk(b"PLTE", pal_bytes[:768]))
    chunks.append(_png_chunk(b"IDAT", zlib.compress(scanlines, level=6)))
    chunks.append(_png_chunk(b"IEND", b""))
    return b"".join(chunks)


def _build_multiscale_png_parts_from_raw(
    raw: bytes,
    w: int,
    h: int,
    bpp: int,
    color_type: int,
    pal_bytes: bytes | None = None,
) -> list[Any]:
    """Build full-page PNG Part plus 6 overlapping 3x2 regional PNG Parts (with Center Bridge tiles) for non-blank landscape drawings."""
    from google.genai import types

    full_png = _encode_raw_crop_as_png(
        raw, w, h, bpp, color_type, 0, 0, w, h, pal_bytes=pal_bytes
    )
    parts: list[Any] = [types.Part.from_bytes(data=full_png, mime_type="image/png")]

    step = max(1, len(raw) // 4096)
    is_non_blank = len(set(raw[::step])) > 1
    if w > h and w >= 1600 and h >= 1000 and is_non_blank:
        x_mid = int(w * 0.28)
        x_right = int(w * 0.55)
        w_left = int(w * 0.45)
        w_mid = int(w * 0.44)
        w_right = w - x_right
        y_bot = int(h * 0.45)
        h_top = int(h * 0.55)
        h_bot = h - y_bot
        tile_boxes = [
            (0, 0, w_left, h_top),          # Image 2: Top-Left (0..45% w, 0..55% h)
            (x_mid, 0, w_mid, h_top),       # Image 3: Top-Center Bridge (28..72% w, 0..55% h)
            (x_right, 0, w_right, h_top),   # Image 4: Top-Right (55..100% w, 0..55% h)
            (0, y_bot, w_left, h_bot),      # Image 5: Bottom-Left (0..45% w, 45..100% h)
            (x_mid, y_bot, w_mid, h_bot),   # Image 6: Bottom-Center Bridge (28..72% w, 45..100% h)
            (x_right, y_bot, w_right, h_bot),  # Image 7: Bottom-Right (55..100% w, 45..100% h)
        ]
        for x0, y0, cw, ch in tile_boxes:
            t_png = _encode_raw_crop_as_png(
                raw, w, h, bpp, color_type, x0, y0, cw, ch, pal_bytes=pal_bytes
            )
            parts.append(types.Part.from_bytes(data=t_png, mime_type="image/png"))
    return parts


def _page_has_large_xobject(page: Any, min_dim: int = 1200) -> bool:
    """Return True if a pypdf page contains an embedded image XObject with width or height >= min_dim."""
    try:
        resources = page.get("/Resources")
        if hasattr(resources, "get_object"):
            resources = resources.get_object()
        if not isinstance(resources, dict):
            return False
        xobjects = resources.get("/XObject")
        if hasattr(xobjects, "get_object"):
            xobjects = xobjects.get_object()
        if not isinstance(xobjects, dict):
            return False
        for xobj_ref in xobjects.values():
            im = xobj_ref.get_object() if hasattr(xobj_ref, "get_object") else xobj_ref
            if isinstance(im, dict) and im.get("/Subtype") == "/Image":
                w = int(im.get("/Width", 0))
                h = int(im.get("/Height", 0))
                if w >= min_dim or h >= min_dim:
                    return True
    except Exception:
        return False
    return False


def _extract_flate_xobjects_as_png_parts(reader: pypdf.PdfReader) -> list[Any]:
    """Pure-Python converter for embedded high-DPI FlateDecode page XObjects into multi-scale lossless PNG Parts."""
    png_parts: list[Any] = []
    for page in reader.pages:
        resources = page.get("/Resources")
        if hasattr(resources, "get_object"):
            resources = resources.get_object()
        if not isinstance(resources, dict):
            continue
        xobjects = resources.get("/XObject")
        if hasattr(xobjects, "get_object"):
            xobjects = xobjects.get_object()
        if not isinstance(xobjects, dict):
            continue
        for xobj_ref in xobjects.values():
            try:
                im = xobj_ref.get_object() if hasattr(xobj_ref, "get_object") else xobj_ref
                if im.get("/Subtype") != "/Image":
                    continue
                w = int(im.get("/Width", 0))
                h = int(im.get("/Height", 0))
                bpc = int(im.get("/BitsPerComponent", 8))
                if w < 400 or h < 400 or bpc != 8:
                    continue
                cs = im.get("/ColorSpace")
                if hasattr(cs, "get_object"):
                    cs = cs.get_object()
                raw = im.get_data()
                if isinstance(cs, list) and len(cs) >= 4 and str(cs[0]) == "/Indexed":
                    pal_obj = cs[3].get_object() if hasattr(cs[3], "get_object") else cs[3]
                    pal_bytes = (
                        pal_obj.get_data()
                        if hasattr(pal_obj, "get_data")
                        else bytes(pal_obj)
                    )
                    if len(raw) == w * h:
                        png_parts.extend(
                            _build_multiscale_png_parts_from_raw(
                                raw, w, h, bpp=1, color_type=3, pal_bytes=pal_bytes
                            )
                        )
                elif str(cs) == "/DeviceGray" and len(raw) == w * h:
                    png_parts.extend(
                        _build_multiscale_png_parts_from_raw(
                            raw, w, h, bpp=1, color_type=0
                        )
                    )
                elif str(cs) == "/DeviceRGB" and len(raw) == w * h * 3:
                    png_parts.extend(
                        _build_multiscale_png_parts_from_raw(
                            raw, w, h, bpp=3, color_type=2
                        )
                    )
            except Exception:
                continue
    return png_parts


def _parse_ppm_p6_to_multiscale_png_parts(ppm_bytes: bytes) -> list[Any]:
    """Parse a binary P6 PPM image output from pdftoppm into multi-scale PNG Parts."""
    m = re.match(rb"^P6\s+(\d+)\s+(\d+)\s+255[\s\n\r]", ppm_bytes)
    if not m:
        return []
    w = int(m.group(1))
    h = int(m.group(2))
    header_end = m.end()
    raw = ppm_bytes[header_end : header_end + w * h * 3]
    if len(raw) != w * h * 3:
        return []
    return _build_multiscale_png_parts_from_raw(raw, w, h, bpp=3, color_type=2)


def _render_pdf_pages_to_png_parts(pdf_bytes: bytes, dpi: int = 300) -> list[Any]:
    """Render vector/raster/hybrid PDF pages to 300-DPI multi-scale PNG google.genai Parts.

    Supports:
    - Pure vector/raster P&IDs (0 native text) -> Multi-scale 300-DPI PNG Parts (1 Full-Sheet + 4 Overlapping Quadrants per landscape drawing page).
    - Hybrid searchable-text CAD P&IDs & mixed text+drawing windows -> Native application/pdf Part PLUS multi-scale 300-DPI PNG Parts for any landscape drawing or large-XObject diagram pages.
    - Pure portrait text/table PDFs -> Native application/pdf Part without unnecessary quadrant tiling.
    """
    import io
    import shutil
    import subprocess  # nosec B404
    import tempfile

    from google.genai import types

    has_native_text = False
    has_landscape_or_diagram = False
    reader: pypdf.PdfReader | None = None
    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        total_text = "".join(
            (p.extract_text() or "") for p in reader.pages[:3]
        ).strip()
        has_native_text = len(total_text) >= 50
        for p in reader.pages:
            try:
                mb = p.mediabox
                is_land = float(mb.width) > float(mb.height) * 1.1
            except Exception:
                is_land = False
            p_txt_len = len((p.extract_text() or "").strip())
            if (is_land and (p_txt_len < 1500 or _page_has_large_xobject(p))) or _page_has_large_xobject(p):
                has_landscape_or_diagram = True
                break
    except Exception:
        has_native_text = False

    # 1. Fast lossless extraction for embedded high-DPI FlateDecode XObject drawings (works in both Cloud Run and agent_runtime)
    if reader is not None and (not has_native_text or has_landscape_or_diagram):
        try:
            xobj_parts = _extract_flate_xobjects_as_png_parts(reader)
            if xobj_parts:
                if has_native_text:
                    return [
                        types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                        *xobj_parts,
                    ]
                return xobj_parts
        except Exception as exc:
            logging.getLogger(__name__).debug(
                "Pure-Python XObject PNG extraction notice: %s", exc
            )

    # 2. 300-DPI pdftoppm rasterization with 2x2 overlapping quadrant tiling for vector/hybrid CAD drawings
    pdftoppm_bin = shutil.which("pdftoppm")
    if (not has_native_text or has_landscape_or_diagram) and pdftoppm_bin:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                pdf_tmp = tmp_path / "window.pdf"
                pdf_tmp.write_bytes(pdf_bytes)
                out_prefix = tmp_path / "page"
                subprocess.run(  # nosec B603
                    [
                        pdftoppm_bin,
                        "-r",
                        str(int(dpi)),
                        str(pdf_tmp),
                        str(out_prefix),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=90,
                )
                ppm_files = sorted(tmp_path.glob("page*.ppm"))
                rendered_parts: list[Any] = []
                for ppm_file in ppm_files:
                    rendered_parts.extend(
                        _parse_ppm_p6_to_multiscale_png_parts(ppm_file.read_bytes())
                    )
                if rendered_parts:
                    if has_native_text:
                        return [
                            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                            *rendered_parts,
                        ]
                    return rendered_parts
        except Exception as exc:
            logging.getLogger(__name__).debug(
                "300-DPI PNG rasterization fallback to application/pdf: %s", exc
            )

    return [types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")]


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
    cache_dir = Path(tempfile.gettempdir()) / "extracter_multimodal_cache_v8"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{cache_key_name}_{pdf_sha}.md"

    if cache_file.exists() and cache_file.stat().st_size > 100:
        return cache_file.read_text(encoding="utf-8")

    if cfg.use_gcs_storage:
        try:
            from google.cloud import storage

            st_client = storage.Client(project=cfg.google_cloud_project)
            bucket = st_client.bucket(cfg.destination_gcs_bucket)
            cache_blob = bucket.blob(f"cache/multimodal_v8/{cache_key_name}_{pdf_sha}.md")
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
    content_parts = _render_pdf_pages_to_png_parts(pdf_bytes, dpi=300)

    last_err: Exception | None = None
    gen_cfg_kwargs: dict[str, Any] = {
        "max_output_tokens": 65536,
        "temperature": 0.0,
    }
    media_res_enum = getattr(types, "MediaResolution", None)
    if media_res_enum is not None and hasattr(media_res_enum, "MEDIA_RESOLUTION_HIGH"):
        gen_cfg_kwargs["media_resolution"] = media_res_enum.MEDIA_RESOLUTION_HIGH
    gen_cfg = types.GenerateContentConfig(**gen_cfg_kwargs)
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
                contents=[*content_parts, base_prompt],
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
                            f"cache/multimodal_v8/{cache_key_name}_{pdf_sha}.md"
                        ).upload_from_string(text_out, content_type="text/markdown")
                except Exception as exc:
                    logging.getLogger(__name__).debug("Ignored non-fatal exception: %s", exc)
            return text_out
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2.0 * (2**attempt))
    return f"[Multimodal extraction error: {last_err}]"


def _group_adaptive_page_windows(
    reader: pypdf.PdfReader | None,
    target_indices: list[int],
    effective_window: int,
) -> list[list[int]]:
    """Group target page indices into windows, isolating embedded high-res landscape drawing pages into 1-page windows in mixed PDFs."""
    if reader is None or effective_window <= 1:
        return [
            target_indices[i : i + effective_window]
            for i in range(0, len(target_indices), effective_window)
        ]

    # Check if this is a mixed document containing both text pages and high-res landscape drawing pages
    drawing_indices: set[int] = set()
    for idx in target_indices:
        try:
            page = reader.pages[idx]
            mb = page.mediabox
            is_land = float(mb.width) > float(mb.height) * 1.1
            if is_land and _page_has_large_xobject(page):
                drawing_indices.add(idx)
        except Exception:
            continue

    if not drawing_indices:
        return [
            target_indices[i : i + effective_window]
            for i in range(0, len(target_indices), effective_window)
        ]

    windows: list[list[int]] = []
    current_batch: list[int] = []
    for idx in target_indices:
        if idx in drawing_indices:
            if current_batch:
                windows.append(current_batch)
                current_batch = []
            windows.append([idx])
        else:
            current_batch.append(idx)
            if len(current_batch) >= effective_window:
                windows.append(current_batch)
                current_batch = []
    if current_batch:
        windows.append(current_batch)
    return windows


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
    - Automatically adapts to 1-2 page windowing (`window_size=2`) on landscape vector CAD drawings (`is_vector_drawing(path)`) while keeping `window_size=4` for portrait text/table PDFs, and isolates embedded high-res landscape drawing pages in mixed PDFs into 1-page multi-scale quadrant windows.
    - Supports `start_page`, `max_pages`, and `page_query` filtering across multi-page documents.
    - For single-sheet or <= effective_window PDFs, executes a single cached call keyed by `(pdf_bytes, prompt)` SHA-256.
    - For multi-sheet PDFs (> effective_window pages, up to 150 pages), slices pages into effective_window batches via
      pypdf.PdfWriter, executes windows concurrently (up to 4 parallel workers) with max_output_tokens=65536,
      and caches each window deterministically under extracter_multimodal_cache_v6 / cache/multimodal_v6/.
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

    windows: list[list[int]] = _group_adaptive_page_windows(
        reader=reader,
        target_indices=target_indices,
        effective_window=effective_window,
    )

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




