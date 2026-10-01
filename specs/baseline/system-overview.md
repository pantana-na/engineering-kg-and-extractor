# Baseline Specification: Multi-Agent System Architecture & Reference Invariants

**Document ID:** BASELINE-20260922-EXTRACTER-AGENT-SYSTEM  
**Status:** Approved & Sanitized Open-Share Baseline  
**Last Updated:** 2026-10-01  

---

## 1. System Overview & Baseline Context

This repository (`https://github.com/pantana-na/engineering-kg-and-extractor.git`) hosts the **Chemical Engineering OKF Multi-Agent Knowledge Platform**, consisting of two autonomous cognitive AI agents built on the official **Google Agent Development Kit (`google-adk`)** and deployed on the **Gemini Enterprise Agent Platform (`agent_runtime`)**, paired with two dedicated 3-pane web workbenches deployed on **Google Cloud Run (`cloud_run`)**:

1. **Agent 1 — Autonomous OKF Extracter Agent (`extracter_agent` / `extracter_orchestrator`):** Ingests complex chemical engineering PDFs (process data sheets, P&IDs, PFDs, operating manuals, and standards) from `reference/raw/` (locally and in GCS), extracts structured domain knowledge via 300 DPI multimodal Gemini vision and native text parsing, and compiles cross-linked **Open Knowledge Format (OKF v0.2)** Markdown (`.md`) bundles stored in **Google Cloud Storage (GCS)**.
2. **Consolidated `.md`-Only Spanner Ingestion Engine (`sync_markdown_bundle_to_spanner`):** Deterministically synchronizes the OKF `.md` bundle extracted by `extracter_agent` (`ADDED`, `UPDATED`, `REMOVED`, `UNCHANGED`) into **Google Cloud Spanner (`okf-knowledge-spanner / okf_knowledge_graph`)** and **Google Cloud Dataplex Universal Catalog (`dataplex_v1`)** with zero raw PDF reads and zero LLM calls.
3. **Agent 2 — OKF Spanner Graph-RAG & Data Lineage Query Agent (`query_agent` / `okf_spanner_query_orchestrator`):** Answers engineering parameter lookups, multi-hop P&ID/PFD connectivity traversals (ISO GQL), hybrid 768-d Vector + Full-Text Search (RRF) queries, bidirectional PDF provenance & conflict (`⚠️ CONFLICT`) audits, 5-stage HAZOP & risk assessments, and Dataplex Catalog governance queries **100% from Cloud Spanner and Dataplex**.

---

## 2. Baseline Architecture & Runtime Decoupling

The repository enforces strict separation of concerns across two runtime environments:

| Dimension | Autonomous AI Agents & Reasoning Engines | Web Frontends, API Gateways & Workbenches |
| :--- | :--- | :--- |
| **Target Runtime** | **Gemini Enterprise Agent Platform (`agent_runtime`)** | **Google Cloud Run (`cloud_run`)** |
| **Deployed Artifacts** | 1. **`extracter_orchestrator`** (8 ADK `FunctionTool`s)<br>2. **`okf_spanner_query_orchestrator`** (7 ADK `FunctionTool`s) | 1. **`extracter-agent-web`** (`extracter_agent/web_server.py`)<br>2. **`okf-query-agent-web`** (`query_agent/web_server.py`) |
| **Deployment Mechanism** | `./deploy.sh --target agent_runtime` & `./deploy.sh --target query_agent` (`adk deploy agent_engine`) | `./deploy.sh --target cloud_run` & `./deploy.sh --target query_web` + Terraform (`terraform/`) |
| **Core Responsibilities** | LLM reasoning (`gemini-3.8-flash` via `GEMINI_LOCATION=global`), pre-flight Model Armor guardrails (`before_agent_callback`), tool execution, and live evaluation (`Rule 12`). | HTTP/HTTPS ingress, 3-pane interactive UI rendering, `/healthz` liveness probes, async job polling, and proxying to `agent_runtime` / Cloud Spanner / GCS / Dataplex. |
| **Governance Rule** | `_agents/rules/google_adk_and_agent_runtime.md` | `_agents/rules/devops_security_and_quality_standards.md` |

---

## 3. Sanitized Synthetic Raw Reference Materials (`reference/raw/` Only)

To ensure zero confidential or proprietary plant information is stored or shared in the repository while enabling a true end-to-end agentic workflow, `reference/wiki/` is completely removed and `reference/raw/` contains **20 synthetic chemical engineering PDF documents** (`Acme Petrochemical Demo Complex — Unit 2300`) generated deterministically by `scripts/generate_synthetic_reference.py` covering **all engineering document types and subtypes**:

### 3.1 Synthetic Raw Engineering Documents (`reference/raw/`)
Contains **20 primary synthetic engineering PDF files** across all 5 canonical subdirectories:
- `data_sheets/` (`8` PDFs): Multi-page equipment and instrument process data sheets covering every subtype:
  - Column/Vessel (`DS-V2301_Preflash_Column_Z1.pdf`)
  - Reactor/Decomposer Drum (`DS-D2304_Decomposer_Reactor_Z1.pdf`)
  - Shell & Tube Heat Exchanger (`DS-E2307_Reactor_Cooler_Z1.pdf`)
  - Centrifugal Pump (`DS-P2301_Preflash_Bottoms_Pump_Z1.pdf`)
  - Vacuum Ejector System (`DS-X2301_Flash_Column_Vacuum_System_Z1.pdf`)
  - Control Valves (`DS-PS-0010_Control_Valve_Process_Datasheet_Z1.pdf`)
  - Pressure Relief Valves (`DS-PS-0018_Pressure_Relief_Valve_Datasheet_Z1.pdf`)
  - Flow, Pressure, Level & Temperature Instruments (`DS-PS-0031_Instrument_Process_Datasheet_Z1.pdf`)
- `pid/` (`5` PDFs): Piping and Instrumentation Diagrams covering every subtype:
  - Master Drawing Index & Equipment List (`PID-23-0000_Equipment_and_Drawing_List_Z1.pdf`)
  - Safety Instrumented System (SIS) Cause & Effect Interlock Matrix (`PID-23-0002_Cause_and_Effect_Matrix_Z1.pdf`)
  - Vector CAD P&ID Drawing without embedded text stream (`PID-23-0004_Preflash_Column_Z1.pdf`)
  - Decomposer Reactor & Circulation P&ID with intentional cross-document design pressure discrepancy (`PID-23-0013_Decomposer_Reactor_Z1.pdf`)
  - Pressure Relief & Flare Header P&ID (`PID-23-0022_Pressure_Relief_Header_Z1.pdf`)
- `pfd/` (`2` PDFs): Process Flow Diagrams with Heat & Material Balances:
  - Concentration & Preflash Section (`PFD-23-0001_Concentration_and_Preflash_Section_Z1.pdf`)
  - Decomposer & Neutralization Section (`PFD-23-0005_Decomposer_and_Neutralization_Section_Z1.pdf`)
- `standards/` (`4` PDFs): Corporate Engineering Standards, Risk/HAZOP Procedures & Safety Data Sheets:
  - Corporate Risk Assessment, 5x5 Risk Matrix & HAZOP Study Procedure (`STD-PHA-001_Risk_Assessment_and_HAZOP_Procedure_R1.pdf`)
  - Pressure Relief & Flare System Design Standard (`STD-ENG-014_Pressure_Relief_and_Flare_System_Design_R1.pdf`)
  - Safety Data Sheet — Cumene Hydroperoxide (`SDS_80-15-9_cumene-hydroperoxide.pdf`)
  - Safety Data Sheet — Phenol & Acetone (`SDS_108-95-2_phenol.pdf`)
- `operating_manuals/` (`1` PDF): Plant Operating Manual covering Normal Operation, Startup/Shutdown & Emergency Trip Response (`OM-2300_Operating_Manual_Z1.pdf`).

### 3.2 End-to-End Post-Deployment Extraction & Spanner Seeding Pipeline
Instead of shipping pre-baked Markdown files in `reference/wiki/`, all OKF v0.2 `.md` files are produced dynamically by **`extracter_agent`** from `reference/raw/` after deployment and then ingested into **Cloud Spanner** via `scripts/ingest_okf_bundle_to_spanner.py`.

---

## 4. Open Knowledge Format (OKF v0.2) & Spanner Graph-RAG Baseline Contracts

1. **OKF v0.2 Markdown Document Structure (`extracter_agent` output & `sync_markdown_bundle_to_spanner` input):**
   - UTF-8 Markdown file with `---` delimited YAML frontmatter (`type`, `title`, `description`, `resource`, `tags`, `sources: [{id, resource, title}]`, `generated`, `verified`, `status`).
   - Structured Markdown body sections (`## Design Data`, `## Operating Conditions`, `## Instrumentation & Control Loops (P&ID)`, `## Connections & Stream Summary`, `## Hazards & Safeguards`) with inline `Source` columns and `⚠️ CONFLICT` callouts.
2. **Cloud Spanner Graph-RAG & Lineage Schema (`query_agent/spanner/schema.sql`):**
   - 9 relational tables (`OkfConcepts`, `OkfSectionChunks`, `EngineeringEntities`, `FactAssertions`, `RawSourceDocuments`, `ProcessConnections`, `InstrumentControlEdges`, `ConceptWikiLinks`, `FactLineageEdges`) and ISO GQL Property Graph `OkfKnowledgeGraph`.
   - 100% `.md`-only deterministic lifecycle sync (`sync_markdown_bundle_to_spanner`) supporting `ADDED`, `UPDATED`, `REMOVED`, and `UNCHANGED` `.md` states.

---

## 5. System Invariants & Quality Rules

1. **Reference Immutability & Confidentiality Invariant (Rule 14):** Under no circumstances may any agent or tool modify, delete, or write into `reference/raw/` at runtime, and zero confidential customer/licensor documents or hardcoded GCP project identifiers may be committed to version control.
2. **Zero Regex / Keyword Routing Invariant (Rule 11):** Intent classification, tool routing, and entity resolution in both `extracter_agent` and `query_agent` use cognitive model-driven reasoning (`gemini-3.8-flash`) with structured schemas; hardcoded keyword heuristics are prohibited.
3. **100% `.md`-Only Spanner Ingestion Invariant:** `sync_markdown_bundle_to_spanner()` derives all Spanner nodes, edges, chunks, and PDF source provenance strictly from `.md` files extracted by `extracter_agent` without scanning `reference/raw/`.
4. **100% Spanner-Only Query Execution Invariant:** `query_agent` executes all engineering, graph, lineage, and HAZOP queries against Cloud Spanner and Dataplex Universal Catalog with zero GCS or PDF reads at query time.
5. **Dual-Value Conflict Preservation Invariant:** Whenever cross-document conflicts (`has_conflict = TRUE` / `⚠️ CONFLICT`) exist, both `extracter_agent` and `query_agent` preserve and surface both competing values alongside their respective source PDF citations.
