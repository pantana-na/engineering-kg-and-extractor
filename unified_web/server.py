"""Unified FastAPI Server (`okf-engineering-workbench`) for Cloud Run.

Consolidates both OKF Extractor Studio and OKF Spanner Graph-RAG Query Workbench into a single
Cloud Run service with:
  - Tabbed Zero-Build Vanilla ES Modules SPA at `/`
  - Selectable Gemini 4 Models (`/api/models`: Carbon default for Extractor, Hydrogen default for Query, Argon, Neon)
  - High-Scale Extractor Explorer (`_manifest.json` TTL cache + server-side pagination & search)
  - Parameterized Cloud Run Job Dispatcher (`/api/jobs/run` -> `okf-pipeline-job`, `JOB_MODE=extract|sync|extract_and_sync`)
  - Deterministic HITL Gate (`X-Confirm-Purge: CONFIRMED` + `X-Idempotency-Key`) for destructive Spanner Purge
  - Lazy Two-Tier Spanner Hierarchy (`/api/spanner/hierarchy/summary` & `/items`) + Parallel Concept Dossier (`asyncio.gather`)
  - Real-Time SSE Streaming Query Endpoint (`POST /api/query/chat/stream` with `X-Accel-Buffering: no`)
  - Pattern 1B Direct Cloud Run IAP Cryptographic JWT Verification Middleware & Rate Limiting

Implements SPEC-20261120-UNIFIED-WORKBENCH-V2.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents import Agent
from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

load_dotenv(override=False)

from extracter_agent.agent.classifier import CognitiveClassifier
from extracter_agent.agent.guardrails import (
    SecurityGuardrailError,
    before_agent_callback,
    check_prompt_security,
)
from extracter_agent.agent.orchestrator import create_extracter_agent
from extracter_agent.config import get_config as get_extracter_config
from extracter_agent.deploy_config import get_safe_cloud_run_posture
from extracter_agent.models.intent import IntentCategory
from extracter_agent.pdf.processor import get_raw_mime_type, is_supported_raw_file
from extracter_agent.tools.okf_tools import inspect_existing_okf_concept_tool
from extracter_agent.tools.pdf_tools import (
    _download_pdf_from_gcs,
    find_raw_documents_tool,
    process_raw_pdf_tool,
)
from extracter_agent.web_server import (
    ALLOWED_RAW_SUBFOLDERS,
    ensure_bundle_seeded,
    list_all_okf_files,
    list_all_raw_pdfs,
    resolve_pdf_source_links,
)
from query_agent.guardrails import (
    QuerySecurityGuardrailError,
    check_query_prompt_security,
    query_agent_after_model_callback,
    query_agent_after_tool_callback,
    query_agent_before_callback,
    query_agent_before_model_callback,
)
from query_agent.orchestrator import QUERY_ORCHESTRATOR_INSTRUCTIONS
from query_agent.spanner.repository import SpannerGraphRepository
from query_agent.tools.spanner_rag_tools import (
    execute_multistage_risk_and_hazop_query,
    hybrid_search_okf_spanner,
    lookup_entity_and_parameters,
    read_full_okf_concept_from_spanner,
    set_active_spanner_repository,
    sync_or_inspect_knowledge_catalog,
    trace_data_lineage_and_conflicts,
    traverse_equipment_connectivity_graph,
)
from query_agent.web_server import (
    PRE_BUILT_PROMPTS,
    TOOL_DESCRIPTIONS,
    _extract_referenced_tags,
    _fetch_catalog_payload,
    _summarize_tool_output,
    compute_telemetry_totals,
)
from unified_web.jobs import JOB_DISPATCHER, PipelineJobDispatcher, UpstreamJobServiceError
from unified_web.manifest import MANIFEST_STORE, BundleManifestStore
from unified_web.models import (
    GEMINI_MODEL_CATALOG,
    ModelCatalogResponse,
    PipelineJobRequest,
    get_allowed_gemini_models,
    get_default_extracter_model,
    get_default_query_model,
    validate_gemini_model,
)
from unified_web.security import (
    IDEMPOTENCY_HEADER,
    PURGE_CONFIRM_HEADER,
    SlidingWindowRateLimiter,
    enforce_purge_hitl_gate,
    resolve_request_principal,
)

logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
STATIC_DIR = PACKAGE_DIR / "static"

_FOCUS_TAG_SAFE_RE = re.compile(r"^[A-Za-z0-9_./:\- ()]{1,128}$")


class BoundedTTLCache:
    """Thread-safe bounded LRU cache with TTL expiration for Spanner read acceleration."""

    def __init__(self, *, max_size: int = 256, ttl_seconds: float = 60.0) -> None:
        self.max_size = max(1, int(max_size))
        self.ttl_seconds = float(ttl_seconds)
        self._lock = threading.Lock()
        self._store: OrderedDict[Any, tuple[float, Any]] = OrderedDict()

    def get(self, key: Any) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            ts, val = entry
            if (now - ts) >= self.ttl_seconds:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return val

    def set(self, key: Any, value: Any) -> None:
        now = time.monotonic()
        with self._lock:
            self._store[key] = (now, value)
            self._store.move_to_end(key)
            while len(self._store) > self.max_size:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class UnifiedExtractRequest(BaseModel):
    """Request schema for interactive single-doc extraction or Extractor chat."""

    prompt: str = Field(default="")
    mode: str = Field(default="auto")
    target_equipment: str | None = Field(default=None)
    target_pdf: str | None = Field(default=None)
    concept_id: str = Field(default="")
    subfolder: str = Field(default="data_sheets")
    pdf_filename: str = Field(default="")
    model: str | None = Field(default=None, description="Allowlisted Gemini 4 model (default: gemini-4-carbon)")
    invoke_vertex_llm: bool = Field(default=False)
    async_job: bool = Field(default=False)


class UnifiedQueryChatRequest(BaseModel):
    """Request schema for Knowledge Graph & Query chat (polling & SSE streaming)."""

    question: str = Field(..., min_length=1)
    session_id: str | None = Field(default=None)
    focus_tag: str | None = Field(default=None)
    category: str | None = Field(default=None)
    model: str | None = Field(default=None, description="Allowlisted Gemini 4 model (default: gemini-4-hydrogen)")


class UnifiedWorkbenchState:
    """Isolated runtime state container (cleanly injectable for tests & multi-app instances)."""

    def __init__(
        self,
        *,
        repo: SpannerGraphRepository | None = None,
        manifest_store: BundleManifestStore | None = None,
        job_dispatcher: PipelineJobDispatcher | None = None,
    ) -> None:
        self._repo = repo
        self.manifest_store = manifest_store or MANIFEST_STORE
        self.job_dispatcher = job_dispatcher or JOB_DISPATCHER
        self.session_service = InMemorySessionService()
        self.sessions_meta: dict[str, dict[str, Any]] = {}
        self.extract_jobs: dict[str, dict[str, Any]] = {}
        self.query_jobs: dict[str, dict[str, Any]] = {}
        self.hierarchy_cache = BoundedTTLCache(max_size=16, ttl_seconds=45.0)
        self.concept_cache = BoundedTTLCache(max_size=256, ttl_seconds=60.0)
        self.graph_cache = BoundedTTLCache(max_size=128, ttl_seconds=60.0)
        self.catalog_cache = BoundedTTLCache(max_size=4, ttl_seconds=60.0)
        self.jobs_rate_limiter = SlidingWindowRateLimiter(
            max_requests=int(os.getenv("RATE_LIMIT_JOBS_PER_MIN", "10")),
            window_seconds=60.0,
        )
        self.query_rate_limiter = SlidingWindowRateLimiter(
            max_requests=int(os.getenv("RATE_LIMIT_QUERY_PER_MIN", "60")),
            window_seconds=60.0,
        )
        self._last_invalidated_sync_id: str = ""

    def get_repo(self) -> SpannerGraphRepository:
        if self._repo is None:
            use_in_memory = os.environ.get("QUERY_WEB_USE_IN_MEMORY", "false").lower() in ("true", "1", "yes")
            self._repo = SpannerGraphRepository(use_in_memory=use_in_memory)
            set_active_spanner_repository(self._repo)
        return self._repo

    def invalidate_spanner_caches(self) -> None:
        self.hierarchy_cache.clear()
        self.concept_cache.clear()
        self.graph_cache.clear()
        self.catalog_cache.clear()


def _create_instrumented_query_agent(
    *,
    model_name: str,
    wrap_tool: Any,
) -> Agent:
    from google.adk.models.google_llm import Gemini

    retry_opts = types.HttpRetryOptions(
        attempts=5,
        initial_delay=2.0,
        exp_base=2.0,
        http_status_codes=[429, 500, 502, 503, 504],
    )
    use_vertex = (
        os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("true", "1")
        or os.getenv("GOOGLE_GENAI_USE_ENTERPRISE", "").lower() in ("true", "1")
    )
    gemini_loc = os.getenv("GEMINI_LOCATION", "global")
    llm_model = Gemini(
        model=model_name,
        retry_options=retry_opts,
        client_kwargs={"location": gemini_loc} if use_vertex else None,
    )
    return Agent(
        name="okf_spanner_query_agent_v2",
        model=llm_model,
        description="Unified OKF Spanner Graph-RAG & Data Lineage Query Agent (v2)",
        instruction=QUERY_ORCHESTRATOR_INSTRUCTIONS,
        tools=[
            wrap_tool(lookup_entity_and_parameters),
            wrap_tool(traverse_equipment_connectivity_graph),
            wrap_tool(trace_data_lineage_and_conflicts),
            wrap_tool(hybrid_search_okf_spanner),
            wrap_tool(read_full_okf_concept_from_spanner),
            wrap_tool(execute_multistage_risk_and_hazop_query),
            wrap_tool(sync_or_inspect_knowledge_catalog),
        ],
        before_agent_callback=query_agent_before_callback,
        before_model_callback=query_agent_before_model_callback,
        after_tool_callback=query_agent_after_tool_callback,
        after_model_callback=query_agent_after_model_callback,
    )


def create_unified_app(
    *,
    repo: SpannerGraphRepository | None = None,
    manifest_store: BundleManifestStore | None = None,
    job_dispatcher: PipelineJobDispatcher | None = None,
    iap_verifier: Any = None,
) -> FastAPI:
    """Create the unified FastAPI application for `okf-engineering-workbench`."""
    state = UnifiedWorkbenchState(
        repo=repo,
        manifest_store=manifest_store,
        job_dispatcher=job_dispatcher,
    )
    if repo is not None:
        set_active_spanner_repository(repo)

    app = FastAPI(
        title="OKF Engineering Knowledge Workbench v2",
        version="2.0.0",
        description=(
            "Unified Tabbed Workbench combining OKF Extractor Studio, Parameterized Cloud Run Pipeline Jobs, "
            "Selectable Gemini 4 Models, and High-Scale Cloud Spanner Graph-RAG & Lineage Retrieval."
        ),
    )
    app.state.workbench = state

    @app.middleware("http")
    async def security_and_cache_middleware(request: Request, call_next: Any) -> Any:
        path = request.url.path
        if path not in ("/healthz", "/api/healthz", "/favicon.ico") and not path.startswith("/static/"):
            try:
                principal = resolve_request_principal(request, verifier=iap_verifier)
                request.state.principal = principal
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        response = await call_next(request)
        if path in ("/", "/demo") or path.startswith("/static/") or path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="unified_static")

    # ==========================================================================
    # Shell, Health & Model Catalog
    # ==========================================================================

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    @app.get("/demo", response_class=HTMLResponse, include_in_schema=False)
    async def serve_unified_shell() -> HTMLResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Unified Workbench index.html not found.")
        return HTMLResponse(
            content=index_path.read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
        )

    @app.get("/favicon.ico", include_in_schema=False)
    async def serve_favicon() -> Response:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#38bdf8">'
            '<path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>'
        )
        return Response(content=svg, media_type="image/svg+xml")

    @app.get("/healthz", response_class=JSONResponse)
    @app.get("/api/healthz", response_class=JSONResponse)
    async def healthz() -> dict[str, Any]:
        cfg = get_extracter_config()
        repo_inst = state.get_repo()
        return {
            "status": "healthy",
            "service": os.getenv("UNIFIED_WEB_SERVICE_NAME", "okf-engineering-workbench"),
            "version": "2.0.0",
            "project_id": cfg.google_cloud_project,
            "region": cfg.google_cloud_location,
            "defaults": {
                "extractor": get_default_extracter_model(),
                "query": get_default_query_model(),
            },
            "spanner_instance": repo_inst.instance_id,
            "spanner_database": repo_inst.database_id,
            "spanner_embedding_mode": repo_inst.native_embedding_mode,
            "gcs_bucket": f"gs://{cfg.destination_gcs_bucket}",
            "pipeline_job_name": state.job_dispatcher._get_job_name(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/models", response_model=ModelCatalogResponse)
    async def get_model_catalog() -> ModelCatalogResponse:
        allowed_ids = set(get_allowed_gemini_models())
        models = [m for m in GEMINI_MODEL_CATALOG if m["id"] in allowed_ids]
        return ModelCatalogResponse(
            allowed_models=models,
            defaults={
                "extractor": get_default_extracter_model(),
                "query": get_default_query_model(),
            },
            location=os.getenv("GEMINI_LOCATION", "global"),
        )

    @app.get("/api/status", response_class=JSONResponse)
    @app.get("/api/demo/status", response_class=JSONResponse)
    async def get_unified_status(request: Request) -> dict[str, Any]:
        cfg = get_extracter_config()
        repo_inst = state.get_repo()
        manifest = await asyncio.to_thread(state.manifest_store.get_manifest, force_refresh=False)
        principal = getattr(request.state, "principal", None)
        return {
            "status": "online",
            "service": os.getenv("UNIFIED_WEB_SERVICE_NAME", "okf-engineering-workbench"),
            "version": "2.0.0",
            "project_id": cfg.google_cloud_project,
            "region": cfg.google_cloud_location,
            "gemini_location": cfg.gemini_location,
            "gemini_model": get_default_extracter_model(),
            "models": {
                "allowed": list(get_allowed_gemini_models()),
                "extractor_default": get_default_extracter_model(),
                "query_default": get_default_query_model(),
            },
            "cloud_run_posture": get_safe_cloud_run_posture("EXTRACTER_WEB"),
            "principal": principal.email if principal else "local-dev",
            "gcs_bucket": f"gs://{cfg.destination_gcs_bucket}",
            "gcs_raw_prefix": cfg.source_gcs_raw_prefix,
            "gcs_prefix": cfg.destination_gcs_prefix,
            "use_gcs_storage": cfg.use_gcs_storage,
            "sync_version": manifest.get("sync_version", ""),
            "raw_pdf_count": manifest.get("raw_pdf_count", 0),
            "raw_subfolders": manifest.get("raw_subfolders", {}),
            "okf_file_count": manifest.get("okf_file_count", 0),
            "okf_categories": manifest.get("okf_categories", {}),
            "conflict_count": manifest.get("conflict_count", 0),
            "spanner_instance": repo_inst.instance_id,
            "spanner_database": repo_inst.database_id,
            "spanner_graph": "OkfKnowledgeGraph",
            "spanner_embedding_mode": repo_inst.native_embedding_mode,
            "pipeline_job": {
                "job_name": state.job_dispatcher._get_job_name(),
                "backend": state.job_dispatcher._get_execution_backend(),
                "modes": ["extract", "sync", "extract_and_sync"],
            },
            "pre_built_prompts": PRE_BUILT_PROMPTS,
            "tool_registry": [{"name": k, "description": v} for k, v in TOOL_DESCRIPTIONS.items()],
        }

    # ==========================================================================
    # Tab 1: Extractor Studio (Paginated _manifest.json Explorer & Single Extract)
    # ==========================================================================

    @app.get("/api/files", response_class=JSONResponse)
    @app.get("/api/extractor/files", response_class=JSONResponse)
    async def get_paginated_files(
        kind: str = Query(default="all", pattern="^(all|raw|okf)$"),
        q: str = Query(default=""),
        subfolder: str = Query(default=""),
        category: str = Query(default=""),
        conflicts_only: bool = Query(default=False),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        since_version: str = Query(default=""),
        force_gcs: bool = Query(default=False),
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            state.manifest_store.query_paginated_files,
            kind=kind,
            q=q,
            subfolder=subfolder,
            category=category,
            conflicts_only=conflicts_only,
            limit=limit,
            offset=offset,
            since_version=since_version,
            force_gcs=force_gcs,
        )

    @app.get("/api/raw-pdf/{subfolder}/{filename:path}")
    @app.get("/api/demo/raw-pdf/{subfolder}/{filename:path}")
    async def stream_raw_document(subfolder: str, filename: str) -> FileResponse:
        if subfolder not in ALLOWED_RAW_SUBFOLDERS:
            raise HTTPException(status_code=400, detail="Invalid raw document subfolder.")
        if ".." in filename or filename.startswith("/") or "\\" in filename or "\x00" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename path.")
        if not is_supported_raw_file(filename):
            raise HTTPException(status_code=400, detail="Unsupported raw document format.")

        cfg = get_extracter_config()
        raw_dir = cfg.reference_raw_dir
        if not raw_dir.is_absolute():
            raw_dir = (REPO_ROOT / raw_dir).resolve()
        target = (raw_dir / subfolder / filename).resolve()
        if not target.is_relative_to(raw_dir.resolve()):
            raise HTTPException(status_code=400, detail="Invalid filename path.")

        if not target.is_file() and cfg.use_gcs_storage:
            downloaded = await asyncio.to_thread(
                _download_pdf_from_gcs, pdf_filename=filename, subfolder=subfolder
            )
            downloaded_path = downloaded[0] if isinstance(downloaded, tuple) else downloaded
            if downloaded_path and downloaded_path.is_file():
                target = downloaded_path

        if not target.is_file() or not is_supported_raw_file(target):
            raise HTTPException(status_code=404, detail="Raw document not found.")

        return FileResponse(
            path=str(target),
            media_type=get_raw_mime_type(target),
            headers={"Content-Disposition": f'inline; filename="{target.name}"'},
        )

    @app.get("/api/okf/{concept_id:path}", response_class=JSONResponse)
    @app.get("/api/extractor/okf/{concept_id:path}", response_class=JSONResponse)
    async def get_okf_concept(concept_id: str) -> dict[str, Any]:
        if ".." in concept_id or concept_id.startswith("/") or "\\" in concept_id:
            raise HTTPException(status_code=400, detail="Invalid concept_id.")
        bundle_dir = ensure_bundle_seeded()
        clean_id = concept_id.removesuffix(".md")
        target_md = (bundle_dir / f"{clean_id}.md").resolve()
        if not target_md.is_relative_to(bundle_dir.resolve()) or not target_md.is_file():
            raise HTTPException(status_code=404, detail=f"OKF concept '{clean_id}' not found.")

        raw_md = target_md.read_text(encoding="utf-8", errors="replace")
        insp = await asyncio.to_thread(
            inspect_existing_okf_concept_tool,
            concept_id=clean_id,
            output_bundle_dir=str(bundle_dir),
        )
        manifest = await asyncio.to_thread(state.manifest_store.get_manifest, force_refresh=False)
        raw_pdfs = list(manifest.get("raw_pdfs") or [])
        sources = insp.get("sources", [])
        resolved_pdfs = resolve_pdf_source_links(sources, raw_pdfs)
        conflict_lines = [
            line.strip()
            for line in raw_md.splitlines()
            if "CONFLICT" in line and not line.strip().startswith("#")
        ]
        wikilinks = sorted(set(re.findall(r"\[\[([^\[\]|]+)(?:\|[^\[\]]+)?\]\]", raw_md)))
        return {
            "status": "success",
            "concept_id": clean_id,
            "frontmatter": insp.get("frontmatter", {}),
            "sources": sources,
            "resolved_pdf_sources": resolved_pdfs,
            "headings": insp.get("headings", []),
            "wikilinks": wikilinks,
            "has_conflict": len(conflict_lines) > 0,
            "conflict_lines": conflict_lines,
            "body_markdown": insp.get("body_markdown", raw_md),
            "raw_markdown": raw_md,
            "size_bytes": len(raw_md.encode("utf-8")),
        }

    def _run_interactive_extract_sync(
        req: UnifiedExtractRequest,
        resolved_model: str,
        effective_prompt: str,
        job_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        t0 = time.monotonic()
        bundle_dir = ensure_bundle_seeded()
        tool_calls: list[dict[str, str]] = [
            {
                "step": "STEP 0 // GUARDRAIL",
                "tool": "before_agent_callback",
                "detail": f"Verified clean by pre-flight guardrail (model={resolved_model})",
            }
        ]
        before_hashes = {f["concept_id"]: f["content_hash"] for f in list_all_okf_files(bundle_dir)}

        def _record(step_dict: dict[str, str]) -> None:
            tool_calls.append(step_dict)
            if job_state is not None:
                job_state["tool_calls"] = list(tool_calls)
                job_state["current_step"] = f"{step_dict['step']} ({step_dict['tool']})"
                job_state["duration_ms"] = int((time.monotonic() - t0) * 1000)

        pdf_sub = req.subfolder if req.subfolder in ALLOWED_RAW_SUBFOLDERS else "data_sheets"
        pdf_name = req.pdf_filename.strip()
        if req.target_pdf:
            clean_pdf = req.target_pdf.replace("reference/raw/", "").strip("/")
            if "/" in clean_pdf:
                sub_p, name_p = clean_pdf.split("/", 1)
                if sub_p in ALLOWED_RAW_SUBFOLDERS:
                    pdf_sub, pdf_name = sub_p, name_p
            else:
                pdf_name = clean_pdf

        llm_summary: str | None = None
        if req.invoke_vertex_llm:
            prev_out = os.environ.get("OUTPUT_BUNDLE_DIR")
            os.environ["OUTPUT_BUNDLE_DIR"] = str(bundle_dir)
            try:
                if req.mode == "chat" and not req.target_pdf and not req.target_equipment:
                    intent_res = CognitiveClassifier(model_name=resolved_model).classify_intent(effective_prompt)
                    _record(
                        {
                            "step": "STEP 1 // COGNITIVE INTENT",
                            "tool": "CognitiveClassifier",
                            "detail": f"Intent={intent_res.intent.value} ({resolved_model})",
                        }
                    )

                async def _run_adk() -> str:
                    runner = InMemoryRunner(
                        agent=create_extracter_agent(model_name=resolved_model),
                        app_name="extracter_agent_v2",
                    )
                    sess = await runner.session_service.create_session(
                        app_name="extracter_agent_v2", user_id="workbench_user"
                    )
                    msg = types.Content(role="user", parts=[types.Part.from_text(text=effective_prompt)])
                    texts: list[str] = []
                    async for ev in runner.run_async(
                        user_id="workbench_user", session_id=sess.id, new_message=msg
                    ):
                        if ev.content and ev.content.parts:
                            for part in ev.content.parts:
                                if getattr(part, "function_call", None):
                                    fc = part.function_call
                                    _record(
                                        {
                                            "step": f"ADK TOOL // {fc.name}",
                                            "tool": fc.name,
                                            "detail": f"Executed {fc.name}({dict(fc.args or {})})",
                                        }
                                    )
                                if part.text:
                                    texts.append(part.text)
                    return "\n".join(texts).strip()

                llm_summary = asyncio.run(_run_adk())
            finally:
                if prev_out is None:
                    os.environ.pop("OUTPUT_BUNDLE_DIR", None)
                else:
                    os.environ["OUTPUT_BUNDLE_DIR"] = prev_out
        else:
            if pdf_name:
                parsed = process_raw_pdf_tool(
                    pdf_filename=pdf_name,
                    subfolder=pdf_sub,
                    max_pages=3,
                    enable_multimodal=False,
                )
                _record(
                    {
                        "step": "STEP 1 // PARSER",
                        "tool": "process_raw_pdf_tool",
                        "detail": f"Parsed {pdf_sub}/{pdf_name} (tags={len(parsed.get('tag_candidates', []))})",
                    }
                )
            else:
                disc = find_raw_documents_tool(query=req.target_equipment or req.concept_id or "document")
                _record(
                    {
                        "step": "STEP 1 // DISCOVERY",
                        "tool": "find_raw_documents_tool",
                        "detail": f"Matched {disc.get('match_count', 0)} raw document(s)",
                    }
                )

        # Rebuild fast manifest after write/extraction
        manifest = state.manifest_store.rebuild_manifest(force_gcs=False, persist_to_gcs=False)
        after_files = manifest.get("okf_files", [])
        touched = [
            f["concept_id"]
            for f in after_files
            if before_hashes.get(f["concept_id"]) != f["content_hash"]
        ]
        primary_concept = touched[0] if touched else (req.concept_id or None)
        reply_md = llm_summary or (
            f"### Extractor Workbench Run Complete (`{resolved_model}`)\n\n"
            f"- **Target:** `{pdf_sub}/{pdf_name}`" if pdf_name else f"### Extractor Audit Complete (`{resolved_model}`)\n"
        )
        if not llm_summary:
            reply_md += (
                f"\n- **Bundle Concepts:** `{manifest.get('okf_file_count', 0)}` "
                f"(`sync_version: {manifest.get('sync_version')}`)\n"
                f"- **Tip:** Use **Run Batch Pipeline** or **Sync to Spanner** in the top bar for timeout-free Cloud Run Job execution."
            )

        return {
            "status": "success",
            "verdict": "PASS",
            "mode": req.mode,
            "model": resolved_model,
            "concept_id": primary_concept,
            "touched_concepts": touched,
            "sync_version": manifest.get("sync_version", ""),
            "tool_calls": tool_calls,
            "reply_markdown": reply_md,
            "duration_ms": int((time.monotonic() - t0) * 1000),
        }

    @app.post("/api/chat/extract", response_class=JSONResponse)
    @app.post("/api/extractor/chat", response_class=JSONResponse)
    async def extractor_chat_endpoint(req: UnifiedExtractRequest) -> dict[str, Any]:
        try:
            resolved_model = validate_gemini_model(req.model, default=get_default_extracter_model())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        effective_prompt = req.prompt.strip()
        if not effective_prompt:
            if req.target_pdf:
                effective_prompt = f"Extract engineering facts from '{req.target_pdf}' into OKF v0.2 Markdown."
            elif req.target_equipment:
                effective_prompt = f"Extract all specifications for equipment '{req.target_equipment}'."
            else:
                effective_prompt = "Audit current OKF bundle status and recent extraction log."

        try:
            before_agent_callback(effective_prompt)
        except SecurityGuardrailError as exc:
            return {"status": "blocked", "verdict": "BLOCKED_BY_MODEL_ARMOR", "error": str(exc)}

        if req.async_job:
            job_id = f"ejob-{uuid.uuid4().hex[:10]}"
            job_state: dict[str, Any] = {
                "job_id": job_id,
                "status": "running",
                "verdict": "IN_PROGRESS",
                "model": resolved_model,
                "current_step": f"Running extraction ({resolved_model})...",
                "tool_calls": [],
                "duration_ms": 0,
            }
            state.extract_jobs[job_id] = job_state

            def _bg() -> None:
                try:
                    res = _run_interactive_extract_sync(req, resolved_model, effective_prompt, job_state)
                    job_state.update(res)
                    job_state["status"] = "completed"
                except Exception as exc:
                    job_state["status"] = "error"
                    job_state["error"] = str(exc)

            threading.Thread(target=_bg, daemon=True).start()
            return job_state

        return await asyncio.to_thread(
            _run_interactive_extract_sync, req, resolved_model, effective_prompt, None
        )

    @app.get("/api/chat/jobs/{job_id}", response_class=JSONResponse)
    async def get_extract_job(job_id: str) -> dict[str, Any]:
        job = state.extract_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Extraction job '{job_id}' not found.")
        return job

    # ==========================================================================
    # Parameterized Cloud Run Pipeline Jobs (`okf-pipeline-job`)
    # ==========================================================================

    @app.post("/api/jobs/run", status_code=202, response_class=JSONResponse)
    async def trigger_pipeline_job(
        req: PipelineJobRequest,
        request: Request,
        x_confirm_purge: str | None = Header(default=None, alias=PURGE_CONFIRM_HEADER),
        x_idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    ) -> JSONResponse:
        principal = getattr(request.state, "principal", None)
        principal_email = principal.email if principal else "local-dev@workbench.local"
        state.jobs_rate_limiter.check(principal_email)

        # Deterministic SAIF RAC HITL Gate for destructive purge
        enforce_purge_hitl_gate(
            purge=req.purge,
            confirm_header=x_confirm_purge,
            idempotency_key=x_idempotency_key,
        )

        try:
            record, is_duplicate = await asyncio.to_thread(
                state.job_dispatcher.submit_job,
                req,
                triggered_by=principal_email,
                idempotency_key=x_idempotency_key,
            )
        except UpstreamJobServiceError as exc:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "UPSTREAM_UNAVAILABLE_DEGRADED",
                    "component": "cloud_run_jobs_v2",
                    "retryable": True,
                    "detail": str(exc),
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        payload = record.model_dump()
        payload["idempotent_replay"] = is_duplicate
        return JSONResponse(status_code=200 if is_duplicate else 202, content=payload)

    @app.get("/api/jobs", response_class=JSONResponse)
    async def list_pipeline_jobs(limit: int = Query(default=20, ge=1, le=50)) -> dict[str, Any]:
        jobs = await asyncio.to_thread(state.job_dispatcher.list_jobs, limit)
        for j in jobs:
            if j.status == "SUCCEEDED" and j.job_mode in ("sync", "extract_and_sync"):
                if state._last_invalidated_sync_id != j.execution_id:
                    state.invalidate_spanner_caches()
                    state.manifest_store.invalidate()
                    state._last_invalidated_sync_id = j.execution_id
                break
        return {
            "status": "success",
            "jobs": [j.model_dump() for j in jobs],
        }

    @app.get("/api/jobs/{execution_id}", response_class=JSONResponse)
    async def get_pipeline_job(execution_id: str) -> dict[str, Any]:
        job = await asyncio.to_thread(state.job_dispatcher.get_job, execution_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Pipeline job '{execution_id}' not found.")
        if job.status == "SUCCEEDED" and state._last_invalidated_sync_id != job.execution_id:
            if job.job_mode in ("sync", "extract_and_sync"):
                state.invalidate_spanner_caches()
            state.manifest_store.invalidate()
            state._last_invalidated_sync_id = job.execution_id
        return job.model_dump()

    # ==========================================================================
    # Tab 2: Knowledge Graph & Query Workbench (Lazy Spanner + Parallel RPCs + SSE)
    # ==========================================================================

    @app.get("/api/spanner/hierarchy/summary", response_class=JSONResponse)
    async def api_spanner_hierarchy_summary(refresh: bool = Query(default=False)) -> dict[str, Any]:
        t0 = time.perf_counter()
        if not refresh:
            cached = state.hierarchy_cache.get("summary")
            if cached is not None:
                out = dict(cached)
                out["cached"] = True
                out["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                return out

        repo_inst = state.get_repo()
        data = await asyncio.to_thread(repo_inst.get_equipment_hierarchy_summary)
        data["cached"] = False
        data["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        state.hierarchy_cache.set("summary", data)
        return data

    @app.get("/api/spanner/hierarchy/items", response_class=JSONResponse)
    async def api_spanner_hierarchy_items(
        unit: str | None = Query(default=None),
        class_name: str | None = Query(default=None),
        category: str | None = Query(default=None),
        q: str | None = Query(default=None),
        conflicts_only: bool = Query(default=False),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        repo_inst = state.get_repo()
        data = await asyncio.to_thread(
            repo_inst.get_equipment_hierarchy_items,
            unit=unit,
            class_name=class_name,
            category=category,
            q=q,
            conflicts_only=conflicts_only,
            limit=limit,
            offset=offset,
        )
        data["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return data

    @app.get("/api/spanner/hierarchy", response_class=JSONResponse)
    async def api_spanner_hierarchy_compat(refresh: bool = Query(default=False)) -> dict[str, Any]:
        t0 = time.perf_counter()
        if not refresh:
            cached = state.hierarchy_cache.get("full")
            if cached is not None:
                out = dict(cached)
                out["cached"] = True
                out["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                return out
        repo_inst = state.get_repo()
        data = await asyncio.to_thread(repo_inst.get_equipment_hierarchy)
        data["cached"] = False
        data["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        state.hierarchy_cache.set("full", data)
        return data

    @app.get("/api/spanner/graph", response_class=JSONResponse)
    async def api_spanner_graph(
        center_tag: str = Query(default="D-2304", min_length=1),
        max_hops: int = Query(default=2, ge=1, le=3),
        include_lineage: bool = Query(default=True),
        max_nodes: int = Query(default=120, ge=10, le=300),
        refresh: bool = Query(default=False),
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        cache_key = (center_tag.strip(), max_hops, include_lineage, max_nodes)
        if not refresh:
            cached = state.graph_cache.get(cache_key)
            if cached is not None:
                out = dict(cached)
                out["cached"] = True
                out["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                return out

        repo_inst = state.get_repo()
        graph_data = await asyncio.to_thread(
            repo_inst.get_interactive_graph,
            center_tag=center_tag,
            max_hops=max_hops,
            include_lineage=include_lineage,
        )
        # Bound graph node/edge count for responsive browser rendering at scale
        nodes = list(graph_data.get("nodes") or [])
        edges = list(graph_data.get("edges") or [])
        truncated = False
        if len(nodes) > max_nodes:
            nodes.sort(key=lambda n: (int(n.get("hop_distance", 99)), str(n.get("id", ""))))
            kept = nodes[:max_nodes]
            kept_ids = {n["id"] for n in kept}
            edges = [e for e in edges if e.get("source") in kept_ids and e.get("target") in kept_ids]
            graph_data["nodes"] = kept
            graph_data["edges"] = edges
            truncated = True
        graph_data["truncated"] = truncated
        graph_data["max_nodes"] = max_nodes
        graph_data["cached"] = False
        graph_data["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        state.graph_cache.set(cache_key, graph_data)
        return graph_data

    @app.get("/api/spanner/concept/{concept_id:path}", response_class=JSONResponse)
    async def api_spanner_concept(concept_id: str, refresh: bool = Query(default=False)) -> dict[str, Any]:
        t0 = time.perf_counter()
        cache_key = concept_id.strip()
        if not refresh:
            cached = state.concept_cache.get(cache_key)
            if cached is not None:
                out = dict(cached)
                out["cached"] = True
                out["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                return out

        repo_inst = state.get_repo()
        doc = await asyncio.to_thread(repo_inst.read_full_concept, concept_id_or_tag=concept_id)
        if not doc or doc.get("found") is False:
            raise HTTPException(status_code=404, detail=f"Concept '{concept_id}' not found in Spanner.")

        resolved_cid = str(doc.get("concept_id") or concept_id)
        is_non_eq = (
            "/" in resolved_cid and not resolved_cid.lower().startswith("equipment/")
        ) or resolved_cid.lower() in ("overview", "project")
        target_tag = (
            resolved_cid.split("/", 1)[-1]
            if resolved_cid.lower().startswith("equipment/")
            else str(doc.get("canonical_tag") or resolved_cid)
        )

        if is_non_eq:
            parameters_list: list[dict[str, Any]] = []
            entities_list: list[dict[str, Any]] = []
            lineage_list: list[dict[str, Any]] = []
        else:
            # Parallel Spanner RPC execution via asyncio.gather (eliminates sequential RTT waterfall)
            lookup_res, lineage = await asyncio.gather(
                asyncio.to_thread(repo_inst.lookup_entity_and_parameters, entity_tag_or_id=target_tag),
                asyncio.to_thread(
                    repo_inst.trace_lineage_gql,
                    target_id=target_tag,
                    direction="BACKWARD_TO_PDF",
                    conflicts_only=False,
                ),
            )
            parameters_list = lookup_res.get("parameters", [])[:50]
            entities_list = lookup_res.get("entities", [])[:10]
            lineage_list = [t.model_dump() for t in lineage[:25]]

        catalog_dossier = repo_inst.build_catalog_dossier(
            concept_doc=doc,
            lineage_traces=lineage_list,
            parameters=parameters_list,
            fallback_tag=target_tag,
            fallback_unit=str(doc.get("unit") or ""),
        )
        payload = {
            "status": "OK",
            "cached": False,
            "execution_time_ms": round((time.perf_counter() - t0) * 1000, 2),
            "concept": doc,
            "entities": entities_list,
            "parameters": parameters_list,
            "lineage_traces": lineage_list,
            "catalog_dossier": catalog_dossier,
        }
        state.concept_cache.set(cache_key, payload)
        return payload

    @app.get("/api/catalog", response_class=JSONResponse)
    async def api_catalog_inspect(refresh: bool = Query(default=False)) -> dict[str, Any]:
        t0 = time.perf_counter()
        if not refresh:
            cached = state.catalog_cache.get("catalog")
            if cached is not None:
                out = dict(cached)
                out["cached"] = True
                out["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
                return out
        repo_inst = state.get_repo()
        data = await asyncio.to_thread(_fetch_catalog_payload, repo_inst, False)
        data["cached"] = False
        data["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        state.catalog_cache.set("catalog", data)
        return data

    @app.post("/api/catalog/sync", response_class=JSONResponse)
    async def api_catalog_sync() -> dict[str, Any]:
        t0 = time.perf_counter()
        repo_inst = state.get_repo()
        data = await asyncio.to_thread(_fetch_catalog_payload, repo_inst, True)
        data["cached"] = False
        data["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        state.catalog_cache.set("catalog", data)
        return data

    async def _get_or_create_query_session(
        session_id: str | None = None,
        *,
        force_new: bool = False,
    ) -> dict[str, Any]:
        clean_id = (session_id or "").strip()
        if not force_new and clean_id and clean_id in state.sessions_meta:
            existing = await state.session_service.get_session(
                app_name="okf_unified_query",
                user_id="workbench_user",
                session_id=clean_id,
            )
            if existing is None:
                await state.session_service.create_session(
                    app_name="okf_unified_query",
                    user_id="workbench_user",
                    session_id=clean_id,
                )
            return state.sessions_meta[clean_id]

        target_id = clean_id if (clean_id and not force_new) else f"qsess-{uuid.uuid4().hex[:10]}"
        adk_sess = await state.session_service.create_session(
            app_name="okf_unified_query",
            user_id="workbench_user",
            session_id=target_id,
        )
        meta: dict[str, Any] = {
            "session_id": adk_sess.id,
            "user_id": "workbench_user",
            "turn_count": 0,
            "history": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        state.sessions_meta[adk_sess.id] = meta
        return meta

    async def _execute_query_turn(
        *,
        job: dict[str, Any],
        session_id: str,
        question: str,
        focus_tag: str | None,
        category: str | None,
        model_name: str,
        event_queue: asyncio.Queue[dict[str, Any] | None] | None = None,
    ) -> None:
        sess_meta = state.sessions_meta.get(session_id) or await _get_or_create_query_session(session_id)
        t_start = time.perf_counter()
        t_cursor = t_start

        def _emit(ev_type: str, data: dict[str, Any]) -> None:
            if event_queue is not None:
                event_queue.put_nowait({"event": ev_type, "data": data})

        try:
            raw_focus = focus_tag if isinstance(focus_tag, str) else ""
            has_ctrl = any(ch in raw_focus for ch in ("\r", "\n", "\x00"))
            clean_focus = raw_focus.strip() or None
            focus_ok = not has_ctrl and (clean_focus is None or bool(_FOCUS_TAG_SAFE_RE.match(clean_focus)))
            effective_focus = clean_focus if focus_ok else None
            prompt_ctx = (
                f"[Active Equipment/Concept Selection in Workbench: {effective_focus}]\n{question}"
                if effective_focus
                else question
            )
            sec = check_query_prompt_security(f"{raw_focus}\n{category or ''}\n{prompt_ctx}")
            blocked = sec.get("filterMatchState") == "MATCH_FOUND" or not focus_ok
            threat_cat = (
                sec.get("violation_type") or "POLICY_VIOLATION"
                if sec.get("filterMatchState") == "MATCH_FOUND"
                else "INVALID_FOCUS_TAG"
            )
            reason = (
                sec.get("matched_pattern") or "Adversarial directive detected"
                if sec.get("filterMatchState") == "MATCH_FOUND"
                else "focus_tag contains disallowed syntax"
            )

            t_now = time.perf_counter()
            step0 = {
                "step_index": 0,
                "phase": "STEP 0 // GUARDRAIL",
                "title": "Model Armor & Prompt Injection Inspection",
                "status": "BLOCKED" if blocked else "COMPLETED",
                "duration_ms": round((t_now - t_cursor) * 1000, 1),
                "detail": f"Blocked ({threat_cat}): {reason}" if blocked else "Input verified clean.",
            }
            t_cursor = t_now
            job["steps"].append(step0)
            _emit("step", step0)

            if blocked:
                t_end = time.perf_counter()
                s_sum, tot = compute_telemetry_totals(job["steps"], t_end - t_start)
                job.update(
                    {
                        "status": "COMPLETED",
                        "blocked_by_guardrail": True,
                        "answer_markdown": (
                            f"### Security Guardrail Intervention\n\n"
                            f"Request blocked by pre-flight guardrail (`{threat_cat}`): {reason}"
                        ),
                        "steps_sum_ms": s_sum,
                        "total_duration_ms": tot,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                _emit("done", job)
                return

            if os.environ.get("QUERY_WEB_TEST_FAST_AGENT", "false").lower() in ("true", "1"):
                target_tag = effective_focus or "D-2304"
                raw_lookup = lookup_entity_and_parameters(target_tag)
                t_tool = time.perf_counter()
                summary = _summarize_tool_output("lookup_entity_and_parameters", raw_lookup)
                tc = {
                    "call_index": 1,
                    "tool_name": "lookup_entity_and_parameters",
                    "description": TOOL_DESCRIPTIONS["lookup_entity_and_parameters"],
                    "args": {"entity_tag_or_id": target_tag},
                    "status": "COMPLETED",
                    "duration_ms": round((t_tool - t_cursor) * 1000, 1),
                    "summary": summary["summary"],
                    "metrics": summary["metrics"],
                }
                job["tool_calls"].append(tc)
                _emit("tool_call", tc)
                st1 = {
                    "step_index": 1,
                    "phase": "STEP 1 // ADK TOOL CALL #1",
                    "title": f"lookup_entity_and_parameters ({model_name})",
                    "status": "COMPLETED",
                    "duration_ms": tc["duration_ms"],
                    "detail": summary["summary"],
                }
                job["steps"].append(st1)
                _emit("step", st1)

                answer_md = (
                    f"### Grounded Spanner Retrieval (`{target_tag}` · `{model_name}`)\n\n"
                    f"- **Summary:** {summary['summary']}\n"
                    f"- **Model:** `{model_name}`"
                )
                _emit("token", {"text": answer_md})
                t_end = time.perf_counter()
                s_sum, tot = compute_telemetry_totals(job["steps"], t_end - t_start)
                job.update(
                    {
                        "status": "COMPLETED",
                        "answer_markdown": answer_md,
                        "referenced_tags": [target_tag],
                        "steps_sum_ms": s_sum,
                        "total_duration_ms": tot,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                sess_meta.setdefault("history", []).append(
                    {"turn": job.get("turn_count", 1), "question": question, "model": model_name}
                )
                _emit("done", job)
                return

            tool_counter = 0

            def _wrap_tool(fn: Any) -> Any:
                import functools

                tname = fn.__name__

                @functools.wraps(fn)
                def _wrapped(*args: Any, **kwargs: Any) -> Any:
                    nonlocal tool_counter, t_cursor
                    tool_counter += 1
                    idx = tool_counter
                    t_ts = time.perf_counter()
                    tc = {
                        "call_index": idx,
                        "tool_name": tname,
                        "description": TOOL_DESCRIPTIONS.get(tname, tname),
                        "args": kwargs or {"args": list(args)},
                        "status": "RUNNING",
                        "duration_ms": None,
                        "summary": f"Running {tname} against Cloud Spanner...",
                        "metrics": {},
                    }
                    job["tool_calls"].append(tc)
                    _emit("tool_call", tc)
                    try:
                        res = fn(*args, **kwargs)
                        t_te = time.perf_counter()
                        dur = round((t_te - t_ts) * 1000, 1)
                        t_cursor = t_te
                        sinfo = _summarize_tool_output(tname, res)
                        tc.update({"status": "COMPLETED", "duration_ms": dur, **sinfo})
                        st_rec = {
                            "step_index": len(job["steps"]),
                            "phase": f"STEP {len(job['steps'])} // ADK TOOL #{idx}",
                            "title": tname,
                            "status": "COMPLETED",
                            "duration_ms": dur,
                            "detail": sinfo["summary"],
                        }
                        job["steps"].append(st_rec)
                        _emit("tool_call", tc)
                        _emit("step", st_rec)
                        return res
                    except Exception as exc:
                        t_te = time.perf_counter()
                        tc.update(
                            {
                                "status": "ERROR",
                                "duration_ms": round((t_te - t_ts) * 1000, 1),
                                "summary": f"Error: {exc}",
                            }
                        )
                        _emit("tool_call", tc)
                        raise

                return _wrapped

            agent = _create_instrumented_query_agent(model_name=model_name, wrap_tool=_wrap_tool)
            runner = Runner(
                agent=agent,
                app_name="okf_unified_query",
                session_service=state.session_service,
            )
            await _get_or_create_query_session(session_id, force_new=False)
            content = types.Content(role="user", parts=[types.Part.from_text(text=prompt_ctx)])
            parts_out: list[str] = []
            async for event in runner.run_async(
                user_id="workbench_user",
                session_id=session_id,
                new_message=content,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if getattr(part, "text", None):
                            parts_out.append(part.text)
                            _emit("token", {"text": part.text})

            answer_md = "\n".join(parts_out).strip() or "No response text generated."
            t_end = time.perf_counter()
            synth_step = {
                "step_index": len(job["steps"]),
                "phase": "FINAL // SYNTHESIS",
                "title": f"Grounded Answer ({model_name})",
                "status": "COMPLETED",
                "duration_ms": round(max(0.0, (t_end - t_cursor) * 1000), 1),
                "detail": f"Synthesized {len(answer_md)} chars across {len(job['tool_calls'])} Spanner tool call(s).",
            }
            job["steps"].append(synth_step)
            _emit("step", synth_step)
            ref_tags = _extract_referenced_tags(answer_md)
            if effective_focus and effective_focus not in ref_tags:
                ref_tags.insert(0, effective_focus)
            s_sum, tot = compute_telemetry_totals(job["steps"], t_end - t_start)
            job.update(
                {
                    "status": "COMPLETED",
                    "answer_markdown": answer_md,
                    "referenced_tags": ref_tags,
                    "steps_sum_ms": s_sum,
                    "total_duration_ms": tot,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            sess_meta.setdefault("history", []).append(
                {"turn": job.get("turn_count", 1), "question": question, "model": model_name}
            )
            _emit("done", job)
        except QuerySecurityGuardrailError as exc:
            t_end = time.perf_counter()
            s_sum, tot = compute_telemetry_totals(job["steps"], t_end - t_start)
            job.update(
                {
                    "status": "COMPLETED",
                    "blocked_by_guardrail": True,
                    "answer_markdown": f"### Security Guardrail Intervention\n\n- **Reason:** {exc}",
                    "steps_sum_ms": s_sum,
                    "total_duration_ms": tot,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _emit("done", job)
        except Exception as exc:
            logger.exception("Unified query job %s failed", job["job_id"])
            t_end = time.perf_counter()
            s_sum, tot = compute_telemetry_totals(job["steps"], t_end - t_start)
            job.update(
                {
                    "status": "ERROR",
                    "error": "Query execution failed due to an upstream error.",
                    "steps_sum_ms": s_sum,
                    "total_duration_ms": tot,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            _emit("error", {"error": job["error"], "job_id": job["job_id"]})
        finally:
            if event_queue is not None:
                event_queue.put_nowait(None)

    @app.post("/api/query/session/new", response_class=JSONResponse)
    async def api_query_session_new() -> dict[str, Any]:
        meta = await _get_or_create_query_session(force_new=True)
        return {
            "session_id": meta["session_id"],
            "user_id": meta["user_id"],
            "turn_count": meta["turn_count"],
            "created_at": meta["created_at"],
        }

    @app.get("/api/query/session/{session_id}", response_class=JSONResponse)
    async def api_query_session_inspect(session_id: str) -> dict[str, Any]:
        meta = state.sessions_meta.get(session_id)
        if not meta:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
        return meta

    def _init_query_job(req: UnifiedQueryChatRequest, sess_meta: dict[str, Any], resolved_model: str) -> dict[str, Any]:
        sess_meta["turn_count"] = int(sess_meta.get("turn_count") or 0) + 1
        job_id = f"qjob-{uuid.uuid4().hex[:12]}"
        job: dict[str, Any] = {
            "job_id": job_id,
            "session_id": sess_meta["session_id"],
            "turn_count": sess_meta["turn_count"],
            "question": req.question.strip(),
            "focus_tag": req.focus_tag,
            "category": req.category,
            "model": resolved_model,
            "status": "RUNNING",
            "blocked_by_guardrail": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "steps_sum_ms": None,
            "total_duration_ms": None,
            "steps": [],
            "tool_calls": [],
            "answer_markdown": None,
            "referenced_tags": [req.focus_tag] if req.focus_tag else [],
            "error": None,
        }
        state.query_jobs[job_id] = job
        return job

    @app.post("/api/query/chat", response_class=JSONResponse)
    async def api_query_chat(req: UnifiedQueryChatRequest, request: Request) -> dict[str, Any]:
        principal = getattr(request.state, "principal", None)
        state.query_rate_limiter.check(principal.email if principal else "local-dev")
        try:
            resolved_model = validate_gemini_model(req.model, default=get_default_query_model())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        question = req.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="Question must not be empty.")

        sess_meta = await _get_or_create_query_session(req.session_id, force_new=False)
        job = _init_query_job(req, sess_meta, resolved_model)
        asyncio.create_task(
            _execute_query_turn(
                job=job,
                session_id=sess_meta["session_id"],
                question=question,
                focus_tag=req.focus_tag,
                category=req.category,
                model_name=resolved_model,
                event_queue=None,
            )
        )
        return {
            "job_id": job["job_id"],
            "session_id": job["session_id"],
            "turn_count": job["turn_count"],
            "status": "RUNNING",
            "question": question,
            "focus_tag": req.focus_tag,
            "model": resolved_model,
        }

    @app.post("/api/query/chat/stream")
    async def api_query_chat_stream(req: UnifiedQueryChatRequest, request: Request) -> StreamingResponse:
        principal = getattr(request.state, "principal", None)
        state.query_rate_limiter.check(principal.email if principal else "local-dev")
        try:
            resolved_model = validate_gemini_model(req.model, default=get_default_query_model())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        question = req.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="Question must not be empty.")

        sess_meta = await _get_or_create_query_session(req.session_id, force_new=False)
        job = _init_query_job(req, sess_meta, resolved_model)
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        asyncio.create_task(
            _execute_query_turn(
                job=job,
                session_id=sess_meta["session_id"],
                question=question,
                focus_tag=req.focus_tag,
                category=req.category,
                model_name=resolved_model,
                event_queue=queue,
            )
        )

        async def _sse_generator() -> AsyncIterator[str]:
            init_payload = {
                "job_id": job["job_id"],
                "session_id": job["session_id"],
                "model": resolved_model,
                "turn_count": job["turn_count"],
            }
            yield f"event: start\ndata: {json.dumps(init_payload)}\n\n"
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"event: {item['event']}\ndata: {json.dumps(item['data'], ensure_ascii=False)}\n\n"

        return StreamingResponse(
            _sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.get("/api/query/jobs/{job_id}", response_class=JSONResponse)
    async def api_query_job_status(job_id: str) -> dict[str, Any]:
        job = state.query_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Query job '{job_id}' not found.")
        return job

    return app


app = create_unified_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("unified_web.server:app", host="0.0.0.0", port=port, reload=False)
