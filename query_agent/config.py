"""Self-contained configuration loader for the Separate ADK OKF Spanner Query Agent."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv(override=False)


class QueryAgentConfig(BaseModel):
    """Configuration parsed from environment variables for query_agent."""

    service_name: str = Field(
        default_factory=lambda: os.getenv("QUERY_SERVICE_NAME", "okf-query-agent")
    )
    google_cloud_project: str = Field(
        default_factory=lambda: os.getenv(
            "GOOGLE_CLOUD_PROJECT", "your-gcp-project-id"
        )
    )
    google_cloud_location: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_LOCATION", "asia-southeast1")
    )
    gemini_location: str = Field(
        default_factory=lambda: os.getenv("GEMINI_LOCATION", "global")
    )
    gemini_model: str = Field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    )
    destination_gcs_bucket: str = Field(
        default_factory=lambda: os.getenv(
            "DESTINATION_GCS_BUCKET",
            "your-gcp-project-id-okf-knowledge",
        )
    )
    destination_gcs_prefix: str = Field(
        default_factory=lambda: os.getenv(
            "DESTINATION_GCS_PREFIX", "okf-bundles/chemical-plant"
        )
    )
    output_bundle_dir: Path = Field(
        default_factory=lambda: Path(
            os.getenv("OUTPUT_BUNDLE_DIR", "build/okf_bundle")
        )
    )
    reference_raw_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("REFERENCE_RAW_DIR", "reference/raw"))
    )
    source_gcs_raw_prefix: str = Field(
        default_factory=lambda: os.getenv("SOURCE_GCS_RAW_PREFIX", "reference/raw")
    )
    spanner_instance_id: str = Field(
        default_factory=lambda: os.getenv(
            "SPANNER_INSTANCE_ID", "okf-knowledge-spanner"
        )
    )
    spanner_database_id: str = Field(
        default_factory=lambda: os.getenv("SPANNER_DATABASE_ID", "okf_knowledge_graph")
    )
    spanner_processing_units: int = Field(
        default_factory=lambda: int(os.getenv("SPANNER_PROCESSING_UNITS", "100"))
    )
    embedding_model: str = Field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "text-embedding-005")
    )
    dataplex_entry_group_id: str = Field(
        default_factory=lambda: os.getenv(
            "DATAPLEX_ENTRY_GROUP_ID", "okf_knowledge_assets"
        )
    )
    dataplex_tag_template_id: str = Field(
        default_factory=lambda: os.getenv(
            "DATAPLEX_TAG_TEMPLATE_ID", "okf_governance_template"
        )
    )
    nonprod_query_agent_runtime_id: str = Field(
        default_factory=lambda: os.getenv(
            "NONPROD_QUERY_AGENT_RUNTIME_ID",
            "okf-query-agent-nonprod",
        )
    )


def get_config() -> QueryAgentConfig:
    """Retrieve the active QueryAgentConfig instance."""
    return QueryAgentConfig()
