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

