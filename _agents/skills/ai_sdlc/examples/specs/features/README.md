# Feature Specifications (`specs/features/`)

This directory contains formal **Enterprise Solution Design & Feature Specifications** authored prior to implementation using [`specs/templates/sdd-template.md`](../templates/sdd-template.md) under [`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../_agents/rules/ai_sdlc_and_sdd_standards.md).

## Workload Modes (`Regular App` vs. `AI Agent` / `Hybrid`)
- **`Regular App`:** Standard web, REST/gRPC API, microservice, or data pipeline workloads on `cloud_run` / GCP native services. Omit or mark `N/A` all **`[AI-Agent Only]`** subsections; enforces **Google Cloud WAF (6 Pillars)** and **Rules 1–10 & Rule 13**.
- **`AI Agent` / `Hybrid`:** Dual-Runtime workloads (`cloud_run` + `agent_runtime`). Enforces **Google Cloud WAF (6 Pillars)**, **Google SAIF / SAIF 2.0**, and **all Rules 1–13**.

## Required Document Sections (`sdd-template.md`)
- **Document Control:** `Spec ID`, `Workload Type`, `Status`, `Author`, `Date`, `Version`, `Baseline Reference`.
1. **Executive Summary & Problem Framing:** Context & Goals (§1.1), Scope & Operational / `[AI-Agent Only]` Autonomy Boundaries (§1.2), and Acceptance Criteria & SLAs (§1.3).
2. **System Architecture, Topology & Code Contracts:** Architecture Diagram (§2.1), Service Flow & `[AI-Agent Only]` Agent Topology (§2.2), Compute Runtime, WAF 6 Pillars & `[AI-Agent Only]` Model Selection (§2.3), and Data Models, API Contracts & UI State Schemas (§2.4).
3. **Security, Privacy, Compliance & `[AI-Agent Only]` SAIF Alignment:** Guardrails & Injection Defenses (§3.1), Identity, Auth & Sandboxing (§3.2), Network Perimeter, VPC-SC & CMEK (§3.3), and Rules 1–13 + `[AI-Agent Only]` SAIF 15-Risk Matrix (§3.4).
4. **Resiliency, Reliability & State Integrity:** Timeouts & `[AI-Agent Only]` Anti-Loop Safeguards (§4.1), Idempotency & Transactions (§4.2), and HA, Graceful Degradation & `[AI-Agent Only]` Model Fallbacks (§4.3).
5. **Observability, Operations & `[AI-Agent Only]` AgentOps:** `/healthz` Probes, SLOs & OpenTelemetry Span Hierarchy (§5.1), Structured Logging (§5.2), and CI/CD, Unit/PBT Testing & `[AI-Agent Only]` Live `agents-cli eval` (§5.3).
6. **Performance Optimization, FinOps & Sustainability:** Latency & Caching (§6.1) and Unit-Cost Modeling, Sustainability (`CFE %`) & `[AI-Agent Only]` Token Economics (§6.2).
7. **Architectural Decision Records (ADRs):** Cross-pillar WAF trade-offs (`ADR-01`, `ADR-02`, ...).
8. **Failure Mode & Effects Analysis (FMEA):** Component failure modes, blast radius, detection signals, and automated mitigations.
9. **Step-by-Step Implementation Plan & Test Design:** Sequential steps with **Deterministic Unit Tests** + **Generative Property-Based Tests (PBT)** *(+ `[AI-Agent Only]` live `agents-cli eval`)* and **Rule 13 4-Step RCA** enforcement.
10. **Plan Progress Tracking & Living Spec Synchronization:** Linkage to `specs/plan/` with zero spec drift.

## Document Naming Convention
- `SPEC-<YYYYMMDD>-<FEATURE_NAME>.md` (e.g., `SPEC-20261104-ORDER-SERVICE.md`)
