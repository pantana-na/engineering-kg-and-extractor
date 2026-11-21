# Baseline Specifications (`specs/baseline/`)

This directory houses **Brownfield Baseline Specifications** capturing reverse-engineered architecture, data contracts, and core invariants across `extracter_agent`, `query_agent`, and `unified_web`.

## Active Baseline Specifications

- [`system-overview.md`](./system-overview.md) (`BASELINE-20261120-EXTRACTER-AGENT-SYSTEM`): Comprehensive brownfield baseline covering the multi-agent architecture, immutable `reference/raw/` invariants, Cloud Spanner & Dataplex contracts, and WAF/SAIF gap assessment prior to the v2 Unified Workbench upgrade.

## Naming Convention
- `system-overview.md`: System-wide baseline architecture and invariants.
- `<subsystem>-baseline.md`: Subsystem-specific baseline specification (authored from [`../templates/baseline-template.md`](../templates/baseline-template.md)).
