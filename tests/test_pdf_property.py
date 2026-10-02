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


@given(
    raw_bytes=st.binary(min_size=1, max_size=256),
    prompt_hint=st.text(min_size=0, max_size=120),
)
def test_pbt_render_pdf_pages_to_png_parts_fallback_and_digest_invariants(
    raw_bytes: bytes,
    prompt_hint: str,
) -> None:
    """Invariant: _compute_multimodal_cache_digest is deterministic 24-hex and _render_pdf_pages_to_png_parts never raises on arbitrary bytes."""
    from extracter_agent.pdf.processor import (
        _build_multimodal_prompt,
        _compute_multimodal_cache_digest,
        _render_pdf_pages_to_png_parts,
    )

    prompt = _build_multimodal_prompt(prompt_hint=prompt_hint or None)
    d1 = _compute_multimodal_cache_digest(raw_bytes, prompt)
    d2 = _compute_multimodal_cache_digest(raw_bytes, prompt)
    d_mut = _compute_multimodal_cache_digest(raw_bytes + b"\x01", prompt)

    assert len(d1) == 24
    assert d1 == d2
    assert d1 != d_mut

    parts = _render_pdf_pages_to_png_parts(raw_bytes, dpi=150)
    assert isinstance(parts, list)
    assert len(parts) >= 1


@given(
    w=st.integers(min_value=16, max_value=120),
    h=st.integers(min_value=16, max_value=120),
    effective_window=st.integers(min_value=1, max_value=6),
    page_count=st.integers(min_value=1, max_value=20),
)
def test_pbt_encode_raw_crop_and_adaptive_windows_invariants(
    w: int,
    h: int,
    effective_window: int,
    page_count: int,
) -> None:
    """Invariant: _encode_raw_crop_as_png produces valid PNG headers/footers and _group_adaptive_page_windows preserves exact page order without loss or duplication."""
    from extracter_agent.pdf.processor import (
        _encode_raw_crop_as_png,
        _group_adaptive_page_windows,
    )

    raw = bytes((i % 256) for i in range(w * h))
    cw = max(1, w // 2)
    ch = max(1, h // 2)
    png_bytes = _encode_raw_crop_as_png(
        raw=raw,
        w=w,
        h=h,
        bpp=1,
        color_type=0,
        x0=w - cw,
        y0=h - ch,
        cw=cw,
        ch=ch,
    )
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert png_bytes.endswith(b"IEND\xaeB`\x82")

    indices = list(range(page_count))
    windows = _group_adaptive_page_windows(
        reader=None,
        target_indices=indices,
        effective_window=effective_window,
    )
    flattened = [idx for win in windows for idx in win]
    assert flattened == indices
    assert all(1 <= len(win) <= effective_window for win in windows)

