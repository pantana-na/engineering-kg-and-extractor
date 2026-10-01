# Agent 1: Autonomous OKF Extracter Agent (`extracter_agent`)

Official **Google Agent Development Kit (`google-adk`)** multimodal extraction and Open Knowledge Format (**OKF v0.2**) synthesis agent powered by **`gemini-3.8-flash`** (`GEMINI_LOCATION=global`), paired with the **3-Pane Split Engineering Extraction Workbench UI (`extracter-agent-web`)** on Google Cloud Run.

- **Root Documentation & Architecture:** [`../README.md`](../README.md)
- **Feature Specification (SDD):** [`../specs/features/SPEC-20260922-OKF-EXTRACTER-AGENT.md`](../specs/features/SPEC-20260922-OKF-EXTRACTER-AGENT.md)
- **Progress Reports:** [`../specs/plan/PROGRESS_REPORT_20260929.md`](../specs/plan/PROGRESS_REPORT_20260929.md) & [`../specs/plan/PROGRESS_REPORT_20260922.md`](../specs/plan/PROGRESS_REPORT_20260922.md)
- **Vertex AI Agent Runtime (`agent_runtime`):** `projects/YOUR_PROJECT_NUMBER/locations/asia-southeast1/reasoningEngines/YOUR_EXTRACTER_ENGINE_ID`
- **Cloud Run Workbench (`cloud_run`):** `extracter-agent-web` (configured via `.env`)

---

## 1. Core Capabilities & 8 ADK `FunctionTools`

| Tool (`extracter_agent/tools/`) | Responsibility |
| :--- | :--- |
| **`find_raw_documents_tool`** | Boundary-aware document discovery across `reference/raw/` (`data_sheets`, `pid`, `pfd`, `operating_manuals`, `standards`) locally and in GCS. |
| **`process_raw_pdf_tool`** | Native text extraction + adaptive 300 DPI Gemini 3.8 Flash multimodal vision windowing (`window_size=2` for vector CAD drawings, `window_size=4` for multi-sheet tables) with SHA-256 prompt-hashed caching. |
| **`inspect_existing_okf_concept_tool`** | Reads existing `.md` concepts or queries all concepts citing a specific raw PDF before incremental merging. |
| **`generate_equipment_okf_tool`** | Synthesizes or merges (`merge_existing=True`) `equipment/<TAG>.md` files with revision-aware parameter supersession, `⚠️ CONFLICT` detection, and dynamic instrument/stream cross-linking. |
| **`generate_okf_concept_tool`** | Synthesizes or merges (`merge_markdown_bodies` + `append_sections_markdown`) non-equipment OKF v0.2 concepts (`instruments/`, `hazards/`, `units/`, `procedures/`, `troubleshooting/`, `hazop/`, `sources/`). |
| **`build_okf_indexes_and_validate_tool`** | Builds progressive disclosure `index.md` files, the root Master Plant Catalog `index.md`, and `log.md`, and validates the bundle. |
| **`validate_okf_bundle_tool`** | Verifies YAML frontmatter, footnote joins, trust tiers, and `0` broken Markdown links. |
| **`export_bundle_to_gcs_tool`** | Parallel (`max_workers=16`) MD5-verified synchronization of `.md` bundles to Google Cloud Storage. |

---

## 2. Running Locally, Deploying & Testing

```bash
# 1. Start the 3-Pane Extraction Workbench UI locally on port 8080
PYTHONPATH=. .venv/bin/uvicorn extracter_agent.web_server:app --host 0.0.0.0 --port 8080 --reload

# 2. Deploy Agent Runtime & Cloud Run Workbench
./deploy.sh --target agent_runtime
./deploy.sh --target cloud_run

# 3. Run all 96 Unit & Hypothesis Property-Based Tests for extracter_agent
PYTHONPATH=. .venv/bin/pytest \
  tests/test_models_unit.py tests/test_models_property.py \
  tests/test_pdf_unit.py tests/test_pdf_property.py \
  tests/test_okf_unit.py tests/test_okf_property.py \
  tests/test_gcs_unit.py tests/test_gcs_property.py \
  tests/test_agent_unit.py tests/test_agent_property.py \
  tests/test_web_server_and_ui.py evals/test_eval_benchmarks.py -q
```
