# Feature Specifications (`specs/features/`)

This directory contains formal **Feature Specifications** and architectural change proposals authored prior to implementation.

## Feature Authoring Guidelines

Every feature document in this directory must be created using the official template at [`specs/templates/sdd-template.md`](../templates/sdd-template.md) and adhere to the **Spec-Driven Development (SDD)** standard ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../_agents/rules/ai_sdlc_and_sdd_standards.md)).

### Required Document Sections
1. **Problem Statement & Objectives:** Context, Goals, and explicit Non-Goals.
2. **System Architecture & Component Interaction:**
   - Explicit runtime allocation (Agent Platform `agent_runtime` vs Cloud Run `cloud_run`).
   - Sequence/flow diagram showing client, proxy, ADK orchestrator, and data stores.
3. **Data Models & Type Contracts:** Single source of truth TypeScript types, Pydantic schemas, or SQL DDL.
4. **API Contracts & Integrations:** Endpoints, request/response bodies, HTTP status codes, error models.
5. **UI/UX & Behavioral Specifications:** Client state transitions, loading states, error boundaries.
6. **DevOps, Security & Governance Checklist:** Alignment with the 13 repository standards (CodeMender SAST, Cloud Run `/healthz`, ADK agent platform runtime, etc.).
7. **Step-by-Step Implementation Plan & Test Design:**
   - Granular steps from foundational models to UI.
   - **Deterministic Unit Tests** for every step.
   - **Generative Property-Based Tests (PBT)** for every step.
   - **Live Environment Evaluation (`agents-cli eval`)** for all agent reasoning flows.
   - Enforcement of the **4-Step RCA Protocol** if any test fails (zero quick fixes or regex patches).
8. **Plan Progress Tracking & Living Spec Synchronization:** Linkage to `specs/plan/` and zero spec drift.

## Document Naming Convention
- `SPEC-<YYYYMMDD>-<FEATURE_NAME>.md` (e.g. `SPEC-20260920-STREAMING-VOICE-GATEWAY.md`)
