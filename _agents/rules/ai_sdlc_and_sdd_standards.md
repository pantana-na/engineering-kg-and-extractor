---
trigger: always_on
description: "Core always-on engineering rule enforcing the 3-Phase AI-Driven Software Development Lifecycle (AI-SDLC) via the ai-sdlc skill, proactive ask_question clarification on unknowns, Spec-Driven Development (SDD) with brownfield baselines and Unit/Property-Based Testing at every step, and the mandatory 4-Step Root Cause Investigation (RCA) protocol."
---

# Rule: 3-Phase AI-SDLC, Spec-Driven Development (SDD) & Root Cause Investigation Standard

## Core Mandate
All software engineering, architectural design, feature development, refactoring, testing, bug fixing, and cloud/agent deployments in this repository **MUST strictly follow the 3-Phase AI-Driven Software Development Lifecycle (AI-SDLC)** orchestrated by the **[`ai-sdlc` skill](../skills/ai_sdlc/SKILL.md)**:

1. **Phase 1: Inception (Intent Framing & Architecture)**
2. **Phase 2: Execution (The Spec-Driven Development Cycle)**
3. **Phase 3: Operation (Repository Integration, Security Gates & Dual-Runtime Deployment)**

Whenever a user initiates or continues a project, feature, architectural change, bug fix, or deployment, the agent **MUST immediately load and follow [`_agents/skills/ai_sdlc/SKILL.md`](../skills/ai_sdlc/SKILL.md)**, and load the relevant domain rules:
- **Conversational AI Agents (`agent_runtime`):** [`_agents/rules/google_adk_and_agent_runtime.md`](./google_adk_and_agent_runtime.md)
- **Cloud Run, CI/CD, SAST & IaC (`cloud_run`):** [`_agents/rules/devops_security_and_quality_standards.md`](./devops_security_and_quality_standards.md)

---

## 1. Mandatory Zero-Assumption Clarification & Phase Gate Protocol

Across **every phase** of the AI-SDLC (Inception, Execution, and Operation):

1. **Zero Silent Assumptions (`ask_question` Mandate):**
   - The agent **MUST NEVER** guess, invent, or silently assume unknown business requirements, target personas, brownfield behaviors, data model fields, API error contracts, IAM/Ingress patterns, workload sizing parameters, or target deployment environments.
   - Whenever any factor is ambiguous, underspecified, or missing, the agent **MUST pause and use the `ask_question` tool** (presenting clear choices with `(Recommended)` options and trade-offs) before proceeding.
2. **Strict Interactive Phase Gates:**
   - The agent **MUST NOT** automatically transition from **Phase 1 (Inception) $\rightarrow$ Phase 2 (Execution)**, from **Phase 2 Spec Authoring $\rightarrow$ Phase 2 Code Implementation**, or from **Phase 2 (Execution) $\rightarrow$ Phase 3 (Operation)** without presenting the completed phase artifacts and obtaining **explicit user sign-off via `ask_question`**.

```
+===================================================================================+
|                     PHASE 1: INCEPTION (Intent Framing & Architecture)            |
|  - Elicit business intent, personas, goals/non-goals, greenfield vs. brownfield   |
|  - Check/discover brownfield baseline in specs/baseline/                          |
|  - Define Dual-Runtime Split: Agent Platform (agent_runtime) vs Cloud Run         |
|  - Define ADK Agent Hierarchy, Canonical Intent Topology & IAM/Ingress Pattern    |
|  - Offer companion skills: architecture-diagram (docs/) & gcp-cost-estimator      |
+===================================================================================+
                                         │
                        [Interactive Gate 1: ask_question Sign-Off]
                                         ▼
+===================================================================================+
|                  PHASE 2: EXECUTION (Spec-Driven Development Cycle)               |
|  - SDD Step 0: Codify Brownfield Baseline (specs/baseline/) if applicable         |
|  - SDD Step 1: Author Feature Specification (specs/features/SPEC-YYYYMMDD-*.md)   |
|  - SDD Step 2: Granular Implementation Plan + Unit Tests + PBT + Live Agent Eval  |
|  - SDD Step 3: Stakeholder Review & Alignment Sub-Gate (ask_question sign-off)    |
|  - SDD Step 4: Step-by-Step Code & Test Execution (4-Step RCA on any red test)    |
|  - SDD Step 5: Verification, Living Spec Sync & Progress Report (specs/plan/)     |
+===================================================================================+
                                         │
                        [Interactive Gate 2: ask_question Sign-Off]
                                         ▼
+===================================================================================+
|                PHASE 3: OPERATION (Repository Integration & Deployment)           |
|  - Pre-Merge Gate: Static Analysis + CodeMender SAST (cm find/verify/fix) + .env  |
|  - Repo Integration: Multi-branch Git (main/develop -> PR to prod), clean tree    |
|  - Dual-Runtime Deploy:                                                           |
|      1) ADK Agents -> Gemini Enterprise Agent Platform (agents-cli deploy)        |
|      2) Web UI / API Proxy -> Cloud Build + Terraform Infra Manager -> Cloud Run  |
|  - Post-Deploy Gate: Live /healthz & smoke tests, live agents-cli eval run        |
|    (>=95% precision, 1.000 groundedness), Observability check, specs/plan/ sync   |
+===================================================================================+
```

---

## 2. Spec-Driven Development (SDD) & Brownfield Protocol (Phase 2)

**Code is a downstream artifact derived from specification documents.** No feature implementation, architectural change, refactoring, or API modification may begin without an approved Specification Document under `specs/`.

### 2.1 Two-Track Brownfield Development Protocol (Mandatory Baseline & Safety Net First)
When working on an existing (brownfield) codebase or modernizing any legacy subsystem (see [`brownfield_assessment_playbook.md`](../skills/ai_sdlc/references/brownfield_assessment_playbook.md)):
1. **Classify & Reverse-Engineer Baseline First (`specs/baseline/`):**
   - Author `specs/baseline/system-overview.md` or `specs/baseline/<subsystem>-baseline.md` using `specs/templates/baseline-template.md` (scaffolded from [`_agents/skills/ai_sdlc/examples/specs/templates/baseline-template.md`](../skills/ai_sdlc/examples/specs/templates/baseline-template.md)).
   - **Track A — Legacy Enterprise / 3-Tier Apps (`.NET Framework`, ASP.NET WebForms/MVC, WCF/SOAP, SQL Server):** Map the Presentation, Business, and Data tiers; extract **hidden business logic** embedded in SQL Stored Procedures (`sp_*`/`usp_*`), Triggers, UI code-behind (`.aspx.cs`), stateful `Session`/`ViewState`, and `Web.config`/`App.config` settings.
   - **Track B — Modern Cloud-Native Code Lacking Docs & Tests:** Reverse-engineer undocumented route/API contracts, reconcile type drift across frontend/backend/DB schemas, and audit against the **13-Rule Governance Gap Matrix** (flagging coupled LLM agents, regex/keyword routing, missing `/healthz`, or scattered `.env.*` files).
2. **Clarify Baseline Unknowns & Modernization Strategy (`ask_question`):**
   - Pause and use `ask_question` to: (a) decide whether ambiguous/quirky legacy behaviors are **Baseline Invariants** or **Defects to Remediate**, and (b) select the **Modernization Strategy** (*Strangler Fig / API Facade*, *Full Dual-Runtime Re-Architecture*, or *In-Place Cloud-Native Hardening*).
3. **Lock In Characterization Tests & Property-Based Tests (PBT) Before Touching Code:**
   - Backfill **Characterization Unit Tests** (Golden Master input/output parity) and **Generative Property-Based Tests (PBT)** verifying core baseline invariants before refactoring or migrating code.
4. **Baseline Before Delta:** Only after `specs/baseline/` and the characterization test safety net are established may feature specs (`specs/features/`) be drafted against them.

### 2.2 SDD Authoring & Step-by-Step Implementation Plan
1. **Feature Specification (`specs/features/SPEC-<YYYYMMDD>-<TITLE>.md`):**
   - Author using `specs/templates/sdd-template.md` (scaffolded from [`_agents/skills/ai_sdlc/examples/specs/templates/sdd-template.md`](../skills/ai_sdlc/examples/specs/templates/sdd-template.md)) covering: (1) Problem Statement & Goals/Non-Goals, (2) Dual-Runtime Architecture & Sequence Diagram, (3) Data Models & Type Contracts, (4) API & `FunctionTool` Contracts, (5) UI/UX State Machines, (6) Governance Checklist, (7) Step-by-Step Implementation Plan & Test Design, and (8) Plan Progress Tracking.
2. **Mandatory Testing Standards for EVERY Implementation Step:**
   - **Deterministic Unit Tests:** Concrete examples testing happy paths, boundary conditions, malformed payloads, and error handling.
   - **Generative Property-Based Tests (PBT):** Mathematical and logical invariants verified across randomized/fuzzed input spaces using `fast-check` (TypeScript/JS) or `hypothesis` (Python) (e.g., serialization round-tripping, canonical intent enum membership, security callback interception, state reducer invariants).
   - **Live Environment Agent Evaluation (`agents-cli eval`):** For ADK agent steps, evaluate against live backends verifying $\ge 95\%$ tool selection precision and $1.000$ ($100\%$) groundedness (see [`google_adk_and_agent_runtime.md`](./google_adk_and_agent_runtime.md)).
3. **Pre-Code Stakeholder Alignment Sub-Gate:**
   - Review the authored SDD and step-by-step test plan with the user and obtain explicit approval via `ask_question` before writing production code.

### 2.3 Living Specs & Plan Progress Tracking (`specs/plan/`)
1. **Zero Spec Drift:** Whenever code contracts, schemas, or behaviors change, update the corresponding SDD in `specs/` in the same change.
2. **Living Plan Progress Reports (`specs/plan/PROGRESS_REPORT_<YYYYMMDD>.md`):**
   - Continuously record linked SDD IDs, step-by-step completion matrices, unit/PBT/live-eval pass metrics, architectural decisions, RCA logs, and next actions.
   - Always update `specs/plan/` and synchronize `specs/README.md` before pausing development or transitioning between phases.

---

## 3. Mandatory 4-Step Root Cause Investigation (RCA) & Zero Quick-Patch Standard

When **any** test fails (**Agent Evaluation (`agents-cli eval`)**, **Property-Based Tests (PBT)**, **Unit Tests**, or **Integration/Smoke Tests**), or when a user reports a defect or requests a bug fix:

**DEVELOPERS AND AI AGENTS ARE STRICTLY PROHIBITED FROM APPLYING QUICK FIXES, MOCKUP FALLBACK DATA, REGEX PATCHES, OR RULE-BASED CODE WORKAROUNDS.**

### 3.1 Strictly Prohibited Anti-Patterns (The "Quick-Fix" Trap)
1. ❌ **Mockup Data & Fallback Dictionaries:** Injecting synthetic fallback dictionaries or offline mockup data into application code to bypass missing/inconsistent database records (e.g., `if not db_result: return {"id": "ITEM-123"}`).
2. ❌ **Rule-Based Quick Patching & Special-Casing:** Writing prompt-specific `if/else` checks or hardcoding special-case answers for specific test inputs.
3. ❌ **Regex & Keyword Heuristics in Agents:** Adding regex matching or substring heuristics to patch agent intent classification or routing errors.
4. ❌ **Assertion Weakening / Test Deletion:** Modifying test assertions, deleting failing test cases, or widening tolerances simply to make a red test turn green.
5. ❌ **Hardcoding Domain Constants in Code:** Storing business rules, operational limits, or entity definitions in code constants instead of querying the live systems of record.

### 3.2 Mandatory 4-Step RCA Protocol
Execute these four steps sequentially whenever a failure or defect occurs:
1. **Step 1: Deep Root Cause Analysis (RCA):**
   - Inspect live database records, ADK `FunctionTool` docstrings, model system prompts, temperature settings, network logs, and stack traces to isolate the true data, cognitive, or architectural root cause.
2. **Step 2: Transparent Failure Explanation to User:**
   - Present a factual diagnostic report detailing the exact failing test/prompt, expected vs. actual output, technical root cause mechanics, and supporting log/query evidence.
3. **Step 3: Present Architectural Fix Options & Trade-Offs:**
   - Formulate at least **two (2) viable, sustainable architectural options** (e.g., Data Tier Resolution, Cognitive Tool Prompt/Docstring Refinement, or Schema/Contract Hardening) with pros, cons, blast radius, and effort.
4. **Step 4: Await Explicit User Instruction (`ask_question`) Before Coding:**
   - Present the options via `ask_question` and wait for the user's explicit selection before writing any code modification.

---

## 4. Workspace Scaffolding & Phase-by-Phase Output Folders (`specs/` vs. `docs/`)

- **Automatic Scaffolding on Skill Activation (`--init`):** Canonical templates for `specs/` and `docs/` reside in [`_agents/skills/ai_sdlc/examples/specs/`](../skills/ai_sdlc/examples/specs/) and [`_agents/skills/ai_sdlc/examples/docs/`](../skills/ai_sdlc/examples/docs/). When the `ai-sdlc` skill is activated, running `python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --init` automatically scaffolds `specs/` and `docs/` into the project root.
- **Phase 1 (Inception) Outputs:** Brownfield discovery in `specs/baseline/`, intent & architecture framing in `specs/features/SPEC-*.md` (Sections 1–2), and companion architecture/cost reports in `docs/*-architecture.{md,html}` & `docs/gcp_cost_estimate_*.md`.
- **Phase 2 (Execution / SDD) Outputs:** Complete feature SDD (`specs/features/SPEC-*.md`), production code (`app/`, `src/`, `server/`), Unit & Property-Based Tests (`tests/`, `evals/`), and living execution progress reports (`specs/plan/PROGRESS_REPORT_*.md`).
- **Phase 3 (Operation / Deploy) Outputs:** Pre-build CodeMender SAST reports (`docs/codemender-*.md`), CI/CD & IaC (`cloudbuild.yaml`, `terraform/`, `.env.example`), and final post-deploy verification updates in `specs/plan/PROGRESS_REPORT_*.md`.

