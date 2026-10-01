"""Canonical Query Intent Topology and Classification schemas for OKF Query Agent.

Enforces Rule 11 & Model-Driven Reasoning (Zero regex / hardcoded heuristics).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class QueryIntentCategory(str, Enum):
    """MECE Intent categories for the OKF Spanner Graph-RAG & Lineage Query Agent."""

    ENTITY_AND_PARAMETER_LOOKUP = "ENTITY_AND_PARAMETER_LOOKUP"
    HYBRID_SEMANTIC_KEYWORD_SEARCH = "HYBRID_SEMANTIC_KEYWORD_SEARCH"
    GRAPH_CONNECTIVITY_TRAVERSAL = "GRAPH_CONNECTIVITY_TRAVERSAL"
    DATA_LINEAGE_AND_CONFLICT_AUDIT = "DATA_LINEAGE_AND_CONFLICT_AUDIT"
    MULTISTAGE_RISK_AND_HAZOP_ANALYSIS = "MULTISTAGE_RISK_AND_HAZOP_ANALYSIS"
    SYNC_BUNDLE_TO_SPANNER = "SYNC_BUNDLE_TO_SPANNER"
    OTHERS = "OTHERS"


class QueryIntentClassificationResult(BaseModel):
    """Cognitive query intent classification result structured output."""

    intent: QueryIntentCategory = Field(
        ..., description="The categorized query intent from the canonical enum"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score between 0 and 1"
    )
    reasoning: str = Field(
        ..., description="Explicit step-by-step cognitive explanation"
    )
    target_entities: list[str] = Field(
        default_factory=list,
        description="Extracted equipment tags, instrument tags, piping lines, or concept names",
    )
    raw_sources: list[str] = Field(
        default_factory=list,
        description="Raw PDF filenames or document codes referenced in the query",
    )
