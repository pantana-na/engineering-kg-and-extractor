# Specification Templates (`specs/templates/`)

This directory contains standardized templates for authoring **Spec-Driven Development (SDD)** documents.

## Available Templates

- **[`sdd-template.md`](./sdd-template.md):** Standardized Feature Specification Document template (`specs/features/SPEC-*.md`) with embedded:
  - Runtime separation matrix (Gemini Enterprise Agent Platform vs Google Cloud Run)
  - Interactive Mermaid sequence diagrams
  - Type and API contract schemas
  - 13-rule DevOps, Security, ADK, and RCA governance checklist
  - Step-by-step implementation plan requiring **Unit Tests** and **Property-Based Tests (PBT)** for every step
  - Live agent evaluation (`agents-cli eval`) verification criteria
  - Plan progress tracking protocol
- **[`baseline-template.md`](./baseline-template.md):** Standardized Brownfield Baseline & Modernization Assessment template (`specs/baseline/*.md`) supporting:
  - **Track A (Legacy 3-Tier / `.NET Framework` Apps):** 3-Tier component inventory, stateful `Session`/`ViewState` coupling, `Web.config` mapping, and **Hidden Business Logic Extraction** from SQL Stored Procedures, Triggers, and WCF services.
  - **Track B (Modern Cloud-Native Code Lacking Docs & Tests):** Implicit route/schema reverse-engineering, type drift reconciliation, and **13-Rule Governance & Dual-Runtime Gap Matrix**.
  - **Characterization Test + Property-Based Test (PBT) Safety Net** and confirmed Modernization Strategy (*Strangler Fig*, *Full Dual-Runtime Re-Architecture*, or *In-Place Hardening*).

## Usage

1. **For Brownfield Systems (Step 0 — Baseline First):**
   - Copy `baseline-template.md` to `specs/baseline/system-overview.md` or `specs/baseline/<subsystem>-baseline.md`.
   - Complete the reverse-engineering, hidden logic catalog, `ask_question` defect triage, and Characterization + PBT safety net before authoring delta features.
2. **For New Features or Modernization Deltas (Step 1 — Feature Spec):**
   - Copy `sdd-template.md` to `specs/features/SPEC-<YYYYMMDD>-<FEATURE_NAME>.md`.
   - Fill out all sections completely and align with stakeholders via `ask_question` before writing production code.
   - Execute implementation step-by-step with continuous progress updates in [`specs/plan/`](../plan/).

