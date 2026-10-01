"""Core Node, Edge, Vector Chunk, and Data Lineage models for Cloud Spanner Graph-RAG.

Implements SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT Section 3.
Zero hardcoded domain tags or static mappings.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field


def compute_deterministic_id(*parts: str, prefix: str = "", length: int = 32) -> str:
    """Compute a deterministic, collision-resistant hex identifier from normalized parts."""
    normalized = "|".join((p or "").strip() for p in parts)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[: max(8, length)]
    return f"{prefix}:{digest}" if prefix else digest


class RawSourceNode(BaseModel):
    """Represents a raw engineering PDF document node in RawSourceDocuments."""

    source_id: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1)
    subfolder: str = Field(..., min_length=1)
    doc_code: str = Field(default="")
    revision: str = Field(default="")
    md5_hash: str = Field(default="")
    gcs_uri: str = Field(default="")


class OkfConceptNode(BaseModel):
    """Represents an OKF v0.2 Markdown document node in OkfConcepts."""

    concept_id: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(default="")
    unit: str = Field(default="")
    trust_tier: str = Field(default="human-reviewed")
    has_conflict: bool = Field(default=False)
    conflict_count: int = Field(default=0, ge=0)
    frontmatter_json: dict[str, Any] = Field(default_factory=dict)
    body_markdown: str = Field(..., min_length=1)
    md5_hash: str = Field(..., min_length=1)
    bundle_version: str = Field(default="v3-by-equipment")
    gcs_uri: str = Field(default="")


class EngineeringEntityNode(BaseModel):
    """Represents a canonical plant entity node in EngineeringEntities."""

    entity_id: str = Field(..., min_length=1)
    entity_type: str = Field(
        ...,
        description="EQUIPMENT, INSTRUMENT, PIPING_LINE, HAZARD, UNIT, PROCEDURE, SOURCE, CONCEPT",
    )
    canonical_tag: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    equipment_class: str = Field(default="")
    unit: str = Field(default="")
    concept_id: str = Field(..., min_length=1)


class FactAssertionNode(BaseModel):
    """Represents a granular design, operating, or table parameter claim in FactAssertions."""

    fact_id: str = Field(..., min_length=1)
    concept_id: str = Field(..., min_length=1)
    entity_id: str = Field(default="")
    section_heading: str = Field(..., min_length=1)
    parameter_name: str = Field(..., min_length=1)
    parameter_value: str = Field(..., min_length=1)
    parameter_unit: str = Field(default="—")
    has_conflict: bool = Field(default=False)
    conflict_note: str = Field(default="")
    bundle_version: str = Field(default="v3-by-equipment")


class OkfSectionChunkNode(BaseModel):
    """Represents a header-preserved H2/table section chunk with 768-d embedding."""

    chunk_id: str = Field(..., min_length=1)
    concept_id: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    unit: str = Field(default="")
    section_heading: str = Field(..., min_length=1)
    chunk_index: int = Field(default=0, ge=0)
    header_preserved_markdown: str = Field(..., min_length=1)
    has_conflict: bool = Field(default=False)
    embedding: list[float] | None = Field(default=None)


class ProcessConnectionEdge(BaseModel):
    """Represents a directed CONNECTS_TO edge in ProcessConnections."""

    edge_id: str = Field(..., min_length=1)
    from_entity_id: str = Field(..., min_length=1)
    to_entity_id: str = Field(..., min_length=1)
    stream_or_line_id: str = Field(..., min_length=1)
    fluid_service: str = Field(default="")
    temperature: str = Field(default="")
    pressure: str = Field(default="")
    flow_rate: str = Field(default="")
    source_concept_id: str = Field(..., min_length=1)
    source_id: str = Field(default="")


class InstrumentControlEdge(BaseModel):
    """Represents a directed MONITORS_OR_TRIPS edge in InstrumentControlEdges."""

    edge_id: str = Field(..., min_length=1)
    instrument_entity_id: str = Field(..., min_length=1)
    target_entity_id: str = Field(..., min_length=1)
    loop_id: str = Field(..., min_length=1)
    instrument_type: str = Field(default="")
    setpoint_or_range: str = Field(default="")
    interlock_or_alarm: str = Field(default="")
    source_concept_id: str = Field(..., min_length=1)
    source_id: str = Field(default="")


class ConceptWikiLinkEdge(BaseModel):
    """Represents a directed LINKS_TO_CONCEPT edge in ConceptWikiLinks."""

    edge_id: str = Field(..., min_length=1)
    from_concept_id: str = Field(..., min_length=1)
    to_concept_id: str = Field(..., min_length=1)
    section_heading: str = Field(default="")


class FactLineageEdge(BaseModel):
    """Represents a directed DERIVED_FROM edge in FactLineageEdges."""

    lineage_id: str = Field(..., min_length=1)
    fact_id: str = Field(..., min_length=1)
    concept_id: str = Field(..., min_length=1)
    source_id: str = Field(..., min_length=1)
    raw_citation_string: str = Field(..., min_length=1)
    source_role: str = Field(
        default="PRIMARY",
        description="PRIMARY, CONFLICTING, or CONCEPT_CITATION",
    )
    bundle_version: str = Field(default="v3-by-equipment")


class BundleGraphExtractionResult(BaseModel):
    """Container holding all extracted Spanner nodes, chunks, and edges for an OKF bundle."""

    raw_sources: list[RawSourceNode] = Field(default_factory=list)
    concepts: list[OkfConceptNode] = Field(default_factory=list)
    entities: list[EngineeringEntityNode] = Field(default_factory=list)
    facts: list[FactAssertionNode] = Field(default_factory=list)
    chunks: list[OkfSectionChunkNode] = Field(default_factory=list)
    process_edges: list[ProcessConnectionEdge] = Field(default_factory=list)
    instrument_edges: list[InstrumentControlEdge] = Field(default_factory=list)
    wikilink_edges: list[ConceptWikiLinkEdge] = Field(default_factory=list)
    lineage_edges: list[FactLineageEdge] = Field(default_factory=list)


class HybridSearchResult(BaseModel):
    """Ranked result returned by Hybrid Vector (768-d COSINE) + Full-Text RRF search."""

    chunk_id: str
    concept_id: str
    concept_title: str
    category: str = ""
    unit: str = ""
    section_heading: str
    chunk_markdown: str
    has_conflict: bool = False
    rrf_score: float
    vector_rank: int | None = None
    fts_rank: int | None = None
    cosine_similarity: float | None = None


class GraphTraversalHop(BaseModel):
    """Single hop in a Spanner Graph ISO GQL connectivity or control loop traversal."""

    hop_distance: int
    from_tag: str
    from_name: str
    edge_type: str
    to_tag: str
    to_name: str
    stream_or_loop_id: str
    fluid_or_instrument_type: str | None = None
    operating_conditions: str | None = None
    source_concept_id: str


class LineageTraceResult(BaseModel):
    """Claim-to-PDF or PDF-to-Claim lineage trace result from Spanner Graph."""

    fact_id: str
    entity_id: str
    concept_id: str
    parameter_name: str
    parameter_value: str
    has_conflict: bool
    conflict_note: str | None = None
    raw_citation_string: str
    source_role: str
    source_id: str
    filename: str
    gcs_uri: str
    md5_hash: str
    revision: str | None = None


class HazopScenarioRecord(BaseModel):
    """Structured HAZOP deviation, cause, consequence, risk tier, and safeguard record."""

    node_or_equipment: str
    deviation: str
    potential_cause: str
    consequence_and_implication: str
    risk_tier_or_severity: str
    safeguards: list[str] = Field(default_factory=list)
    source_citation: str = ""


class MultiStageRiskHazopReport(BaseModel):
    """Comprehensive 5-stage Risk Assessment & HAZOP query output."""

    target_equipment_or_node: str
    risk_matrix_governance_rules: list[str] = Field(default_factory=list)
    hazop_scenarios: list[HazopScenarioRecord] = Field(default_factory=list)
    upstream_cause_propagation: list[GraphTraversalHop] = Field(default_factory=list)
    downstream_plant_implications: list[GraphTraversalHop] = Field(default_factory=list)
    verified_safeguards_and_interlocks: list[dict[str, Any]] = Field(default_factory=list)
    lineage_and_conflict_alerts: list[LineageTraceResult] = Field(default_factory=list)


class CatalogSyncReport(BaseModel):
    """Dataplex Data Catalog & OpenLineage synchronization report."""

    entry_group_id: str
    tag_template_id: str
    entries_synced: int
    lineage_events_emitted: int
    total_concepts: int
    total_entities: int
    total_assertions: int
    total_conflicts: int
    total_lineage_edges: int
    status: str


class MarkdownSpannerSyncReport(BaseModel):
    """Structured report for the consolidated `.md`-only Spanner ingestion and lifecycle sync engine."""

    sync_mode: str = "FULL_MIRROR"
    source_type: str = "MD_BUNDLE_ONLY"
    bundle_dir: str = ""
    total_md_files_scanned: int = 0
    added_concepts: list[str] = Field(default_factory=list)
    updated_concepts: list[str] = Field(default_factory=list)
    removed_concepts: list[str] = Field(default_factory=list)
    unchanged_concepts: list[str] = Field(default_factory=list)
    rows_deleted: dict[str, int] = Field(default_factory=dict)
    rows_upserted: dict[str, int] = Field(default_factory=dict)
    deleted_counts: dict[str, int] = Field(default_factory=dict)
    upserted_counts: dict[str, int] = Field(default_factory=dict)
    live_counts_after_sync: dict[str, int] = Field(default_factory=dict)
    catalog_sync_status: str = "NOT_RUN"
    duration_ms: float = 0.0
    status: str = "OK"


