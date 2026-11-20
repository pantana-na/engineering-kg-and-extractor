"""Cloud Run Jobs v2 REST Dispatcher & Local Subprocess Fallback (`okf-pipeline-job`).

Uses Google ADC (`google.auth.default`) + `httpx` to call the official Cloud Run Jobs v2 API
with zero additional PyPI dependencies, supporting:
  - Container env overrides (`JOB_MODE`, `GEMINI_MODEL`, `SYNC_MODE`, `PURGE`, etc.)
  - `X-Idempotency-Key` deduplication (60s TTL window)
  - Live progress overlay from GCS `_job_status/<execution_id>.json`
  - Typed `503 UPSTREAM_UNAVAILABLE_DEGRADED` on API failures (WAF Pillar 3 & Rule 13)
  - Automatic local subprocess fallback when running outside GCP / in dev tests
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from extracter_agent.config import get_config
from unified_web.models import (
    PipelineJobRequest,
    PipelineJobStatus,
    get_default_extracter_model,
    validate_gemini_model,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
JOB_STATUS_DIR = Path(os.getenv("JOB_STATUS_DIR", "/tmp/okf_job_status"))
IDEMPOTENCY_TTL_SECONDS = 60.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UpstreamJobServiceError(RuntimeError):
    """Raised when Cloud Run Jobs v2 API is unavailable (mapped to HTTP 503 degraded response)."""


class PipelineJobDispatcher:
    """Dispatches and monitors parameterized `okf-pipeline-job` executions."""

    def __init__(
        self,
        *,
        http_client_factory: Callable[[], httpx.Client] | None = None,
        token_provider: Callable[[], str] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, tuple[float, str]] = {}
        self._hydrated_at: float = 0.0
        self._exec_cache_at: float = 0.0
        self._exec_cache: list[dict[str, Any]] = []
        self._http_client_factory = http_client_factory
        self._token_provider = token_provider

    def reset(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._idempotency.clear()
            self._hydrated_at = 0.0
            self._exec_cache_at = 0.0
            self._exec_cache = []

    def _get_execution_backend(self) -> str:
        raw = os.getenv("CLOUD_RUN_JOBS_EXECUTION_MODE", "auto").strip().lower()
        if raw in ("cloud_run_job", "cloud_run", "gcp"):
            return "cloud_run_job"
        if raw in ("local", "local_subprocess", "subprocess"):
            return "local_subprocess"
        # auto: use Cloud Run Jobs API when running on Cloud Run (`K_SERVICE` set)
        return "cloud_run_job" if os.getenv("K_SERVICE", "").strip() else "local_subprocess"

    def _get_job_name(self) -> str:
        env_tier = os.getenv("DEPLOYMENT_ENV", "NONPROD").strip().upper()
        for key in (f"{env_tier}_PIPELINE_JOB_NAME", "PIPELINE_JOB_NAME"):
            val = os.getenv(key, "").strip()
            if val:
                return val
        return "okf-pipeline-job"

    def _get_access_token(self) -> str:
        if self._token_provider is not None:
            return self._token_provider()
        import google.auth
        from google.auth.transport.requests import Request as GoogleAuthRequest

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(GoogleAuthRequest())
        return str(creds.token)

    def _build_env_overrides(
        self,
        *,
        execution_id: str,
        req: PipelineJobRequest,
        resolved_model: str,
        triggered_by: str,
    ) -> dict[str, str]:
        env_map: dict[str, str] = {
            "JOB_EXECUTION_ID": execution_id,
            "JOB_MODE": req.job_mode.value,
            "GEMINI_MODEL": resolved_model,
            "SYNC_MODE": req.sync_mode.value,
            "PURGE": "true" if req.purge else "false",
            "BUNDLE_VERSION": req.bundle_version,
            "COMPUTE_EMBEDDINGS": "true" if req.compute_embeddings else "false",
            "SYNC_DATAPLEX_CATALOG": "true" if req.sync_dataplex_catalog else "false",
            "TRIGGERED_BY": triggered_by,
        }
        if req.target_subfolder:
            env_map["TARGET_SUBFOLDER"] = req.target_subfolder
        if req.target_files:
            env_map["TARGET_FILES_JSON"] = json.dumps(req.target_files)
        return env_map

    def _trigger_cloud_run_job(
        self,
        *,
        job_name: str,
        env_overrides: dict[str, str],
    ) -> str:
        cfg = get_config()
        url = (
            f"https://run.googleapis.com/v2/projects/{cfg.google_cloud_project}"
            f"/locations/{cfg.google_cloud_location}/jobs/{job_name}:run"
        )
        body = {
            "overrides": {
                "containerOverrides": [
                    {
                        "env": [{"name": k, "value": v} for k, v in env_overrides.items()],
                    }
                ]
            }
        }
        try:
            token = self._get_access_token()
            client = self._http_client_factory() if self._http_client_factory else httpx.Client(timeout=30.0)
            with client:
                resp = client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            if resp.status_code >= 400:
                raise UpstreamJobServiceError(
                    f"Cloud Run Jobs API returned HTTP {resp.status_code}: {resp.text[:240]}"
                )
            data = resp.json()
            meta = data.get("metadata") or {}
            return str(meta.get("name") or data.get("name") or "")
        except UpstreamJobServiceError:
            raise
        except Exception as exc:
            raise UpstreamJobServiceError(f"Cloud Run Jobs API unreachable: {exc}") from exc

    def _spawn_local_subprocess(
        self,
        *,
        execution_id: str,
        env_overrides: dict[str, str],
    ) -> None:
        child_env = os.environ.copy()
        child_env.update(env_overrides)
        child_env["PYTHONPATH"] = str(REPO_ROOT)
        child_env["JOB_STATUS_DIR"] = str(JOB_STATUS_DIR)
        cmd = [sys.executable, "-m", "scripts.pipeline_job_runner"]
        subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            env=child_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def submit_job(
        self,
        req: PipelineJobRequest,
        *,
        triggered_by: str,
        idempotency_key: str | None = None,
    ) -> tuple[PipelineJobStatus, bool]:
        """Submit a pipeline job. Returns `(status, is_duplicate_idempotent_hit)`."""
        clean_idem = (idempotency_key or "").strip() or None
        now = time.monotonic()

        existing_id: str | None = None
        with self._lock:
            # Prune expired idempotency entries
            expired = [k for k, (ts, _) in self._idempotency.items() if (now - ts) > IDEMPOTENCY_TTL_SECONDS]
            for k in expired:
                self._idempotency.pop(k, None)

            if clean_idem and clean_idem in self._idempotency:
                _, existing_id = self._idempotency[clean_idem]

        if existing_id is not None:
            existing = self.get_job(existing_id)
            if existing is not None:
                return existing, True

        resolved_model = validate_gemini_model(req.model, default=get_default_extracter_model())
        execution_id = f"job-{uuid.uuid4().hex[:12]}"
        job_name = self._get_job_name()
        backend = self._get_execution_backend()
        env_overrides = self._build_env_overrides(
            execution_id=execution_id,
            req=req,
            resolved_model=resolved_model,
            triggered_by=triggered_by,
        )

        cloud_run_exec_name = ""
        if backend == "cloud_run_job":
            cloud_run_exec_name = self._trigger_cloud_run_job(
                job_name=job_name,
                env_overrides=env_overrides,
            )
        else:
            self._spawn_local_subprocess(
                execution_id=execution_id,
                env_overrides=env_overrides,
            )

        now_iso = _now_iso()
        record = PipelineJobStatus(
            execution_id=execution_id,
            job_name=job_name,
            job_mode=req.job_mode.value,
            model=resolved_model,
            sync_mode=req.sync_mode.value,
            purge=req.purge,
            status="QUEUED",
            execution_backend=backend,
            triggered_by=triggered_by,
            step=f"Dispatched {req.job_mode.value} job to {backend}",
            created_at=now_iso,
            updated_at=now_iso,
            summary={"cloud_run_execution": cloud_run_exec_name} if cloud_run_exec_name else {},
            idempotency_key=clean_idem,
        )

        with self._lock:
            self._jobs[execution_id] = record.model_dump()
            if clean_idem:
                self._idempotency[clean_idem] = (now, execution_id)
            if len(self._jobs) > 50:
                oldest = next(iter(self._jobs))
                self._jobs.pop(oldest, None)

        # Persist initial QUEUED record immediately so restarts/scale-to-zero never lose the job
        self._persist_initial_heartbeat(execution_id, record.model_dump())

        return record, False

    def _persist_initial_heartbeat(self, execution_id: str, payload: dict[str, Any]) -> None:
        status_dir = Path(os.getenv("JOB_STATUS_DIR", str(JOB_STATUS_DIR)))
        try:
            status_dir.mkdir(parents=True, exist_ok=True)
            (status_dir / f"{execution_id}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.debug("Initial local heartbeat write notice: %s", exc)

        cfg = get_config()
        if cfg.use_gcs_storage:
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
                logger.debug("Initial GCS heartbeat write notice: %s", exc)

    def _hydrate_from_storage(self, *, ttl_seconds: float = 5.0) -> None:
        """Hydrate persisted `_job_status/*.json` records from local dir and GCS so jobs survive restarts."""
        now = time.monotonic()
        with self._lock:
            if (now - self._hydrated_at) < ttl_seconds:
                return
            self._hydrated_at = now

        loaded: list[dict[str, Any]] = []
        status_dir = Path(os.getenv("JOB_STATUS_DIR", str(JOB_STATUS_DIR)))
        if status_dir.is_dir():
            for fp in sorted(status_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:25]:
                try:
                    obj = json.loads(fp.read_text(encoding="utf-8"))
                    if isinstance(obj, dict) and obj.get("execution_id"):
                        loaded.append(obj)
                except Exception:
                    continue

        cfg = get_config()
        if cfg.use_gcs_storage:
            try:
                from google.cloud import storage

                client = storage.Client(project=cfg.google_cloud_project)
                bucket = client.bucket(cfg.destination_gcs_bucket)
                prefix = cfg.destination_gcs_prefix.strip("/")
                blobs = [
                    b
                    for b in bucket.list_blobs(prefix=f"{prefix}/_job_status/")
                    if b.name.endswith(".json")
                ]
                blobs.sort(key=lambda b: b.updated.timestamp() if b.updated else 0.0, reverse=True)
                for blob in blobs[:25]:
                    try:
                        obj = json.loads(blob.download_as_text(encoding="utf-8"))
                        if isinstance(obj, dict) and obj.get("execution_id"):
                            loaded.append(obj)
                    except Exception:
                        continue
            except Exception as exc:
                logger.debug("GCS _job_status hydration notice: %s", exc)

        if not loaded:
            return
        with self._lock:
            for item in loaded:
                eid = str(item["execution_id"])
                existing = self._jobs.get(eid)
                if existing is None:
                    self._jobs[eid] = item
                else:
                    # Merge keeping whichever record has the newer updated_at timestamp
                    if str(item.get("updated_at") or "") >= str(existing.get("updated_at") or ""):
                        merged_summary = {
                            **(existing.get("summary") or {}),
                            **(item.get("summary") or {}),
                        }
                        self._jobs[eid] = {**existing, **item, "summary": merged_summary}

    def _list_live_cloud_run_executions(self, *, ttl_seconds: float = 10.0) -> list[dict[str, Any]]:
        """Query live Cloud Run Jobs v2 Executions API to reconcile cancelled/completed/failed states."""
        if self._get_execution_backend() != "cloud_run_job":
            return []
        if not os.getenv("K_SERVICE", "").strip() and self._http_client_factory is None:
            return []
        now = time.monotonic()
        with self._lock:
            if (now - self._exec_cache_at) < ttl_seconds and self._exec_cache:
                return list(self._exec_cache)
        try:
            cfg = get_config()
            job_name = self._get_job_name()
            url = (
                f"https://run.googleapis.com/v2/projects/{cfg.google_cloud_project}"
                f"/locations/{cfg.google_cloud_location}/jobs/{job_name}/executions?pageSize=15"
            )
            token = self._get_access_token()
            client = self._http_client_factory() if self._http_client_factory else httpx.Client(timeout=8.0)
            with client:
                resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
            if resp.status_code >= 400:
                return []
            execs = list((resp.json() or {}).get("executions") or [])
            with self._lock:
                self._exec_cache_at = now
                self._exec_cache = execs
            return execs
        except Exception as exc:
            logger.debug("Cloud Run live execution reconcile notice: %s", exc)
            return []

    def _reconcile_cloud_run_status(self, merged: dict[str, Any], live_execs: list[dict[str, Any]]) -> dict[str, Any]:
        """Reconcile a RUNNING/QUEUED heartbeat against live Cloud Run Job executions (handles external cancel/crash)."""
        if merged.get("execution_backend") != "cloud_run_job" or merged.get("status") not in ("QUEUED", "RUNNING"):
            return merged
        if not live_execs:
            return merged

        recorded_name = str((merged.get("summary") or {}).get("cloud_run_execution") or "").strip()
        matched: dict[str, Any] | None = None
        if recorded_name:
            for ex in live_execs:
                if str(ex.get("name") or "") == recorded_name:
                    matched = ex
                    break
        else:
            # Match by closest creation timestamp within 120 seconds (for legacy heartbeats without cloud_run_execution)
            try:
                hb_dt = datetime.fromisoformat(str(merged.get("created_at") or "").replace("Z", "+00:00"))
                best_diff = 120.0
                for ex in live_execs:
                    ex_ct = str(ex.get("createTime") or "")
                    if not ex_ct:
                        continue
                    ex_dt = datetime.fromisoformat(ex_ct.replace("Z", "+00:00"))
                    diff = abs((hb_dt - ex_dt).total_seconds())
                    if diff < best_diff:
                        best_diff = diff
                        matched = ex
            except Exception:
                matched = None

        if matched is None:
            return merged

        cancelled = int(matched.get("cancelledCount") or 0)
        failed = int(matched.get("failedCount") or 0)
        succeeded = int(matched.get("succeededCount") or 0)
        running = int(matched.get("runningCount") or 0)
        if running > 0:
            return merged

        updated = dict(merged)
        if cancelled > 0:
            updated["status"] = "CANCELLED"
            updated["step"] = f"Execution cancelled ({str(matched.get('name') or '').split('/')[-1]})"
            updated["completed_at"] = str(matched.get("completionTime") or _now_iso())
        elif failed > 0:
            updated["status"] = "FAILED"
            updated["completed_at"] = str(matched.get("completionTime") or _now_iso())
            if not updated.get("error"):
                updated["error"] = "Cloud Run Job execution failed (check Cloud Logging)."
        elif succeeded > 0:
            updated["status"] = "SUCCEEDED"
            updated["percent"] = 100.0
            updated["completed_at"] = str(matched.get("completionTime") or _now_iso())
        return updated

    def _read_status_heartbeat(self, execution_id: str) -> dict[str, Any] | None:
        status_dir = Path(os.getenv("JOB_STATUS_DIR", str(JOB_STATUS_DIR)))
        local_file = status_dir / f"{execution_id}.json"
        if local_file.is_file():
            try:
                return json.loads(local_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        cfg = get_config()
        if cfg.use_gcs_storage:
            try:
                from google.cloud import storage

                client = storage.Client(project=cfg.google_cloud_project)
                bucket = client.bucket(cfg.destination_gcs_bucket)
                prefix = cfg.destination_gcs_prefix.strip("/")
                blob = bucket.blob(f"{prefix}/_job_status/{execution_id}.json")
                if blob.exists():
                    return json.loads(blob.download_as_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    def get_job(self, execution_id: str, *, _live_execs: list[dict[str, Any]] | None = None) -> PipelineJobStatus | None:
        with self._lock:
            base = dict(self._jobs.get(execution_id) or {})

        heartbeat = self._read_status_heartbeat(execution_id)
        if not base and not heartbeat:
            return None

        merged = {**base, **(heartbeat or {})}
        if base.get("summary") or (heartbeat and heartbeat.get("summary")):
            merged["summary"] = {
                **(base.get("summary") or {}),
                **((heartbeat or {}).get("summary") or {}),
            }
        if not merged.get("execution_id"):
            merged["execution_id"] = execution_id

        if merged.get("status") in ("QUEUED", "RUNNING") and merged.get("execution_backend") == "cloud_run_job":
            execs = _live_execs if _live_execs is not None else self._list_live_cloud_run_executions()
            merged = self._reconcile_cloud_run_status(merged, execs)

        with self._lock:
            self._jobs[execution_id] = merged
        return PipelineJobStatus(**merged)

    def list_jobs(self, limit: int = 20) -> list[PipelineJobStatus]:
        self._hydrate_from_storage()
        with self._lock:
            ids = list(self._jobs.keys())
        has_active_cr = any(
            self._jobs.get(eid, {}).get("status") in ("QUEUED", "RUNNING")
            and self._jobs.get(eid, {}).get("execution_backend") == "cloud_run_job"
            for eid in ids
        )
        live_execs = self._list_live_cloud_run_executions() if has_active_cr else []

        items: list[PipelineJobStatus] = []
        for eid in ids:
            st_obj = self.get_job(eid, _live_execs=live_execs)
            if st_obj is not None:
                items.append(st_obj)
        items.sort(key=lambda j: str(j.created_at or ""), reverse=True)
        return items[:limit]


JOB_DISPATCHER = PipelineJobDispatcher()
