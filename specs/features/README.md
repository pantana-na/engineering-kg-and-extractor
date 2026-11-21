# Feature Specifications (`specs/features/`)

This directory contains formal **Enterprise Solution Design & Feature Specifications** authored prior to implementation using [`../templates/sdd-template.md`](../templates/sdd-template.md) under the **3-Phase AI-SDLC** and **Spec-Driven Development (SDD)** standard ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../_agents/rules/ai_sdlc_and_sdd_standards.md)).

## Active Feature Specifications Registry

| Spec ID | Target Platform / Scope | Runtime | Status |
| :--- | :--- | :--- | :--- |
| [`SPEC-20261120-UNIFIED-WORKBENCH-V2.md`](./SPEC-20261120-UNIFIED-WORKBENCH-V2.md) | **Unified Engineering OKF Workbench v2.x** (`okf-engineering-workbench` + `okf-pipeline-job`), Gemini 4 Allowlist & Failover, Spanner Enterprise ANN Vector + `ML.PREDICT`, MOC/ECN Lifecycle, and Living Execution Plan (§10) | `cloud_run` + Cloud Run Job (`24h`) + `agent_runtime` + Cloud Spanner & Dataplex | **Implemented & Deployed (`engineering-kg-demo`)** |

## Naming Convention
- `SPEC-<YYYYMMDD>-<FEATURE_NAME>.md`
