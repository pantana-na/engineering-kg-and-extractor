"""Ingest or Purge-and-Reload an OKF v0.2 Markdown Bundle into Cloud Spanner & Dataplex Catalog.

Operates 100% on OKF Markdown (.md) files via `sync_markdown_bundle_to_spanner`
with optional full Cloud Spanner + Dataplex Universal Catalog purge before reload.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from extracter_agent.config import get_config
from query_agent.models.schemas import MarkdownSpannerSyncReport
from query_agent.spanner.catalog_sync import DataplexCatalogAndLineageSync
from query_agent.spanner.repository import SpannerGraphRepository


def purge_and_reload_spanner(
    bundle_dir: Path,
    *,
    bundle_version: str = "v5-by-equipment",
    purge: bool = False,
    sync_mode: str = "FULL_MIRROR",
    force_reingest: bool = False,
    compute_embeddings: bool = True,
    sync_dataplex_catalog: bool = True,
    repo: SpannerGraphRepository | None = None,
    catalog_syncer: DataplexCatalogAndLineageSync | None = None,
) -> dict[str, Any]:
    """Purge (optional) and reload Cloud Spanner + Dataplex Catalog from an OKF .md bundle.

    Args:
        bundle_dir: Path to the OKF v0.2 Markdown bundle directory (or single .md file).
        bundle_version: Version tag stored on ingested concepts (e.g. 'v5-by-equipment').
        purge: If True, deletes all rows across all 9 Cloud Spanner tables and purges
            governed Dataplex Catalog entries before reloading.
        sync_mode: 'FULL_MIRROR' (deletes concepts missing from bundle_dir) or 'INCREMENTAL'.
        force_reingest: If True (or if purge is True), forces full re-extraction and re-upsert.
        compute_embeddings: If True, computes 768-d text-embedding-005 vectors for chunks.
        sync_dataplex_catalog: If True, synchronizes Dataplex Universal Catalog & OpenLineage.
        repo: Optional pre-configured SpannerGraphRepository (used for dependency injection/testing).
        catalog_syncer: Optional pre-configured DataplexCatalogAndLineageSync.

    Returns:
        Dictionary containing purge metrics, sync report, live Spanner counts, and elapsed time.
    """
    if not bundle_dir.exists():
        raise FileNotFoundError(f"Bundle directory or file not found: {bundle_dir}")

    cfg = get_config()
    t0 = time.monotonic()

    if repo is None:
        repo = SpannerGraphRepository(
            project_id=cfg.google_cloud_project,
            instance_id=cfg.spanner_instance_id,
            database_id=cfg.spanner_database_id,
            use_in_memory=False,
        )

    purged_spanner_counts: dict[str, int] = {}
    post_purge_counts: dict[str, int] = {}
    purged_catalog_report: dict[str, Any] = {}

    if purge:
        print(
            f"[1/4] Purging all existing rows from Cloud Spanner "
            f"({cfg.spanner_instance_id}/{cfg.spanner_database_id})..."
        )
        purged_spanner_counts = repo.purge_all_spanner_data()
        print(f"  -> Purged row counts: {json.dumps(purged_spanner_counts, indent=2)}")

        post_purge_counts = repo.get_live_counts()
        print(f"  -> Post-purge live counts (verify all 0): {json.dumps(post_purge_counts, indent=2)}")

        if sync_dataplex_catalog:
            if catalog_syncer is None:
                catalog_syncer = DataplexCatalogAndLineageSync(
                    project_id=cfg.google_cloud_project,
                    location=cfg.google_cloud_location,
                )
            print("  -> Purging governed Dataplex Universal Catalog entries...")
            purged_catalog_report = catalog_syncer.purge_catalog_entries(
                dry_run=repo.use_in_memory
            )
            print(f"  -> Purged Dataplex Catalog report: {json.dumps(purged_catalog_report)}")
    else:
        print("[1/4] Skipping full purge (incremental / mirror sync mode).")

    print(
        f"[2/4] Synchronizing OKF Markdown bundle '{bundle_dir}' "
        f"(version='{bundle_version}', mode='{sync_mode}') to Cloud Spanner..."
    )
    report: MarkdownSpannerSyncReport = repo.sync_markdown_bundle_to_spanner(
        md_source=bundle_dir,
        sync_mode=sync_mode,
        compute_embeddings=compute_embeddings,
        sync_dataplex_catalog=sync_dataplex_catalog,
        force_reingest=(force_reingest or purge),
        bundle_version=bundle_version,
    )

    print("[3/4] Sync Report Summary:")
    print(f"  status:               {report.status}")
    print(f"  total_md_scanned:     {report.total_md_files_scanned}")
    print(f"  added_concepts:       {len(report.added_concepts)}")
    print(f"  updated_concepts:     {len(report.updated_concepts)}")
    print(f"  removed_concepts:     {len(report.removed_concepts)}")
    print(f"  unchanged_concepts:   {len(report.unchanged_concepts)}")
    print(f"  upserted_counts:      {json.dumps(report.upserted_counts, indent=2)}")
    print(f"  live_counts_after:    {json.dumps(report.live_counts_after_sync, indent=2)}")
    print(f"  catalog_sync_status:  {report.catalog_sync_status}")

    elapsed_s = round(time.monotonic() - t0, 2)
    print(f"[4/4] Completed in {elapsed_s}s!")

    return {
        "bundle_dir": str(bundle_dir),
        "bundle_version": bundle_version,
        "purged": purge,
        "purged_spanner_counts": purged_spanner_counts,
        "post_purge_counts": post_purge_counts,
        "purged_catalog_report": purged_catalog_report,
        "sync_report": report.model_dump(),
        "elapsed_seconds": elapsed_s,
    }


def build_arg_parser(*, default_purge: bool = False) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Purge (optional) and reload Cloud Spanner (okf_knowledge_graph) and "
            "Dataplex Universal Catalog from an OKF v0.2 Markdown (.md) bundle."
        )
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=Path("build/okf_bundle"),
        help="Path to the OKF Markdown bundle directory (default: build/okf_bundle).",
    )
    parser.add_argument(
        "--bundle-version",
        type=str,
        default="v1-acme-demo",
        help="Version tag for ingested concepts (default: v1-acme-demo).",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        default=default_purge,
        help="Purge all existing rows in Cloud Spanner and Dataplex Catalog before reloading.",
    )
    parser.add_argument(
        "--no-purge",
        action="store_false",
        dest="purge",
        help="Disable full purge before syncing.",
    )
    parser.add_argument(
        "--sync-mode",
        type=str,
        choices=["FULL_MIRROR", "INCREMENTAL"],
        default="FULL_MIRROR",
        help="Sync mode: FULL_MIRROR (removes concepts absent from bundle) or INCREMENTAL.",
    )
    parser.add_argument(
        "--force-reingest",
        action="store_true",
        default=False,
        help="Force full re-extraction and re-embedding even when MD5 hashes are unchanged.",
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        default=False,
        help="Skip computing 768-d text-embedding-005 vectors.",
    )
    parser.add_argument(
        "--skip-catalog",
        action="store_true",
        default=False,
        help="Skip synchronizing Google Cloud Dataplex Universal Catalog & OpenLineage.",
    )
    return parser


def main(argv: list[str] | None = None, *, default_purge: bool = False) -> int:
    parser = build_arg_parser(default_purge=default_purge)
    args = parser.parse_args(argv)

    try:
        result = purge_and_reload_spanner(
            bundle_dir=args.bundle_dir,
            bundle_version=args.bundle_version,
            purge=args.purge,
            sync_mode=args.sync_mode,
            force_reingest=args.force_reingest,
            compute_embeddings=not args.skip_embeddings,
            sync_dataplex_catalog=not args.skip_catalog,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    sync_status = result["sync_report"].get("status", "OK")
    return 0 if sync_status in ("OK", "SUCCESS", "NO_CHANGES") else 1


if __name__ == "__main__":
    raise SystemExit(main())
