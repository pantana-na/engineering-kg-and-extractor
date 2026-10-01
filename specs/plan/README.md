# Living Plan Progress Tracking (`specs/plan/`)

This directory houses continuous execution reports, milestone tracking documents, test verification metrics, and architectural decision records generated during implementation across **all agents** (`extracter_agent` and `query_agent`) and **both Cloud Run workbenches** (`extracter-agent-web` and `okf-query-agent-web`).

## Progress Tracking Protocol

Under the **Spec-Driven Development (SDD)** standard ([`_agents/rules/spec_driven_development.md`](../../_agents/rules/spec_driven_development.md)):

1. **Mandatory Progress Updates:** Whenever development pauses, a session concludes, or a major milestone is reached, developers and autonomous agents **MUST** author or update an execution progress report in this directory.
2. **Required Report Elements:**
   - **Specification Linkage:** Reference the parent feature SDD (e.g., `specs/features/SPEC-YYYYMMDD-TITLE.md`).
   - **Step-by-Step Progress Matrix:** Table detailing completed vs pending steps, implemented source files, unit test suites, property-based test suites, and live evaluation passes across all agents.
   - **Verification & Quality Metrics:** Test pass rates, evaluation benchmark scores ($\ge 95\%$ tool selection precision, 1.000 groundedness), and latency figures.
   - **Architectural & Design Decisions:** Non-obvious design choices, trade-offs, and user alignments made during development.
   - **Root Cause Analysis (RCA) Log:** If any defects, red tests, or eval regressions were investigated, summarize the 4-step RCA findings and user-selected fixes ([`_agents/rules/root_cause_investigation_and_zero_quick_patch.md`](../../_agents/rules/root_cause_investigation_and_zero_quick_patch.md)).
   - **Resumption Guide & Next Actions:** Explicit next steps for resuming development seamlessly.

---

## Multi-Agent & Cloud Run Platform Status Summary

| Subsystem / Agent | ADK Agent Runtime (`agent_runtime`) | Cloud Run Workbench (`cloud_run`) | Live Eval Pass Rate | Unit & PBT Suite | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Agent 1: Autonomous OKF Extracter Agent (`extracter_agent`)** | `extracter_orchestrator`<br>`reasoningEngines/<EXTRACTER_AGENT_ENGINE_ID>`<br>Model: `gemini-3.8-flash` | `extracter-agent-web` | **By-Equipment:** `20/20` (`100.0%`)<br>**By-PDF:** `20/20` (`100.0%`)<br>Trajectory: `1.000` \| Groundedness: `1.000` | `100 / 100` Passing (`100%`) | **COMPLETED & LIVE** |
| **Consolidated `.md`-Only Spanner Sync (`sync_markdown_bundle_to_spanner`)** | Deterministic Python Engine (`query_agent/spanner/repository.py`) | Integrated into `okf-query-agent-web` & `scripts/purge_and_reload_spanner.py` | Domain & Source Concepts, Chunks, Entities, Facts, Lineage Edges, `3` Live Dataplex Entries | Covered by `query_agent` Unit & PBT Suites | **COMPLETED & LIVE** |
| **Agent 2: OKF Spanner Graph-RAG Query Agent (`query_agent`)** | `okf_spanner_query_orchestrator`<br>`reasoningEngines/<QUERY_AGENT_ENGINE_ID>`<br>Model: `gemini-3.8-flash` | `okf-query-agent-web` | **Live Spanner & Dataplex Eval:** `100.0%` (`1.0000` precision, `1.0000` groundedness) | `37 / 37` Passing (`100%`) | **COMPLETED & LIVE** |
| **Combined Repository Totals** | **2 Live Reasoning Engines (`asia-southeast1`)** | **2 Live Cloud Run Services (`asia-southeast1`)** | **`100.0%` Live Eval Queries Passed** | **`143 / 143` Passing (`100%`, `0` Ruff/Bandit Issues)** | **PHASE 2 COMPLETE (PHASE 3 QUEUED)** |

---

## Document Naming Convention
- `PROGRESS_REPORT_<YYYYMMDD>.md` (e.g. `PROGRESS_REPORT_20261001.md`)

## Active Progress Reports & Evaluation Logs
- [`PROGRESS_REPORT_20261001.md`](./PROGRESS_REPORT_20261001.md): **Repository Sanitization, 20-Document Synthetic Engineering Dataset & Isolated Cloud Deployment Report** covering complete confidential data removal (`reference/raw/` & `reference/wiki/`), synthetic PDF generation (`scripts/generate_synthetic_reference.py`), zero application logic changes (`git diff` verified), `143 / 143` passing unit & property-based tests, and Phase 3 isolated deployment runbook.
- [`PROGRESS_REPORT_20260929.md`](./PROGRESS_REPORT_20260929.md): **Master Multi-Agent Progress Report** covering both **Agent 1 (`extracter_agent` Steps 1–28)** and **Agent 2 (`query_agent` Steps 1–7)**, consolidated 100% `.md`-only Spanner ingestion (`sync_markdown_bundle_to_spanner` & `scripts/purge_and_reload_spanner.py`), Dataplex Universal Catalog (`dataplex_v1`) & OpenLineage sync, and both 3-Pane Cloud Run Workbenches (`extracter-agent-web` and `okf-query-agent-web`).
- [`PROGRESS_REPORT_20260922.md`](./PROGRESS_REPORT_20260922.md): Detailed Step 1–28 historical execution log, multi-source extraction audits, zero-collision canonical resolution (Option A), and CodeMender security audit for `extracter_agent` and `query_agent`.
- [`QUERY_AGENT_EVAL_REPORT.md`](./QUERY_AGENT_EVAL_REPORT.md): Live OKF Spanner Graph-RAG Query Agent Evaluation Report (`100.00%` pass rate, `1.0000` tool trajectory precision, `1.0000` groundedness across all 8 query archetypes).

