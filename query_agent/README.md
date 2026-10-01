# Agent 2: OKF Spanner Graph-RAG, Vector, FTS & Data Lineage Query Agent (`query_agent`)

Official **Google Agent Development Kit (`google-adk`)** Graph-RAG, hybrid search, 5-stage HAZOP, and data lineage retrieval agent powered by **`gemini-3.8-flash`** (`GEMINI_LOCATION=global`), backed **100% by Google Cloud Spanner (`okf-knowledge-spanner / okf_knowledge_graph`)** and **Google Cloud Dataplex Universal Catalog (`dataplex_v1`)**, and paired with the **3-Pane Spanner Graph & Retrieval Workbench UI (`okf-query-agent-web`)** on Google Cloud Run.

- **Root Documentation & Architecture:** [`../README.md`](../README.md)
- **Feature Specifications (SDD):**
  - [`../specs/features/SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT.md`](../specs/features/SPEC-20260929-OKF-SPANNER-GRAPH-RAG-AGENT.md)
  - [`../specs/features/SPEC-20260929-QUERY-AGENT-RETRIEVAL-WORKBENCH-UI.md`](../specs/features/SPEC-20260929-QUERY-AGENT-RETRIEVAL-WORKBENCH-UI.md)
- **Progress & Live Evaluation Reports:**
  - [`../specs/plan/PROGRESS_REPORT_20260929.md`](../specs/plan/PROGRESS_REPORT_20260929.md)
  - [`../specs/plan/QUERY_AGENT_EVAL_REPORT.md`](../specs/plan/QUERY_AGENT_EVAL_REPORT.md) (`100.00%` Pass Rate)
- **Vertex AI Agent Runtime (`agent_runtime`):** `projects/YOUR_PROJECT_NUMBER/locations/asia-southeast1/reasoningEngines/YOUR_QUERY_ENGINE_ID`
- **Cloud Run Workbench (`cloud_run`):** `okf-query-agent-web` (configured via `.env`)

---

## 1. Consolidated 100% `.md`-Only Spanner Purge, Reload & Incremental Sync

All `.md`-to-Spanner ingestion is consolidated into [`sync_markdown_bundle_to_spanner()`](./spanner/repository.py) and exposed via [`scripts/purge_and_reload_spanner.py`](../scripts/purge_and_reload_spanner.py) and [`scripts/ingest_okf_bundle_to_spanner.py`](../scripts/ingest_okf_bundle_to_spanner.py), operating **100% on `.md` files alone** (zero raw PDF scanning and zero LLM calls) and handling the full `.md` lifecycle (`ADDED`, `UPDATED`, `REMOVED`, `UNCHANGED`):

```bash
# 1. Clean Purge & Reload Cloud Spanner + Dataplex Catalog from OKF .md bundle
PYTHONPATH=. .venv/bin/python scripts/purge_and_reload_spanner.py \
  --bundle-dir build/okf_bundle \
  --bundle-version v1-acme-demo

# 2. Incremental / Mirror Sync (skips UNCHANGED .md files via MD5 hash)
PYTHONPATH=. .venv/bin/python scripts/ingest_okf_bundle_to_spanner.py \
  --no-purge \
  --bundle-dir build/okf_bundle
```

---

## 2. 7 Registered ADK `FunctionTools` (`query_agent/tools/spanner_rag_tools.py`)

| Tool | Spanner / Dataplex Execution |
| :--- | :--- |
| **`lookup_entity_and_parameters`** | Parameterized SQL lookup on `EngineeringEntities` & `FactAssertions` joined with `FactLineageEdges` and `RawSourceDocuments`. |
| **`hybrid_search_okf_spanner`** | Reciprocal Rank Fusion ($k=60$) combining 768-d `COSINE_DISTANCE` (`text-embedding-005`) and `SEARCH(ChunkTokens)` / `SEARCH_SUBSTRING(SubTokens)` on `OkfSectionChunks`. |
| **`traverse_equipment_connectivity_graph`** | Multi-hop ISO GQL traversal (`GRAPH OkfKnowledgeGraph MATCH ...`) across `CONNECTS_TO` and `MONITORS_OR_TRIPS` edges (`1..4` hops). |
| **`trace_data_lineage_and_conflicts`** | Bidirectional ISO GQL lineage audit (`BACKWARD_TO_PDF` and `FORWARD_FROM_PDF`) with `⚠️ CONFLICT` surfacing. |
| **`execute_multistage_risk_and_hazop_query`** | 5-Stage deterministic HAZOP & Risk Assessment dossier combining Risk Matrix rules, node design limits, upstream causes (GQL), downstream consequences (GQL), and SIS/PSV safeguards + conflict audit. |
| **`read_full_okf_concept_from_spanner`** | Primary-key lookup on `OkfConcepts` returning full Markdown and YAML frontmatter with zero GCS reads. |
| **`sync_or_inspect_knowledge_catalog`** | Inspects or synchronizes live governance aspects in **Google Cloud Dataplex Universal Catalog (`dataplex_v1.CatalogServiceClient`)** and emits **OpenLineage** run events. |

---

## 3. Running Locally, Deploying & Testing

```bash
# 1. Start the 3-Pane Spanner Retrieval Workbench UI (v2.2) locally on port 8081
PYTHONPATH=. .venv/bin/uvicorn query_agent.web_server:app --host 0.0.0.0 --port 8081 --reload

# 2. Deploy Separate Cloud Run Workbench (okf-query-agent-web)
./deploy.sh --target query_web

# 3. Run all 41 Unit & Hypothesis Property-Based Tests for query_agent & okf-query-agent-web
PYTHONPATH=. .venv/bin/pytest \
  tests/test_query_agent_unit.py tests/test_query_agent_property.py \
  tests/test_query_web_server_unit.py tests/test_query_web_server_property.py -q

# 4. Run the 120-Question Live Evaluation against agent_runtime + Cloud Spanner
PYTHONPATH=. .venv/bin/python -u evals/run_live_query_agent_eval.py --use-agent-runtime --concurrency 4
```

