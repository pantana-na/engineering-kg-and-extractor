"""7 Specialized Cloud Spanner Graph-RAG, Vector, Full-Text & Data Lineage ADK FunctionTools.

Implements SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT Section 4.1:
1. lookup_entity_and_parameters_tool
2. hybrid_search_okf_spanner_tool
3. traverse_equipment_connectivity_graph_tool
4. trace_data_lineage_and_conflicts_tool
5. execute_multistage_risk_and_hazop_query_tool
6. read_full_okf_concept_from_spanner_tool
7. sync_or_inspect_knowledge_catalog_tool
"""

from __future__ import annotations

import json

from google.adk.tools import FunctionTool

from query_agent.config import get_config
from query_agent.spanner.catalog_sync import DataplexCatalogAndLineageSync
from query_agent.spanner.repository import SpannerGraphRepository

_ACTIVE_REPOSITORY: SpannerGraphRepository | None = None


def set_active_spanner_repository(repo: SpannerGraphRepository | None) -> None:
    """Override the active SpannerGraphRepository instance (used by tests or custom runtimes)."""
    global _ACTIVE_REPOSITORY
    _ACTIVE_REPOSITORY = repo


def get_active_spanner_repository() -> SpannerGraphRepository:
    """Return the singleton SpannerGraphRepository connected to Cloud Spanner."""
    global _ACTIVE_REPOSITORY
    if _ACTIVE_REPOSITORY is None:
        cfg = get_config()
        _ACTIVE_REPOSITORY = SpannerGraphRepository(
            project_id=cfg.google_cloud_project,
            instance_id=cfg.spanner_instance_id,
            database_id=cfg.spanner_database_id,
            use_in_memory=False,
        )
    return _ACTIVE_REPOSITORY


def lookup_entity_and_parameters(
    entity_tag_or_id: str,
    parameter_filter: str = "",
) -> str:
    """Look up an engineering entity (equipment tag, instrument tag, line ID, chemical, or unit) in Cloud Spanner.

    Returns exact design/operating parameters, units, conflict flags, and raw PDF provenance citations.

    Args:
        entity_tag_or_id: Canonical tag or name (e.g. 'R-0201', 'C-0201', 'P-0102A', 'TI-0201', 'Cumene').
        parameter_filter: Optional keyword to filter parameter names or sections (e.g. 'temperature', 'pressure', 'material').
    """
    repo = get_active_spanner_repository()
    result = repo.lookup_entity_and_parameters(
        entity_tag_or_id=entity_tag_or_id,
        parameter_filter=parameter_filter or None,
    )
    return json.dumps(result, ensure_ascii=False, default=str)


def hybrid_search_okf_spanner(
    query: str,
    domain_filter: str = "",
    top_k: int = 8,
) -> str:
    """Execute Hybrid Search combining 768-d Vector Search (COSINE_DISTANCE) and Full-Text Search (TOKENLIST) with Reciprocal Rank Fusion (RRF).

    Use for conceptual engineering questions, operating procedures, chemical hazard SDS properties, or cross-plant searches.

    Args:
        query: Natural-language search query or technical phrase.
        domain_filter: Optional category or unit filter (e.g. 'equipment', 'hazards', 'units', 'U0200').
        top_k: Maximum number of top RRF-ranked section chunks to return (default 8).
    """
    repo = get_active_spanner_repository()
    hits = repo.hybrid_rrf_search(
        query=query,
        domain_filter=domain_filter or None,
        top_k=top_k,
    )
    payload = {
        "query": query,
        "domain_filter": domain_filter,
        "result_count": len(hits),
        "results": [h.model_dump() for h in hits],
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def traverse_equipment_connectivity_graph(
    start_tag: str,
    direction: str = "BOTH",
    max_hops: int = 3,
    edge_filter: str = "ALL",
) -> str:
    """Traverse multi-hop equipment connectivity (CONNECTS_TO) and instrument/interlock loops (MONITORS_OR_TRIPS) in Spanner Graph using ISO GQL.

    Use whenever a question asks what feeds an equipment item, what is downstream/upstream, or which instruments/trips protect a vessel.

    Args:
        start_tag: Starting equipment or instrument tag (e.g. 'R-0201', 'V-0101', 'C-0201').
        direction: Traversal direction: 'DOWNSTREAM', 'UPSTREAM', or 'BOTH'.
        max_hops: Maximum number of graph hops to traverse (1 to 5, default 3).
        edge_filter: Edge filter: 'ALL', 'CONNECTS_TO', or 'MONITORS_OR_TRIPS'.
    """
    repo = get_active_spanner_repository()
    hops = repo.traverse_connectivity_gql(
        start_tag=start_tag,
        direction=direction,
        max_hops=max_hops,
        edge_filter=edge_filter,
    )
    payload = {
        "start_tag": start_tag,
        "direction": direction,
        "max_hops": max_hops,
        "edge_filter": edge_filter,
        "hop_count": len(hops),
        "hops": [h.model_dump() for h in hops],
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def trace_data_lineage_and_conflicts(
    target_id: str = "",
    direction: str = "BACKWARD_TO_PDF",
    conflicts_only: bool = False,
) -> str:
    """Trace bidirectional claim-to-PDF data lineage (DERIVED_FROM edges) and audit cross-document conflicts in Spanner Graph.

    Supports:
    - BACKWARD_TO_PDF: Given an equipment tag, concept_id, parameter name, or fact_id, returns the exact RawSourceDocuments (filename, doc_code, revision, MD5, GCS URI) and conflict notes.
    - FORWARD_FROM_PDF: Given a raw PDF filename or document code (e.g. 'PID-23-0013'), returns every OKF concept and FactAssertion derived from that PDF (blast-radius analysis).

    Args:
        target_id: Equipment tag, concept_id, parameter keyword, or PDF document code/filename.
        direction: 'BACKWARD_TO_PDF' or 'FORWARD_FROM_PDF'.
        conflicts_only: If True, return only FactAssertions where has_conflict=True.
    """
    repo = get_active_spanner_repository()
    traces = repo.trace_lineage_gql(
        target_id=target_id,
        direction=direction,
        conflicts_only=conflicts_only,
    )
    payload = {
        "target_id": target_id,
        "direction": direction,
        "conflicts_only": conflicts_only,
        "trace_count": len(traces),
        "lineage_traces": [t.model_dump() for t in traces],
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def execute_multistage_risk_and_hazop_query(
    target_tag_or_deviation: str,
    max_propagation_hops: int = 2,
    include_interlocks_and_psvs: bool = True,
) -> str:
    """Execute a 5-stage deterministic Risk Assessment & HAZOP Study query across Spanner Graph, Vector, and Lineage stores.

    Stage 1: Retrieve Risk Matrix & Severity Tier Governance Rules.
    Stage 2: Extract HAZOP Scenario Records (Deviation, Potential Cause, Consequence, Risk Tier, Safeguards).
    Stage 3: Traverse Upstream Cause & Downstream Plant Implication propagation paths via Spanner Graph GQL.
    Stage 4: Verify Active Safeguards, SIS Interlocks, Trips, and PSV/Relief setpoints.
    Stage 5: Audit Claim-to-PDF Lineage & Flagged Engineering Conflicts on safety-critical parameters.

    Args:
        target_tag_or_deviation: Equipment tag (e.g. 'R-0201', 'R-0101A') or HAZOP deviation scenario (e.g. 'R-0201 high temperature runaway').
        max_propagation_hops: Graph hops for upstream cause and downstream implication analysis (default 2).
        include_interlocks_and_psvs: Whether to verify instrument interlocks and relief setpoints (default True).
    """
    repo = get_active_spanner_repository()
    report = repo.execute_multistage_risk_and_hazop_query(
        target_tag_or_deviation=target_tag_or_deviation,
        max_propagation_hops=max_propagation_hops,
        include_interlocks_and_psvs=include_interlocks_and_psvs,
    )
    return report.model_dump_json()


def read_full_okf_concept_from_spanner(
    concept_id_or_tag: str,
    section_filter: str = "",
) -> str:
    """Read the complete OKF v0.2 Markdown concept document, YAML frontmatter, and outgoing wiki-links directly from Cloud Spanner (Zero GCS reads).

    Args:
        concept_id_or_tag: Concept ID (e.g. 'equipment/R-0201', 'hazards/CHP') or equipment tag/name (e.g. 'R-0201').
        section_filter: Optional H2 section heading filter (e.g. 'Design', 'Safety', 'Nozzles').
    """
    repo = get_active_spanner_repository()
    doc = repo.read_full_concept(
        concept_id_or_tag=concept_id_or_tag,
        section_filter=section_filter or None,
    )
    return json.dumps(doc, ensure_ascii=False, default=str)


def sync_or_inspect_knowledge_catalog(
    action: str = "INSPECT",
) -> str:
    """Inspect or synchronize Google Cloud Dataplex Data Catalog governance tags and OpenLineage pipeline topology.

    Args:
        action: 'INSPECT' to view catalog entries, governance tag metrics, and OpenLineage topology; 'SYNC' to trigger a live catalog sync.
    """
    repo = get_active_spanner_repository()
    live_counts = repo.get_live_counts()
    syncer = DataplexCatalogAndLineageSync()
    if (action or "INSPECT").strip().upper() == "SYNC":
        report = syncer.sync_catalog_and_lineage(live_counts, dry_run=repo.use_in_memory)
        return report.model_dump_json()
    state = syncer.inspect_catalog_state(live_counts, dry_run=repo.use_in_memory)
    return json.dumps(state, ensure_ascii=False, default=str)


lookup_entity_and_parameters_tool = FunctionTool(func=lookup_entity_and_parameters)
hybrid_search_okf_spanner_tool = FunctionTool(func=hybrid_search_okf_spanner)
traverse_equipment_connectivity_graph_tool = FunctionTool(func=traverse_equipment_connectivity_graph)
trace_data_lineage_and_conflicts_tool = FunctionTool(func=trace_data_lineage_and_conflicts)
execute_multistage_risk_and_hazop_query_tool = FunctionTool(func=execute_multistage_risk_and_hazop_query)
read_full_okf_concept_from_spanner_tool = FunctionTool(func=read_full_okf_concept_from_spanner)
sync_or_inspect_knowledge_catalog_tool = FunctionTool(func=sync_or_inspect_knowledge_catalog)

ALL_QUERY_AGENT_TOOLS = [
    lookup_entity_and_parameters_tool,
    hybrid_search_okf_spanner_tool,
    traverse_equipment_connectivity_graph_tool,
    trace_data_lineage_and_conflicts_tool,
    execute_multistage_risk_and_hazop_query_tool,
    read_full_okf_concept_from_spanner_tool,
    sync_or_inspect_knowledge_catalog_tool,
]
