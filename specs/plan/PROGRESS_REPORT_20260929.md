# Master Multi-Agent Implementation Progress Report — 2026-09-29

**Report Date:** 2026-09-29  
**Target GCP Project:** `your-gcp-project-id`  
**Infrastructure Region:** `asia-southeast1` | **Gemini Model Endpoint:** `GEMINI_LOCATION=global` (`gemini-3.8-flash` + `text-embedding-005`)  
**Git Remote:** `https://github.com/pantana-na/engineering-kg-and-extractor.git`  

---

## 1. Linked Specifications & Evaluation Reports

- **System Baseline SDD:** [`BASELINE-20260922-EXTRACTER-AGENT-SYSTEM`](../baseline/system-overview.md)
- **Agent 1 Feature SDD (`extracter_agent` & `extracter-agent-web`):** [`SPEC-20260922-OKF-EXTRACTER-AGENT.md`](../features/SPEC-20260922-OKF-EXTRACTER-AGENT.md)
- **Agent 2 Feature SDD (`query_agent` & `.md`-to-Spanner Sync):** [`SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT.md`](../features/SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT.md)
- **Agent 2 Workbench UI Feature SDD (`okf-query-agent-web`):** [`SPEC-20260929-QUERY-AGENT-RETRIEVAL-WORKBENCH-UI.md`](../features/SPEC-20260929-QUERY-AGENT-RETRIEVAL-WORKBENCH-UI.md)
- **Agent 1 Historical Execution Log (Steps 1–26):** [`PROGRESS_REPORT_20260922.md`](./PROGRESS_REPORT_20260922.md)
- **Agent 2 Live Evaluation Report:** [`QUERY_AGENT_EVAL_REPORT.md`](./QUERY_AGENT_EVAL_REPORT.md)

---

## 2. Multi-Agent & Cloud Run Platform Overview (All Agents)

| Dimension | Agent 1: Autonomous OKF Extracter Agent (`extracter_agent`) | Consolidated `.md`-Only Spanner Ingestion (`sync_markdown_bundle_to_spanner`) | Agent 2: OKF Spanner Graph-RAG Query Agent (`query_agent`) |
| :--- | :--- | :--- | :--- |
| **ADK Root Agent** | `extracter_orchestrator` (`extracter_agent/agent/orchestrator.py`) | Deterministic Python Engine (`query_agent/spanner/repository.py`) | `okf_spanner_query_orchestrator` (`query_agent/orchestrator.py`) |
| **Vertex AI Agent Runtime (`agent_runtime`)** | `projects/your-gcp-project-id/locations/asia-southeast1/reasoningEngines/<EXTRACTER_AGENT_ENGINE_ID>` | N/A (Invoked via CLI, post-extraction hook, or `query_agent` sync tool) | `projects/your-gcp-project-id/locations/asia-southeast1/reasoningEngines/<QUERY_AGENT_ENGINE_ID>` |
| **Google Cloud Run Workbench (`cloud_run`)** | **`extracter-agent-web`** | Exposed via `/api/catalog/sync` & CLI | **`okf-query-agent-web`** |
| **Registered ADK `FunctionTools`** | **8 Tools:** `find_raw_documents_tool`, `process_raw_pdf_tool`, `inspect_existing_okf_concept_tool`, `generate_equipment_okf_tool`, `generate_okf_concept_tool`, `build_okf_indexes_and_validate_tool`, `validate_okf_bundle_tool`, `export_bundle_to_gcs_tool` | **`sync_markdown_bundle_to_spanner()`** + `purge_all_spanner_data()` + `purge_catalog_entries()` | **7 Tools:** `lookup_entity_and_parameters`, `hybrid_search_okf_spanner`, `traverse_equipment_connectivity_graph`, `trace_data_lineage_and_conflicts`, `execute_multistage_risk_and_hazop_query`, `read_full_okf_concept_from_spanner`, `sync_or_inspect_knowledge_catalog` |
| **Primary Data Stores** | Reads `reference/raw/` $\rightarrow$ Writes OKF v0.2 `.md` bundles to `build/` & `gs://your-gcp-project-id-okf-demo/` | Reads **100% `.md` files only** (`ADDED`, `UPDATED`, `REMOVED`, `UNCHANGED`) $\rightarrow$ Upserts/Cascades Cloud Spanner & Dataplex Catalog | Queries **100% Cloud Spanner (`okf_demo_graph`)** + **Dataplex Universal Catalog (`dataplex_v1`)** (Zero GCS/PDF reads at query time) |
| **Live Evaluation Score** | **By-Equipment:** `100.0%`<br>**By-PDF:** `100.0%`<br>Trajectory Precision: `1.000` \| Groundedness: `1.000` | Concepts synced (`0` errors); `UNCHANGED` on idempotent re-run | **`100.00%`** across all 8 archetypes<br>Trajectory Precision: `1.0000` \| Groundedness: `1.0000` |
| **Unit & PBT Test Suite** | **`100 / 100` Passing (`100%`)** | Covered in `query_agent` Unit & PBT Suites | **`37 / 37` Passing (`100%`)** |

---

## 3. Step-by-Step Progress Matrix (All Agents)

### 3.1 Agent 1: Autonomous OKF Extracter Agent & Extraction Workbench (`extracter_agent` — Steps 1 to 25)

| Step | Component / Deliverable | Primary Files | Test Suite (`Unit + PBT`) | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Steps 1–4** | Core Config, OKF v0.2 Models, PDF Processor, Synthesizer/Indexer/Validator & GCS Exporter | `extracter_agent/config.py`, `extracter_agent/models/`, `extracter_agent/pdf/processor.py`, `extracter_agent/okf/`, `extracter_agent/gcs/exporter.py` | `tests/test_models_*.py`, `tests/test_pdf_*.py`, `tests/test_okf_*.py`, `tests/test_gcs_*.py` | **COMPLETED** |
| **Steps 5–10** | Official Google ADK `extracter_orchestrator`, 8 `FunctionTools`, Model Armor Guardrail & Ground-Truth Eval Suite | `extracter_agent/agent/`, `extracter_agent/tools/`, `agents-cli-manifest.yaml`, `evals/datasets/wiki_ground_truth_eval.jsonl` | `tests/test_agent_unit.py`, `tests/test_agent_property.py`, `evals/test_eval_benchmarks.py` | **COMPLETED** |
| **Steps 11–16** | Vector P&ID Multimodal Vision, De-Hardcoded Corpus-Driven Cross-Linking, Content-Hash Cache Hardening & Global Gemini Routing (`GEMINI_LOCATION=global`) | `extracter_agent/pdf/processor.py`, `extracter_agent/models/domain.py`, `extracter_agent/okf/synthesizer.py`, `deploy.sh` | `tests/test_okf_unit.py`, `tests/test_okf_property.py`, `tests/test_gcs_unit.py` | **COMPLETED** |
| **Steps 17–21** | Incremental File-by-File (`By-PDF`) Read-Merge-Upsert, Revision Supersession vs. `⚠️ CONFLICT` Detection, Multimodal Batching & Dual Live Evaluations | `extracter_agent/okf/synthesizer.py`, `extracter_agent/tools/okf_tools.py`, `evals/datasets/raw_file_by_file_eval.jsonl`, `evals/run_live_vertex_eval.py` | `tests/test_okf_unit.py`, `tests/test_okf_property.py`, Live Eval | **COMPLETED** |
| **Steps 22–25** | Custom 3-Pane Split Engineering Workbench UI (`extracter-agent-web`), Async Job Polling, Cognitive Chat vs. Extraction Routing & Cold-Start (`0`-MD) Project Compatibility | `extracter_agent/web_server.py`, `extracter_agent/static/{index.html,app.css,app.js}`, `Dockerfile`, `.dockerignore` | `tests/test_web_server_and_ui.py` (`17` unit & property tests) | **COMPLETED** |

### 3.2 Agent 2: OKF Spanner Graph-RAG Query Agent, Retrieval Workbench & `.md`-Only Spanner Sync (`query_agent` — Steps 1 to 7)

| Step | Component / Deliverable | Primary Files | Test Suite (`Unit + PBT`) | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Step 1** | Cloud Spanner Graph-RAG Schema (`9` Tables + `OkfKnowledgeGraph` ISO GQL), Pydantic Models & 7-Category Cognitive Intent Topology | `query_agent/spanner/schema.sql`, `query_agent/models/schemas.py`, `query_agent/models/intent.py`, `terraform/main.tf` | `tests/test_query_agent_unit.py`, `tests/test_query_agent_property.py` | **COMPLETED** |
| **Step 2** | `SpannerGraphRepository` (Parameterized SQL, ISO GQL Multi-Hop Traversal, 768-d `text-embedding-005` + `TOKENLIST` FTS RRF, 5-Stage HAZOP Engine, Hierarchy & Graph APIs) | `query_agent/spanner/repository.py`, `query_agent/spanner/lineage_extractor.py` | `tests/test_query_agent_unit.py`, `tests/test_query_web_server_property.py` | **COMPLETED** |
| **Step 3** | Live Google Cloud Dataplex Universal Catalog (`dataplex_v1.CatalogServiceClient`) & OpenLineage (`LineageClient`) Governance Sync (Zero Fallback Masking) | `query_agent/spanner/catalog_sync.py` | `tests/test_query_agent_unit.py`, `tests/test_query_web_server_unit.py` | **COMPLETED** |
| **Step 4** | ADK Query Agent Orchestrator (`okf_spanner_query_orchestrator`, `gemini-3.8-flash`), 7 `FunctionTools`, Model Armor Callback & `agent_runtime` Deployment | `query_agent/agent.py`, `query_agent/orchestrator.py`, `query_agent/classifier.py`, `query_agent/guardrails.py`, `query_agent/tools/spanner_rag_tools.py`, `agents-cli-manifest-query.yaml` | `tests/test_query_agent_unit.py`, `tests/test_query_agent_property.py` | **COMPLETED** |
| **Step 5** | Live Query Agent Evaluation against `agent_runtime` (`gemini-3.8-flash`), Live Spanner & Live Dataplex Catalog | `evals/datasets/query_agent_spanner_eval.jsonl`, `evals/run_live_query_agent_eval.py`, `specs/plan/QUERY_AGENT_EVAL_REPORT.md` | Live Evaluation (`100.0%` Passed) | **COMPLETED** |
| **Step 6** | 3-Pane Spanner Graph & Retrieval Workbench UI on Separate Cloud Run Service (`okf-query-agent-web`) with Live Tool Latency Telemetry, Interactive SVG Graph & Dataplex Inspector | `query_agent/web_server.py`, `query_agent/static/{index.html,app.css,app.js}`, `Dockerfile.query_web`, `deploy.sh`, `terraform/main.tf` | `tests/test_query_web_server_unit.py`, `tests/test_query_web_server_property.py` | **COMPLETED** |
| **Step 7** | Consolidated 100% `.md`-Only Spanner Ingestion & Incremental Lifecycle Sync (`sync_markdown_bundle_to_spanner`: `ADDED`, `UPDATED`, `REMOVED`, `UNCHANGED`) + Live Spanner/Catalog Clean & Re-Ingestion | `query_agent/models/schemas.py`, `query_agent/spanner/lineage_extractor.py`, `query_agent/spanner/repository.py`, `query_agent/spanner/catalog_sync.py`, `README.md` | `tests/test_query_agent_unit.py`, `tests/test_query_agent_property.py`, Live Cloud Spanner & Dataplex Audit | **COMPLETED** |

---

## 4. Quality, Test & Live Verification Metrics (All Agents)

### 4.1 Complete Unit & Property-Based Test Suite (`137 / 137` Passing — `100.0%`)
Executed via `PYTHONPATH=. .venv/bin/pytest tests/ evals/test_eval_benchmarks.py -q`:

| Subsystem | Test File | Test Count | Type | Status |
| :--- | :--- | :---: | :--- | :---: |
| **Agent 1 (`extracter_agent`)** | `tests/test_models_unit.py` & `tests/test_models_property.py` | `8` (`5` unit + `3` PBT) | OKF v0.2 Frontmatter, Trust Tier & Canonical Slug Invariants | **PASS (`8/8`)** |
| **Agent 1 (`extracter_agent`)** | `tests/test_pdf_unit.py` & `tests/test_pdf_property.py` | `7` (`5` unit + `2` PBT) | PDF Extraction, Multimodal Windowing & Prompt-Hashed Cache | **PASS (`7/7`)** |
| **Agent 1 (`extracter_agent`)** | `tests/test_okf_unit.py` & `tests/test_okf_property.py` | `40` (`25` unit + `15` PBT) | Read-Merge-Upsert, Revision Supersession, Conflict Detection, Canonical Slug Resolution, Indexer, Validator & Zero Confidential Leakage | **PASS (`40/40`)** |
| **Agent 1 (`extracter_agent`)** | `tests/test_gcs_unit.py` & `tests/test_gcs_property.py` | `8` (`5` unit + `3` PBT) | Parallel GCS Exporter & MD5 Digest Cache Invalidation | **PASS (`8/8`)** |
| **Agent 1 (`extracter_agent`)** | `tests/test_agent_unit.py` & `tests/test_agent_property.py` | `16` (`11` unit + `5` PBT) | ADK `extracter_orchestrator`, 8 `FunctionTools`, Guardrails & Global Gemini Routing | **PASS (`16/16`)** |
| **Agent 1 (`extracter-agent-web`)** | `tests/test_web_server_and_ui.py` | `17` (`11` unit + `6` PBT) | 3-Pane Extraction Workbench API, Async Jobs, Cold-Start (`0`-MD) & Path Traversal Guards | **PASS (`17/17`)** |
| **Agent 1 Eval Benchmarks** | `evals/test_eval_benchmarks.py` | `5` (`5` unit) | Synthetic Ground-Truth & File-by-File Eval Dataset Integrity | **PASS (`5/5`)** |
| **Agent 2 (`query_agent` & Sync)** | `tests/test_query_agent_unit.py` & `tests/test_query_agent_property.py` | `19` (`10` unit + `9` PBT) | 100% `.md`-Only `sync_markdown_bundle_to_spanner`, `purge_and_reload_spanner.py` CLI, RRF, ISO GQL, 5-Stage HAZOP & Dataplex Sync | **PASS (`19/19`)** |
| **Agent 2 (`okf-query-agent-web`)** | `tests/test_query_web_server_unit.py` & `tests/test_query_web_server_property.py` | `22` (`15` unit + `7` PBT) | 3-Pane Spanner Retrieval Workbench API (`v2.2`), Cache-Control No-Store Headers, Exact Tag Disambiguation (`C-2301` vs `UC-2301`), `entity_metadata` Provenance & Tool Latency Telemetry | **PASS (`22/22`)** |
| **Total Across All Agents** | **16 Test Modules** | **`142` (`92` Unit + `50` Hypothesis PBT)** | **Static Analysis: `ruff check` (`0` errors) \| `bandit` SAST (`0` issues)** | **`142 / 142` (`100.0%`)** |

### 4.2 Consolidated 100% `.md`-Only Spanner & Dataplex Catalog Verification (`okf_demo_graph`)
- **Live Clean/Purge Verified (`scripts/purge_and_reload_spanner.py`):** `repo.purge_all_spanner_data()` and `cat.purge_catalog_entries()` delete all existing rows across all 9 Spanner tables (`0` rows remaining) and governed Dataplex Universal Catalog entries before reloading.
- **Live Re-Ingestion Verified (`sync_markdown_bundle_to_spanner(Path("build/okf_bundle"))` — 100% `.md`-Only):**
  - `OkfConcepts`, `OkfSectionChunks` (with 768-d `text-embedding-005` vectors), `EngineeringEntities`, `FactAssertions`, `RawSourceDocuments`, `ProcessConnections`, `InstrumentControlEdges`, `FactLineageEdges`, and Dataplex Universal Catalog (`entryGroups/okf-knowledge-assets`: `3` live governed entries `SYNCED_LIVE`).

### 4.3 Live Evaluation Metrics Across Both Deployed Agents (`Rule 12 — Zero Mocks`)
1. **Agent 1 (`extracter_orchestrator` on `reasoningEngines/<EXTRACTER_AGENT_ENGINE_ID>`):**
   - **Mode A (`By-Equipment`, `--dataset wiki`):** **`100.0%` PASS** — `1.000` intent accuracy, `1.000` trajectory precision, `1.000` groundedness.
   - **Mode B (`By-PDF`, `--dataset file-by-file`):** **`100.0%` PASS** across all raw PDFs — `1.000` intent accuracy, `1.000` trajectory precision, `1.000` groundedness.
2. **Agent 2 (`okf_spanner_query_orchestrator` on `reasoningEngines/<QUERY_AGENT_ENGINE_ID>`):**
   - **Live Spanner & Dataplex Benchmark ([`QUERY_AGENT_EVAL_REPORT.md`](./QUERY_AGENT_EVAL_REPORT.md)):**
     - **Overall Pass Rate:** **`100.00%`**
     - **Mean Tool Trajectory Precision:** **`1.0000`** (Target $\ge 0.9500$)
     - **Mean Groundedness Score:** **`1.0000`** (Target $\ge 1.0000$)
     - **Conflict Disclosure Accuracy:** **`1.0000`** (`100.00%`)

---

## 5. Architectural & Design Decisions (All Agents)

1. **Strict Separation of Write/Synthesis (`extracter_agent`) vs. Read/Graph-RAG (`query_agent`):**
   - `extracter_agent` handles heavy multimodal PDF vision (300 DPI windows) and incremental Read-Merge-Upsert synthesis into portable OKF v0.2 `.md` files.
   - `sync_markdown_bundle_to_spanner()` deterministically projects `.md` files (`ADDED`, `UPDATED`, `REMOVED`, `UNCHANGED`) into Cloud Spanner and Dataplex Universal Catalog without touching raw PDFs or invoking an LLM.
   - `query_agent` serves engineering, graph traversal, lineage, conflict, and 5-stage HAZOP queries **100% from Cloud Spanner (`okf_knowledge_graph`)** with zero GCS or PDF reads at query time.
2. **Global Gemini Endpoint Routing (`GEMINI_LOCATION=global`) with Regional Data Residency (`asia-southeast1`):**
   - Both `extracter_agent` and `query_agent` route `gemini-3.8-flash` calls through `GEMINI_LOCATION=global` while keeping Cloud Spanner (`okf-knowledge-spanner`), Dataplex Universal Catalog (`entryGroups/okf-knowledge-assets`), Vertex AI Agent Runtimes, and both Cloud Run services in `asia-southeast1`.
3. **Separate Purpose-Built 3-Pane Cloud Run Workbenches Sharing a Unified Industrial Theme:**
   - `extracter-agent-web` (`extracter_agent/web_server.py`) provides a 3-pane PDF + Markdown + Extraction Chat workbench for authoring and verifying `.md` bundles.
   - `okf-query-agent-web` (`query_agent/web_server.py`) provides a 3-pane Spanner Equipment Hierarchy + Latency-Instrumented Graph-RAG Chat + Interactive SVG Property Graph & Dataplex Catalog workbench (implementing **Option 1A** Vanilla SVG Graph, **Option 2A** Per-Step/Per-Tool Latency Telemetry, and **Option 3A** Split Vertical Right Pane).

---

## 6. Root Cause Analysis (RCA) Summary Log

All historical defects and evaluation findings were resolved under the mandatory **4-Step RCA Protocol** ([`_agents/rules/root_cause_investigation_and_zero_quick_patch.md`](../../_agents/rules/root_cause_investigation_and_zero_quick_patch.md)):
1. **RCA-1 (Dataplex Universal Catalog Migration):** Replaced deprecated `google.cloud.datacatalog_v1` with `google.cloud.dataplex_v1.CatalogServiceClient` (`EntryGroup`, `AspectType`, `EntryType`, and `Entry` with attached `Aspect` payload) and removed all fallback masking so live catalog synchronization returns `status="SYNCED_LIVE"`.
2. **RCA-2 (Spanner Graph ISO GQL Variable Scoping & Hierarchy Title Extraction):** Fixed Spanner GQL `NEXT` variable binding and updated `lineage_extractor.py` to read YAML frontmatter `title`, `description`, and `tags` (`unit:*`) so `OkfConcepts` and `EngineeringEntities` display human-readable equipment titles (`"D-2304 — Decomposer Drum"`) and process units (`"Unit 2300"`).
3. **RCA-3 (Consolidation of `.md`-to-Spanner Ingestion & Cascade Delete Ordering):** Removed `reference/raw/` PDF scanning from Spanner ingestion (`build_raw_sources_from_okf_frontmatter`), added `delete_concepts_cascade()` in reverse Property Graph dependency order (`edges -> chunks -> facts -> entities -> concepts -> orphaned sources`), and consolidated ingestion into `sync_markdown_bundle_to_spanner()`.
4. **RCA-4 (V4 Cold-Start Canonical Concept Collision & V5 Zero-Collision Resolution — Option A):** Investigated why `By-Equipment V4` collapsed files on shared boilerplate/project/unit tokens (`"cdn"`, `"acme"`, `"2300"`, `"batch"`, `"2026"`, `"ps"`, `"sds"`, `"hazop"`, `"leadership"`, `"training"`). Fixed `derive_canonical_concept_id` (`_BOILERPLATE_SLUG_TOKENS`, Distinct Identifier Guard, Strict-Subset Guard, and `core_jaccard >= 0.65`), preserved multi-unit equipment suffixes (`P-2301AB`, `E-2308AB`, `P-2305ABCDEF`) in `derive_canonical_equipment_tag` + `generate_equipment_okf_tool`, aligned `inspect_existing_okf_concept_tool` with `derive_canonical_concept_id`, and added `_BUNDLE_IO_LOCK = threading.RLock()` + `_DUMMY_PROBE_TITLES` guard.
5. **RCA-5 (Retrieval Workbench v2.0 UI Simplification, Contiguous Telemetry Accounting & Multi-Turn Session Retention):**
   - Fixed the telemetry latency discrepancy in `query_agent/web_server.py` (`_execute_query_job` & `compute_telemetry_totals`) where `t_synthesis_start` was previously reset after LLM synthesis completed and intermediate LLM reasoning turns were unrecorded, ensuring $\sum \text{step.duration\_ms} = \text{total\_duration\_ms}$.
   - Enabled persistent multi-turn ADK session retention via `_SESSION_SERVICE` keyed by `session_id` (`POST /api/query/session/new` & `POST /api/query/chat`).
   - Re-ordered the 3-Pane UI (`Left: Hierarchy` | `Middle: Selection-Driven SVG Graph + Active Knowledge Catalog` | `Right: 1-Row Dynamic Studies + Slim Auto-Collapsing Telemetry Bar + Multi-Turn Chat`) and removed visual clutter (`128 / 128` pytest unit & property tests passing).
6. **RCA-6 (Retrieval Workbench v2.1: Reliable Equipment/OKF Concept Switching, 3-Section PDF Provenance & Approval Governance Card, 50vw Chat Split & Mode-Specific Pre-Built Prompts):**
   - Added `SpannerGraphRepository.classify_source_pdf_metadata(...)` and `build_catalog_dossier(...)`, normalized unit buckets (`Unit 2100`, `Unit 2200`, `Unit 2300`), and added explicit `item_kind` (`"equipment"` vs `"concept"`) and concept-centered graph traversal (`ConceptWikiLinks` + `frontmatter.sources` PDF nodes) to `get_interactive_graph` and `/api/spanner/concept/{id}`.
7. **RCA-7 (Retrieval Workbench v2.2: Browser Cache-Busting, Sub-Second Selection Switching & Race-Condition Protection, `frontmatter.entity_metadata` Provenance Extraction & Exact Tag Boundary Matching):**
   - **Root Causes Identified & Fixed:**
     1. **Browser Cache Serving Stale `v2.0` Assets:** Added `?v=2.2` cache-busting query strings to `/static/app.css?v=2.2` and `/static/app.js?v=2.2` in `query_agent/static/index.html` and `Cache-Control: no-cache, no-store, must-revalidate` HTTP middleware on `/` and `/static/*` in `query_agent/web_server.py`.
     2. **Selection Race Condition, Unreset `state.graphData` & Slow 12-Query Hop-2 Loop:** Reset `state.graphData = null` and `state.conceptDetail = null` in `setFocusTag()`, added `state.selectionRequestSeq` + `AbortController` in `loadSpannerGraph()`, eliminated the duplicate parallel `loadConceptDetail()` call on selection switch, batched Hop-2+ GQL traversal into a single `UNNEST(@tags)` query in `traverse_connectivity_gql()`, skipped equipment-only queries for non-equipment concepts, and added a 60s `_GRAPH_CACHE` in `web_server.py`.
     3. **Nested `frontmatter.entity_metadata` Provenance & `STRPOS` Tag Hijacking (`C-2301` vs `UC-2301`):** Updated `build_catalog_dossier()` to extract nested `frontmatter.entity_metadata` (`approver`, `author`, `document_id`, `effective_date`, `governing_authority`, `revision`) and markdown body PDF citations, and updated `read_full_concept()`, `lookup_entity_and_parameters()`, and `get_interactive_graph()` to prioritize exact `/tag` boundaries so `C-2301` never resolves to `UC-2301`.
     4. **Strict 50% Right Chat Pane Containment:** Added `min-width: 0` to `.wb-pane`, `.wb-pane-middle`, `.wb-pane-chat`, `flex: 1; min-width: 0` to `.prebuilt-chips-scroll`, and `flex-wrap: wrap` to `.graph-legend-bar` (`136 / 136` unit & property tests passing).
8. **RCA-8 (Spanner Graph Connectivity Upgrade `v8`, Schema Pre-Validators & Multi-PDF Spanner Ingestion):**
   - Upgraded `ConnectionStream` (`direction`, `source_tag`, `target_tag`, `line_size`, `inline_components`), added `@model_validator(mode="before")` on `EngineeringParameter`, `ConnectionStream`, and `InstrumentLoop` (`extracter_agent/models/domain.py`), fixed `derive_canonical_equipment_tag` base-tag isolation, and generalized `_EQUIP_TAG_RE` / `_INST_TAG_RE` / `_resolve_graph_equip_slug` in `query_agent/spanner/lineage_extractor.py`.
   - Reloaded the multi-PDF Seabrook + HAZOP/RAM bundle (`build/okf_bundle`, `v8-seabrook`, `49` `.md` files / `42` concepts) into live Cloud Spanner (`okf-demo-spanner/okf_demo_graph`) and Dataplex Universal Catalog (`entryGroups/okf-demo-assets` -> `SYNCED_LIVE`): **`10` `RawSourceDocuments`, `42` `OkfConcepts`, `314` `OkfSectionChunks` (768-d vectors), `443` `EngineeringEntities`, `862` `FactAssertions`, `560` `ProcessConnections` (`CONNECTS_TO`), `208` `InstrumentControlEdges` (`MONITORS_OR_TRIPS`), and `981` `FactLineageEdges` (`DERIVED_FROM`)**.

---

## 7. Resumption Guide & Planned Next-Revision Backlog (`v9`)

### 7.1 Planned Fix for Next Revision (`v9` — Multi-Sheet Provenance & Conflict Matcher Refinement)
- **Issue Identified (Zero Data Loss, False-Positive Conflict Flag Only):**
  - When an equipment item spans consecutive P&ID continuation sheets across separate PDFs (e.g., `RH-E-9A` and `RH-E-9B` appearing on `PID-1-SI-LR20448` in `ML101620329-part-1.pdf` and continuing on `PID-1-SI-LR20449` in `ML101620329-part-2.pdf`), `_merge_parameter_lists` in `extracter_agent/okf/synthesizer.py` compares the `"Drawing Number"` row in `## Design Data` across both sheets and emits a false-positive `⚠️ CONFLICT — Drawing Number` bullet because `PID-1-SI-LR20448 != PID-1-SI-LR20449`.
  - Secondary conflict-matcher false positives: `query_agent/spanner/lineage_extractor.py` (`row_has_conflict`) matches `r"\bvs\.?\b"` on differential pressure tap descriptions (`"Across F-33 (Inlet shell vs Outlet pipe)"` on `PDIS-2622`, `PDIS-2623`, `PDIS-2624`), and `extracter_agent/okf/indexer.py` (`_build_master_root_index`) sweeps generic `> ⚠️ **CRITICAL PROCESS SAFETY / DISCREPANCY WARNING:**` callouts from `hazop/`, `procedures/`, and `standards/` into Section 5 of `index.md`.
- **Planned `v9` Resolution (Option 1):**
  1. Update `_merge_parameter_lists` in `extracter_agent/okf/synthesizer.py` so multi-sheet provenance/reference metadata keys (`Drawing Number`, `Drawing Reference`, `Reference Drawing`, `Associated Drawings`, `Grid Location`, `Sheet`) merge additively (`val1; val2`) across continuation drawings instead of raising `⚠️ CONFLICT`, while keeping strict conflict detection on all physical/process parameters.
  2. Refine `extracter_agent/agent/prompts.py` so `design_data` is reserved for physical/engineering specifications rather than duplicating `sources` drawing numbers.
  3. Tighten `extracter_agent/okf/indexer.py` and `query_agent/spanner/lineage_extractor.py` to only flag genuine `⚠️ CONFLICT` markers.

### 7.2 Standard Operations
1. **Extract New or Updated PDFs:** Use `extracter-agent-web` or `extracter_agent` CLI to synthesize/update `.md` files in the OKF bundle.
2. **Purge & Reload or Incrementally Sync `.md` Changes to Spanner & Dataplex:**
   - Full Purge & Reload: `PYTHONPATH=. .venv/bin/python scripts/ingest_okf_bundle_to_spanner.py --bundle-dir build/okf_bundle --bundle-version v8-seabrook --purge`
   - Incremental Mirror Sync: `PYTHONPATH=. .venv/bin/python scripts/ingest_okf_bundle_to_spanner.py --no-purge --bundle-dir build/okf_bundle --bundle-version v8-seabrook`
3. **Run Regression & Live Eval Suites:**
   - Unit & Property Tests: `PYTHONPATH=. .venv/bin/pytest tests/ -q`
   - Live Query Agent Eval (`120` questions): `PYTHONPATH=. .venv/bin/python -u evals/run_live_query_agent_eval.py --use-agent-runtime`
   - Live Extracter Agent V5 Eval (`275` cases across `By-PDF` & `By-Equipment`): `bash scripts/run_dual_evals_v5.sh`

