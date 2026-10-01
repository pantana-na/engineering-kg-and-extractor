"""Property-based tests (Hypothesis) for the OKF Spanner Graph & Retrieval Workbench (`okf-query-agent-web`)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from query_agent.spanner.repository import SpannerGraphRepository
from query_agent.web_server import (
    _extract_referenced_tags,
    _summarize_tool_output,
    compute_telemetry_totals,
)
from tests.test_query_web_server_unit import build_seeded_in_memory_repo

_SHARED_MEM_REPO: SpannerGraphRepository | None = None


def _get_mem_repo() -> SpannerGraphRepository:
    global _SHARED_MEM_REPO
    if _SHARED_MEM_REPO is None:
        _SHARED_MEM_REPO = build_seeded_in_memory_repo()
    return _SHARED_MEM_REPO


@settings(max_examples=25, deadline=None)
@given(
    center_tag=st.sampled_from(
        ["D-2304", "E-2304", "PSV-2304A", "hazards/CHP", "UNKNOWN-9999"]
    ),
    max_hops=st.integers(min_value=1, max_value=3),
    include_lineage=st.booleans(),
)
def test_property_interactive_graph_referential_integrity(
    center_tag: str,
    max_hops: int,
    include_lineage: bool,
) -> None:
    """Property: Every edge in get_interactive_graph must reference valid nodes in nodes list,
    and edge_type_counts must sum exactly to edge_count.
    """
    repo = _get_mem_repo()
    graph = repo.get_interactive_graph(
        center_tag=center_tag,
        max_hops=max_hops,
        include_lineage=include_lineage,
    )
    node_ids = {n["id"] for n in graph["nodes"]}
    assert graph["node_count"] == len(graph["nodes"])
    assert graph["edge_count"] == len(graph["edges"])
    assert graph["center_node_id"] in node_ids

    for edge in graph["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids
        assert 1 <= edge["hop_distance"] <= max_hops

    assert sum(graph["edge_type_counts"].values()) == graph["edge_count"]
    dossier = graph["selected_entity_detail"]["catalog_dossier"]
    assert "governance" in dossier
    assert "source_documents" in dossier


def test_property_equipment_hierarchy_counts_invariants() -> None:
    """Property: Equipment hierarchy counts must be non-negative and conflict_count <= parameter_count."""
    repo = _get_mem_repo()
    h = repo.get_equipment_hierarchy()
    summary = h["summary_counts"]
    assert summary["total_units"] == len(h["units"])
    assert summary["total_entities"] >= 1
    assert summary["total_conflicts"] <= summary["total_parameters"]

    for unit in h["units"]:
        for cls in unit["equipment_classes"]:
            assert cls["count"] == len(cls["items"])
            for item in cls["items"]:
                assert item["parameter_count"] >= 0
                assert item["conflict_count"] >= 0
                assert item["instrument_count"] >= 0
                assert item["conflict_count"] <= item["parameter_count"]


@settings(max_examples=40, deadline=None)
@given(
    tags=st.lists(
        st.sampled_from(
            [
                "D-2304",
                "C-2301",
                "E-2304",
                "PSV-2304A",
                "OKF-0012",
                "API-521",
                "ASME-VIII",
                "REV-001",
                "P-2302A",
            ]
        ),
        min_size=0,
        max_size=20,
    ),
    noise=st.text(min_size=0, max_size=80),
)
def test_property_extract_referenced_tags_bounded_and_filtered(
    tags: list[str],
    noise: str,
) -> None:
    """Property: _extract_referenced_tags returns unique engineering tags (<= 10) and excludes standard prefixes."""
    text = f"{noise} " + " , ".join(tags)
    extracted = _extract_referenced_tags(text)
    assert len(extracted) <= 10
    assert len(extracted) == len(set(extracted))
    for t in extracted:
        assert not t.startswith(("OKF-", "REV-", "API-", "ASME-", "ISO-", "SHA-", "PID-"))


@settings(max_examples=30, deadline=None)
@given(
    tool_name=st.sampled_from(
        [
            "lookup_entity_and_parameters",
            "traverse_equipment_connectivity_graph",
            "trace_data_lineage_and_conflicts",
            "hybrid_search_okf_spanner",
            "read_full_okf_concept_from_spanner",
            "execute_multistage_risk_and_hazop_query",
            "sync_or_inspect_knowledge_catalog",
        ]
    ),
    raw_text=st.text(min_size=0, max_size=120),
)
def test_property_summarize_tool_output_never_raises(
    tool_name: str,
    raw_text: str,
) -> None:
    """Property: _summarize_tool_output must gracefully handle any string or dict payload without raising."""
    res = _summarize_tool_output(tool_name, raw_text)
    assert "summary" in res
    assert "metrics" in res
    assert isinstance(res["summary"], str)


@settings(max_examples=50, deadline=None)
@given(
    step_durations_ms=st.lists(
        st.floats(min_value=0.0, max_value=15000.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=10,
    ),
    jitter_ms=st.floats(min_value=-2.0, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_property_telemetry_latency_conservation(
    step_durations_ms: list[float],
    jitter_ms: float,
) -> None:
    """Property: compute_telemetry_totals guarantees non-negative step durations and exact conservation with total_duration_ms."""
    steps = [
        {"step_index": i, "phase": f"STEP {i}", "duration_ms": d}
        for i, d in enumerate(step_durations_ms)
    ]
    raw_sum_ms = sum(step_durations_ms)
    total_elapsed_s = max(0.0, (raw_sum_ms + jitter_ms) / 1000.0)
    steps_sum_ms, total_ms = compute_telemetry_totals(steps, total_elapsed_s)
    for s in steps:
        assert s["duration_ms"] >= 0.0
    recomputed_sum = round(sum(float(s["duration_ms"]) for s in steps), 1)
    assert abs(total_ms - recomputed_sum) <= 0.2
    assert abs(steps_sum_ms - total_ms) <= 0.2


@settings(max_examples=40, deadline=None)
@given(
    subfolder=st.sampled_from(["data_sheets", "pid", "pfd", "operating_manuals", "standards", ""]),
    stem=st.sampled_from(
        [
            "DS-D2304_Decomposer_Reactor_Z1.pdf",
            "PID-23-0013_Decomposer_Reactor_Z1.pdf",
            "PFD-23-0005_Decomposer_and_Neutralization_Section_Z1.pdf",
            "STD-PHA-001_Risk_Assessment_and_HAZOP_Procedure_R1.pdf",
            "OM-2300_Operating_Manual_Z1.pdf",
        ]
    ),
    role=st.sampled_from(["PRIMARY", "CONFLICTING", "REFERENCED", "unknown_role"]),
)
def test_property_source_pdf_classifier_invariants(
    subfolder: str,
    stem: str,
    role: str,
) -> None:
    """Property: classify_source_pdf_metadata always produces non-empty doc_code, filename, doc_type, revision, and canonical source_role."""
    path = f"reference/raw/{subfolder}/{stem}" if subfolder else stem
    meta = SpannerGraphRepository.classify_source_pdf_metadata(
        filename_or_path=path,
        source_role=role,
    )
    assert meta["doc_code"] != ""
    assert meta["filename"] != ""
    assert meta["doc_type"] in {
        "Process Data Sheet",
        "P&ID Drawing",
        "Process Flow Diagram (PFD)",
        "Operating Manual",
        "Engineering Standard / HAZOP",
        "Engineering Reference PDF",
    }
    assert meta["revision"] != ""
    assert meta["source_role"] in {"PRIMARY", "CONFLICTING", "REFERENCED", "SECONDARY"}


@settings(max_examples=40, deadline=None)
@given(
    approver=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
        min_size=1,
        max_size=40,
    ).filter(lambda s: bool(s.strip())),
    author=st.text(
        alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")),
        min_size=1,
        max_size=40,
    ).filter(lambda s: bool(s.strip())),
    doc_id=st.sampled_from(["STD-PHA-001", "DS-D2304", "STD-ENG-014"]),
    eff_date=st.sampled_from(["2026-05-26", "2026-09-30", "2025-11-15"]),
)
def test_property_entity_metadata_and_exact_suffix_disambiguation(
    approver: str,
    author: str,
    doc_id: str,
    eff_date: str,
) -> None:
    """Property: build_catalog_dossier preserves nested frontmatter.entity_metadata fields,
    and get_interactive_graph('C-2301') never resolves to 'UC-2301'.
    """
    repo = _get_mem_repo()
    concept_doc = {
        "found": True,
        "concept_id": "hazop/test-concept",
        "category": "hazop",
        "title": "Test HAZOP Concept",
        "description": "Test description",
        "unit": "Plant-Wide",
        "trust_tier": "human-reviewed",
        "frontmatter": {
            "entity_metadata": {
                "approver": approver,
                "author": author,
                "document_id": doc_id,
                "effective_date": eff_date,
                "governing_authority": "Acme Process Safety Governance Board",
                "revision": "Rev 1",
            }
        },
        "body_markdown": "## References\nSee [DS-D2304_Decomposer_Reactor_Z1.pdf].",
        "wiki_links": [],
    }
    dossier = repo.build_catalog_dossier(
        concept_doc=concept_doc,
        lineage_traces=[],
        parameters=[],
        fallback_tag="hazop/test-concept",
        fallback_unit="Plant-Wide",
    )
    gov = dossier["governance"]
    assert gov["approver"] == approver.strip()
    assert gov["author"] == author.strip()
    assert gov["document_id"] == doc_id
    assert gov["effective_date"] == eff_date
    assert any(approver.strip() in a for a in gov["approved_by"])
    assert len(dossier["source_documents"]) >= 1

    # Exact suffix disambiguation invariant: C-2301 must never resolve to UC-2301
    g_c2301 = repo.get_interactive_graph(center_tag="C-2301", max_hops=1)
    assert g_c2301["center_tag"] == "C-2301"
    assert g_c2301["concept_id"] == "equipment/C-2301"


