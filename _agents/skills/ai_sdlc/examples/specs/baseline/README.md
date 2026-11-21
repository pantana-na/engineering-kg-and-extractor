# Baseline Specifications (`specs/baseline/`)

This directory houses **Brownfield `"As-Is"` Baseline Specifications** authored using [`../templates/baseline-template.md`](../templates/baseline-template.md) under [`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../_agents/rules/ai_sdlc_and_sdd_standards.md) and the [Brownfield Assessment Playbook](../../_agents/skills/ai_sdlc/references/brownfield_assessment_playbook.md).

## Mirrored 8-Section Brownfield Baseline Structure (`baseline-template.md`)

[`baseline-template.md`](../templates/baseline-template.md) mirrors the Enterprise Solution Design sections (1–8) from an **"As-Is & Gaps"** perspective and supports **`Workload Type: Regular App | AI Agent | Hybrid`** (omitting **`[AI-Agent Only]`** items for non-AI legacy or cloud apps):

- **Document Control:** `Baseline ID`, `Workload Type`, `Assessment Track` (`Track A` | `Track B` | `Hybrid`), `Author`, `Date`, `Version`, `Status`.
1. **Executive Summary & Problem Framing (As-Is):** Purpose, **Track A (Legacy 3-Tier `.NET`/WCF/SQL)** vs. **Track B (Modern Undocumented Cloud/AI)** classification (§1.1), operational scope (§1.2), and observed SLAs (§1.3).
2. **"As-Is" System Architecture, Topology & Reverse-Engineered Contracts:** Sequence diagram (§2.1), tier inventory (§2.2), runtime & `Web.config`/`.env` inventory (§2.3), and schemas, APIs & **Hidden Business Logic Extraction Matrix** (SQL Stored Procedures `sp_*`/`usp_*`, Triggers, UI code-behind) (§2.4).
3. **"As-Is" Security, Privacy & `[AI-Agent Only]` SAIF Gap Assessment:** SAST baseline, auth/IAM posture, perimeter/secrets, and Rules 1–13 + WAF[/SAIF] Gap Matrix (§3.4).
4. **"As-Is" Resiliency, Reliability & State Integrity:** Timeouts, `Session`/`ViewState` stateful coupling, idempotency gaps, and HA/failover gaps.
5. **"As-Is" Observability, Characterization Safety Net & `[AI-Agent Only]` AgentOps:** Probes/logging gaps + mandatory **Characterization Unit Tests (Golden Master)** and **Generative Property-Based Tests (PBT)** safety net (§5.3).
6. **"As-Is" Performance, Caching & Cost / FinOps Baseline:** Bottlenecks, caching, current run-rate, and region `CFE %`.
7. **Ambiguity Triage Log (`ask_question`) & Modernization ADRs:** Legacy quirk triage (`Preserve as Baseline Invariant` vs. `Remediate as Defect`) (§7.1) and confirmed Modernization Strategy (*Strangler Fig*, *Full Re-Architecture*, or *In-Place Hardening*) (§7.2).
8. **"As-Is" Failure Mode & Effects Analysis (FMEA) & Migration Risks:** Stateful cutover risks, hidden trigger side-effects, and rollback safeguards.

## Document Naming Convention
- `system-overview.md`: System-wide `"as-is"` architecture and modernization strategy.
- `<subsystem>-baseline.md`: Subsystem-specific baseline (e.g., `order-processing-baseline.md`).
