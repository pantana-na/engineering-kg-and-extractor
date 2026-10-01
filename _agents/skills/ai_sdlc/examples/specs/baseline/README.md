# Baseline Specifications (`specs/baseline/`)

This directory houses **Baseline Specifications** for existing (brownfield) code, reverse-engineered architecture, hidden business logic catalogs, data contracts, and invariant models authored using [`../templates/baseline-template.md`](../templates/baseline-template.md).

## Two-Track Brownfield Baseline Mandate

Under the **Spec-Driven Development (SDD)** protocol ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../_agents/rules/ai_sdlc_and_sdd_standards.md)) and the [Brownfield Assessment Playbook](../_agents/skills/ai_sdlc/references/brownfield_assessment_playbook.md):

1. **Baseline Before Delta:** Before modifying any existing subsystem, modernizing legacy apps, or refactoring untested code, an accurate Baseline SDD reflecting the "as-is" system must be generated here using [`../templates/baseline-template.md`](../templates/baseline-template.md).
2. **Two-Track Assessment Coverage:**
   - **Track A — Legacy Enterprise / 3-Tier Apps (e.g., `.NET Framework`, ASP.NET WebForms/MVC, WCF/SOAP, SQL Server):**
     - Captures Presentation, Business, and Data tier dependencies, stateful `Session`/`ViewState` coupling, `Web.config`/`App.config` settings, and **hidden business logic** extracted from SQL Stored Procedures (`sp_*`/`usp_*`), Triggers, and code-behind files.
   - **Track B — Modern Cloud-Native Code Lacking Documentation & Testing:**
     - Captures reverse-engineered API/streaming routes, reconciles frontend/backend/database type drift, and audits the codebase against the **13-Rule Governance & Dual-Runtime Gap Matrix** (`agent_runtime` vs `cloud_run`).
3. **Characterization Tests + Property-Based Testing (PBT) Safety Net:**
   - Invariants documented in the baseline are locked in via **Characterization Unit Tests** (Golden Master parity) and **Generative Property-Based Tests (PBT)** (`hypothesis` / `fast-check`) before any refactoring or migration begins.

## Document Naming Convention
- `system-overview.md`: Comprehensive system-wide "as-is" architecture, 3-tier/component inventory, and modernization strategy.
- `<subsystem>-baseline.md`: Subsystem-specific baseline specification (e.g., `order-processing-baseline.md`, `legacy-wcf-billing-baseline.md`, `agent-orchestrator-baseline.md`).

