"""Property-based tests for PDF document processor using Hypothesis."""

from hypothesis import given
from hypothesis import strategies as st

from extracter_agent.pdf.processor import (
    chunk_document_text,
    extract_equipment_tag_candidates,
)


@given(
    page_texts=st.lists(st.text(min_size=0, max_size=500), max_size=15),
    max_chunk_size=st.integers(min_value=100, max_value=2000),
    overlap=st.integers(min_value=0, max_value=50),
)
def test_pbt_chunk_document_text_invariants(page_texts, max_chunk_size, overlap):
    """Invariant: Chunking never loses pages and assigns valid 1-based bounds."""
    pages = [
        {"page_number": idx + 1, "text": txt} for idx, txt in enumerate(page_texts)
    ]
    chunks = chunk_document_text(pages, max_chunk_size=max_chunk_size, overlap=overlap)

    non_empty_pages = [p for p in pages if p["text"].strip()]
    if not non_empty_pages:
        assert len(chunks) == 0
    else:
        assert len(chunks) >= 1
        for chunk in chunks:
            assert 1 <= chunk["start_page"] <= len(pages)
            assert 1 <= chunk["end_page"] <= len(pages)
            assert chunk["start_page"] <= chunk["end_page"]
            assert chunk["char_count"] > 0


@given(arbitrary_text=st.text())
def test_pbt_extract_tag_candidates_safe(arbitrary_text):
    """Invariant: Candidate tag extraction never throws exceptions and returns strings."""
    candidates = extract_equipment_tag_candidates(arbitrary_text)
    assert isinstance(candidates, list)
    for tag in candidates:
        assert isinstance(tag, str)
        assert "-" in tag
