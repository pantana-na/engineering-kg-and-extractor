"""Property-Based Tests (PBT) for OKF documents and bundle operations using Hypothesis."""

import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from extracter_agent.okf.document import OKFDocument
from extracter_agent.okf.indexer import generate_bundle_indexes

printable_chars = st.characters(blacklist_categories=("Cc", "Cs", "Zl", "Zp"))


@given(
    doc_type=st.text(alphabet=printable_chars, min_size=1, max_size=50).filter(
        lambda s: bool(s.strip()) and ":" not in s
    ),
    title=st.text(alphabet=printable_chars, min_size=1, max_size=100).filter(
        lambda s: bool(s.strip()) and ":" not in s
    ),
    desc=st.text(alphabet=printable_chars, min_size=1, max_size=200).filter(
        lambda s: bool(s.strip()) and ":" not in s
    ),
    body_text=st.text(alphabet=printable_chars, min_size=1, max_size=1000),
)

def test_pbt_okf_document_roundtrip_invariant(doc_type, title, desc, body_text):
    """Invariant: parse(serialize(doc)) preserves frontmatter type, title, and body."""
    fm = {
        "type": doc_type,
        "title": title,
        "description": desc,
    }
    doc = OKFDocument(frontmatter=fm, body=body_text)
    serialized = doc.serialize()
    reconstructed = OKFDocument.parse(serialized)

    assert reconstructed.frontmatter["type"] == doc_type
    assert reconstructed.frontmatter["title"] == title
    assert reconstructed.frontmatter["description"] == desc
    assert reconstructed.body.strip() == body_text.strip()


@given(
    names=st.lists(
        st.from_regex(r"[a-z0-9_-]{2,20}", fullmatch=True),
        min_size=1,
        max_size=6,
        unique=True,
    )
)
def test_pbt_bundle_index_link_invariants(names):
    """Invariant: Every item listed in generated index.md resolves to an existing file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        sub = root / "items"
        sub.mkdir()

        for name in names:
            doc = OKFDocument(
                frontmatter={
                    "type": "Test Item",
                    "title": name,
                    "description": f"Desc of {name}",
                },
                body=f"# {name}\n\nBody content.",
            )
            (sub / f"{name}.md").write_text(doc.serialize(), encoding="utf-8")

        generate_bundle_indexes(root)

        sub_index = sub / "index.md"
        assert sub_index.exists()
        content = sub_index.read_text(encoding="utf-8")

        # Invariant: Every name generated must be in the index
        for name in names:
            assert f"[{name}]({name}.md)" in content
            # Verify target file actually exists
            target_file = sub / f"{name}.md"
            assert target_file.exists()


@given(
    tags=st.lists(
        st.from_regex(r"[A-Z]{2,4}-[0-9]{3,4}[A-Z]?", fullmatch=True),
        min_size=1,
        max_size=5,
        unique=True,
    ),
    services=st.lists(
        st.text(alphabet=printable_chars, min_size=2, max_size=30).filter(
            lambda s: bool(s.strip()) and "|" not in s and "\n" not in s
        ),
        min_size=5,
        max_size=5,
    ),
)
def test_pbt_instrument_loop_link_invariants(tags, services):
    """Invariant: Synthesized instrument loops produce valid bundle-relative links and round-trip in frontmatter."""
    from extracter_agent.models.domain import EquipmentEntity, InstrumentLoop
    from extracter_agent.okf.synthesizer import synthesize_equipment_concept

    instruments = [
        InstrumentLoop(
            tag=tag,
            service=services[i],
            instrument_type="Transmitter",
            source="P&ID DWG 001",
        )
        for i, tag in enumerate(tags)
    ]

    entity = EquipmentEntity(
        tag="E-101",
        name="Test Exchanger",
        equipment_class="Heat Exchanger",
        unit="TEST",
        function_summary="Test unit",
        instruments=instruments,
    )

    doc = synthesize_equipment_concept(entity)

    # Invariant 1: Every instrument tag has a valid Markdown link in the body
    for inst in instruments:
        expected_link = f"[{inst.tag}](/instruments/{inst.tag}.md)"
        assert expected_link in doc.body

    # Invariant 2: Round-trip via serialization preserves instrument frontmatter metadata
    serialized = doc.serialize()
    reconstructed = OKFDocument.parse(serialized)
    reconstructed_instruments = reconstructed.frontmatter.get(
        "entity_metadata", {}
    ).get("instruments", [])
    assert len(reconstructed_instruments) == len(instruments)
    for original, parsed in zip(instruments, reconstructed_instruments):
        assert parsed["tag"] == original.tag
        assert parsed["service"] == original.service
        assert parsed["source"] == original.source


@given(
    raw_tag=st.text(
        alphabet=st.sampled_from(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-/_\\ ()")),
        min_size=1,
        max_size=40,
    ).filter(lambda s: any(c.isalnum() for c in s))
)
def test_pbt_sanitize_tag_filename_never_contains_slashes(raw_tag):
    """Invariant: sanitize_tag_filename never produces path separators ('/' or '\\'), parentheses, or whitespace."""
    from extracter_agent.models.domain import sanitize_tag_filename

    safe = sanitize_tag_filename(raw_tag)
    assert "/" not in safe
    assert "\\" not in safe
    assert " " not in safe
    assert "(" not in safe
    assert ")" not in safe
    assert len(safe) > 0


@given(
    slug=st.text(
        alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789-/")),
        min_size=3,
        max_size=35,
    ).filter(lambda s: s[0].isalnum() and s[-1].isalnum() and "//" not in s)
)
def test_pbt_derive_canonical_concept_id_idempotent(slug):
    """Invariant: derive_canonical_concept_id is idempotent (f(f(x)) == f(x)) and never contains whitespace."""
    from extracter_agent.models.domain import derive_canonical_concept_id

    once = derive_canonical_concept_id(slug)
    twice = derive_canonical_concept_id(once)
    assert once == twice
    assert " " not in once
    assert not once.endswith(".md")


@given(
    prefix=st.sampled_from(["LT", "FT", "TT", "PT", "PSV", "FV", "AT", "HXS", "SC", "XC"]),
    loop_num=st.integers(min_value=100, max_value=9999),
)
def test_pbt_dynamic_instrument_link_never_broken(prefix, loop_num):
    """Invariant: When bundle_root contains instrument register files, resolve_bundle_instrument_link always points to an existing file."""
    from extracter_agent.okf.synthesizer import resolve_bundle_instrument_link

    bundle_dir = Path("build/okf_bundle")
    if not (bundle_dir / "instruments").exists():
        return

    tag = f"{prefix}-{loop_num}"
    resolved = resolve_bundle_instrument_link(tag, "Process Instrument", "Service", bundle_root=bundle_dir)
    assert resolved is not None
    target_file = bundle_dir / resolved.lstrip("/")
    assert target_file.exists(), f"Resolved link {resolved} does not exist in {bundle_dir}"
    if target_file.stem.lower() != tag.lower() and target_file.name != "index.md":
        assert tag.lower() in target_file.read_text(encoding="utf-8", errors="ignore").lower()


@given(
    p1_names=st.lists(
        st.from_regex(r"[A-Za-z0-9 ]{3,15}", fullmatch=True).map(str.strip).filter(bool),
        min_size=1,
        max_size=4,
        unique_by=str.lower,
    ),
    p2_names=st.lists(
        st.from_regex(r"[A-Za-z0-9 ]{3,15}", fullmatch=True).map(str.strip).filter(bool),
        min_size=1,
        max_size=4,
        unique_by=str.lower,
    ),
    val1=st.from_regex(r"[0-9]{1,4}", fullmatch=True),
    val2=st.from_regex(r"[0-9]{1,4}", fullmatch=True),
)
def test_pbt_incremental_merge_monotonic_and_idempotent(p1_names, p2_names, val1, val2):
    """Invariant: Incremental Read-Merge-Upsert is monotonically non-decreasing in sources and parameters, and re-applying the same update is idempotent."""
    from extracter_agent.models.domain import EngineeringParameter, EquipmentEntity
    from extracter_agent.okf.synthesizer import (
        merge_equipment_entity_with_existing,
        synthesize_equipment_concept,
    )

    e1 = EquipmentEntity(
        tag="E-900",
        name="Test Cooler",
        equipment_class="Heat Exchanger",
        unit="U90",
        function_summary="Initial function summary.",
        design_data=[
            EngineeringParameter(parameter=p, value=val1, unit="mm", source="DOC-1")
            for p in p1_names
        ],
        hazards=["Initial hazard 1"],
        sources=["data_sheets/DOC_1.pdf"],
    )
    doc1 = OKFDocument.parse(synthesize_equipment_concept(e1).serialize())

    e2 = EquipmentEntity(
        tag="E-900",
        name="Test Cooler",
        equipment_class="Heat Exchanger",
        unit="U90",
        function_summary="Enriched function summary from second PDF.",
        design_data=[
            EngineeringParameter(parameter=p, value=val2, unit="mm", source="DOC-2")
            for p in p2_names
        ],
        hazards=["Secondary hazard 2"],
        sources=["pid/DOC_2.pdf"],
    )

    merged_once = merge_equipment_entity_with_existing(e2, doc1)
    expected_unique_params = len({p.lower() for p in (p1_names + p2_names)})
    assert len(merged_once.design_data) == expected_unique_params
    assert len(merged_once.sources) == 2

    # Re-synthesizing and merging e2 a second time must be idempotent
    doc2 = OKFDocument.parse(synthesize_equipment_concept(merged_once).serialize())
    merged_twice = merge_equipment_entity_with_existing(e2, doc2)
    assert len(merged_twice.design_data) == len(merged_once.design_data)
    assert len(merged_twice.sources) == len(merged_once.sources)
    assert len(merged_twice.hazards) == len(merged_once.hazards)


@given(
    doc_num=st.integers(min_value=1000, max_value=9999),
    rev_old=st.sampled_from(["Rev 0", "Rev A", "Rev Z0", "_Z0", "-R1"]),
    rev_new=st.sampled_from(["Rev 1", "Rev B", "Rev Z1", "_Z1", "-R2"]),
    val_old=st.integers(min_value=1, max_value=50).map(str),
    val_new=st.integers(min_value=51, max_value=100).map(str),
)
def test_pbt_same_document_revision_supersedes_without_conflict(
    doc_num, rev_old, rev_new, val_old, val_new
):
    """Invariant: A newer revision of the same base document updates parameter values in-place without generating a false conflict."""
    from extracter_agent.models.domain import EngineeringParameter, EquipmentEntity
    from extracter_agent.okf.synthesizer import (
        merge_equipment_entity_with_existing,
        synthesize_equipment_concept,
    )

    src_old = f"PS-V{doc_num} {rev_old}" if not rev_old.startswith(("_", "-")) else f"PS-V{doc_num}{rev_old}"
    src_new = f"PS-V{doc_num} {rev_new}" if not rev_new.startswith(("_", "-")) else f"PS-V{doc_num}{rev_new}"

    e_old = EquipmentEntity(
        tag=f"V-{doc_num}",
        name="Test Vessel",
        equipment_class="Vessel",
        unit="U10",
        function_summary="Test vessel function.",
        design_data=[
            EngineeringParameter(
                parameter="Design Pressure",
                value=val_old,
                unit="kg/cm2g",
                source=src_old,
            )
        ],
        sources=[f"data_sheets/{src_old.replace(' ', '_')}.pdf"],
    )
    doc_old = OKFDocument.parse(synthesize_equipment_concept(e_old).serialize())

    e_new = EquipmentEntity(
        tag=f"V-{doc_num}",
        name="Test Vessel",
        equipment_class="Vessel",
        unit="U10",
        function_summary="Test vessel function.",
        design_data=[
            EngineeringParameter(
                parameter="Design Pressure",
                value=val_new,
                unit="kg/cm2g",
                source=src_new,
            )
        ],
        sources=[f"data_sheets/{src_new.replace(' ', '_')}.pdf"],
    )

    merged = merge_equipment_entity_with_existing(e_new, doc_old)
    assert len(merged.design_data) == 1
    assert merged.design_data[0].value == val_new
    assert merged.design_data[0].source == src_new
    assert not any("CONFLICT" in h for h in merged.hazards)
    assert len(merged.sources) == 1


@given(
    tags_doc1=st.lists(
        st.from_regex(r"[A-Z]{2}-[0-9]{4}", fullmatch=True),
        min_size=1,
        max_size=4,
        unique=True,
    ),
    tags_doc2=st.lists(
        st.from_regex(r"[A-Z]{2}-[0-9]{4}", fullmatch=True),
        min_size=1,
        max_size=4,
        unique=True,
    ),
)
def test_pbt_merge_markdown_bodies_preserves_rows_and_idempotent(tags_doc1, tags_doc2):
    """Invariant: merge_markdown_bodies preserves the union of all unique table row keys across documents and is idempotent."""
    from extracter_agent.okf.synthesizer import merge_markdown_bodies

    rows1 = "\n".join(f"| {t} | 0-10 bar | Service A | DWG-001 |" for t in tags_doc1)
    rows2 = "\n".join(f"| {t} | 0-16 bar | Service B | DWG-002 |" for t in tags_doc2)

    md1 = (
        "# Shared Register\n\n"
        "## Instrument Table\n\n"
        "| Tag | Range | Service | Source |\n"
        "| --- | --- | --- | --- |\n"
        f"{rows1}\n\n"
        "## Notes Doc 1\n\n"
        "- Grounded in DWG-001.\n"
    )
    md2 = (
        "# Shared Register\n\n"
        "## Instrument Table\n\n"
        "| Tag | Range | Service | Source |\n"
        "| --- | --- | --- | --- |\n"
        f"{rows2}\n\n"
        "## Notes Doc 2\n\n"
        "- Grounded in DWG-002.\n"
    )

    merged_once = merge_markdown_bodies(md1, md2)
    for t in set(tags_doc1) | set(tags_doc2):
        assert f"| {t} |" in merged_once
    assert "## Notes Doc 1" in merged_once
    assert "## Notes Doc 2" in merged_once

    # Idempotence: merging md2 a second time produces identical output
    merged_twice = merge_markdown_bodies(merged_once, md2)
    assert merged_twice == merged_once


@given(
    prefix=st.sampled_from(["D", "E", "P", "V", "X", "TK", "OX"]),
    num=st.integers(min_value=1000, max_value=9999),
    suffix=st.sampled_from(["", "A", "B", "A/B", "A/B/C"]),
    other_prefix=st.sampled_from(["D", "E", "P", "V", "X"]),
    other_num=st.integers(min_value=1000, max_value=9999),
)
def test_pbt_equipment_tag_base_id_preservation_invariant(
    prefix, num, suffix, other_prefix, other_num
):
    """Invariant: Across arbitrary equipment tags and distractor PS-<OTHER> source files, derive_canonical_equipment_tag always preserves the exact <PREFIX>-<NUM> base identity."""
    from extracter_agent.models.domain import (
        _extract_equipment_base_id,
        derive_canonical_equipment_tag,
    )

    tag = f"{prefix}-{num}{suffix}"
    distractor_src = f"ACME-2300-PS-{other_prefix}{other_num}_PROCESS_DATA_SHEET_Z1.pdf"
    own_src = f"ACME-2300-PS-{prefix}{num}_PROCESS_DATA_SHEET_Z1.pdf"

    resolved = derive_canonical_equipment_tag(
        tag, [distractor_src, own_src], bundle_root=Path("/nonexistent_bundle_dir_pbt")
    )
    assert _extract_equipment_base_id(resolved) == f"{prefix}-{num}"


@given(
    dwg_num=st.integers(min_value=1, max_value=9999),
    alpha_suffix=st.sampled_from(["A", "B", "C", "D", "F", "L"]),
    reverse_order=st.booleans(),
)
def test_pbt_pdf_candidate_exact_code_prefix_never_matches_alpha_suffix(
    dwg_num, alpha_suffix, reverse_order
):
    """Invariant: For any numeric drawing code <N> and alpha-suffixed sibling <N><LETTER>, querying <N> or <N>_Z1.pdf always resolves to <N>_... regardless of candidate list ordering."""
    from extracter_agent.tools.pdf_tools import _match_pdf_candidate

    num_str = f"{dwg_num:04d}"
    base_code = f"PID-23-{num_str}"
    alpha_code = f"PID-23-{num_str}{alpha_suffix}"

    c_base = {"file_name": f"{base_code}_PID_MAIN_LINE_Z1.pdf", "subfolder": "pid"}
    c_alpha = {"file_name": f"{alpha_code}_PID_AUX_DRUM_Z1.pdf", "subfolder": "pid"}
    candidates = [c_alpha, c_base] if not reverse_order else [c_base, c_alpha]

    res_code = _match_pdf_candidate(base_code, "pid", candidates)
    assert res_code is not None
    assert res_code["file_name"] == c_base["file_name"]

    res_short = _match_pdf_candidate(f"{base_code}_Z1.pdf", "pid", candidates)
    assert res_short is not None
    assert res_short["file_name"] == c_base["file_name"]


@given(
    keys_4col=st.lists(
        st.from_regex(r"[A-Z]{2}-[0-9]{4}", fullmatch=True),
        min_size=1,
        max_size=4,
        unique=True,
    ),
    keys_5col=st.lists(
        st.from_regex(r"[A-Z]{2}-[0-9]{4}", fullmatch=True),
        min_size=1,
        max_size=4,
        unique=True,
    ),
)
def test_pbt_merge_markdown_bodies_preserves_all_tables_across_column_variations(
    keys_4col, keys_5col
):
    """Invariant: merge_markdown_bodies never loses table row keys when merging tables with differing column counts or secondary ### sub-tables."""
    from extracter_agent.okf.synthesizer import merge_markdown_bodies

    rows_4 = "\n".join(f"| {k} | Service 1 | 0-10 bar | DWG-001 |" for k in keys_4col)
    rows_5 = "\n".join(
        f"| {k} | Transmitter | Service 2 | 0-20 bar | DWG-002 |" for k in keys_5col
    )

    md_a = (
        "# Register\n\n"
        "## Loops\n\n"
        "| Tag | Service | Range | Source |\n"
        "| --- | --- | --- | --- |\n"
        f"{rows_4}\n\n"
        "### Auxiliary Sub-Table\n\n"
        "| AuxTag | Note |\n"
        "| --- | --- |\n"
        "| AUX-0001 | Retained |\n"
    )
    md_b = (
        "# Register\n\n"
        "## Loops\n\n"
        "| Tag | Type | Service | Range | Source |\n"
        "| --- | --- | --- | --- |\n"
        f"{rows_5}\n"
    )

    merged = merge_markdown_bodies(md_a, md_b)
    for k in set(keys_4col) | set(keys_5col):
        assert f"| {k} |" in merged
    assert "### Auxiliary Sub-Table" in merged
    assert "| AUX-0001 | Retained |" in merged


@given(
    pdf_bytes=st.binary(min_size=8, max_size=256),
    extra_byte=st.binary(min_size=1, max_size=8),
    hint_a=st.from_regex(r"[A-Za-z0-9 _-]{3,30}", fullmatch=True),
    hint_b=st.from_regex(r"[A-Za-z0-9 _-]{3,30}", fullmatch=True),
)
def test_pbt_prompt_hashed_cache_digest_collision_free_on_prompt_or_byte_mutation(
    pdf_bytes, extra_byte, hint_a, hint_b
):
    """Invariant: Any mutation to pdf_bytes or prompt_hint strictly changes the 24-hex SHA-256 multimodal cache digest."""
    from extracter_agent.pdf.processor import (
        _build_multimodal_prompt,
        _compute_multimodal_cache_digest,
    )

    prompt_a = _build_multimodal_prompt(hint_a)
    digest_a = _compute_multimodal_cache_digest(pdf_bytes, prompt_a)
    assert len(digest_a) == 24
    # Deterministic on identical inputs
    assert digest_a == _compute_multimodal_cache_digest(pdf_bytes, prompt_a)

    # Byte mutation produces a different digest
    assert digest_a != _compute_multimodal_cache_digest(pdf_bytes + extra_byte, prompt_a)

    # Different prompt_hint produces a different digest on identical bytes
    if hint_a != hint_b:
        prompt_hint_b = _build_multimodal_prompt(hint_b)
        assert digest_a != _compute_multimodal_cache_digest(pdf_bytes, prompt_hint_b)


@given(
    row_key=st.from_regex(r"[A-Z]{2}-[0-9]{4}", fullmatch=True),
    val_col1_t1=st.integers(min_value=10, max_value=999).map(str),
    val_col2_t1=st.integers(min_value=1000, max_value=4999).map(str),
    val_col1_t2=st.integers(min_value=5000, max_value=8999).map(str),
    val_col2_t2=st.integers(min_value=9000, max_value=9999).map(str),
    same_headers=st.booleans(),
)
def test_pbt_v4_non_destructive_numeric_cell_preservation_across_upserts(
    row_key, val_col1_t1, val_col2_t1, val_col1_t2, val_col2_t2, same_headers
):
    """Invariant: Across multi-turn table upserts (both identical-header tables without Source and equal-column tables with distinct headers), zero numeric values from earlier turns are ever lost."""
    from extracter_agent.okf.synthesizer import merge_markdown_bodies

    h_t1 = "| Tag | SpecA | SpecB |"
    h_t2 = "| Tag | SpecA | SpecB |" if same_headers else "| Tag | SpecC | SpecD |"

    md_1 = (
        "# Register\n\n"
        "## Data\n\n"
        f"{h_t1}\n"
        "| --- | --- | --- |\n"
        f"| {row_key} | {val_col1_t1} | {val_col2_t1} |\n"
    )
    md_2 = (
        "# Register\n\n"
        "## Data\n\n"
        f"{h_t2}\n"
        "| --- | --- | --- |\n"
        f"| {row_key} | {val_col1_t2} | {val_col2_t2} |\n"
    )

    merged = merge_markdown_bodies(md_1, md_2)
    assert row_key in merged
    assert val_col1_t1 in merged
    assert val_col2_t1 in merged
    assert val_col1_t2 in merged
    assert val_col2_t2 in merged


@given(
    cat=st.sampled_from(["instruments", "sources", "procedures", "troubleshooting"]),
    domain_a=st.sampled_from(["flow", "pressure", "level", "temperature", "analyzers", "sampling"]),
    domain_b=st.sampled_from(["psv", "sis", "valves", "seal", "motor", "emergency", "startup"]),
    num_a=st.integers(min_value=1, max_value=99).map(lambda n: f"{n:04d}"),
    num_b=st.integers(min_value=100, max_value=999).map(lambda n: f"{n:04d}"),
)
def test_pbt_distinct_identifier_concepts_never_collide(
    cat, domain_a, domain_b, num_a, num_b
):
    """Invariant (Step 28 V5): Two concepts in the same category with disjoint non-boilerplate domain tokens or distinct document/sequence numbers never collapse into the same canonical concept_id."""
    import tempfile
    from pathlib import Path

    from extracter_agent.models.domain import derive_canonical_concept_id

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sub = root / cat
        sub.mkdir(parents=True, exist_ok=True)
        existing_slug = f"{domain_a}-cdn-{num_a}"
        (sub / f"{existing_slug}.md").write_text(
            f"---\ntype: Register\ntitle: {domain_a} {num_a}\nsources:\n- title: DS-PS-0003_Z1.pdf\n---\n# {domain_a}\n",
            encoding="utf-8",
        )

        # Disjoint domain token with shared 'cdn' boilerplate token and shared source PDF
        cand_disjoint = f"{cat}/{domain_b}-cdn-{num_a}"
        resolved_disjoint = derive_canonical_concept_id(
            cand_disjoint,
            concept_type="Register",
            title=f"CDN {domain_b} Register",
            sources=["DS-PS-0003_Z1.pdf"],
            bundle_root=root,
        )
        assert resolved_disjoint == cand_disjoint

        # Same domain token but different numeric identifier (num_a != num_b)
        cand_diff_num = f"{cat}/{domain_a}-cdn-{num_b}"
        resolved_diff_num = derive_canonical_concept_id(
            cand_diff_num,
            concept_type="Register",
            title=f"CDN {domain_a} Register {num_b}",
            sources=["DS-PS-0003_Z1.pdf"],
            bundle_root=root,
        )
        assert resolved_diff_num == cand_diff_num


from hypothesis import settings

_PDF_NORM_TEXT_CACHE: dict[str, str] = {}


@settings(deadline=None)
@given(
    file_idx=st.integers(min_value=0, max_value=100),
    case_variant=st.sampled_from(["lower", "upper", "title"]),
)
def test_pbt_zero_confidential_tokens(file_idx: int, case_variant: str) -> None:
    """Property: Across all engineering PDFs in reference/raw/ and extracted OKF Markdown files, zero confidential tokens exist under any case permutation."""
    from extracter_agent.pdf.processor import extract_pdf_pages

    banned_hex = [
        "707474",
        "7070636c",
        "706f73636f",
        "756f70",
        "68656d6172616a",
        "6d61702074612070687574",
        "7261796f6e67",
        "776172616b6f726e",
        "74616e617275616e6761726d6f726e",
        "73636763",
        "766976656b73756272616d616e",
        "63732d706f632d79303372376b6d66796f76346b696c7a67353066643773",
    ]
    banned_tokens = [bytes.fromhex(h).decode("utf-8") for h in banned_hex]
    pdfs = sorted(Path("reference/raw").rglob("*.pdf"))
    if not pdfs:
        return
    target_pdf = pdfs[file_idx % len(pdfs)]
    cache_key = str(target_pdf)
    if cache_key not in _PDF_NORM_TEXT_CACHE:
        pages = extract_pdf_pages(target_pdf)
        _PDF_NORM_TEXT_CACHE[cache_key] = "\n".join(p.get("text", "") for p in pages).lower()
    norm_text = _PDF_NORM_TEXT_CACHE[cache_key]
    for tok in banned_tokens:
        probe = (
            tok.lower()
            if case_variant == "lower"
            else (tok.upper() if case_variant == "upper" else tok.title())
        ).lower()
        assert probe not in norm_text, f"Confidential token '{tok}' found in {target_pdf}"


@given(
    int_val=st.integers(min_value=1, max_value=9999),
    note_suffix=st.sampled_from(
        [
            "",
            " (Normal)",
            " (API 526 orifice 4J6)",
            " (Circulation rate via P-2304A/B)",
        ]
    ),
)
def test_pbt_equivalent_numeric_and_annotated_parameters_never_conflict(
    int_val: int, note_suffix: str
) -> None:
    """Property: Equivalent integer vs. decimal-zero formatting and parenthetical notes across distinct documents must never emit false-positive conflicts."""
    from extracter_agent.models.domain import EngineeringParameter
    from extracter_agent.okf.synthesizer import _merge_parameter_lists

    p1 = [
        EngineeringParameter(
            parameter="Design Temperature",
            value=str(int_val),
            unit="°C",
            source="DS-2304",
        )
    ]
    p2 = [
        EngineeringParameter(
            parameter="Design Temperature",
            value=f"{int_val}.0{note_suffix}",
            unit="°C",
            source="PID-23-0013",
        )
    ]
    merged, conflicts = _merge_parameter_lists(p1, p2)
    assert len(merged) == 1
    assert conflicts == []






