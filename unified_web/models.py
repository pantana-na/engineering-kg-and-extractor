"""Core v2 Pydantic contracts, Gemini 4 model registry, and pagination/job schemas.

Implements SPEC-20261120-UNIFIED-WORKBENCH-V2 Section 2.4.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

ALLOWED_GEMINI_MODELS: tuple[str, ...] = (
    "gemini-4-carbon",
    "gemini-4-hydrogen",
    "gemini-4-argon",
    "gemini-4-neon",
)

GEMINI_MODEL_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "gemini-4-carbon",
        "label": "Gemini 4 Carbon",
        "tier": "Extractor Default",
        "description": "High-precision multimodal vision & technical document extraction.",
    },
    {
        "id": "gemini-4-hydrogen",
        "label": "Gemini 4 Hydrogen",
        "tier": "Query Default",
        "description": "Low-latency reasoning for interactive Spanner Graph-RAG queries.",
    },
    {
        "id": "gemini-4-argon",
        "label": "Gemini 4 Argon",
        "tier": "Balanced",
        "description": "Balanced multimodal extraction and engineering synthesis.",
    },
    {
        "id": "gemini-4-neon",
        "label": "Gemini 4 Neon",
        "tier": "Deep Reasoning",
        "description": "Deep multi-step HAZOP, safety interlock, and root-cause reasoning.",
    },
)

DEFAULT_EXTRACTER_MODEL: str = "gemini-4-carbon"
DEFAULT_QUERY_MODEL: str = "gemini-4-hydrogen"

ALLOWED_RAW_SUBFOLDERS: tuple[str, ...] = (
    "data_sheets",
    "pid",
    "pfd",
    "operating_manuals",
    "standards",
    "moc",
)


def get_allowed_gemini_models() -> tuple[str, ...]:
    """Return the canonical allowlist of selectable Gemini 4 models."""
    raw = os.getenv("ALLOWED_GEMINI_MODELS", "").strip()
    if not raw:
        return ALLOWED_GEMINI_MODELS
    parsed = tuple(m.strip() for m in raw.split(",") if m.strip() in ALLOWED_GEMINI_MODELS)
    return parsed or ALLOWED_GEMINI_MODELS


def get_default_extracter_model() -> str:
    """Resolve the default Extractor Gemini 4 model (default: gemini-4-carbon)."""
    cand = os.getenv("EXTRACTER_DEFAULT_MODEL", DEFAULT_EXTRACTER_MODEL).strip()
    return cand if cand in ALLOWED_GEMINI_MODELS else DEFAULT_EXTRACTER_MODEL


def get_default_query_model() -> str:
    """Resolve the default Query Gemini 4 model (default: gemini-4-hydrogen)."""
    cand = os.getenv("QUERY_DEFAULT_MODEL", DEFAULT_QUERY_MODEL).strip()
    return cand if cand in ALLOWED_GEMINI_MODELS else DEFAULT_QUERY_MODEL


def validate_gemini_model(model: str | None, *, default: str) -> str:
    """Validate an optional requested model against the strict Gemini 4 allowlist."""
    if model is None or not str(model).strip():
        return default
    cleaned = str(model).strip()
    allowed = get_allowed_gemini_models()
    if cleaned not in allowed:
        raise ValueError(
            f"Unsupported Gemini model '{cleaned}'. Allowed models: {', '.join(allowed)}."
        )
    return cleaned


class PipelineJobMode(str, Enum):
    """Supported execution modes for the single parameterized Cloud Run Job (`okf-pipeline-job`)."""

    EXTRACT = "extract"
    SYNC = "sync"
    EXTRACT_AND_SYNC = "extract_and_sync"


class SpannerSyncMode(str, Enum):
    """Supported Spanner ingestion sync modes."""

    FULL_MIRROR = "FULL_MIRROR"
    INCREMENTAL = "INCREMENTAL"


class PipelineJobRequest(BaseModel):
    """Request payload for `POST /api/jobs/run`."""

    job_mode: PipelineJobMode = Field(
        default=PipelineJobMode.SYNC,
        description="extract | sync | extract_and_sync",
    )
    model: str | None = Field(
        default=None,
        description="Optional allowlisted Gemini 4 model for extraction (defaults to gemini-4-carbon)",
    )
    sync_mode: SpannerSyncMode = Field(
        default=SpannerSyncMode.FULL_MIRROR,
        description="FULL_MIRROR or INCREMENTAL Spanner sync mode",
    )
    purge: bool = Field(
        default=False,
        description="Destructive full Spanner + Dataplex purge before reload (requires X-Confirm-Purge: CONFIRMED)",
    )
    target_subfolder: str | None = Field(
        default=None,
        description="Optional subfolder filter for batch extraction (e.g., pid, data_sheets)",
    )
    target_files: list[str] = Field(
        default_factory=list,
        description="Optional explicit relative file paths (subfolder/filename) for targeted batch extraction",
    )
    bundle_version: str = Field(
        default="v2-unified",
        min_length=1,
        max_length=64,
        description="Version tag persisted onto synced Spanner concepts",
    )
    compute_embeddings: bool = Field(
        default=True,
        description="Compute 768-d embeddings (via native Spanner ML.PREDICT by default)",
    )
    sync_dataplex_catalog: bool = Field(
        default=True,
        description="Synchronize Dataplex Universal Catalog & OpenLineage after Spanner sync",
    )

    @field_validator("model")
    @classmethod
    def _validate_model_field(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        return validate_gemini_model(v, default=get_default_extracter_model())

    @field_validator("target_subfolder")
    @classmethod
    def _validate_subfolder(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        cleaned = v.strip().lower()
        if cleaned not in ALLOWED_RAW_SUBFOLDERS:
            raise ValueError(
                f"Invalid target_subfolder '{v}'. Allowed: {', '.join(ALLOWED_RAW_SUBFOLDERS)}."
            )
        return cleaned

    @field_validator("target_files")
    @classmethod
    def _validate_target_files(cls, files: list[str]) -> list[str]:
        cleaned_list: list[str] = []
        for item in files:
            s = str(item or "").strip()
            if not s:
                continue
            if ".." in s or s.startswith("/") or "\\" in s or "\x00" in s:
                raise ValueError(f"Unsafe path in target_files: '{s}'")
            cleaned_list.append(s)
        if len(cleaned_list) > 500:
            raise ValueError("target_files cannot exceed 500 entries per job request.")
        return cleaned_list


class PipelineJobStatus(BaseModel):
    """Structured execution telemetry for a Cloud Run Job or local fallback pipeline run."""

    execution_id: str
    job_name: str
    job_mode: str
    model: str
    sync_mode: str
    purge: bool = False
    status: str = Field(default="QUEUED", description="QUEUED | RUNNING | SUCCEEDED | FAILED")
    execution_backend: str = Field(default="cloud_run_job", description="cloud_run_job | local_subprocess")
    triggered_by: str = Field(default="local-dev")
    step: str = Field(default="Initializing pipeline job")
    processed_count: int = Field(default=0, ge=0)
    total_count: int = Field(default=0, ge=0)
    percent: float = Field(default=0.0, ge=0.0, le=100.0)
    created_at: str
    updated_at: str
    completed_at: str | None = None
    spanner_counts: dict[str, int] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    idempotency_key: str | None = None


class ModelCatalogResponse(BaseModel):
    """Response payload for `GET /api/models`."""

    allowed_models: list[dict[str, str]]
    defaults: dict[str, str]
    location: str = "global"
