# System Specifications & SDD Registry (`specs/`)

This directory is the **Single Source of Truth** for system specifications, baseline reverse-engineering documentation, and living execution plans under the **3-Phase AI-SDLC** and **Spec-Driven Development (SDD)** mandate.

## Directory Structure

```text
specs/
├── README.md                                          # Registry index
├── templates/                                         # Canonical SDD, Baseline & Discovery templates
├── baseline/
│   └── system-overview.md                             # Brownfield Baseline SDD (BASELINE-20261120)
├── features/
│   └── SPEC-20261120-UNIFIED-WORKBENCH-V2.md          # Consolidated Master SDD + Living Execution Plan (v1 -> MOC -> v2.2)
└── plan/                                              # Embedded in Master SDD §10 (templates/README retained)
```

---

## Active Specifications Registry

1. **Brownfield Baseline ([`specs/baseline/system-overview.md`](./baseline/system-overview.md)):**
   - `BASELINE-20261120-EXTRACTER-AGENT-SYSTEM` — Reverse-engineered as-is baseline, upstream `engineering-kg-gc` delta, Spanner/Dataplex analysis, Reference Immutability Invariants, and WAF/SAIF gap assessment.
2. **Consolidated Master Specification & Living Execution Plan ([`specs/features/SPEC-20261120-UNIFIED-WORKBENCH-V2.md`](./features/SPEC-20261120-UNIFIED-WORKBENCH-V2.md)):**
   - `SPEC-20261120-UNIFIED-WORKBENCH-V2` (Version `2.2` — `Implemented & Deployed`) — Single unified SDD + Living Plan combining v1 OKF Extracter & Spanner Graph-RAG Query Agent, MOC Authority & Document Revision Lifecycle, v2 Unified Workbench + Cloud Run Job + Selectable Gemini 4 Models + Spanner Native `ML.PREDICT` & ANN Vector Index, v2.1–v2.2 Streamlined 2-Extract-Button UI + `Sync GCS` + All 6 Doc Types + Non-Blocking Live Tool/Vision Latency Telemetry, Live GCP Deployment Inventory (`engineering-kg-demo`), and Rule 13 RCA Log.

---

## Related Documentation
- **Agent Operating Manual:** [`AGENTS.md`](../AGENTS.md)
- **Governance Rules (Rules 1–13):** [`_agents/rules/`](../_agents/rules/)
- **Operational Architecture, Demo Guide & Security Audit:** [`docs/README.md`](../docs/README.md)
