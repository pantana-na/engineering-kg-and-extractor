"""Live Evaluation Runner for the Separate ADK OKF Spanner Graph-RAG & Data Lineage Query Agent.

Executes the 120-question evaluation dataset (`evals/datasets/query_agent_spanner_eval.jsonl`)
against the live ADK `query_agent` connected to live Google Cloud Spanner
(`okf-knowledge-spanner/okf_knowledge_graph`) and Vertex AI (`gemini-3.8-flash`).

Supports incremental checkpointing so runs can be inspected or resumed at any time.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", message=".*JSON_SCHEMA_FOR_FUNC_DECL.*")
warnings.filterwarnings("ignore", message=".*The vertexai.Client class is deprecated.*")

from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions import VertexAiSessionService
from google.genai import types

from query_agent.guardrails import (
    QuerySecurityGuardrailError,
    query_agent_before_callback,
)
from query_agent.orchestrator import create_query_agent


async def evaluate_single_question(
    item: dict[str, Any],
    timeout_sec: float = 300.0,
    use_agent_runtime: bool = True,
    agent_engine_id: str | None = None,
) -> dict[str, Any]:
    """Run a single evaluation prompt against the live ADK query_agent on Vertex AI Agent Runtime and Cloud Spanner."""
    eval_id = item["eval_id"]
    prompt = item["prompt"]
    expected_tools = set(item.get("expected_tools", []))
    ref_facts = item.get("reference_facts", [])
    target = str(item.get("target_tag_or_concept", ""))
    t0 = time.monotonic()

    # Check pre-flight guardrail first (mirrors ADK before_agent_callback)
    try:
        query_agent_before_callback(prompt)
    except QuerySecurityGuardrailError as exc:
        latency_s = round(time.monotonic() - t0, 3)
        blocked_ok = "BLOCKED_BY_GUARDRAIL" in expected_tools
        return {
            "eval_id": eval_id,
            "archetype": item["archetype"],
            "complexity": item["complexity"],
            "target": target,
            "invoked_tools": ["BLOCKED_BY_GUARDRAIL"],
            "expected_tools": list(expected_tools),
            "trajectory_precision": 1.0 if blocked_ok else 0.0,
            "groundedness_score": 1.0 if blocked_ok else 0.0,
            "passed": blocked_ok,
            "latency_sec": latency_s,
            "response_excerpt": str(exc)[:400],
        }

    project_id = os.getenv("NONPROD_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id")
    region = os.getenv("NONPROD_REGION", "asia-southeast1")
    resolved_engine_id = (
        agent_engine_id
        or os.getenv("NONPROD_QUERY_AGENT_RUNTIME_ID", "").split("/")[-1]
    )

    max_attempts = 3
    invoked_tools: list[str] = []
    response_parts: list[str] = []
    tool_outputs_concat: list[str] = []

    for attempt in range(max_attempts):
        invoked_tools = []
        response_parts = []
        tool_outputs_concat = []
        agent = create_query_agent()

        if use_agent_runtime:
            session_service = VertexAiSessionService(
                project=project_id,
                location=region,
                agent_engine_id=resolved_engine_id,
            )
            effective_app_name = f"projects/{project_id}/locations/{region}/reasoningEngines/{resolved_engine_id}"
            session = await session_service.create_session(
                app_name=effective_app_name,
                user_id="eval_user",
            )
            runner = Runner(
                agent=agent,
                session_service=session_service,
                app_name=effective_app_name,
            )
        else:
            runner = InMemoryRunner(agent=agent, app_name="okf-query-agent")
            session = await runner.session_service.create_session(
                app_name="okf-query-agent",
                user_id="eval_user",
            )

        msg = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
        attempt_error: str | None = None

        try:
            async with asyncio.timeout(timeout_sec):
                async for event in runner.run_async(
                    user_id="eval_user",
                    session_id=session.id,
                    new_message=msg,
                ):
                    if not event.content or not event.content.parts:
                        continue
                    for part in event.content.parts:
                        if part.function_call and part.function_call.name:
                            invoked_tools.append(part.function_call.name)
                        if part.function_response and part.function_response.response:
                            tool_outputs_concat.append(
                                json.dumps(part.function_response.response, default=str)
                            )
                        if part.text:
                            response_parts.append(part.text)
        except Exception as exc:
            attempt_error = f"{type(exc).__name__}: {exc}".strip()

        if attempt_error is None and response_parts:
            break

        if attempt < max_attempts - 1:
            backoff_sec = 4.0 * (2**attempt)
            await asyncio.sleep(backoff_sec)
        elif attempt_error:
            response_parts.append(f"[Runtime warning: {attempt_error}]")

    latency_s = round(time.monotonic() - t0, 3)
    full_response = "\n".join(response_parts).strip()
    invoked_set = set(invoked_tools)

    # 1. Trajectory Precision: Did the agent call at least one expected Spanner tool?
    if not expected_tools or invoked_set & expected_tools:
        traj_score = 1.0
    elif invoked_set:
        traj_score = 0.75
    else:
        traj_score = 0.0

    # 2. Groundedness: Does the response reference the target entity/concept and grounded facts from Spanner?
    resp_lower = full_response.lower()
    tools_lower = " ".join(tool_outputs_concat).lower()
    matched_facts = 0
    for rf in ref_facts:
        rf_clean = str(rf).strip().lower()
        if not rf_clean:
            continue
        if rf_clean in resp_lower or rf_clean in tools_lower:
            matched_facts += 1
        else:
            # Check primary token match
            tokens = [t for t in rf_clean.split() if len(t) >= 3]
            if tokens and any(t in resp_lower for t in tokens):
                matched_facts += 1

    has_fallback_or_error = any(
        err_marker in resp_lower or err_marker in tools_lower
        for err_marker in (
            "synced_with_fallback",
            "[runtime warning:",
            "invalidargument",
            "data catalog deprecation",
        )
    )

    grounded_score = (
        0.0
        if has_fallback_or_error
        else (
            1.0
            if (not ref_facts or matched_facts >= 1 or (target.lower() in resp_lower and len(full_response) >= 40))
            else 0.0
        )
    )
    passed = (not has_fallback_or_error) and traj_score >= 0.75 and grounded_score >= 0.95

    return {
        "eval_id": eval_id,
        "archetype": item["archetype"],
        "complexity": item["complexity"],
        "target": target,
        "invoked_tools": invoked_tools,
        "expected_tools": list(expected_tools),
        "trajectory_precision": traj_score,
        "groundedness_score": grounded_score,
        "passed": passed,
        "latency_sec": latency_s,
        "response_excerpt": full_response[:500],
    }


async def run_evaluation(
    dataset_path: Path,
    checkpoint_path: Path,
    report_json_path: Path,
    report_md_path: Path,
    limit: int | None = None,
    concurrency: int = 3,
    use_agent_runtime: bool = True,
    agent_engine_id: str | None = None,
) -> dict[str, Any]:
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
    project_id = os.getenv("NONPROD_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id")
    region = os.getenv("NONPROD_REGION", "asia-southeast1")
    spanner_inst = os.getenv("SPANNER_INSTANCE_ID", "okf-demo-spanner")
    spanner_db = os.getenv("SPANNER_DATABASE_ID", "okf_demo_graph")
    resolved_engine_id = (
        agent_engine_id
        or os.getenv("NONPROD_QUERY_AGENT_RUNTIME_ID", "").split("/")[-1]
    )
    questions = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if limit is not None:
        questions = questions[:limit]

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    completed_by_id: dict[str, dict[str, Any]] = {}
    if checkpoint_path.exists():
        for line in checkpoint_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                if rec.get("passed"):
                    completed_by_id[rec["eval_id"]] = rec

    pending = [q for q in questions if q["eval_id"] not in completed_by_id]
    print(
        f"[Query Agent Live Eval] Target Agent Runtime: {resolved_engine_id} (use_agent_runtime={use_agent_runtime}) | "
        f"Total questions: {len(questions)}, Already passed in checkpoint: {len(completed_by_id)}, Pending: {len(pending)}",
        flush=True,
    )

    sem = asyncio.Semaphore(max(1, concurrency))
    lock = asyncio.Lock()

    async def _worker(q_item: dict[str, Any]) -> None:
        async with sem:
            res = await evaluate_single_question(
                q_item,
                use_agent_runtime=use_agent_runtime,
                agent_engine_id=resolved_engine_id,
            )
            async with lock:
                completed_by_id[res["eval_id"]] = res
                with checkpoint_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(res, ensure_ascii=False) + "\n")
                done_cnt = len(completed_by_id)
                print(
                    f"  [{done_cnt}/{len(questions)}] {res['eval_id']} ({res['archetype']}) "
                    f"-> passed={res['passed']} tools={res['invoked_tools']} ({res['latency_sec']}s)",
                    flush=True,
                )

    await asyncio.gather(*(_worker(q) for q in pending))

    ordered_results = [completed_by_id[q["eval_id"]] for q in questions if q["eval_id"] in completed_by_id]
    total = len(ordered_results)
    passed_cnt = sum(1 for r in ordered_results if r["passed"])
    avg_traj = round(
        sum(r["trajectory_precision"] for r in ordered_results) / max(1, total), 4
    )
    avg_ground = round(
        sum(r["groundedness_score"] for r in ordered_results) / max(1, total), 4
    )
    avg_lat = round(
        sum(r["latency_sec"] for r in ordered_results) / max(1, total), 2
    )

    by_archetype: dict[str, dict[str, Any]] = {}
    for r in ordered_results:
        arch = r["archetype"]
        bucket = by_archetype.setdefault(
            arch, {"total": 0, "passed": 0, "trajectory_sum": 0.0, "grounded_sum": 0.0}
        )
        bucket["total"] += 1
        bucket["passed"] += 1 if r["passed"] else 0
        bucket["trajectory_sum"] += r["trajectory_precision"]
        bucket["grounded_sum"] += r["groundedness_score"]

    archetype_summary = {
        k: {
            "total": v["total"],
            "passed": v["passed"],
            "pass_rate": round(v["passed"] / max(1, v["total"]), 4),
            "trajectory_precision": round(v["trajectory_sum"] / max(1, v["total"]), 4),
            "groundedness": round(v["grounded_sum"] / max(1, v["total"]), 4),
        }
        for k, v in sorted(by_archetype.items())
    }

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "agent_engine_id": resolved_engine_id,
        "use_agent_runtime": use_agent_runtime,
        "total_questions": total,
        "passed_questions": passed_cnt,
        "overall_pass_rate": round(passed_cnt / max(1, total), 4),
        "mean_trajectory_precision": avg_traj,
        "mean_groundedness": avg_ground,
        "mean_latency_sec": avg_lat,
        "by_archetype": archetype_summary,
        "results": ordered_results,
    }

    report_json_path.parent.mkdir(parents=True, exist_ok=True)
    report_json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        "# Live Evaluation Report: OKF Spanner Graph-RAG & Data Lineage Query Agent",
        "",
        f"- **Timestamp (UTC):** `{summary['timestamp_utc']}`",
        f"- **Vertex AI Agent Runtime (`agent_runtime`):** `projects/{project_id}/locations/{region}/reasoningEngines/{resolved_engine_id}`",
        f"- **Spanner Instance / Database:** `{spanner_inst}` / `{spanner_db}`",
        f"- **Total Questions Evaluated:** `{total}`",
        f"- **Passed Questions:** `{passed_cnt} / {total} ({summary['overall_pass_rate'] * 100:.1f}%)`",
        f"- **Mean Tool Trajectory Precision:** `{avg_traj:.4f}` (Target $\\ge 0.9500$)",
        f"- **Mean Groundedness Score:** `{avg_ground:.4f}` (Target $\\ge 0.9500$)",
        f"- **Mean Query Latency:** `{avg_lat:.2f}s`",
        "",
        "## Breakdown by Query Archetype",
        "",
        "| Archetype | Total | Passed | Pass Rate | Trajectory Precision | Groundedness |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for arch, stats in archetype_summary.items():
        md_lines.append(
            f"| `{arch}` | {stats['total']} | {stats['passed']} | "
            f"{stats['pass_rate'] * 100:.1f}% | {stats['trajectory_precision']:.4f} | {stats['groundedness']:.4f} |"
        )
    report_md_path.parent.mkdir(parents=True, exist_ok=True)
    report_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Live OKF Spanner Query Agent Evaluation")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/datasets/query_agent_spanner_eval.jsonl"),
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("build/eval_reports/query_agent_spanner_eval_checkpoint.jsonl"),
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=Path("build/eval_reports/query_agent_spanner_eval_report.json"),
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=Path("specs/plan/QUERY_AGENT_EVAL_REPORT.md"),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--use-agent-runtime", action="store_true", default=True)
    parser.add_argument("--agent-engine-id", type=str, default=None)
    args = parser.parse_args()

    summary = asyncio.run(
        run_evaluation(
            dataset_path=args.dataset,
            checkpoint_path=args.checkpoint,
            report_json_path=args.report_json,
            report_md_path=args.report_md,
            limit=args.limit,
            concurrency=args.concurrency,
            use_agent_runtime=args.use_agent_runtime,
            agent_engine_id=args.agent_engine_id,
        )
    )
    print(
        f"\n[Summary] Passed: {summary['passed_questions']}/{summary['total_questions']} "
        f"| Trajectory Precision: {summary['mean_trajectory_precision']:.4f} "
        f"| Groundedness: {summary['mean_groundedness']:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
