"""OKF (Open Knowledge Format) v0.2 Pydantic Data Models.

Implements the official OKF v0.2 specification from Google Cloud Knowledge Catalog.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class OKFConceptStatus(str, Enum):
    DRAFT = "draft"
    STABLE = "stable"
    DEPRECATED = "deprecated"


class OKFSource(BaseModel):
    """Source provenance record with optional credibility signals."""

    id: str
    resource: str
    title: str | None = None
    author: str | None = None
    usage_count: int | None = None
    last_modified: str | None = None


class OKFActor(BaseModel):
    """Actor record conforming to <producer>/<version>, human:<id>, or process:<id>."""

    by: str
    at: str


class OKFFrontmatter(BaseModel):
    """Full OKF v0.2 YAML frontmatter schema."""

    type: str = Field(
        ..., min_length=1, description="REQUIRED: descriptive concept type"
    )
    title: str | None = None
    description: str | None = None
    resource: str | None = None
    tags: list[str] = Field(default_factory=list)
    sources: list[OKFSource] = Field(default_factory=list)
    generated: OKFActor | None = None
    verified: list[OKFActor] = Field(default_factory=list)
    status: OKFConceptStatus = OKFConceptStatus.STABLE
    stale_after: str | None = None
    entity_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("verified", mode="before")
    @classmethod
    def normalize_verified(cls, v: Any) -> list[Any]:
        if v is None:
            return []
        if isinstance(v, dict):
            return [v]
        if isinstance(v, list):
            return v
        return []


def derive_trust_tier(frontmatter: OKFFrontmatter | dict[str, Any]) -> str:
    """Derive OKF v0.2 trust tier from verified events (§5.3).

    - No verified key => 'unverified'
    - verified by non-human: actors only => 'machine-confirmed'
    - verified by human:<id> => 'human-reviewed'
    """
    if isinstance(frontmatter, OKFFrontmatter):
        verified = frontmatter.verified
    else:
        raw = frontmatter.get("verified")
        if isinstance(raw, dict):
            verified = [raw]
        elif isinstance(raw, list):
            verified = raw
        else:
            verified = []

    if not verified:
        return "unverified"

    for item in verified:
        by = item.by if isinstance(item, OKFActor) else str(item.get("by") or "")
        if by.startswith("human:"):
            return "human-reviewed"

    return "machine-confirmed"
