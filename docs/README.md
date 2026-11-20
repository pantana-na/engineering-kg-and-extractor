# Operational & Architecture Documentation (`docs/`)

This directory contains standardized operational architecture documentation, security audit reports, and interactive standalone HTML/SVG visual assets for the **OKF Engineering Knowledge Workbench v2**.

## Separation of Documentation Responsibilities
- **Master Specification & Living Execution Plan ([`specs/`](../specs/)):** Authoritative baseline ([`specs/baseline/system-overview.md`](../specs/baseline/system-overview.md)) and unified master feature SDD + living progress plan ([`specs/features/SPEC-20261120-UNIFIED-WORKBENCH-V2.md`](../specs/features/SPEC-20261120-UNIFIED-WORKBENCH-V2.md)).
- **Operational Docs & Visual Assets ([`docs/`](./)):** Consolidated architecture & demo guide, CodeMender SAST & security audit summary, and standalone HTML/SVG diagrams.

---

## Document & Visual Asset Catalog

### 1. Architecture, Data Ingestion & Demo Guide
- **[Unified Architecture, Ingestion & Demo Guide (`engineering-kg-workbench-architecture.md`)](./engineering-kg-workbench-architecture.md):** End-to-end Dual-Runtime topology, Zero-Trust Pattern 1B IAP, 6-folder multi-format & MOC ingestion pipeline, Cloud Spanner Enterprise Graph + native `ML.PREDICT` + ANN Vector Index, and 5-minute executive walkthrough.
- **Interactive Standalone HTML/SVG Assets:**
  - [`high-level-system-architecture.html`](./high-level-system-architecture.html) — High-level system architecture topology.
  - [`data-ingestion-architecture.html`](./data-ingestion-architecture.html) — Multi-format ingestion & Spanner synchronization flow.
  - [`okf-query-agent-mockup.html`](./okf-query-agent-mockup.html) — Interactive UI reference mockup.

### 2. Security & SAST Audit Summary
- **[CodeMender SAST & Security Audit Summary (`codemender-security-audit-summary.md`)](./codemender-security-audit-summary.md):** Consolidated vulnerability scan results (`0` findings), PyJWT ES256 JWK Set IAP enforcement, SAIF 2.0 4-point guardrails, and deterministic HITL verification.

---

## Related Governance
- **Agent Operating Manual:** [`AGENTS.md`](../AGENTS.md)
- **AI-SDLC & SDD Governance Rules:** [`_agents/rules/`](../_agents/rules/)
- **Master Spec & Plan Index:** [`specs/README.md`](../specs/README.md)
