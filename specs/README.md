# System Specifications & SDD Registry (`specs/`)

This directory serves as the **Single Source of Truth** for all formal specifications, baseline reverse-engineering documents, feature proposals, and implementation progress tracking under the **Spec-Driven Development (SDD)** mandate.

## Directory Structure

```
specs/
├── README.md                      # Index of all specifications and progress reports
├── templates/
│   ├── README.md                  # Specification authoring instructions and guidelines
│   └── sdd-template.md            # Standardized template with Implementation Plan & Testing sections
├── baseline/                      # Baseline SDDs for existing/brownfield code
│   └── README.md                  # Brownfield discovery protocol and baseline index
├── features/                      # Feature specifications and enhancement proposals
│   └── README.md                  # Feature specification drafting guide and active spec registry
└── plan/                          # Living implementation progress reports and milestone tracking
    └── README.md                  # Plan progress tracking protocol and execution logs index
```

---

## SDD Governance & Core Principles

All work in this repository is governed by the rules codified in [`_agents/rules/`](../_agents/rules/):

1. **Spec First, Code Second:** Code is a downstream artifact derived from specifications. Direct code changes without an approved specification and step-by-step implementation plan are strictly prohibited ([`_agents/rules/spec_driven_development.md`](../_agents/rules/spec_driven_development.md)).
2. **Brownfield Baseline First:** When modifying existing systems, reverse-engineer and document the "as-is" state under `specs/baseline/` before authoring feature changes.
3. **Mandatory Testing at Every Step:** Every implementation step must define and implement:
   - **Deterministic Unit Tests:** Happy paths, boundary conditions, error handling.
   - **Generative Property-Based Tests (PBT):** Mathematical and logical invariants tested across generative input spaces (e.g., `fast-check` in TS, `hypothesis` in Python).
4. **Runtime Separation of Responsibilities:**
   - **Conversational AI Agents & Tool Registries:** Built with official `google-adk` and deployed to the **Gemini Enterprise Agent Platform (`agent_runtime`)** ([`_agents/rules/google_adk_and_agent_runtime.md`](../_agents/rules/google_adk_and_agent_runtime.md)).
   - **Web Applications, API Proxies & Streaming Gateways:** Hosted on **Google Cloud Run (`cloud_run`)** ([`_agents/rules/devops_security_and_quality_standards.md`](../_agents/rules/devops_security_and_quality_standards.md)).
5. **Model-Driven Reasoning:** Agent intent routing and tool execution are strictly cognitive and model-driven; keyword heuristics, regex routing, and hardcoded fallback arrays are strictly forbidden.
6. **Live Environment Agent Evaluation:** Trajectory fidelity and tool selection precision ($\ge 95\%$) are continuously evaluated against the live environment via `agents-cli eval`.
7. **Mandatory Root Cause Investigation & Zero Quick-Patch Standard:** When tests or evals fail, developers/agents must execute the 4-step RCA protocol. Zero quick fixes, mockups, regex patches, or assertion weakening ([`_agents/rules/root_cause_investigation_and_zero_quick_patch.md`](../_agents/rules/root_cause_investigation_and_zero_quick_patch.md)).
8. **Zero Spec Drift:** Synchronize specification files in `specs/` whenever code contracts or behaviors change.
9. **Living Plan Progress Tracking:** Continuous execution reports, test verification metrics, and milestone statuses are maintained under `specs/plan/`.

---

## Active Specifications Registry

### 1. Baseline Specifications ([`specs/baseline/`](./baseline/))
- [`BASELINE-20260922-EXTRACTER-AGENT-SYSTEM`](./baseline/system-overview.md): Full baseline architecture, immutable reference data sources, environment parameters, and core invariants.

### 2. Feature Specifications ([`specs/features/`](./features/))
- [`SPEC-20260922-OKF-EXTRACTER-AGENT`](./features/SPEC-20260922-OKF-EXTRACTER-AGENT.md): Autonomous OKF Extracter Agent on Google ADK, Gemini Enterprise Agent Platform, PDF processing, and GCS publication.
- [`SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT`](./features/SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT.md): Separate ADK OKF Spanner Graph-RAG & Automated Data Lineage Query Agent (`query_agent`) on Gemini Enterprise Agent Platform (`agent_runtime`) backed by Cloud Spanner (`Spanner Graph` ISO GQL + Vector Search + Full-Text Keyword Search).
- [`SPEC-20260929-QUERY-AGENT-RETRIEVAL-WORKBENCH-UI`](./features/SPEC-20260929-QUERY-AGENT-RETRIEVAL-WORKBENCH-UI.md): 3-Pane Interactive Spanner Graph & Retrieval Workbench UI deployed as a separate Cloud Run service (`okf-query-agent-web`).
- [`SPEC-20261001-REPOSITORY-SANITIZATION-AND-SYNTHETIC-DATASET`](./features/SPEC-20261001-REPOSITORY-SANITIZATION-AND-SYNTHETIC-DATASET.md): Complete repository confidentiality sanitization, 20-document synthetic engineering PDF suite (`reference/raw/`), and isolated environment deployment verification.
- [`SPEC-20261005-MOC-AND-DOCUMENT-UPDATE-LIFECYCLE`](./features/SPEC-20261005-MOC-AND-DOCUMENT-UPDATE-LIFECYCLE.md): Management of Change (MOC) authority (`MOC_AUTHORITY` / `PENDING_REDRAFT`), topological removals/reroutes (`removed_instruments`, `removed_connections`), cross-filename supersession (`superseded_sources`), deterministic revision rank comparator (`compare_revision_tokens`), auto-clearing resolved conflicts, and `reference/raw/moc/` synthetic MOC fixture.

### 3. Plan Progress Reports ([`specs/plan/`](./plan/))
- [`PROGRESS_REPORT_20260922`](./plan/PROGRESS_REPORT_20260922.md): Implementation milestone tracking, unit & property-based test verification, and CodeMender security audit.
- [`PROGRESS_REPORT_20260929`](./plan/PROGRESS_REPORT_20260929.md): OKF Spanner Graph-RAG Query Agent (`100%` live eval pass rate on `gemini-3.8-flash`), Dataplex Universal Catalog (`dataplex_v1`) migration, 3-Pane Retrieval Workbench UI (`okf-query-agent-web`) Cloud Run deployment, and consolidated 100% `.md`-only Spanner ingestion & lifecycle sync (`Step 7` completed).
- [`PROGRESS_REPORT_20261001`](./plan/PROGRESS_REPORT_20261001.md): Repository sanitization, 20 synthetic engineering PDFs (`reference/raw/`), zero application logic changes (`143/143` tests passing), and Phase 3 isolated deployment runbook.
- [`PROGRESS_REPORT_20261005`](./plan/PROGRESS_REPORT_20261005.md): MOC authority (`PENDING_REDRAFT`), topological removals/reroutes, and document revision hardening progress tracker.
- [`QUERY_AGENT_EVAL_REPORT`](./plan/QUERY_AGENT_EVAL_REPORT.md): Live OKF Spanner Query Agent Evaluation Report (`100.00%` pass rate, `1.0000` trajectory precision, `1.0000` groundedness).

---

## Related Documentation
- **Agent Operating Manual:** [`AGENTS.md`](../AGENTS.md)
- **Governance Rules:** [`_agents/rules/`](../_agents/rules/)
- **Operational & Skill Reports:** [`docs/`](../docs/) (CodeMender SAST audits, GCP cost models, architecture diagrams)
