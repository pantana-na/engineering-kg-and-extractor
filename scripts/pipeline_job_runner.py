"""Parameterized Cloud Run Job Entrypoint (`okf-pipeline-job`).

Executes long-running batch document extraction and/or Cloud Spanner + Dataplex synchronization
outside the HTTP request lifecycle so large document sets never hit Cloud Run web timeouts.

Supported `JOB_MODE` values (via env vars or CLI args):
  - `extract`: Batch-extract raw documents (PDF/DOCX/XLSX/PPTX) using selected Gemini 4 model,
               build OKF indexes, refresh `_manifest.json`, and publish to GCS.
  - `sync`: Pull OKF `.md` bundle from GCS (if enabled), ensure Spanner DDL v2 (`OkfTextEmbeddingModel`,
            ANN `VECTOR INDEX`, edge secondary indexes), sync `.md` -> Cloud Spanner (with native
            `ML.PREDICT` embeddings), and update Dataplex Universal Catalog + OpenLineage.
  - `extract_and_sync`: Execute `extract` followed immediately by `sync`.

Implements SPEC-20261120-UNIFIED-WORKBENCH-V2 Sections 2.2, 4.2 & 9 (Step 4).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(override=False)

from extracter_agent.config import get_config
from extracter_agent.okf.indexer import generate_bundle_indexes
from unified_web.models import (
    PipelineJobMode,
    SpannerSyncMode,
    get_default_extracter_model,
    validate_gemini_model,
)

logging.basicConfig(
    level=logging.INFO,
    format='{"severity":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger("okf_pipeline_job")

JOB_STATUS_DIR = Path(os.getenv("JOB_STATUS_DIR", "/tmp/okf_job_status"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_job_status(
    execution_id: str,
    payload: dict[str, Any],
    *,
    persist_gcs: bool = True,
) -> None:
    """Persist structured live progress heartbeat locally and to GCS `_job_status/<id>.json`."""
    payload["updated_at"] = _now_iso()
    try:
        JOB_STATUS_DIR.mkdir(parents=True, exist_ok=True)
        local_file = JOB_STATUS_DIR / f"{execution_id}.json"
        local_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.debug("Local job status write notice: %s", exc)

    cfg = get_config()
    if persist_gcs and cfg.use_gcs_storage:
        try:
            from google.cloud import storage

            client = storage.Client(project=cfg.google_cloud_project)
            bucket = client.bucket(cfg.destination_gcs_bucket)
            prefix = cfg.destination_gcs_prefix.strip("/")
            blob = bucket.blob(f"{prefix}/_job_status/{execution_id}.json")
            blob.upload_from_string(
                json.dumps(payload, ensure_ascii=False),
                content_type="application/json",
            )
        except Exception as exc:
            logger.debug("GCS job status heartbeat notice: %s", exc)


def _run_batch_extract(
    *,
    execution_id: str,
    model_name: str,
    target_subfolder: str | None,
    target_files: list[str],
    status_payload: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run batch document extraction over matching raw documents using the selected Gemini 4 model."""
    from extracter_agent.agent.orchestrator import create_extracter_agent
    from extracter_agent.gcs.exporter import GCSExporter
    from extracter_agent.pdf.processor import multimodal_execution_context
    from extracter_agent.web_server import ensure_bundle_seeded, list_all_raw_pdfs
    from unified_web.manifest import MANIFEST_STORE

    cfg = get_config()
    bundle_dir = ensure_bundle_seeded()
    all_raw = list_all_raw_pdfs()

    if target_files:
        wanted = {f.strip().lstrip("/") for f in target_files}
        docs = [d for d in all_raw if d["relative_path"] in wanted or d["file_name"] in wanted]
    elif target_subfolder:
        docs = [d for d in all_raw if d["subfolder"].lower() == target_subfolder.lower()]
    else:
        docs = all_raw

    total = len(docs)
    status_payload["total_count"] = total
    status_payload["processed_count"] = 0
    status_payload["step"] = f"Batch extracting {total} document(s) with {model_name}"
    _write_job_status(execution_id, status_payload)

    extracted_ok = 0
    errors: list[dict[str, str]] = []

    if dry_run:
        status_payload["processed_count"] = total
        status_payload["percent"] = 100.0 if status_payload["job_mode"] == "extract" else 50.0
        status_payload["step"] = f"Dry-run batch extract complete ({total} docs)"
        _write_job_status(execution_id, status_payload)
        return {"total_docs": total, "extracted_ok": total, "errors": [], "dry_run": True}

    from google.adk.runners import InMemoryRunner
    from google.genai import types

    prev_out = os.environ.get("OUTPUT_BUNDLE_DIR")
    os.environ["OUTPUT_BUNDLE_DIR"] = str(bundle_dir)
    try:
        agent = create_extracter_agent(model_name=model_name)
        runner = InMemoryRunner(agent=agent, app_name="okf_pipeline_job")

        async def _extract_one(rel_path: str) -> None:
            sess = await runner.session_service.create_session(
                app_name="okf_pipeline_job",
                user_id="pipeline-job",
            )
            prompt = (
                f"Extract all engineering facts, parameters, equipment tags, instrumentation, "
                f"connections, and hazards from raw document '{rel_path}' and incrementally "
                f"create or merge-update all corresponding OKF v0.2 Markdown concept files."
            )
            msg = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
            async for _event in runner.run_async(
                user_id="pipeline-job",
                session_id=sess.id,
                new_message=msg,
            ):
                pass

        for idx, doc in enumerate(docs, start=1):
            rel = doc["relative_path"]
            status_payload["step"] = f"[{idx}/{total}] Extracting {rel} ({model_name})"
            _write_job_status(execution_id, status_payload)
            try:
                with multimodal_execution_context(model_name=model_name):
                    asyncio.run(_extract_one(rel))
                extracted_ok += 1
            except Exception as exc:
                logger.warning("Extraction failed for %s: %s", rel, exc)
                errors.append({"file": rel, "error": str(exc)})
            status_payload["processed_count"] = idx
            max_pct = 90.0 if status_payload["job_mode"] == "extract" else 50.0
            status_payload["percent"] = round((idx / max(1, total)) * max_pct, 1)
            _write_job_status(execution_id, status_payload)

        status_payload["step"] = "Building OKF indexes and refreshing _manifest.json"
        _write_job_status(execution_id, status_payload)
        generate_bundle_indexes(bundle_dir)

        if cfg.use_gcs_storage:
            exporter = GCSExporter(bucket_name=cfg.destination_gcs_bucket)
            exporter.export_bundle(bundle_dir, prefix=cfg.destination_gcs_prefix, dry_run=False)
        MANIFEST_STORE.rebuild_manifest(force_gcs=False, persist_to_gcs=cfg.use_gcs_storage)
    finally:
        if prev_out is None:
            os.environ.pop("OUTPUT_BUNDLE_DIR", None)
        else:
            os.environ["OUTPUT_BUNDLE_DIR"] = prev_out

    return {
        "total_docs": total,
        "extracted_ok": extracted_ok,
        "errors": errors,
    }


def _run_spanner_sync(
    *,
    execution_id: str,
    sync_mode: str,
    purge: bool,
    bundle_version: str,
    compute_embeddings: bool,
    sync_dataplex_catalog: bool,
    status_payload: dict[str, Any],
    use_in_memory: bool = False,
) -> dict[str, Any]:
    """Pull OKF .md bundle from GCS (if enabled), ensure DDL v2, and sync to Cloud Spanner & Dataplex."""
    from extracter_agent.web_server import ensure_bundle_seeded, sync_bundle_from_gcs
    from query_agent.spanner.repository import SpannerGraphRepository
    from scripts.ingest_okf_bundle_to_spanner import purge_and_reload_spanner

    cfg = get_config()
    status_payload["step"] = "Syncing OKF Markdown bundle from GCS"
    _write_job_status(execution_id, status_payload)

    if cfg.use_gcs_storage and not use_in_memory:
        sync_bundle_from_gcs(force=True)
    bundle_dir = ensure_bundle_seeded()

    repo = SpannerGraphRepository(
        project_id=cfg.google_cloud_project,
        instance_id=cfg.spanner_instance_id,
        database_id=cfg.spanner_database_id,
        use_in_memory=use_in_memory,
    )

    status_payload["step"] = "Ensuring Cloud Spanner DDL v2 (Native ML.PREDICT Model & ANN Vector Index)"
    _write_job_status(execution_id, status_payload)
    try:
        repo.ensure_schema_v2()
    except Exception as exc:
        logger.warning("Spanner DDL v2 check notice (continuing with graceful fallback): %s", exc)

    status_payload["step"] = f"Synchronizing OKF .md bundle to Cloud Spanner ({sync_mode}, purge={purge})"
    status_payload["percent"] = 70.0 if status_payload["job_mode"] == "extract_and_sync" else 40.0
    _write_job_status(execution_id, status_payload)

    result = purge_and_reload_spanner(
        bundle_dir=bundle_dir,
        bundle_version=bundle_version,
        purge=purge,
        sync_mode=sync_mode,
        force_reingest=purge,
        compute_embeddings=compute_embeddings,
        sync_dataplex_catalog=sync_dataplex_catalog,
        repo=repo,
    )
    sync_report = result.get("sync_report") or {}
    live_counts = sync_report.get("live_counts_after_sync") or {}
    status_payload["spanner_counts"] = {k: int(v) for k, v in live_counts.items()}
    return result


def run_pipeline(
    *,
    job_mode: str,
    model: str | None = None,
    sync_mode: str = "FULL_MIRROR",
    purge: bool = False,
    target_subfolder: str | None = None,
    target_files: list[str] | None = None,
    bundle_version: str = "v2-unified",
    compute_embeddings: bool = True,
    sync_dataplex_catalog: bool = True,
    execution_id: str | None = None,
    triggered_by: str = "pipeline-cli",
    dry_run_extract: bool = False,
    use_in_memory_spanner: bool = False,
) -> dict[str, Any]:
    """Execute the parameterized pipeline job and persist structured live status updates."""
    mode_enum = PipelineJobMode(job_mode.strip().lower())
    sync_enum = SpannerSyncMode(sync_mode.strip().upper())
    resolved_model = validate_gemini_model(model, default=get_default_extracter_model())
    exec_id = (execution_id or os.getenv("JOB_EXECUTION_ID") or f"exec-{uuid.uuid4().hex[:12]}").strip()
    job_name = os.getenv("PIPELINE_JOB_NAME", "okf-pipeline-job")

    t0 = time.monotonic()
    status_payload: dict[str, Any] = {
        "execution_id": exec_id,
        "job_name": job_name,
        "job_mode": mode_enum.value,
        "model": resolved_model,
        "sync_mode": sync_enum.value,
        "purge": bool(purge),
        "status": "RUNNING",
        "execution_backend": "cloud_run_job" if os.getenv("CLOUD_RUN_EXECUTION") else "local_subprocess",
        "triggered_by": triggered_by,
        "step": "Pipeline job started",
        "processed_count": 0,
        "total_count": 0,
        "percent": 5.0,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "completed_at": None,
        "spanner_counts": {},
        "summary": {},
        "error": None,
    }
    _write_job_status(exec_id, status_payload)

    try:
        summary: dict[str, Any] = {}
        if mode_enum in (PipelineJobMode.EXTRACT, PipelineJobMode.EXTRACT_AND_SYNC):
            summary["extract"] = _run_batch_extract(
                execution_id=exec_id,
                model_name=resolved_model,
                target_subfolder=target_subfolder,
                target_files=list(target_files or []),
                status_payload=status_payload,
                dry_run=dry_run_extract,
            )

        if mode_enum in (PipelineJobMode.SYNC, PipelineJobMode.EXTRACT_AND_SYNC):
            summary["sync"] = _run_spanner_sync(
                execution_id=exec_id,
                sync_mode=sync_enum.value,
                purge=bool(purge),
                bundle_version=bundle_version,
                compute_embeddings=compute_embeddings,
                sync_dataplex_catalog=sync_dataplex_catalog,
                status_payload=status_payload,
                use_in_memory=use_in_memory_spanner,
            )

        status_payload["status"] = "SUCCEEDED"
        status_payload["step"] = "Completed successfully"
        status_payload["percent"] = 100.0
        status_payload["completed_at"] = _now_iso()
        status_payload["summary"] = {
            **summary,
            "elapsed_seconds": round(time.monotonic() - t0, 2),
        }
        _write_job_status(exec_id, status_payload)
        return status_payload
    except Exception as exc:
        logger.exception("Pipeline job %s failed", exec_id)
        status_payload["status"] = "FAILED"
        status_payload["step"] = f"Failed: {exc}"
        status_payload["error"] = str(exc)
        status_payload["completed_at"] = _now_iso()
        _write_job_status(exec_id, status_payload)
        return status_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OKF Parameterized Cloud Run Pipeline Job Runner")
    parser.add_argument("--job-mode", default=os.getenv("JOB_MODE", "sync"))
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", get_default_extracter_model()))
    parser.add_argument("--sync-mode", default=os.getenv("SYNC_MODE", "FULL_MIRROR"))
    parser.add_argument(
        "--purge",
        action="store_true",
        default=os.getenv("PURGE", "false").strip().lower() in ("true", "1", "yes"),
    )
    parser.add_argument("--target-subfolder", default=os.getenv("TARGET_SUBFOLDER", "") or None)
    parser.add_argument("--bundle-version", default=os.getenv("BUNDLE_VERSION", "v2-unified"))
    parser.add_argument("--execution-id", default=os.getenv("JOB_EXECUTION_ID", "") or None)
    parser.add_argument("--triggered-by", default=os.getenv("TRIGGERED_BY", "cloud-run-job"))
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        default=os.getenv("COMPUTE_EMBEDDINGS", "true").strip().lower() in ("false", "0", "no"),
    )
    parser.add_argument(
        "--skip-catalog",
        action="store_true",
        default=os.getenv("SYNC_DATAPLEX_CATALOG", "true").strip().lower() in ("false", "0", "no"),
    )
    parser.add_argument(
        "--dry-run-extract",
        action="store_true",
        default=os.getenv("PIPELINE_DRY_RUN_EXTRACT", "false").strip().lower() in ("true", "1", "yes"),
    )
    parser.add_argument(
        "--in-memory-spanner",
        action="store_true",
        default=os.getenv("QUERY_WEB_USE_IN_MEMORY", "false").strip().lower() in ("true", "1", "yes"),
    )
    args = parser.parse_args(argv)

    raw_files_json = os.getenv("TARGET_FILES_JSON", "").strip()
    target_files: list[str] = []
    if raw_files_json:
        try:
            parsed = json.loads(raw_files_json)
            if isinstance(parsed, list):
                target_files = [str(x) for x in parsed]
        except Exception:
            target_files = []

    res = run_pipeline(
        job_mode=args.job_mode,
        model=args.model,
        sync_mode=args.sync_mode,
        purge=args.purge,
        target_subfolder=args.target_subfolder,
        target_files=target_files,
        bundle_version=args.bundle_version,
        compute_embeddings=not args.skip_embeddings,
        sync_dataplex_catalog=not args.skip_catalog,
        execution_id=args.execution_id,
        triggered_by=args.triggered_by,
        dry_run_extract=args.dry_run_extract,
        use_in_memory_spanner=args.in_memory_spanner,
    )
    return 0 if res.get("status") == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
