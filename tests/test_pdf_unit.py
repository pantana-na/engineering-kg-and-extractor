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


def test_extract_pdf_pages_real_file():
    """Test extraction on actual project sample PDF in reference/raw."""
    assert SAMPLE_PDF.exists(), f"Sample PDF missing: {SAMPLE_PDF}"

    pages = extract_pdf_pages(SAMPLE_PDF)
    assert len(pages) == 9
    assert pages[0]["page_number"] == 1
    assert "V-2301" in pages[0]["text"]
    assert "Preflash" in pages[0]["text"]


def test_get_pdf_metadata():
    """Test metadata retrieval on actual PDF."""
    meta = get_pdf_metadata(SAMPLE_PDF)
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
    """Test regex candidate extraction helper."""
    sample_text = (
        "Feed from OX-2201 enters V-2301, with reflux from P-2301AB and overhead"
        " to E-2301."
    )
    tags = extract_equipment_tag_candidates(sample_text)
    assert "OX-2201" in tags
    assert "V-2301" in tags
    assert "P-2301AB" in tags
    assert "E-2301" in tags
