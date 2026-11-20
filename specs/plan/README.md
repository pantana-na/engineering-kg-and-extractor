# Living Plan Progress Tracking (`specs/plan/`)

This directory tracks implementation progress, verification metrics, architectural decisions, and Root Cause Analysis (RCA) logs under the **Spec-Driven Development (SDD)** standard ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../_agents/rules/ai_sdlc_and_sdd_standards.md)).

> **Consolidated v2 Living Plan:** All active v2.0–v2.3 execution tracking, live GCP deployment inventory (`engineering-kg-demo`), test/eval metrics (`229` pytest tests passing), and Rule 13 RCA logs are maintained directly in **Section 10** of [`../features/SPEC-20261120-UNIFIED-WORKBENCH-V2.md`](../features/SPEC-20261120-UNIFIED-WORKBENCH-V2.md).

## Platform Status Snapshot

| Component | Runtime | Default Model | Status |
| :--- | :--- | :--- | :--- |
| **Unified Workbench (`okf-engineering-workbench`)** | Cloud Run Service (`asia-southeast1`, Native IAP, `3600s` timeout) | Selectable Gemini 4 allowlist | **Live & Verified** |
| **Batch Pipeline (`okf-pipeline-job`)** | Cloud Run Job (`4 vCPU / 8 GiB`, `24h` timeout) | `gemini-4-carbon` (+ `gemini-4-hydrogen` `LOW` vision failover) | **Live & Verified** |
| **Agent 1 (`extracter_orchestrator`)** | Google ADK / Vertex AI Agent Runtime (`8` Tools) | `gemini-4-carbon` | **Live & Verified** |
| **Agent 2 (`okf_spanner_query_orchestrator`)** | Google ADK / Vertex AI Agent Runtime (`7` Tools) | `gemini-4-hydrogen` | **Live & Verified** |
| **Test & Security Gate** | `pytest` + Hypothesis PBT + `node --check` + Ruff/Bandit | `229 passed, 2 skipped` | **Passing** |

## Naming Convention for Standalone Reports
- `PROGRESS_REPORT_<YYYYMMDD>.md`
