"""Canonical Intent Topology and Classification schemas.

Enforces Rule 11 & Model-Driven Reasoning (Zero regex / hardcoded heuristics).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class IntentCategory(str, Enum):
    """MECE Intent categories for the Extracter Agent system."""

    EXTRACT_DOCUMENT = "EXTRACT_DOCUMENT"
    GENERATE_OKF_CONCEPT = "GENERATE_OKF_CONCEPT"
    BUILD_OKF_BUNDLE = "BUILD_OKF_BUNDLE"
    EXPORT_TO_GCS = "EXPORT_TO_GCS"
    VALIDATE_OKF_BUNDLE = "VALIDATE_OKF_BUNDLE"
    OTHERS = "OTHERS"


class IntentClassificationResult(BaseModel):
    """Cognitive intent classification result structured output."""

    intent: IntentCategory = Field(
        ..., description="The categorized intent from the canonical enum"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score between 0 and 1"
    )
    reasoning: str = Field(
        ..., description="Explicit step-by-step cognitive explanation"
    )
    target_entities: list[str] = Field(
        default_factory=list,
        description="Extracted equipment tags or concept names",
    )
    raw_sources: list[str] = Field(
        default_factory=list,
        description="Raw PDF or source file paths referenced",
    )
