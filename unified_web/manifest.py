"""High-scale Extractor Metadata Manifest (`_manifest.json`) & Paginated File Index.

Eliminates O(N) full-bundle GCS listing, YAML parsing, SHA-256 hashing, and full
`validate_okf_bundle_tool()` scans on every UI poll for up to 5,000 raw docs & 10,000 OKF concepts.
Implements SPEC-20261120-UNIFIED-WORKBENCH-V2 Section 6.1.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extracter_agent.config import get_config
from extracter_agent.web_server import (
    ensure_bundle_seeded,
    list_all_okf_files,
    list_all_raw_pdfs,
    sync_bundle_from_gcs,
)

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "_manifest.json"
MANIFEST_CACHE_TTL_SECONDS = 15.0


class BundleManifestStore:
    """Thread-safe TTL-cached metadata manifest for Raw Documents & OKF Markdown Concepts."""

    def __init__(self, ttl_seconds: float = MANIFEST_CACHE_TTL_SECONDS) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self._lock = threading.Lock()
        self._cached_at: float = 0.0
        self._cached_bundle_dir: str = ""
        self._manifest: dict[str, Any] | None = None

    def invalidate(self) -> None:
        """Invalidate in-memory manifest cache (called after extraction or Cloud Run Job sync)."""
        with self._lock:
            self._cached_at = 0.0
            self._manifest = None

    def _compute_sync_version(
        self,
        raw_pdfs: list[dict[str, Any]],
        okf_files: list[dict[str, Any]],
    ) -> str:
        hasher = hashlib.sha256()
        for item in okf_files:
            entry = f"okf:{item['relative_path']}:{item['size_bytes']}:{item['content_hash']}\n"
            hasher.update(entry.encode("utf-8"))
        for pdf in raw_pdfs:
            entry = f"pdf:{pdf['relative_path']}:{pdf['size_bytes']}\n"
            hasher.update(entry.encode("utf-8"))
        return hasher.hexdigest()[:16]

    def rebuild_manifest(
        self,
        *,
        force_gcs: bool = False,
        persist_to_gcs: bool = False,
    ) -> dict[str, Any]:
        """Rebuild `_manifest.json` from local bundle + raw docs (and optionally sync/upload GCS)."""
        cfg = get_config()
        gcs_sync = (
            sync_bundle_from_gcs(force=force_gcs)
            if cfg.use_gcs_storage
            else {"synced": False, "reason": "gcs_disabled", "downloaded_count": 0}
        )
        bundle_dir = ensure_bundle_seeded()

        raw_pdfs = list_all_raw_pdfs()
        okf_files = list_all_okf_files(bundle_dir)
        sync_version = self._compute_sync_version(raw_pdfs, okf_files)

        raw_counts: dict[str, int] = {}
        for p in raw_pdfs:
            sub = str(p.get("subfolder") or "root")
            raw_counts[sub] = raw_counts.get(sub, 0) + 1

        okf_counts: dict[str, int] = {}
        conflict_count = 0
        for f in okf_files:
            cat = str(f.get("category") or "root")
            okf_counts[cat] = okf_counts.get(cat, 0) + 1
            if f.get("has_conflict"):
                conflict_count += 1

        manifest = {
            "schema_version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sync_version": sync_version,
            "gcs_sync": gcs_sync,
            "raw_pdf_count": len(raw_pdfs),
            "okf_file_count": len(okf_files),
            "conflict_count": conflict_count,
            "raw_subfolders": raw_counts,
            "okf_categories": okf_counts,
            "raw_pdfs": raw_pdfs,
            "okf_files": okf_files,
        }

        manifest_path = bundle_dir / MANIFEST_FILENAME
        try:
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("Could not write local _manifest.json: %s", exc)

        if persist_to_gcs and cfg.use_gcs_storage:
            try:
                from google.cloud import storage

                client = storage.Client(project=cfg.google_cloud_project)
                bucket = client.bucket(cfg.destination_gcs_bucket)
                prefix = cfg.destination_gcs_prefix.strip("/")
                blob = bucket.blob(f"{prefix}/{MANIFEST_FILENAME}")
                blob.upload_from_string(
                    json.dumps(manifest, ensure_ascii=False),
                    content_type="application/json",
                )
            except Exception as exc:
                logger.warning("GCS _manifest.json upload notice: %s", exc)

        with self._lock:
            self._cached_at = time.monotonic()
            self._cached_bundle_dir = str(bundle_dir)
            self._manifest = manifest

        return manifest

    def _try_load_gcs_manifest(self) -> dict[str, Any] | None:
        """Attempt O(1) single-object fetch of `_manifest.json` from GCS if enabled."""
        cfg = get_config()
        if not cfg.use_gcs_storage:
            return None
        try:
            from google.cloud import storage

            client = storage.Client(project=cfg.google_cloud_project)
            bucket = client.bucket(cfg.destination_gcs_bucket)
            prefix = cfg.destination_gcs_prefix.strip("/")
            blob = bucket.blob(f"{prefix}/{MANIFEST_FILENAME}")
            if not blob.exists():
                return None
            raw_json = blob.download_as_text(encoding="utf-8")
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict) and "okf_files" in parsed and "raw_pdfs" in parsed:
                return parsed
        except Exception as exc:
            logger.debug("GCS _manifest.json fast-path skipped: %s", exc)
        return None

    def get_manifest(self, *, force_refresh: bool = False) -> dict[str, Any]:
        """Return cached metadata manifest or rebuild/fetch when stale."""
        bundle_dir = ensure_bundle_seeded()
        now = time.monotonic()

        with self._lock:
            if (
                not force_refresh
                and self._manifest is not None
                and self._cached_bundle_dir == str(bundle_dir)
                and (now - self._cached_at) < self.ttl_seconds
            ):
                return self._manifest

        if not force_refresh:
            gcs_manifest = self._try_load_gcs_manifest()
            if gcs_manifest is not None:
                with self._lock:
                    self._cached_at = now
                    self._cached_bundle_dir = str(bundle_dir)
                    self._manifest = gcs_manifest
                return gcs_manifest

        return self.rebuild_manifest(force_gcs=force_refresh, persist_to_gcs=force_refresh)

    def query_paginated_files(
        self,
        *,
        kind: str = "all",
        q: str = "",
        subfolder: str = "",
        category: str = "",
        conflicts_only: bool = False,
        limit: int = 50,
        offset: int = 0,
        since_version: str = "",
        force_gcs: bool = False,
    ) -> dict[str, Any]:
        """Return server-side filtered & paginated Raw PDFs and OKF Markdown files."""
        cfg = get_config()
        manifest = self.get_manifest(force_refresh=force_gcs)
        sync_version = str(manifest.get("sync_version") or "")
        changed = (not since_version) or (since_version != sync_version)

        safe_limit = max(1, min(200, int(limit)))
        safe_offset = max(0, int(offset))
        clean_q = (q or "").strip().lower()
        clean_sub = (subfolder or "").strip().lower()
        clean_cat = (category or "").strip().lower()

        raw_pdfs: list[dict[str, Any]] = list(manifest.get("raw_pdfs") or [])
        okf_files: list[dict[str, Any]] = list(manifest.get("okf_files") or [])

        if clean_sub:
            raw_pdfs = [p for p in raw_pdfs if str(p.get("subfolder") or "").lower() == clean_sub]
        if clean_q:
            raw_pdfs = [
                p
                for p in raw_pdfs
                if clean_q in str(p.get("file_name") or "").lower()
                or clean_q in str(p.get("relative_path") or "").lower()
            ]

        if clean_cat:
            okf_files = [f for f in okf_files if str(f.get("category") or "").lower() == clean_cat]
        if conflicts_only:
            okf_files = [f for f in okf_files if f.get("has_conflict")]
        if clean_q:
            okf_files = [
                f
                for f in okf_files
                if clean_q in str(f.get("title") or "").lower()
                or clean_q in str(f.get("concept_id") or "").lower()
                or clean_q in str(f.get("category") or "").lower()
            ]

        raw_total = len(raw_pdfs)
        okf_total = len(okf_files)

        raw_page = raw_pdfs[safe_offset : safe_offset + safe_limit] if kind in ("all", "raw") else []
        okf_page = okf_files[safe_offset : safe_offset + safe_limit] if kind in ("all", "okf") else []

        return {
            "status": "success",
            "changed": changed,
            "sync_version": sync_version,
            "generated_at": manifest.get("generated_at"),
            "gcs_bucket": f"gs://{cfg.destination_gcs_bucket}",
            "gcs_raw_prefix": cfg.source_gcs_raw_prefix,
            "gcs_okf_prefix": cfg.destination_gcs_prefix,
            "raw_pdf_count": int(manifest.get("raw_pdf_count", 0)),
            "okf_file_count": int(manifest.get("okf_file_count", 0)),
            "conflict_count": int(manifest.get("conflict_count", 0)),
            "raw_subfolders": manifest.get("raw_subfolders", {}),
            "okf_categories": manifest.get("okf_categories", {}),
            "pagination": {
                "limit": safe_limit,
                "offset": safe_offset,
                "raw_filtered_total": raw_total,
                "raw_has_more": (safe_offset + len(raw_page)) < raw_total,
                "okf_filtered_total": okf_total,
                "okf_has_more": (safe_offset + len(okf_page)) < okf_total,
            },
            "raw_pdfs": raw_page,
            "okf_files": okf_page,
        }


MANIFEST_STORE = BundleManifestStore()
