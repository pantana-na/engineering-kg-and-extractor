"""Unit tests for PDF document processor."""

from pathlib import Path

import pytest

from extracter_agent.pdf.processor import (
    PDFProcessingError,
    chunk_document_text,
    extract_equipment_tag_candidates,
    extract_pdf_pages,
    get_pdf_metadata,
)

SAMPLE_PDF = Path(
    "reference/raw/data_sheets/DS-V2301_Preflash_Column_Z1.pdf"
)


def _get_or_create_sample_pdf(tmp_path: Path) -> Path:
    """Return SAMPLE_PDF if present, or generate synthetic PDFs in tmp_path."""
    if SAMPLE_PDF.exists():
        return SAMPLE_PDF
    from scripts.generate_synthetic_reference import generate_synthetic_raw_pdfs

    raw_dir = tmp_path / "raw"
    generate_synthetic_raw_pdfs(raw_dir)
    return raw_dir / "data_sheets" / "DS-V2301_Preflash_Column_Z1.pdf"


def test_extract_pdf_pages_real_file(tmp_path: Path):
    """Test extraction on project sample PDF or generated fixture when reference/raw is purged."""
    target_pdf = _get_or_create_sample_pdf(tmp_path)

    pages = extract_pdf_pages(target_pdf)
    assert len(pages) == 9
    assert pages[0]["page_number"] == 1
    assert "V-2301" in pages[0]["text"]
    assert "Preflash" in pages[0]["text"]


def test_get_pdf_metadata(tmp_path: Path):
    """Test metadata retrieval on PDF."""
    target_pdf = _get_or_create_sample_pdf(tmp_path)
    meta = get_pdf_metadata(target_pdf)
    assert meta["file_name"] == SAMPLE_PDF.name
    assert meta["page_count"] == 9
    assert meta["file_size_bytes"] > 0


def test_nonexistent_pdf_raises_error():
    """Test that missing file raises PDFProcessingError."""
    with pytest.raises(PDFProcessingError):
        extract_pdf_pages(Path("nonexistent/path/file.pdf"))

    with pytest.raises(PDFProcessingError):
        get_pdf_metadata(Path("nonexistent/path/file.pdf"))


def test_chunk_document_text():
    """Test text chunking logic."""
    pages = [
        {"page_number": 1, "text": "Page 1 intro: V-2301 column details."},
        {"page_number": 2, "text": "Page 2 operating specs and reboiler."},
        {"page_number": 3, "text": "Page 3 materials of construction."},
    ]
    chunks = chunk_document_text(pages, max_chunk_size=50, overlap=10)
    assert len(chunks) >= 2
    assert chunks[0]["start_page"] == 1


def test_extract_equipment_tag_candidates():
    """Test regex candidate extraction helper across standard and multi-segment unit tags."""
    sample_text = (
        "Feed from OX-2201 enters V-2301, with reflux from P-2301AB and overhead"
        " to E-2301. In Unit 1-SF, skimmer pump 1-SF-P-11 feeds demineralizer 1-SF-DM-11"
        " and prefilter 1-SF-F-39."
    )
    tags = extract_equipment_tag_candidates(sample_text)
    assert "OX-2201" in tags
    assert "V-2301" in tags
    assert "P-2301AB" in tags
    assert "E-2301" in tags
    assert "1-SF-P-11" in tags
    assert "1-SF-DM-11" in tags
    assert "1-SF-F-39" in tags


def test_multimodal_start_page_and_max_pages_windowing(monkeypatch, tmp_path):
    """Verify extract_pdf_multimodal_summary respects start_page and max_pages and reuses per-window cache keys."""
    import pypdf

    from extracter_agent.pdf import processor

    pdf_path = tmp_path / "ML101620329_SAMPLE.pdf"
    writer = pypdf.PdfWriter()
    for _ in range(10):
        writer.add_blank_page(width=792, height=612)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    called_windows: list[str] = []

    def fake_single_window(
        pdf_bytes: bytes,
        cache_key_name: str,
        prompt_hint: str | None = None,
    ) -> str:
        called_windows.append(cache_key_name)
        return f"Extracted {cache_key_name}"

    monkeypatch.setattr(processor, "_extract_single_pdf_window_multimodal", fake_single_window)

    out = processor.extract_pdf_multimodal_summary(pdf_path, start_page=3, max_pages=4)
    assert called_windows == [
        "ML101620329_SAMPLE_p3-4",
        "ML101620329_SAMPLE_p5-6",
    ]
    assert "Pages 3–4 of 10" in out
    assert "Pages 5–6 of 10" in out
    assert "Pages 1–2 of 10" not in out


def test_resolve_bundle_instrument_link_case_insensitive_and_no_cross_unit_collision(tmp_path):
    """Verify resolve_bundle_instrument_link matches lowercase files and never links unmatched tags to unrelated single-tag files."""
    from extracter_agent.okf.synthesizer import resolve_bundle_instrument_link

    inst_dir = tmp_path / "instruments"
    inst_dir.mkdir(parents=True)
    (inst_dir / "index.md").write_text("# Instruments Index\n", encoding="utf-8")
    (inst_dir / "lt-0401.md").write_text(
        "---\ntype: Instrument Specification\ntitle: LT-0401 Level Transmitter\n---\n# LT-0401\n",
        encoding="utf-8",
    )
    (inst_dir / "1-re-2524.md").write_text(
        "---\ntype: Instrument Specification\ntitle: 1-RE-2524 Radiation Monitor\n---\n# 1-RE-2524\n",
        encoding="utf-8",
    )

    assert (
        resolve_bundle_instrument_link("1-RE-2524", "Radiation Monitor", "SFP Return", bundle_root=tmp_path)
        == "/instruments/1-re-2524.md"
    )
    assert (
        resolve_bundle_instrument_link("1-SF-PI-2517", "Pressure Indicator", "Pump Discharge", bundle_root=tmp_path)
        == "/instruments/index.md"
    )


def test_vector_pdf_300dpi_png_rasterization_and_single_page_windowing(monkeypatch, tmp_path):
    """Verify Option A: vector PDF windows rasterize to 300-DPI image/png Parts and process_raw_pdf_tool uses window_size=1 on vector drawings."""
    import pypdf

    from extracter_agent.pdf import processor
    from extracter_agent.tools import pdf_tools

    vec_pdf = tmp_path / "VECTOR_PID_SHEET.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=792, height=612)
    with open(vec_pdf, "wb") as f:
        writer.write(f)
    pdf_bytes = vec_pdf.read_bytes()

    parts = processor._render_pdf_pages_to_png_parts(pdf_bytes, dpi=300)
    assert len(parts) == 1
    inline_data = getattr(parts[0], "inline_data", None)
    assert inline_data is not None
    assert inline_data.mime_type in ("image/png", "application/pdf")

    # When pdftoppm is absent, falls back cleanly to application/pdf
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    fallback_parts = processor._render_pdf_pages_to_png_parts(pdf_bytes, dpi=300)
    assert len(fallback_parts) == 1
    assert fallback_parts[0].inline_data.mime_type == "application/pdf"

    # Verify process_raw_pdf_tool passes window_size=1 when is_vector_drawing is True
    captured_kwargs: dict[str, object] = {}

    def fake_mm_summary(file_path, **kwargs):
        captured_kwargs.update(kwargs)
        return "Verbatim Tag: F-33 (1-SF-F-33)"

    monkeypatch.setattr(pdf_tools, "is_vector_drawing", lambda p: True)
    monkeypatch.setattr(pdf_tools, "extract_pdf_multimodal_summary", fake_mm_summary)

    res = pdf_tools.process_raw_pdf_tool(
        pdf_filename=str(vec_pdf),
        subfolder="pid",
        enable_multimodal=True,
    )
    assert res["status"] == "success"
    assert captured_kwargs.get("window_size") == 1
    assert "F-33" in (res["multimodal_analysis"] or "")


def test_verbatim_tag_prompt_and_v5_300dpi_cache_invalidation():
    """Verify _build_multimodal_prompt mandates verbatim printed symbol tags, 3x2 center bridge zooms, cross-sheet continuity, nozzle size verification, arrowhead flow direction, and relief valve vs RO distinction."""
    from extracter_agent.pdf.processor import (
        _build_multimodal_prompt,
        _compute_multimodal_cache_digest,
    )

    prompt = _build_multimodal_prompt()
    assert "exact verbatim tag printed inside or beside each equipment symbol" in prompt
    assert "General Note" in prompt
    assert "6 overlapping high-resolution 3x2 regional zooms" in prompt
    assert "Top-Center Bridge" in prompt
    assert "Spanner-Graph-ready connectivity breakdown" in prompt
    assert "Cross-Sheet Line Continuity & Zero False Proximity Attachment" in prompt
    assert "Nozzle Line-Size Verification, Unique Valve Per Branch & Bypass Tee Tracing" in prompt
    assert "True Flow Direction via Arrowheads & Check Valves" in prompt
    assert "Relief Valves + Open Drains vs. Restriction Orifices" in prompt
    assert "physical leader line or impulse tap" in prompt
    assert "NEVER double-prefix it" in prompt
    digest = _compute_multimodal_cache_digest(b"%PDF-1.4 test", prompt)
    assert len(digest) == 24


def test_multiscale_2x2_quadrant_tiling_and_mixed_pdf_adaptive_windows():
    """Verify Step 31 (multimodal_v7): non-blank landscape drawings produce 7 PNG Parts (1 full + 6 overlapping 3x2 bridge tiles), portrait/blank pages produce 1 Part, and mixed PDFs isolate drawing pages into 1-page windows."""
    from extracter_agent.pdf.processor import (
        _build_multiscale_png_parts_from_raw,
        _group_adaptive_page_windows,
    )

    # 1. Non-blank landscape drawing (1800 x 1200) -> 7 PNG Parts (1 overview + 6 overlapping 3x2 tiles)
    w_land, h_land = 1800, 1200
    raw_non_blank = (b"\x00\xff\x80" * ((w_land * h_land) // 3 + 1))[: w_land * h_land]
    land_parts = _build_multiscale_png_parts_from_raw(
        raw_non_blank, w_land, h_land, bpp=1, color_type=0
    )
    assert len(land_parts) == 7
    for p in land_parts:
        assert p.inline_data.mime_type == "image/png"
        assert p.inline_data.data.startswith(b"\x89PNG\r\n\x1a\n")

    # 2. Portrait page (1200 x 1800) -> 1 PNG Part (no tile split)
    w_port, h_port = 1200, 1800
    raw_port = (b"\x10\xe0" * ((w_port * h_port) // 2))[: w_port * h_port]
    port_parts = _build_multiscale_png_parts_from_raw(
        raw_port, w_port, h_port, bpp=1, color_type=0
    )
    assert len(port_parts) == 1

    # 3. Mixed PDF adaptive windowing: pages 0,1,2 are portrait text; page 3 is landscape high-res drawing; pages 4,5 are portrait text
    class FakeBox:
        def __init__(self, width: float, height: float):
            self.width = width
            self.height = height

    class FakePage:
        def __init__(self, width: float, height: float, has_xobj: bool):
            self.mediabox = FakeBox(width, height)
            self._has_xobj = has_xobj

        def get(self, key: str):
            if key == "/Resources" and self._has_xobj:
                return {
                    "/XObject": {
                        "/Im0": {
                            "/Subtype": "/Image",
                            "/Width": 4970,
                            "/Height": 3234,
                        }
                    }
                }
            return {}

    class FakeReader:
        def __init__(self):
            self.pages = [
                FakePage(612, 792, False),  # p0: portrait text
                FakePage(612, 792, False),  # p1: portrait text
                FakePage(612, 792, False),  # p2: portrait text
                FakePage(1224, 792, True),  # p3: landscape P&ID drawing
                FakePage(612, 792, False),  # p4: portrait text
                FakePage(612, 792, False),  # p5: portrait text
            ]

    windows = _group_adaptive_page_windows(
        reader=FakeReader(),  # type: ignore[arg-type]
        target_indices=[0, 1, 2, 3, 4, 5],
        effective_window=4,
    )
    assert windows == [[0, 1, 2], [3], [4, 5]]



