# Multi-Modal Extraction Guide & 1-to-1 Mapping (`Discovery Document` $\rightarrow$ `ai-sdlc` SDD)

This reference defines (1) modality-specific locator and citation standards when consolidating raw discovery packages, and (2) the deterministic mapping from `specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md` into [`ai-sdlc`](../../ai_sdlc/SKILL.md) Phase 1/2 and [`sdd-template.md`](../../ai_sdlc/examples/specs/templates/sdd-template.md).

---

## 1. Multi-Modal Artifact Ingestion & Locator Conventions

Every requirement (`FR-*`, `NFR-*`) and constraint (`CON-*`) must specify an exact `Source Artifact`, `Locator`, and `Verbatim Quote`:

| Input Modality | How to Inspect | Standard `Locator` Format | `Verbatim Quote` Rule |
| :--- | :--- | :--- | :--- |
| **Interview Scripts / Transcripts** (`.txt`, `.md`, `.vtt`, `.srt`, `.docx`) | `view_file` | Speaker + timestamp or line range (e.g., `Speaker: VP Ops [12:40–13:05]` or `L84–L91`) | Exact speaker words in quotation marks. |
| **Drawings, Whiteboards & Architecture Sketches** (`.png`, `.jpg`, `.webp`, `.svg`, scanned `.pdf`) | `view_file` (multimodal vision) | Diagram title/zone + box/arrow label (e.g., `Swimlane: Order Intake -> Arrow 'Sync ERP'`) | Prefix with `[Diagram Transcription]:` followed by exact box/edge text and topology connection. |
| **User Emails & Chat Threads** (`.eml`, `.txt`, `.md`, `.pdf`) | `view_file` | Sender + timestamp/date + paragraph (e.g., `Email from CISO (2026-10-14), para 2`) | Exact sentence(s) from the email/message body. |
| **Manuals, SOPs, Policies & RFPs** (`.pdf`, `.md`, `.html`) | `view_file` | Page + section/heading (e.g., `p. 14, §4.2 'Refund Approval Rules'`) | Exact policy/manual excerpt. |
| **Spreadsheets & Data Exports** (`.csv`, `.tsv`, `.json`, `.xlsx` export) | `view_file` / Python read | Sheet/file + row/column header (e.g., `sla_targets.csv, Row 6 'Peak_RPS'`) | Exact cell header + value pair. |
| **Audio / Video Recordings** (`.mp3`, `.wav`, `.mp4`) | `view_file` | Timestamp range (e.g., `[04:15–04:48]`) | Exact spoken quote from segment. |

---

## 2. Deterministic 1-to-1 Handoff Map (`Discovery Document` $\rightarrow$ `sdd-template.md`)

When `ai-sdlc` detects an approved `specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md`, it uses the table below to **auto-populate known fields first** and restrict `ask_question` strictly to unresolved blockers:

| Discovery Document Section (`specs/discovery/DISCOVERY-*.md`) | Target `ai-sdlc` Step & [`sdd-template.md`](../../ai_sdlc/examples/specs/templates/sdd-template.md) Section | How `ai-sdlc` Uses It |
| :--- | :--- | :--- |
| **§1 Document Control** (`Candidate Workload Type`, `Discovery ID`) | **SDD `Document Control`** (`Workload Type`, `Baseline / Discovery Ref`) | Pre-selects `Regular App` vs. `AI Agent` vs. `Hybrid` (confirming via `ask_question` only if marked `Pending Phase 1`). |
| **§2.1–§2.4 Executive Summary** & **§4.1 Current State** | **SDD `§1.1 Business Context & Problem Statement`** & `specs/baseline/` | Populates customer problem statement, quantified business value, target personas, and legacy pain points without re-asking. |
| **§7.1 Negative Scope**, **§11.3 Phase 1 Cut Line** & **§11.4 De-Prioritisations** | **SDD `§1.2 Scope Definition & Autonomy Boundaries`** | Populates in-scope automated capabilities, role-gated workflows, explicit non-goals, and *(if AI Agent)* autonomous vs. HITL scope. |
| **§6 NFR Register** & **§6.1 WAF Quality Attribute Check** | **SDD `§1.3 SLAs`**, **`§4 Resiliency`**, **`§5 Observability`**, **`§6 Performance/FinOps/CFE%`** | Transfers verified availability, latency, RTO/RPO, throughput, budget, and sustainability metrics; triggers `ask_question` for attributes flagged `Missing` in §6.1. |
| **§3 Stakeholder Register & §3.1 Tensions** | **Phase Gates 1–2** & **SDD `§7 Architectural Decision Records (ADRs)`** | Maps sign-off/veto authorities and converts reconciled stakeholder tensions into formal cross-pillar ADRs. |
| **§4.2–§4.3 Regulatory / Incidents**, **§7 Constraints** & **§12.3 Sensitive Data** | **SDD `§3 Security, Privacy, Compliance & [AI-Agent Only] SAIF Alignment`** | Maps PII/PHI/PCI fields to Cloud DLP tokenization, Assured Workloads residency, VPC-SC, CMEK, Zero-Trust IAP/OAuth2, and SAIF 2.0 4-point callbacks. |
| **§5 Functional Requirements** & **§12.1–§12.2 Data/Integration Inventory** | **SDD `§2.1–§2.4 Architecture, Service Flow, Data Models, API / FunctionTool Contracts`** | Drives system component topology, structured DB/API schemas, and *(if AI Agent)* unstructured RAG corpora + `FunctionTool` definitions. |
| **§2.5 Top 3 Blockers**, **§8 Open Questions (`Blocking = Yes`)**, **§9 Assumptions** & **§10.1 Contradictions** | **`ai-sdlc` Step 1.2 / Step 2.1 `ask_question` Queue** | Serves as the **exact clarification agenda**—`ai-sdlc` presents each blocker with its recommended default via `ask_question` to lock in final answers before coding. |
| **§10.2–§10.3 Undefined Dependencies / Discovery Risks** | **SDD `§8 Failure Mode & Effects Analysis (FMEA)`** | Seeds upstream dependency failure modes, blast-radius mitigations, and WAF graceful degradation contracts (`503 UPSTREAM_UNAVAILABLE_DEGRADED`). |
| **§13 Dependencies & Proposed Phasing** + **§5 Acceptance Criteria** | **SDD `§9 Step-by-Step Implementation Plan & Test Design`** | Orders implementation steps and translates `FR-*` acceptance criteria directly into **Deterministic Unit Tests** and **Property-Based Test (PBT)** invariants. |
