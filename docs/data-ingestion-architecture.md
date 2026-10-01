# Dual-Mode Data Ingestion & Autonomous OKF v0.2 Extraction Architecture

> 📊 **Interactive Standalone HTML/SVG Diagram:** Open [`docs/data-ingestion-architecture.html`](./data-ingestion-architecture.html) in any browser (`xdg-open ./docs/data-ingestion-architecture.html`) to view the full dark-themed SVG architecture visualizer.

---

## 1. Architectural Overview

The **Chemical Engineering OKF Extracter Agent** (`extracter_orchestrator`) is an autonomous **Google Agent Development Kit (`google-adk`)** reasoning engine deployed on the **Gemini Enterprise Agent Platform (`agent_runtime`)** in `asia-southeast1` and powered by **`gemini-3.8-flash`** on the **Vertex AI Global Endpoint (`GEMINI_LOCATION=global`)**.

It ingests **20 synthetic engineering PDFs** (`data_sheets/`, `pid/`, `pfd/`, `operating_manuals/`, `standards/`) from **Google Cloud Storage (`gs://your-gcp-project-id-okf-knowledge/reference/raw/`)** or local [`reference/raw/`](../reference/raw/) and compiles them into **Open Knowledge Format (`OKF v0.2`)** Markdown knowledge bundles under **`gs://your-gcp-project-id-okf-knowledge/okf-bundles/acme-plant/`** and local `build/okf_bundle/`.

---

## 2. Dual Data Ingestion Modes (Mode A vs. Mode B)

The architecture supports two complementary ingestion workflows through the same unified 8-tool ADK agent without any hardcoded tags or regex routing:

```mermaid
flowchart LR
    subgraph ModeA["Mode A: Entity-Centric Ingestion (Equipment / Concept ID)"]
        A1["User Prompt / Eval Runner\n'Extract D-2304' or 'Extract sis-interlocks'\n(--dataset equipment)"]
        A2["Step 1: find_raw_documents_tool\nDiscovers ALL matching PDFs\n(DS-D2304_Z1.pdf + PID-23-0013_Z1.pdf + PFD-23-0005_Z1.pdf)"]
        A3["Step 2: process_raw_pdf_tool\nExtracts text, tables & 300 DPI vision\nacross all discovered PDFs in 1 turn"]
        A4["Step 4: generate_equipment_okf_tool\nReconciles all sources & writes\nequipment/D-2304.md + syncs to GCS"]
        A1 --> A2 --> A3 --> A4
    end

    subgraph ModeB["Mode B: Raw PDF File-by-File Incremental Ingestion"]
        B1["Turn 1: Ingest PDF #1\n'Process data_sheets/DS-D2304_Decomposer_Reactor_Z1.pdf'\n(--dataset file-by-file: 20 PDFs)"]
        B2["Creates sources/DS-D2304.md\n& equipment/D-2304.md\n(Mechanical design & nozzles)"]
        B3["Turn 2: Ingest PDF #2\n'Process pid/PID-23-0013_Decomposer_Reactor_Z1.pdf'"]
        B4["Step 3: inspect_existing_okf_concept_tool\n+ Step 4: Non-Destructive Read-Merge-Upsert\nEnriches D-2304.md & pressure-relief-valves.md"]
        B1 --> B2 --> B3 --> B4
    end
```

| Dimension | Mode A: Entity-Centric (Equipment / Concept ID) | Mode B: Raw PDF File-by-File (Document-Centric) |
| :--- | :--- | :--- |
| **Input Granularity** | Target entity tag or concept topic (e.g., `D-2304`, `V-2301`, `cumene-hydroperoxide`, `sis-interlocks`, `unit-2300-overview`). | Single raw PDF path (e.g., `reference/raw/data_sheets/DS-D2304_Decomposer_Reactor_Z1.pdf` or `reference/raw/pid/PID-23-0013_Decomposer_Reactor_Z1.pdf`). |
| **Discovery Pattern** | Multi-folder search across `data_sheets/`, `pid/`, `pfd/`, `operating_manuals/`, and `standards/` to gather all documents referencing the entity. | Direct ingestion of the specified PDF (`find_raw_documents_tool` $\rightarrow$ `process_raw_pdf_tool`) + inspection of existing concepts via `inspect_existing_okf_concept_tool`. |
| **Synthesis & Persistence** | Synthesizes the complete cross-referenced `.md` concept in a single trajectory (and merges with any existing file on disk). | Always writes/updates `sources/<doc-slug>.md` **and** incrementally creates or merges (`Read-Merge-Upsert`) every equipment, instrument, unit, hazard, or procedure concept in that PDF. |
| **Evaluation Dataset** | [`evals/datasets/extraction_eval.jsonl`](../evals/datasets/extraction_eval.jsonl) (`--dataset equipment`). | [`evals/datasets/raw_file_by_file_eval.jsonl`](../evals/datasets/raw_file_by_file_eval.jsonl) (`20` Synthetic Raw PDFs, `--dataset file-by-file`). |

---

## 3. How the Agent Extracts, Reconciles & Synthesizes Data (6-Step Pipeline)

Every user request or evaluation turn executes a deterministic 6-step pipeline inside [`extracter_orchestrator`](../extracter_agent/agent/orchestrator.py):

```mermaid
sequenceDiagram
    autonumber
    participant Client as Cloud Run Web UI (/dev-ui/) or Eval CLI
    participant Guard as Model Armor Guardrail (before_agent_callback)
    participant Agent as extracter_orchestrator (Gemini 3.8 Flash Global)
    participant PDF as PDF & Vision Tools (PyMuPDF + 300 DPI Vision)
    participant Merge as Read-Merge-Upsert Engine (synthesizer.py)
    participant GCS as GCS & Local Bundle Store

    Client->>Guard: User Prompt (Mode A: Tag/Concept OR Mode B: Raw PDF File)
    Guard->>Guard: Check prompt injection & path traversal
    Guard->>Agent: Verified Prompt + Cognitive Intent Classification
    Agent->>PDF: Step 1: find_raw_documents_tool(query, subfolder)
    PDF-->>GCS: List blobs + check size_bytes & base64 MD5 (blob.md5_hash)
    PDF-->>Agent: Matching PDF paths & GCS URIs
    Agent->>PDF: Step 2: process_raw_pdf_tool(pdf_filename, subfolder)
    alt Digital PDF Text/Tables Present (chars >= 50)
        PDF->>PDF: Extract digital text, tables & tag candidates via PyMuPDF
    else Vector CAD Drawing (P&ID / PFD) or Scanned Sheet (chars < 50)
        PDF->>PDF: Render pages at 300 DPI + check SHA-256 Multimodal Cache
        PDF->>Agent: 300 DPI Gemini 3.8 Flash visual extraction (loops, nozzles, ratings)
    end
    opt Incremental Enrichment of Existing Concepts
        Agent->>Merge: Step 3: inspect_existing_okf_concept_tool(concept_id / source_filter)
        Merge-->>Agent: Existing frontmatter, sources, ## headings & Markdown tables
    end
    Agent->>Merge: Step 4: generate_equipment_okf_tool OR generate_okf_concept_tool (merge_existing=True)
    Merge->>Merge: Revision-Aware Reconciliation (_is_same_source_or_revision_update)\n- Same doc / newer rev (Rev Z0 -> Rev Z1): Update in-place (NO CONFLICT)\n- Cross-doc / multi-sheet discrepancy: Emit ⚠️ CONFLICT callout\n- Merge equipment tables OR Markdown ## sections & table rows
    Merge->>GCS: Write OKF v0.2 .md locally + immediate GCS upload
    Agent->>GCS: Step 5 & 6: build_okf_indexes_and_validate_tool()\nCompile Master index.md + log.md & verify 0 broken links
    Agent-->>Client: Grounded Engineering Summary + Validation Report
```

### Detailed Breakdown of Each Extraction Stage

#### Stage 0: Pre-Flight Security Guardrail & Cognitive Intent Classification
- **Model Armor Hook ([`before_agent_callback`](../extracter_agent/agent/guardrails.py)):** Intercepts every incoming prompt before LLM tool reasoning to block prompt injection, system instruction overrides, and path traversal attempts (`../`).
- **Cognitive Intent Classifier ([`CognitiveClassifier`](../extracter_agent/agent/classifier.py)):** Uses `gemini-3.8-flash` (`location="global"`) with structured `IntentClassificationResult` output to classify requests into the canonical intents (`EXTRACT_DOCUMENT`, `GENERATE_OKF_CONCEPT`, `BUILD_OKF_BUNDLE`, `VALIDATE_OKF_BUNDLE`, `EXPORT_TO_GCS`, `OTHERS`) with zero regex heuristics.

#### Stage 1: Raw Document Discovery & MD5 Cache Verification ([`find_raw_documents_tool`](../extracter_agent/tools/pdf_tools.py))
- Searches across all 5 raw engineering subfolders (`data_sheets/`, `pid/`, `pfd/`, `operating_manuals/`, `standards/`).
- When `USE_GCS_STORAGE=true`, lists blobs directly from `gs://your-gcp-project-id-okf-knowledge/reference/raw/` and records each blob's `size_bytes`, `md5_hash` (base64 MD5), and `updated` timestamp.
- When downloading a PDF to `/tmp/extracter_gcs_raw_cache/`, verifies **both** file size and base64 MD5 digest (`_compute_file_md5_b64`). If a PDF in GCS was overwritten in-place under the same filename, the cache automatically invalidates and re-downloads the fresh PDF.

#### Stage 2: Hybrid PDF Parsing & 300 DPI Multimodal Vision ([`process_raw_pdf_tool`](../extracter_agent/tools/pdf_tools.py) & [`processor.py`](../extracter_agent/pdf/processor.py))
- **Digital Text & Table Stream (`PyMuPDF`):** Extracts native text blocks, structured tables, and candidate equipment/instrument tags per page.
- **Vector CAD & Raster Detection:** AutoCAD P&IDs (`pid/*.pdf`), PFDs (`pfd/*.pdf`), and scanned mechanical vessel sketches often contain `< 50` embedded characters (`is_vector_drawing: True`).
- **300 DPI Multimodal Visual Extraction (`extract_pdf_multimodal_summary`):**
  - Renders pages at **300 DPI** and sends them to **`gemini-3.8-flash` (`GEMINI_LOCATION=global`)** to visually read instrument bubbles, stacked/redundant loops (`LT-0601/0602/0603`, `FT-0401A/B/C`), control valve failure actions (`FC`/`FO`), PSV set pressures, nozzle schedules, and decimal values (`0.5` vs `5.0 kg/cm²g`).
  - **Two-Tier SHA-256 Vision Cache:** Caches multimodal extraction results by file SHA-256 digest in `/tmp/extracter_multimodal_cache/` and `gs://.../cache/multimodal/`, attaching the multimodal transcript once per PDF to prevent context window bloat.

#### Stage 3: Bundle State Inspection ([`inspect_existing_okf_concept_tool`](../extracter_agent/tools/okf_tools.py))
- Before updating shared concepts (`equipment/<TAG>`, `instruments/<register>`, `units/<unit>`, `hazards/<chemical>`), the agent can inspect the existing `.md` file by `concept_id` or query all concepts citing a specific PDF via `source_filter`.
- Returns existing frontmatter `sources`, `tags`, `entity_metadata`, and `body_markdown` so the agent reuses existing `## <Heading>` names and Markdown table columns.

#### Stage 4: Revision-Aware Read-Merge-Upsert & Conflict Detection ([`synthesizer.py`](../extracter_agent/okf/synthesizer.py))
Both synthesis tools perform **non-destructive Read-Merge-Upsert (`merge_existing=True` by default)**:

1. **Structured Equipment Merging ([`merge_equipment_entity_with_existing`](../extracter_agent/okf/synthesizer.py#L610-L756)):**
   - Parses the existing `equipment/<TAG>.md` document (`## Design Data`, `## Operating Conditions`, `## Instrumentation & Control Loops (P&ID)`, `## Connections & Stream Summary`, `## Hazards & Safeguards`, `## Function`).
   - Merges `design_data` and `operating_conditions` by normalized parameter name using [`_is_same_source_or_revision_update`](../extracter_agent/okf/synthesizer.py#L510-L522):
     - **Same Document or Newer Revision (`DS-D2304 Rev Z0` $\rightarrow$ `DS-D2304 Rev Z1`):** Updates the value and source citation **in-place** without generating a conflict warning, and replaces the superseded revision in `frontmatter.sources`.
     - **Different Active Documents (`DS-D2304` vs. `PID-23-0013`) or Different Sheets (`Sheet 1 Cover` vs. `Sheet 4 Sketch`):** Preserves both values in the table `note` column and automatically appends `⚠️ CONFLICT — <Parameter>: <Doc A> specifies <Val A>, whereas <Doc B> specifies <Val B> — verify with engineer before HAZOP` to `## Hazards & Safeguards`.
   - Merges `instruments` by normalized `tag` and `connections` by `stream_id`, and dynamically resolves every instrument tag link against actual `instruments/*.md` registers in the bundle via [`resolve_bundle_instrument_link`](../extracter_agent/okf/synthesizer.py#L72-L162) (zero hardcoded ISA prefix tables).

2. **Non-Equipment Concept & Shared Register Table Merging ([`merge_markdown_bodies`](../extracter_agent/okf/synthesizer.py#L879-L934)):**
   - Used by [`generate_okf_concept_tool`](../extracter_agent/tools/okf_tools.py#L221-L361) for `instruments/`, `units/`, `hazards/`, `procedures/`, `troubleshooting/`, `parameters/`, `hazop/`, and `sources/`.
   - Splits existing and incoming Markdown bodies into `## <Heading>` blocks, retains any `## <Heading>` sections from earlier PDFs omitted in the new turn, merges Markdown table rows by normalized first-column key (`Tag`, `Parameter`, `Stream`), applies revision-aware source supersession on the `Source`/`Drawing` column, and preserves top-level `> ⚠️ **CRITICAL PROCESS SAFETY / DISCREPANCY WARNING:**` blockquotes and bullet lists.

#### Stage 5 & 6: Master Catalog Indexing, OKF v0.2 Validation & Parallel GCS Sync ([`indexer.py`](../extracter_agent/okf/indexer.py), [`validator.py`](../extracter_agent/okf/validator.py), [`exporter.py`](../extracter_agent/gcs/exporter.py))
- Compiles the progressive disclosure Master Catalog (`index.md`, `equipment/index.md`) and chronological audit log (`log.md`).
- Validates 100% OKF v0.2 YAML frontmatter compliance, trust-tier monotonicity, and **zero broken internal Markdown links**.
- Syncs all updated files to `gs://your-gcp-project-id-okf-knowledge/okf-bundles/acme-plant/` using a 16-worker `ThreadPoolExecutor` with base64 MD5 digest verification (`compute_file_md5_b64` vs. `blob.md5_hash`).
