"""FastAPI Web Server for the OKF Spanner Graph & Knowledge Retrieval Workbench UI.

Deployed as a dedicated Cloud Run service (`okf-query-agent-web`) providing:
- Left Pane API: Live Spanner Equipment Hierarchy Tree (`Unit -> Class -> Tag`) + OKF Concept Categories
- Middle Pane API: Conversational ADK Query Agent with Pre-Built Prompts & Live Per-Step / Per-Tool Latency Telemetry
- Right Pane API: Interactive Spanner Property Graph (`OkfKnowledgeGraph`) + Live Google Cloud Dataplex Universal Catalog (`dataplex_v1`)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from query_agent.guardrails import check_query_prompt_security
from query_agent.orchestrator import QUERY_ORCHESTRATOR_INSTRUCTIONS
from query_agent.spanner.catalog_sync import DataplexCatalogAndLineageSync
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

load_dotenv()

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Pre-built engineering prompt templates for the Middle Pane
PRE_BUILT_PROMPTS: list[dict[str, Any]] = [
    {
        "id": "hazop_d2304",
        "title": "5-Stage HAZOP & Risk Study (D-2304)",
        "badge": "HAZOP // 5-STAGE",
        "category": "G_MULTISTAGE_HAZOP_AND_RISK_ASSESSMENT",
        "focus_tag": "D-2304",
        "question": (
            "Perform a comprehensive 5-stage HAZOP and risk assessment for Debutanizer Reflux Drum D-2304 "
            "under blocked vapor outlet and fire exposure scenarios: determine the risk tier, cause-to-consequence "
            "chain, connected relief valves and trip instruments, plant-wide blast radius across Unit 23, "
            "and verify if any governing design parameters have cross-document conflicts."
        ),
    },
    {
        "id": "risk_c2301",
        "title": "Column Overpressure Risk Assessment (C-2301)",
        "badge": "RISK // TIER AUDIT",
        "category": "G_MULTISTAGE_HAZOP_AND_RISK_ASSESSMENT",
        "focus_tag": "C-2301",
        "question": (
            "Execute a multi-stage risk assessment on Debutanizer Column C-2301 and its overhead condenser E-2304: "
            "what are the high-severity HAZOP nodes, design pressure/temperature limits, overpressure protection "
            "devices, and downstream plant implications if reflux is lost?"
        ),
    },
    {
        "id": "graph_traversal_d2304",
        "title": "Multi-Hop Process & Trip Graph Traversal (D-2304)",
        "badge": "GRAPH // 2-HOP GQL",
        "category": "D_GRAPH_CONNECTIVITY_AND_BLAST_RADIUS",
        "focus_tag": "D-2304",
        "question": (
            "Traverse the Spanner Property Graph (OkfKnowledgeGraph) up to 2 hops around D-2304: "
            "list all upstream and downstream process connections (CONNECTS_TO), stream IDs, and all safety "
            "instruments or interlocks (MONITORS_OR_TRIPS) protecting D-2304."
        ),
    },
    {
        "id": "conflict_audit_d2304",
        "title": "Cross-Document Parameter Conflict & Lineage Audit",
        "badge": "LINEAGE // CONFLICT",
        "category": "E_BACKWARD_LINEAGE_AND_CONFLICT_AUDIT",
        "focus_tag": "D-2304",
        "question": (
            "Audit Debutanizer Reflux Drum D-2304 for cross-document parameter conflicts in Spanner: "
            "compare design pressure, operating temperature, and corrosion allowance across authoritative datasheets "
            "and P&IDs, and trace the backward PDF lineage with exact document revisions and MD5 hashes."
        ),
    },
    {
        "id": "instrument_interlock_lookup",
        "title": "Safety Instrument & ESD Trip Loop Verification",
        "badge": "SIS // INTERLOCKS",
        "category": "B_INSTRUMENT_AND_INTERLOCK_LOOKUP",
        "focus_tag": "PSV-2304A",
        "question": (
            "Look up safety relief valve PSV-2304A and high-level/pressure instruments on D-2304: "
            "what are their setpoints, governing relief cases, orifice designations, and connected process equipment?"
        ),
    },
    {
        "id": "hybrid_vector_fts_search",
        "title": "Hybrid Vector + Full-Text Search (Blowdown & Relief)",
        "badge": "HYBRID // RRF SEARCH",
        "category": "C_HYBRID_SEMANTIC_AND_KEYWORD_SEARCH",
        "focus_tag": "D-2304",
        "question": (
            "Use hybrid semantic vector + full-text RRF search in Spanner to find all engineering concepts, "
            "operating procedures, and relief philosophy rules governing emergency depressuring, flare header "
            "backpressure, and liquid carry-over in Unit 23."
        ),
    },
    {
        "id": "dataplex_catalog_governance",
        "title": "Dataplex Universal Catalog & OpenLineage Governance",
        "badge": "DATAPLEX // CATALOG",
        "category": "H_CATALOG_AND_GOVERNANCE",
        "focus_tag": "D-2304",
        "question": (
            "Synchronize and inspect the Google Cloud Dataplex Universal Catalog and OpenLineage governance registry "
            "for the OKF Spanner Graph: report the registered entry group, aspect type schema, governed assets, "
            "steward metadata, and verification status."
        ),
    },
]

TOOL_DESCRIPTIONS: dict[str, str] = {
    "lookup_entity_and_parameters": "Parameterized SQL lookup on OkfEngineeringEntities & OkfDesignParameters",
    "traverse_equipment_connectivity_graph": "ISO GQL multi-hop traversal on OkfKnowledgeGraph (CONNECTS_TO / MONITORS_OR_TRIPS)",
    "trace_data_lineage_and_conflicts": "ISO GQL lineage & cross-document conflict audit (DERIVED_FROM -> OkfSourceDocuments)",
    "hybrid_search_okf_spanner": "Hybrid Reciprocal Rank Fusion (Cosine Vector 768-dim + Full-Text Search)",
    "read_full_okf_concept_from_spanner": "Full OKF Concept Markdown & Structured Payload Reader (OkfConcepts)",
    "execute_multistage_risk_and_hazop_query": "5-Stage Composite HAZOP & Risk Assessment Engine (SQL + GQL + FTS + Lineage)",
    "sync_or_inspect_knowledge_catalog": "Google Cloud Dataplex Universal Catalog (dataplex_v1) & OpenLineage Sync",
}


class ChatQueryRequest(BaseModel):
    """Request payload for the Retrieval Workbench multi-turn chat endpoint."""

    question: str = Field(..., min_length=1, description="User engineering question")
    session_id: str | None = Field(
        default=None,
        description="Optional persistent ADK session_id for multi-turn context retention",
    )
    focus_tag: str | None = Field(
        default=None, description="Optional equipment tag currently focused in the UI"
    )
    category: str | None = Field(
        default=None, description="Optional canonical intent category hint"
    )


# Shared repository, persistent ADK session service, and state caches
_REPO: SpannerGraphRepository | None = None
_SESSION_SERVICE: InMemorySessionService = InMemorySessionService()
_SESSIONS_META: dict[str, dict[str, Any]] = {}
_HIERARCHY_CACHE: dict[str, Any] = {"timestamp": 0.0, "data": None}
_CATALOG_CACHE: dict[str, Any] = {"timestamp": 0.0, "data": None}
_GRAPH_CACHE: dict[tuple[str, int, bool], dict[str, Any]] = {}
_QUERY_JOBS: dict[str, dict[str, Any]] = {}


def get_repo() -> SpannerGraphRepository:
    """Return singleton SpannerGraphRepository instance."""
    global _REPO
    if _REPO is None:
        use_in_memory = os.environ.get("QUERY_WEB_USE_IN_MEMORY", "false").lower() in (
            "true",
            "1",
            "yes",
        )
        _REPO = SpannerGraphRepository(use_in_memory=use_in_memory)
        set_active_spanner_repository(_REPO)
    return _REPO


def set_repo_for_testing(repo: SpannerGraphRepository) -> None:
    """Inject a custom repository instance for unit/property testing."""
    global _REPO, _SESSION_SERVICE
    _REPO = repo
    _SESSION_SERVICE = InMemorySessionService()
    _SESSIONS_META.clear()
    _QUERY_JOBS.clear()
    _GRAPH_CACHE.clear()
    set_active_spanner_repository(repo)
    _HIERARCHY_CACHE["timestamp"] = 0.0
    _HIERARCHY_CACHE["data"] = None
    _CATALOG_CACHE["timestamp"] = 0.0
    _CATALOG_CACHE["data"] = None


async def _get_or_create_session(
    session_id: str | None = None,
    *,
    force_new: bool = False,
) -> dict[str, Any]:
    """Retrieve an existing multi-turn ADK session or create a new one."""
    clean_id = (session_id or "").strip()
    if not force_new and clean_id and clean_id in _SESSIONS_META:
        existing_adk = await _SESSION_SERVICE.get_session(
            app_name="okf_query_workbench",
            user_id="workbench_user",
            session_id=clean_id,
        )
        if existing_adk is None:
            await _SESSION_SERVICE.create_session(
                app_name="okf_query_workbench",
                user_id="workbench_user",
                session_id=clean_id,
            )
        return _SESSIONS_META[clean_id]

    target_id = (
        clean_id
        if (clean_id and not force_new)
        else f"qsess-{uuid.uuid4().hex[:10]}"
    )
    adk_session = await _SESSION_SERVICE.create_session(
        app_name="okf_query_workbench",
        user_id="workbench_user",
        session_id=target_id,
    )
    meta: dict[str, Any] = {
        "session_id": adk_session.id,
        "user_id": "workbench_user",
        "turn_count": 0,
        "history": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _SESSIONS_META[adk_session.id] = meta
    return meta


def compute_telemetry_totals(
    steps: list[dict[str, Any]],
    total_elapsed_s: float,
) -> tuple[float, float]:
    """Compute steps_sum_ms and reconciled total_duration_ms from contiguous step durations."""
    for s in steps:
        dur = float(s.get("duration_ms") or 0.0)
        s["duration_ms"] = round(max(0.0, dur), 1)
    steps_sum_ms = round(sum(float(s.get("duration_ms") or 0.0) for s in steps), 1)
    raw_total_ms = round(max(0.0, total_elapsed_s * 1000.0), 1)
    # Reconcile any residual rounding gap onto the final completed step so sum(steps) == total_duration_ms
    if steps:
        residual = round(raw_total_ms - steps_sum_ms, 1)
        if abs(residual) > 0.0:
            last_step = steps[-1]
            adjusted = round(max(0.0, float(last_step.get("duration_ms") or 0.0) + residual), 1)
            last_step["duration_ms"] = adjusted
            steps_sum_ms = round(sum(float(s.get("duration_ms") or 0.0) for s in steps), 1)
    return steps_sum_ms, steps_sum_ms if steps else raw_total_ms


def _summarize_tool_output(tool_name: str, response_payload: Any) -> dict[str, Any]:
    """Extract concise telemetry metrics from a tool response payload for the UI log."""
    if isinstance(response_payload, str):
        try:
            data = json.loads(response_payload)
        except Exception:
            return {"summary": response_payload[:160], "metrics": {}}
    elif isinstance(response_payload, dict):
        raw_res = response_payload.get("result", response_payload)
        if isinstance(raw_res, str):
            try:
                data = json.loads(raw_res)
            except Exception:
                return {"summary": raw_res[:160], "metrics": {}}
        elif isinstance(raw_res, dict):
            data = raw_res
        else:
            return {"summary": str(raw_res)[:160], "metrics": {}}
    else:
        return {"summary": str(response_payload)[:160], "metrics": {}}

    if not isinstance(data, dict):
        return {"summary": str(data)[:160], "metrics": {}}

    status = data.get("status", "OK")
    if tool_name == "lookup_entity_and_parameters":
        entities = data.get("entities", [])
        params = data.get("parameters", [])
        conflicts = sum(1 for p in params if p.get("has_conflict"))
        tags = [e.get("canonical_tag") for e in entities[:4] if e.get("canonical_tag")]
        return {
            "summary": f"Status={status} | Matched {len(entities)} entities ({', '.join(tags) or 'none'}), {len(params)} parameters ({conflicts} conflicts)",
            "metrics": {
                "entities": len(entities),
                "parameters": len(params),
                "conflicts": conflicts,
                "tags": tags,
            },
        }
    if tool_name == "traverse_equipment_connectivity_graph":
        hops = data.get("hops", [])
        start_tag = data.get("start_tag", "")
        return {
            "summary": f"Status={status} | Traversed {len(hops)} GQL edges from {start_tag} (max_hops={data.get('max_hops', 2)})",
            "metrics": {"start_tag": start_tag, "hop_count": len(hops)},
        }
    if tool_name == "trace_data_lineage_and_conflicts":
        traces = data.get("lineage_traces", data.get("traces", []))
        conflicts = sum(1 for t in traces if t.get("has_conflict"))
        return {
            "summary": f"Status={status} | Traced {len(traces)} lineage edges ({conflicts} conflicts) for {data.get('target_id', '')}",
            "metrics": {"trace_count": len(traces), "conflict_count": conflicts},
        }
    if tool_name == "hybrid_search_okf_spanner":
        results = data.get("results", [])
        return {
            "summary": f"Status={status} | RRF Hybrid Search returned {len(results)} ranked OKF concepts",
            "metrics": {"result_count": len(results)},
        }
    if tool_name == "read_full_okf_concept_from_spanner":
        cid = data.get("concept_id", "")
        md_len = len(data.get("markdown_content", ""))
        return {
            "summary": f"Status={status} | Loaded full OKF concept '{cid}' ({md_len} chars)",
            "metrics": {"concept_id": cid},
        }
    if tool_name == "execute_multistage_risk_and_hazop_query":
        tier = data.get("highest_risk_tier", data.get("overall_risk_tier", "UNKNOWN"))
        hazop_rows = len(data.get("hazop_scenarios", []))
        blast = len(data.get("propagation_hops", []))
        conflicts = len(data.get("lineage_and_conflicts", []))
        return {
            "summary": f"Status={status} | Risk Tier={tier} | {hazop_rows} HAZOP rows, {blast} blast-radius hops, {conflicts} lineage traces",
            "metrics": {
                "overall_risk_tier": tier,
                "hazop_rows": hazop_rows,
                "blast_radius_hops": blast,
                "lineage_traces": conflicts,
            },
        }
    if tool_name == "sync_or_inspect_knowledge_catalog":
        entries = data.get("catalog_entries", data.get("dataplex_entries", []))
        return {
            "summary": f"Status={status} | Inspected/Synced {len(entries)} Dataplex Universal Catalog assets",
            "metrics": {"entries": len(entries)},
        }
    return {"summary": f"Status={status}", "metrics": {}}


def _extract_referenced_tags(text: str) -> list[str]:
    """Extract canonical engineering tags mentioned in an answer for quick graph focus."""
    if not text:
        return []
    matches = re.findall(r"\b([A-Z]{1,4}-\d{3,5}[A-Z0-9-]*)\b", text)
    seen: set[str] = set()
    ordered: list[str] = []
    for m in matches:
        if m.startswith(("OKF-", "REV-", "API-", "ASME-", "ISO-", "SHA-", "PID-")):
            continue
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered[:10]


async def _execute_query_job(
    job_id: str,
    session_id: str,
    question: str,
    focus_tag: str | None,
    category: str | None,
) -> None:
    """Execute the ADK Query Agent while recording contiguous step-by-step and per-tool latency (`ms`)."""
    job = _QUERY_JOBS[job_id]
    sess_meta = _SESSIONS_META.get(session_id) or await _get_or_create_session(session_id)
    t_job_start = time.perf_counter()
    t_phase_cursor = t_job_start

    try:
        # STEP 0: Pre-flight Security Guardrail
        sec = check_query_prompt_security(question)
        allowed = sec.get("filterMatchState") != "MATCH_FOUND"
        threat_cat = sec.get("violation_type") or "POLICY_VIOLATION"
        reason = sec.get("matched_pattern") or "Adversarial directive detected"
        t_after_step0 = time.perf_counter()
        step0_ms = round((t_after_step0 - t_phase_cursor) * 1000, 1)
        t_phase_cursor = t_after_step0
        job["steps"].append(
            {
                "step_index": 0,
                "phase": "STEP 0 // GUARDRAIL",
                "title": "Model Armor & Prompt Injection Inspection",
                "status": "BLOCKED" if not allowed else "COMPLETED",
                "duration_ms": step0_ms,
                "detail": (
                    f"Blocked ({threat_cat}): {reason}"
                    if not allowed
                    else "Input passed pre-flight security & prompt-injection checks."
                ),
            }
        )

        if not allowed:
            t_end = time.perf_counter()
            steps_sum_ms, total_ms = compute_telemetry_totals(
                job["steps"], t_end - t_job_start
            )
            job["status"] = "COMPLETED"
            job["blocked_by_guardrail"] = True
            job["answer_markdown"] = (
                f"### Security Guardrail Intervention\n\n"
                f"Your request was blocked by the pre-flight security guardrail (`{threat_cat}`).\n\n"
                f"- **Reason:** {reason}\n"
                f"- **Policy:** Read-only engineering retrieval and governance operations only."
            )
            job["steps_sum_ms"] = steps_sum_ms
            job["total_duration_ms"] = total_ms
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
            return

        # Fast deterministic test mode when QUERY_WEB_TEST_FAST_AGENT=true
        if os.environ.get("QUERY_WEB_TEST_FAST_AGENT", "false").lower() in ("true", "1"):
            prior_history = list(sess_meta.get("history") or [])
            prior_tag = prior_history[-1].get("focus_tag") if prior_history else None
            target_tag = focus_tag or prior_tag or "D-2304"

            t_routing_end = time.perf_counter()
            routing_ms = round((t_routing_end - t_phase_cursor) * 1000, 1)
            t_phase_cursor = t_routing_end
            job["steps"].append(
                {
                    "step_index": 1,
                    "phase": "STEP 1 // COGNITIVE ROUTING",
                    "title": f"Model-Driven Intent & Session Context ({job['model']})",
                    "status": "COMPLETED",
                    "duration_ms": routing_ms,
                    "detail": f"Turn #{job.get('turn_count', 1)} in session {session_id} ({len(prior_history)} prior turns).",
                }
            )

            raw_lookup = lookup_entity_and_parameters(target_tag)
            t_tool_end = time.perf_counter()
            tool_ms = round((t_tool_end - t_phase_cursor) * 1000, 1)
            t_phase_cursor = t_tool_end
            summary_info = _summarize_tool_output(
                "lookup_entity_and_parameters", raw_lookup
            )
            job["tool_calls"].append(
                {
                    "call_index": 1,
                    "tool_name": "lookup_entity_and_parameters",
                    "description": TOOL_DESCRIPTIONS["lookup_entity_and_parameters"],
                    "args": {"entity_tag_or_id": target_tag},
                    "status": "COMPLETED",
                    "duration_ms": tool_ms,
                    "summary": summary_info["summary"],
                    "metrics": summary_info["metrics"],
                }
            )
            job["steps"].append(
                {
                    "step_index": 2,
                    "phase": "STEP 2 // ADK TOOL CALL #1",
                    "title": "lookup_entity_and_parameters",
                    "status": "COMPLETED",
                    "duration_ms": tool_ms,
                    "detail": summary_info["summary"],
                }
            )

            context_note = (
                f"\n- **Session Context:** Retained {len(prior_history)} prior turn(s) in `{session_id}`."
                if prior_history
                else ""
            )
            answer_md = (
                f"### Grounded Spanner Retrieval Result (`{target_tag}`)\n\n"
                f"- **Summary:** {summary_info['summary']}\n"
                f"- **Source Citation:** `2269-0114429200-000` (`Rev Z1`)"
                f"{context_note}"
            )
            t_end = time.perf_counter()
            synth_ms = round((t_end - t_phase_cursor) * 1000, 1)
            job["steps"].append(
                {
                    "step_index": 3,
                    "phase": "FINAL // VERTEX AI SYNTHESIS",
                    "title": f"Grounded Engineering Answer Synthesis ({job['model']})",
                    "status": "COMPLETED",
                    "duration_ms": synth_ms,
                    "detail": f"Synthesized {len(answer_md)} chars across 1 Spanner tool call.",
                }
            )

            steps_sum_ms, total_ms = compute_telemetry_totals(
                job["steps"], t_end - t_job_start
            )
            sess_meta.setdefault("history", []).append(
                {
                    "turn": job.get("turn_count", 1),
                    "question": question,
                    "focus_tag": target_tag,
                    "answer_markdown": answer_md,
                }
            )
            job["answer_markdown"] = answer_md
            job["referenced_tags"] = [target_tag]
            job["steps_sum_ms"] = steps_sum_ms
            job["total_duration_ms"] = total_ms
            job["status"] = "COMPLETED"
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
            return

        # STEP 1: Initialize ADK Runner with shared persistent _SESSION_SERVICE
        model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        if os.environ.get("GEMINI_LOCATION"):
            os.environ["GOOGLE_CLOUD_LOCATION"] = os.environ["GEMINI_LOCATION"]

        routing_step: dict[str, Any] = {
            "step_index": len(job["steps"]),
            "phase": "STEP 1 // COGNITIVE ROUTING",
            "title": f"Model-Driven Intent Classification & Tool Selection ({model_name})",
            "status": "RUNNING",
            "duration_ms": None,
            "detail": f"Analyzing query intent in session {session_id} (Turn #{job.get('turn_count', 1)})...",
        }
        job["steps"].append(routing_step)

        tool_call_counter = 0

        def _wrap_tool(fn: Any) -> Any:
            """Wrap an ADK tool function to record contiguous LLM and tool execution latency (`ms`)."""
            import functools

            tool_name = fn.__name__

            @functools.wraps(fn)
            def _wrapped(*args: Any, **kwargs: Any) -> Any:
                nonlocal tool_call_counter, t_phase_cursor
                t_tool_start = time.perf_counter()

                if routing_step["status"] == "RUNNING":
                    routing_ms = round((t_tool_start - t_phase_cursor) * 1000, 1)
                    routing_step["status"] = "COMPLETED"
                    routing_step["duration_ms"] = routing_ms
                    routing_step["detail"] = (
                        f"Cognitive planner selected tool trajectory in {routing_ms} ms."
                    )
                else:
                    inter_llm_ms = round((t_tool_start - t_phase_cursor) * 1000, 1)
                    if inter_llm_ms >= 2.0:
                        job["steps"].append(
                            {
                                "step_index": len(job["steps"]),
                                "phase": f"STEP {len(job['steps'])} // LLM REASONING",
                                "title": f"Multi-Step Cognitive Evaluation ({model_name})",
                                "status": "COMPLETED",
                                "duration_ms": inter_llm_ms,
                                "detail": f"Evaluated previous tool output and planned next tool call in {inter_llm_ms} ms.",
                            }
                        )

                t_phase_cursor = t_tool_start
                tool_call_counter += 1
                idx = tool_call_counter
                call_record: dict[str, Any] = {
                    "call_index": idx,
                    "tool_name": tool_name,
                    "description": TOOL_DESCRIPTIONS.get(tool_name, tool_name),
                    "args": kwargs if kwargs else {"args": list(args)},
                    "status": "RUNNING",
                    "duration_ms": None,
                    "summary": f"Executing {tool_name} against Cloud Spanner...",
                    "metrics": {},
                }
                job["tool_calls"].append(call_record)
                step_record: dict[str, Any] = {
                    "step_index": len(job["steps"]),
                    "phase": f"STEP {len(job['steps'])} // ADK TOOL CALL #{idx}",
                    "title": f"{tool_name}({json.dumps(kwargs, ensure_ascii=False)[:90]})",
                    "status": "RUNNING",
                    "duration_ms": None,
                    "detail": TOOL_DESCRIPTIONS.get(tool_name, tool_name),
                }
                job["steps"].append(step_record)
                try:
                    result = fn(*args, **kwargs)
                    t_tool_end = time.perf_counter()
                    elapsed_ms = round((t_tool_end - t_tool_start) * 1000, 1)
                    t_phase_cursor = t_tool_end
                    summary_info = _summarize_tool_output(tool_name, result)
                    call_record["status"] = "COMPLETED"
                    call_record["duration_ms"] = elapsed_ms
                    call_record["summary"] = summary_info["summary"]
                    call_record["metrics"] = summary_info["metrics"]
                    step_record["status"] = "COMPLETED"
                    step_record["duration_ms"] = elapsed_ms
                    step_record["detail"] = summary_info["summary"]
                    return result
                except Exception as exc:
                    t_tool_end = time.perf_counter()
                    elapsed_ms = round((t_tool_end - t_tool_start) * 1000, 1)
                    t_phase_cursor = t_tool_end
                    call_record["status"] = "ERROR"
                    call_record["duration_ms"] = elapsed_ms
                    call_record["summary"] = f"Error: {exc}"
                    step_record["status"] = "ERROR"
                    step_record["duration_ms"] = elapsed_ms
                    step_record["detail"] = f"Error: {exc}"
                    raise

            return _wrapped

        instrumented_agent = Agent(
            name="okf_spanner_query_agent_ui",
            model=model_name,
            description="Enterprise Engineering Knowledge Graph & Spanner Retrieval Agent (UI Telemetry Wrapper)",
            instruction=QUERY_ORCHESTRATOR_INSTRUCTIONS,
            tools=[
                _wrap_tool(lookup_entity_and_parameters),
                _wrap_tool(traverse_equipment_connectivity_graph),
                _wrap_tool(trace_data_lineage_and_conflicts),
                _wrap_tool(hybrid_search_okf_spanner),
                _wrap_tool(read_full_okf_concept_from_spanner),
                _wrap_tool(execute_multistage_risk_and_hazop_query),
                _wrap_tool(sync_or_inspect_knowledge_catalog),
            ],
        )

        runner = Runner(
            agent=instrumented_agent,
            app_name="okf_query_workbench",
            session_service=_SESSION_SERVICE,
        )

        # Ensure session exists in _SESSION_SERVICE
        await _get_or_create_session(session_id, force_new=False)

        prompt_with_context = (
            f"[Active Equipment/Concept Selection in Workbench: {focus_tag}]\n{question}"
            if focus_tag
            else question
        )
        content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt_with_context)],
        )

        final_text_parts: list[str] = []

        async for event in runner.run_async(
            user_id="workbench_user",
            session_id=session_id,
            new_message=content,
        ):
            if routing_step["status"] == "RUNNING":
                t_first_ev = time.perf_counter()
                routing_ms = round((t_first_ev - t_phase_cursor) * 1000, 1)
                routing_step["status"] = "COMPLETED"
                routing_step["duration_ms"] = routing_ms
                routing_step["detail"] = (
                    f"Cognitive planner processed request in {routing_ms} ms."
                )
                t_phase_cursor = t_first_ev

            if event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "text", None):
                        final_text_parts.append(part.text)

        t_job_end = time.perf_counter()
        if routing_step["status"] == "RUNNING":
            routing_ms = round((t_job_end - t_phase_cursor) * 1000, 1)
            routing_step["status"] = "COMPLETED"
            routing_step["duration_ms"] = routing_ms
            t_phase_cursor = t_job_end

        synthesis_ms = round(max(0.0, (t_job_end - t_phase_cursor) * 1000), 1)
        answer_md = "\n".join(final_text_parts).strip()
        job["steps"].append(
            {
                "step_index": len(job["steps"]),
                "phase": "FINAL // VERTEX AI SYNTHESIS",
                "title": f"Grounded Engineering Answer Synthesis ({model_name})",
                "status": "COMPLETED",
                "duration_ms": synthesis_ms,
                "detail": f"Synthesized {len(answer_md)} chars across {len(job['tool_calls'])} Spanner tool call(s).",
            }
        )

        referenced_tags = _extract_referenced_tags(answer_md)
        if focus_tag and focus_tag not in referenced_tags:
            referenced_tags.insert(0, focus_tag)

        steps_sum_ms, total_ms = compute_telemetry_totals(
            job["steps"], t_job_end - t_job_start
        )
        sess_meta.setdefault("history", []).append(
            {
                "turn": job.get("turn_count", 1),
                "question": question,
                "focus_tag": focus_tag,
                "answer_markdown": answer_md,
            }
        )
        job["answer_markdown"] = answer_md or "No response text generated."
        job["referenced_tags"] = referenced_tags
        job["steps_sum_ms"] = steps_sum_ms
        job["total_duration_ms"] = total_ms
        job["status"] = "COMPLETED"
        job["completed_at"] = datetime.now(timezone.utc).isoformat()

    except Exception as exc:
        logger.exception("Query workbench job %s failed", job_id)
        t_err_end = time.perf_counter()
        steps_sum_ms, total_ms = compute_telemetry_totals(
            job["steps"], t_err_end - t_job_start
        )
        job["status"] = "ERROR"
        job["error"] = str(exc)
        job["steps_sum_ms"] = steps_sum_ms
        job["total_duration_ms"] = total_ms
        job["completed_at"] = datetime.now(timezone.utc).isoformat()


def _fetch_catalog_payload(repo: SpannerGraphRepository, force_sync: bool) -> dict[str, Any]:
    """Query or synchronize Dataplex Universal Catalog & OpenLineage metadata."""
    live_counts = repo.get_live_counts()
    syncer = DataplexCatalogAndLineageSync(project_id=repo.project_id)
    dry_run = repo.use_in_memory
    sync_report = None
    if force_sync:
        sync_report = syncer.sync_catalog_and_lineage(live_counts, dry_run=dry_run)
    state = syncer.inspect_catalog_state(live_counts, dry_run=dry_run)

    # Normalize entries for UI consumption
    entries = state.get("catalog_entries", [])
    dataplex_entries = []
    for e in entries:
        gov = e.get("governance_tags", {})
        dataplex_entries.append(
            {
                "entry_id": e.get("entry_id", ""),
                "display_name": e.get("display_name", ""),
                "dataplex_entry_name": e.get("dataplex_entry_name", ""),
                "linked_resource": e.get("linked_resource", ""),
                "status": "SYNCED_LIVE" if not dry_run else "DRY_RUN",
                "aspects": {
                    "classification": gov.get("domain_profile", "INTERNAL_ENGINEERING"),
                    "verification_status": gov.get(
                        "immutability_policy", "VERIFIED_OKF_V3"
                    ),
                    "data_steward": "okf-process-safety@enterprise.internal",
                    "source_system": e.get("entry_id", "SPANNER_GRAPH"),
                },
                "governance_tags": gov,
            }
        )

    return {
        "status": sync_report.status if sync_report else ("SYNCED_LIVE" if not dry_run else "DRY_RUN"),
        "project_id": state.get("project_id", repo.project_id),
        "location": state.get("location", "asia-southeast1"),
        "entry_group": state.get("entry_group", ""),
        "dataplex_entries": dataplex_entries,
        "dataplex_aspect_type": {
            "aspect_type_id": state.get("tag_template_id", "okf-governance-template"),
            "resource_name": state.get("aspect_type", ""),
            "status": "ACTIVE",
            "fields": [
                "domain_profile (STRING)",
                "total_concepts (INT)",
                "total_entities (INT)",
                "total_assertions (INT)",
                "total_conflicts (INT)",
                "total_lineage_edges (INT)",
                "last_synced_at (DATETIME)",
            ],
        },
        "openlineage_event": {
            "status": "COMPLETE",
            "job_name": "okf_spanner_graph_and_lineage_ingestion",
            "inputs_count": live_counts.get("total_source_docs", 68),
            "outputs_count": live_counts.get("total_concepts", 150),
            "topology": state.get("openlineage_pipeline_topology", []),
        },
        "live_spanner_metrics": live_counts,
    }


def create_app() -> FastAPI:
    """Create and configure the FastAPI application for `okf-query-agent-web`."""
    app = FastAPI(
        title="OKF Spanner Graph & Knowledge Retrieval Workbench",
        description=(
            "3-Pane Interactive Retrieval UI for the OKF Spanner Property Graph, "
            "Conversational ADK Query Agent with Live Per-Tool Latency Telemetry, "
            "and Google Cloud Dataplex Universal Catalog."
        ),
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def no_cache_static_middleware(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index() -> Any:
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(
                str(index_path),
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        return JSONResponse(
            {"service": "okf-query-agent-web", "status": "UI static bundle not found"},
            status_code=200,
        )

    @app.get("/healthz")
    @app.get("/api/healthz")
    async def healthz() -> dict[str, Any]:
        repo = get_repo()
        return {
            "status": "ok",
            "service": "okf-query-agent-web",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
            "spanner_instance": repo.instance_id,
            "spanner_database": repo.database_id,
            "use_in_memory": repo.use_in_memory,
        }

    @app.get("/api/status")
    async def api_status() -> dict[str, Any]:
        repo = get_repo()
        return {
            "status": "online",
            "service": "okf-query-agent-web",
            "project_id": repo.project_id,
            "location": os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-southeast1"),
            "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
            "gemini_location": os.environ.get("GEMINI_LOCATION", "global"),
            "spanner_instance": repo.instance_id,
            "spanner_database": repo.database_id,
            "spanner_graph": "OkfKnowledgeGraph",
            "agent_runtime_id": os.environ.get(
                "QUERY_AGENT_RUNTIME_ID", "okf-query-agent-nonprod"
            ),
            "pre_built_prompts": PRE_BUILT_PROMPTS,
            "tool_registry": [
                {"name": k, "description": v} for k, v in TOOL_DESCRIPTIONS.items()
            ],
        }

    @app.get("/api/spanner/hierarchy")
    async def api_spanner_hierarchy(
        refresh: bool = Query(default=False, description="Bypass 30s cache"),
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        now = time.time()
        if (
            not refresh
            and _HIERARCHY_CACHE["data"] is not None
            and (now - _HIERARCHY_CACHE["timestamp"]) < 30.0
        ):
            cached = dict(_HIERARCHY_CACHE["data"])
            cached["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            cached["cached"] = True
            return cached

        repo = get_repo()
        data = await asyncio.to_thread(repo.get_equipment_hierarchy)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        data["execution_time_ms"] = elapsed_ms
        data["cached"] = False
        _HIERARCHY_CACHE["timestamp"] = now
        _HIERARCHY_CACHE["data"] = data
        return data

    @app.get("/api/spanner/graph")
    async def api_spanner_graph(
        center_tag: str = Query(
            default="D-2304",
            min_length=1,
            description="Canonical tag or concept ID to center the graph around",
        ),
        max_hops: int = Query(
            default=2, ge=1, le=3, description="Traversal hop radius (1..3)"
        ),
        include_lineage: bool = Query(
            default=True,
            description="Include backward PDF lineage nodes and DERIVED_FROM edges",
        ),
        refresh: bool = Query(
            default=False,
            description="Bypass 60s subgraph cache",
        ),
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        now = time.time()
        cache_key = (center_tag.strip(), int(max_hops), bool(include_lineage))
        cached_entry = _GRAPH_CACHE.get(cache_key)
        if (
            not refresh
            and cached_entry is not None
            and (now - float(cached_entry.get("timestamp", 0.0))) < 60.0
        ):
            cached_data = dict(cached_entry["data"])
            cached_data["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            cached_data["cached"] = True
            return cached_data

        repo = get_repo()
        graph_data = await asyncio.to_thread(
            repo.get_interactive_graph,
            center_tag=center_tag,
            max_hops=max_hops,
            include_lineage=include_lineage,
        )
        graph_data["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        graph_data["cached"] = False
        _GRAPH_CACHE[cache_key] = {"timestamp": now, "data": graph_data}
        return graph_data

    @app.get("/api/spanner/concept/{concept_id:path}")
    async def api_spanner_concept(concept_id: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        repo = get_repo()
        doc = await asyncio.to_thread(
            repo.read_full_concept, concept_id_or_tag=concept_id
        )
        if not doc or doc.get("found") is False:
            raise HTTPException(
                status_code=404,
                detail=f"Concept '{concept_id}' not found in Spanner.",
            )
        resolved_cid = str(doc.get("concept_id") or concept_id)
        is_non_eq = (
            "/" in resolved_cid and not resolved_cid.lower().startswith("equipment/")
        ) or resolved_cid.lower() in ("overview", "project")
        if resolved_cid.lower().startswith("equipment/"):
            target_tag = resolved_cid.split("/", 1)[-1]
        else:
            target_tag = str(doc.get("canonical_tag") or resolved_cid)
        if is_non_eq:
            parameters_list: list[dict[str, Any]] = []
            entities_list: list[dict[str, Any]] = []
            lineage_list: list[dict[str, Any]] = []
        else:
            lookup_res = await asyncio.to_thread(
                repo.lookup_entity_and_parameters, entity_tag_or_id=target_tag
            )
            lineage = await asyncio.to_thread(
                repo.trace_lineage_gql,
                target_id=target_tag,
                direction="BACKWARD_TO_PDF",
                conflicts_only=False,
            )
            parameters_list = lookup_res.get("parameters", [])[:50]
            entities_list = lookup_res.get("entities", [])[:10]
            lineage_list = [t.model_dump() for t in lineage[:25]]
        catalog_dossier = repo.build_catalog_dossier(
            concept_doc=doc,
            lineage_traces=lineage_list,
            parameters=parameters_list,
            fallback_tag=target_tag,
            fallback_unit=str(doc.get("unit") or ""),
        )
        return {
            "status": "OK",
            "execution_time_ms": round((time.perf_counter() - t0) * 1000, 2),
            "concept": doc,
            "entities": entities_list,
            "parameters": parameters_list,
            "lineage_traces": lineage_list,
            "catalog_dossier": catalog_dossier,
        }

    @app.get("/api/catalog")
    async def api_catalog_inspect(
        refresh: bool = Query(default=False, description="Force live Dataplex sync"),
    ) -> dict[str, Any]:
        t0 = time.perf_counter()
        now = time.time()
        if (
            not refresh
            and _CATALOG_CACHE["data"] is not None
            and (now - _CATALOG_CACHE["timestamp"]) < 60.0
        ):
            cached = dict(_CATALOG_CACHE["data"])
            cached["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            cached["cached"] = True
            return cached

        repo = get_repo()
        catalog_data = await asyncio.to_thread(_fetch_catalog_payload, repo, False)
        catalog_data["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        catalog_data["cached"] = False
        _CATALOG_CACHE["timestamp"] = now
        _CATALOG_CACHE["data"] = catalog_data
        return catalog_data

    @app.post("/api/catalog/sync")
    async def api_catalog_sync() -> dict[str, Any]:
        t0 = time.perf_counter()
        repo = get_repo()
        catalog_data = await asyncio.to_thread(_fetch_catalog_payload, repo, True)
        catalog_data["execution_time_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        catalog_data["cached"] = False
        _CATALOG_CACHE["timestamp"] = time.time()
        _CATALOG_CACHE["data"] = catalog_data
        return catalog_data

    @app.post("/api/query/session/new")
    async def api_query_session_new() -> dict[str, Any]:
        sess_meta = await _get_or_create_session(force_new=True)
        return {
            "session_id": sess_meta["session_id"],
            "user_id": sess_meta["user_id"],
            "turn_count": sess_meta["turn_count"],
            "created_at": sess_meta["created_at"],
        }

    @app.get("/api/query/session/{session_id}")
    async def api_query_session_inspect(session_id: str) -> dict[str, Any]:
        sess_meta = _SESSIONS_META.get(session_id)
        if not sess_meta:
            raise HTTPException(
                status_code=404, detail=f"Session '{session_id}' not found."
            )
        return sess_meta

    @app.post("/api/query/chat")
    async def api_query_chat(req: ChatQueryRequest) -> dict[str, Any]:
        question = req.question.strip()
        if not question:
            raise HTTPException(status_code=400, detail="Question must not be empty.")

        sess_meta = await _get_or_create_session(req.session_id, force_new=False)
        session_id = sess_meta["session_id"]
        sess_meta["turn_count"] = int(sess_meta.get("turn_count") or 0) + 1
        turn_count = sess_meta["turn_count"]

        job_id = f"qjob-{uuid.uuid4().hex[:12]}"
        job_state: dict[str, Any] = {
            "job_id": job_id,
            "session_id": session_id,
            "turn_count": turn_count,
            "question": question,
            "focus_tag": req.focus_tag,
            "category": req.category,
            "model": os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
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
        _QUERY_JOBS[job_id] = job_state
        asyncio.create_task(
            _execute_query_job(
                job_id=job_id,
                session_id=session_id,
                question=question,
                focus_tag=req.focus_tag,
                category=req.category,
            )
        )
        return {
            "job_id": job_id,
            "session_id": session_id,
            "turn_count": turn_count,
            "status": "RUNNING",
            "question": question,
            "focus_tag": req.focus_tag,
            "model": job_state["model"],
        }

    @app.get("/api/query/jobs/{job_id}")
    async def api_query_job_status(job_id: str) -> dict[str, Any]:
        job = _QUERY_JOBS.get(job_id)
        if not job:
            raise HTTPException(
                status_code=404, detail=f"Query job '{job_id}' not found."
            )
        return job

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8081"))
    uvicorn.run("query_agent.web_server:app", host="0.0.0.0", port=port, reload=False)
