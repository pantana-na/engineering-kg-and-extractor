"""ADK FunctionTools for Google Cloud Storage bundle publishing.

Strictly complies with Rule 11 (FunctionTool docstring contracts, negative constraints).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from extracter_agent.config import get_config
from extracter_agent.gcs.exporter import GCSExporter


def export_bundle_to_gcs_tool(
    bundle_dir: str | None = None,
    destination_bucket: str | None = None,
    destination_prefix: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Publish an OKF knowledge bundle directory to Google Cloud Storage.

    When to use:
        - When an OKF knowledge bundle has been created and validated, and is ready
          to be published to Google Cloud Storage as the primary destination.
        - Example: export_bundle_to_gcs_tool(dry_run=True)

    When NOT to use:
        - Do NOT use on incomplete or unindexed bundles.
        - Do NOT use if the bundle fails OKF validation.
        - Do NOT use for raw unstructured PDF files (only publish compiled OKF bundles).

    Args:
        bundle_dir: Local path to the OKF bundle root directory.
        destination_bucket: Destination GCS bucket name (defaults to configured bucket).
        destination_prefix: GCS object prefix path (defaults to configured prefix).
        dry_run: If True, calculates upload plan without performing network writes.

    Returns:
        A dictionary summarizing uploaded files, byte count, destination URI, and status.
    """
    cfg = get_config()
    root = Path(bundle_dir) if bundle_dir else cfg.output_bundle_dir
    bucket = destination_bucket or cfg.destination_gcs_bucket
    prefix = destination_prefix or cfg.destination_gcs_prefix

    if not root.exists():
        return {
            "status": "error",
            "error": f"Bundle directory not found: {root}",
        }

    exporter = GCSExporter(bucket_name=bucket)
    try:
        res = exporter.export_bundle(root, prefix=prefix, dry_run=dry_run)
        return {
            "status": "success",
            "bucket": res["bucket"],
            "prefix": res["prefix"],
            "dry_run": res["dry_run"],
            "files_count": res["files_count"],
            "total_bytes": res["total_bytes"],
            "destination_root_uri": res["destination_root_uri"],
            "uploaded_uris": res["uploaded_uris"][:10],  # Preview first 10 URIs
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to export bundle to GCS: {e}",
        }
