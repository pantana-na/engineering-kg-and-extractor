# Feature Specifications (`specs/features/`)

This directory contains formal **Feature Specifications** and architectural change proposals authored prior to implementation across all agents and Cloud Run services.

## Feature Authoring Guidelines

Every feature document in this directory must be created using the official template at [`specs/templates/sdd-template.md`](../templates/sdd-template.md) and adhere to the **Spec-Driven Development (SDD)** standard ([`_agents/rules/spec_driven_development.md`](../../_agents/rules/spec_driven_development.md)).

### Required Document Sections
1. **Problem Statement & Objectives:** Context, Goals, and explicit Non-Goals.
2. **System Architecture & Component Interaction:**
   - Explicit runtime allocation (Agent Platform `agent_runtime` vs Cloud Run `cloud_run`).
   - Sequence/flow diagram showing client, proxy, ADK orchestrator, and data stores.
3. **Data Models & Type Contracts:** Single source of truth TypeScript types, Pydantic schemas, or SQL DDL.
4. **API Contracts & Integrations:** Endpoints, request/response bodies, HTTP status codes, error models.
5. **UI/UX & Behavioral Specifications:** Client state transitions, loading states, error boundaries.
6. **DevOps, Security & Governance Checklist:** Alignment with the 14 repository standards (CodeMender SAST, Cloud Run `/healthz`, ADK agent platform runtime, etc.).
7. **Step-by-Step Implementation Plan & Test Design:**
   - Granular steps from foundational models to UI.
   - **Deterministic Unit Tests** for every step.
   - **Generative Property-Based Tests (PBT)** for every step.
   - **Live Environment Evaluation (`agents-cli eval`)** for all agent reasoning flows.
   - Enforcement of the **4-Step RCA Protocol** if any test fails (zero quick fixes or regex patches).
8. **Plan Progress Tracking & Living Spec Synchronization:** Linkage to `specs/plan/` and zero spec drift.

---

## Active Feature Specifications Registry (All Agents)

| Spec ID | Target Agent / Service | Runtime | Status |
| :--- | :--- | :--- | :--- |
| [`SPEC-20260922-OKF-EXTRACTER-AGENT.md`](./SPEC-20260922-OKF-EXTRACTER-AGENT.md) | **Agent 1: Autonomous OKF Extracter Agent (`extracter_agent`) & 3-Pane Extraction Workbench UI (`extracter-agent-web`)** | `agent_runtime` + `cloud_run` (`extracter-agent-web`) | **Implemented & Verified (`Steps 1–25`)** |
| [`SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT.md`](./SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT.md) | **Agent 2: OKF Spanner Graph-RAG Query Agent (`query_agent`), 100% `.md`-Only Spanner Lifecycle Sync (`sync_markdown_bundle_to_spanner`) & Dataplex Catalog (`dataplex_v1`)** | `agent_runtime` + Cloud Spanner (`okf_knowledge_graph`) | **Implemented & Verified (`100%` Live Eval)** |
| [`SPEC-20260929-QUERY-AGENT-RETRIEVAL-WORKBENCH-UI.md`](./SPEC-20260929-QUERY-AGENT-RETRIEVAL-WORKBENCH-UI.md) | **Agent 2 Workbench: 3-Pane Interactive Spanner Graph & Retrieval Workbench UI (`okf-query-agent-web`)** | `cloud_run` (`okf-query-agent-web`) | **Implemented & Verified in Production** |
| [`SPEC-20261001-REPOSITORY-SANITIZATION-AND-SYNTHETIC-DATASET.md`](./SPEC-20261001-REPOSITORY-SANITIZATION-AND-SYNTHETIC-DATASET.md) | **Repository Sanitization, 20 Synthetic Engineering PDFs & Isolated Cloud Environment Deployment** | `agent_runtime` + `cloud_run` + Cloud Spanner (`okf_demo_graph`) | **Phase 2 Completed (`Steps 1–3` Done, `Phase 3` Queued)** |

## Document Naming Convention
- `SPEC-<YYYYMMDD>-<FEATURE_NAME>.md` (e.g. `SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT.md`)
