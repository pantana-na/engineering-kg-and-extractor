# Baseline Specifications (`specs/baseline/`)

This directory houses **Baseline Specifications** for existing (brownfield) code, reverse-engineered architecture, data contracts, and invariant models across all agents (`extracter_agent` and `query_agent`).

## Brownfield Baseline Mandate

Under the **Spec-Driven Development (SDD)** protocol ([`_agents/rules/spec_driven_development.md`](../../_agents/rules/spec_driven_development.md)):

1. **Baseline Before Delta:** Before modifying any existing subsystem, adding features to brownfield components, or executing refactorings, an accurate Baseline SDD reflecting the existing "as-is" code must be generated and stored here.
2. **What Must Be Captured:**
   - Subsystem boundaries and runtime assignments (Agent Platform vs Cloud Run)
   - Data models and schemas (TypeScript, Pydantic, SQL/GQL)
   - API endpoints, request/response formats, headers, and error codes
   - Business rules, invariants, and edge cases
   - External dependencies (Gemini API, Cloud Spanner, Dataplex Universal Catalog, Google Cloud Storage)
3. **Core Invariant Protection:** Invariants documented in the baseline serve as the mathematical properties tested by Property-Based Tests (PBT) to ensure zero regressions during future development.

## Active Baseline Specifications
- [`system-overview.md`](./system-overview.md) (`BASELINE-20260922-EXTRACTER-AGENT-SYSTEM`): Comprehensive multi-agent architecture (`extracter_agent` & `query_agent`), immutable reference data sources (`136` Raw PDFs, `130` Golden Wiki concepts), Cloud Spanner & Dataplex contracts, and core invariants.

## Document Naming Convention
- `system-overview.md`: Comprehensive system architecture and data flow.
- `<subsystem>-baseline.md`: Subsystem-specific baseline specification.
