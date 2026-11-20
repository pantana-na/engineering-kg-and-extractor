# Specification Templates (`specs/templates/`)

This directory contains standardized **Enterprise Solution Design & Spec-Driven Development (SDD)** templates supporting both **Regular (Non-AI) Applications** (`Workload Type: Regular App`) and **AI Agent / Hybrid Workloads** (`Workload Type: AI Agent | Hybrid`).

## Available Templates

- **[`discovery-template.md`](./discovery-template.md):** *(Optional Pre-Inception)* 15-Section Consolidated Discovery Document (`specs/discovery/DISCOVERY-*.md`) used by [`requirements-discovery`](../../_agents/skills/requirements_discovery/SKILL.md) to synthesize raw interview scripts, drawings/diagrams, emails, and manuals into verbatim-cited `FR`/`NFR`/`CON` registers, stakeholder tensions, cross-artifact contradictions, WAF 6-Pillar quality attribute coverage checks, a ranked Phase 1 cut line, and a targeted open-question queue for `ai-sdlc`.
- **[`sdd-template.md`](./sdd-template.md):** Standardized Feature & Solution Design Specification (`specs/features/SPEC-*.md`) structured across **Document Control + 10 Sections**:
  - **Document Control:** `Spec ID`, **`Workload Type` (`Regular App` | `AI Agent` | `Hybrid`)**, `Author`, `Date`, `Version`, `Status` — with explicit **`[AI-Agent Only]`** markers on subsections/rows that must be omitted or marked `N/A` for regular non-AI apps.
  - **1–8 (Enterprise Solution Design Core):** Executive Summary & Scope/Autonomy Boundaries (§1), System Architecture, Topology, WAF 6-Pillar & Code Contracts (§2), Security, Privacy, Rules 1–13 & `[AI-Agent Only]` SAIF Alignment (§3), Resiliency, Reliability & State Integrity (§4), Observability, Operations & `[AI-Agent Only]` AgentOps (§5), Performance, FinOps & Sustainability (§6), Architectural Decision Records / ADRs (§7), and Failure Mode & Effects Analysis / FMEA (§8).
  - **9–10 (Executable SDD Delivery):** Step-by-Step Implementation Plan & Test Design requiring **Deterministic Unit Tests** + **Generative Property-Based Tests (PBT)** *(+ `[AI-Agent Only]` DLP-Safe Live `agents-cli eval`)* (§9) and Living Plan Progress Tracking (§10).
- **[`baseline-template.md`](./baseline-template.md):** Standardized Brownfield `"As-Is"` Baseline & Gap Specification (`specs/baseline/*.md`) mirroring **Document Control + Sections 1–8**:
  - Preserves **Track A (Legacy 3-Tier / `.NET`/SQL)** and **Track B (Undocumented Modern Cloud/AI)** classification (§1.1), **Hidden Business Logic Extraction** from SQL Stored Procedures/Triggers/UI (§2.4), **Governance + WAF[/SAIF] Gap Matrix** (§3.4), **Characterization Test + Baseline PBT Safety Net** (§5.3), **`ask_question` Quirk/Defect Triage + Modernization ADRs** (§7), and **As-Is FMEA & Cutover Risks** (§8), with **`[AI-Agent Only]`** markers throughout.

## Usage

0. **Optional Pre-Inception Consolidation (`requirements-discovery`):** When starting from raw multi-modal artifacts (transcripts, drawings, emails, manuals), copy `discovery-template.md` to `specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md` first; `ai-sdlc` will ingest it automatically to pre-populate the SDD and focus `ask_question` strictly on §2.5 / §8 / §10.1 blockers.
1. **Select `Workload Type` in Document Control:**
   - Choose **`Regular App`** for standard web, API, microservice, or data workloads (omit/mark `N/A` all `[AI-Agent Only]` items; enforces Google Cloud WAF 6 Pillars + Rules 1–10 & 13).
   - Choose **`AI Agent`** or **`Hybrid`** when building conversational or autonomous agents (enforces Dual-Runtime `cloud_run` + `agent_runtime`, WAF 6 Pillars, SAIF 2.0, and all Rules 1–13).
2. **For Brownfield Systems (Step 2.0 — Baseline First):** Copy `baseline-template.md` to `specs/baseline/system-overview.md` (or `<subsystem>-baseline.md`), extract hidden logic, triage quirks via `ask_question`, and lock in Characterization + PBT tests before authoring feature specs.
3. **For New Features or Deltas (Step 2.1 — Feature SDD):** Copy `sdd-template.md` to `specs/features/SPEC-<YYYYMMDD>-<FEATURE_NAME>.md`, obtain stakeholder sign-off via `ask_question`, and track execution in [`specs/plan/`](../plan/).
