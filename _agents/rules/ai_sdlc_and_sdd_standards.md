---
trigger: always_on
description: "Core always-on engineering rule enforcing the 3-Phase AI-Driven Software Development Lifecycle (AI-SDLC) via the ai-sdlc skill, authoritative adherence to the Google Cloud Well-Architected Framework (WAF) and Google Secure AI Framework (SAIF / SAIF 2.0) via the gcp-well-architected-saif skill (which take strict precedence in case of conflict), proactive ask_question clarification on unknowns, Spec-Driven Development (SDD) with brownfield baselines and Unit/Property-Based Testing at every step, and the mandatory 4-Step Root Cause Investigation (RCA) protocol."
---

# Rule: 3-Phase AI-SDLC, Spec-Driven Development (SDD), WAF/SAIF Precedence & Root Cause Investigation Standard

## Core Mandate
All software engineering, solution design, architectural framing, feature development, refactoring, testing, bug fixing, and cloud/agent deployments in this repository **MUST strictly follow the 3-Phase AI-Driven Software Development Lifecycle (AI-SDLC)** orchestrated by the **[`ai-sdlc` skill](../skills/ai_sdlc/SKILL.md)** and adhere to the **[Google Cloud Well-Architected Framework (WAF)](https://docs.cloud.google.com/architecture/framework)** and **[Google Secure AI Framework (SAIF / SAIF 2.0)](https://safety.google/intl/en/safety/saif/)** enforced by the **[`gcp-well-architected-saif` skill](../skills/gcp_well_architected_saif/SKILL.md)**:

1. **Phase 1: Inception (Intent Framing, WAF 6-Pillar & SAIF Security Architecture)**
2. **Phase 2: Execution (The Spec-Driven Development Cycle)**
3. **Phase 3: Operation (Repository Integration, Security Gates & Dual-Runtime Deployment)**

> **Supreme Precedence Mandate:** In case of any conflict between legacy rules, templates, or heuristics and the **Google Cloud Well-Architected Framework (WAF)** or **Google Secure AI Framework (SAIF)**, **WAF and SAIF take strict precedence**.

Whenever a user initiates or continues a project, solution design, feature, architectural change, bug fix, or deployment, the agent **MUST immediately load and follow [`_agents/skills/ai_sdlc/SKILL.md`](../skills/ai_sdlc/SKILL.md)** and **[`_agents/skills/gcp_well_architected_saif/SKILL.md`](../skills/gcp_well_architected_saif/SKILL.md)**, and load the relevant domain rules:
- **Conversational AI Agents & SAIF 2.0 (`agent_runtime`):** [`_agents/rules/google_adk_and_agent_runtime.md`](./google_adk_and_agent_runtime.md)
- **Cloud Run, WAF 6-Pillar DevSecOps, CI/CD, SAST & IaC (`cloud_run`):** [`_agents/rules/devops_security_and_quality_standards.md`](./devops_security_and_quality_standards.md)

---

## 1. Mandatory Requirement Analysis, Zero-Assumption Clarification & Phase Gate Protocol

Across **every phase** of the AI-SDLC (Inception, Execution, and Operation):

1. **Analyze Context First, Then Clarify Missing Inputs (`Analyze -> ask_question` Mandate):**
   - **Step A — Analyze Requirements & Repository First:** Always inspect the user's prompt, attached documents, existing repository code/configs/schemas, and prior `specs/baseline/` or `docs/` artifacts **first** to extract every stated or objectively derivable requirement (never ask redundant questions whose answers already exist in the prompt or codebase).
   - **Step B — Zero Silent Assumptions (`ask_question` on Every Unresolved Section):** The agent **MUST NEVER** guess, invent, or leave `TBD` / `[e.g., ...]` placeholders for unknown business rules, personas, SLAs/RTO/RPO, data models, API error contracts, IAM/Ingress patterns, resiliency bounds, observability/eval targets, FinOps/CFE parameters, ADR trade-offs, or FMEA mitigations. Whenever any required section input in `sdd-template.md` (`Document Control` + Sections `1–10`) or `baseline-template.md` (`Sections 1–8`) remains ambiguous or missing after analysis, the agent **MUST pause and use the `ask_question` tool** (presenting clear choices with `(Recommended)` WAF/SAIF-compliant options and trade-offs) to complete the section before proceeding.
2. **Strict Interactive Phase Gates:**
   - The agent **MUST NOT** automatically transition from **Phase 1 (Inception) $\rightarrow$ Phase 2 (Execution)**, from **Phase 2 Spec Authoring $\rightarrow$ Phase 2 Code Implementation**, or from **Phase 2 (Execution) $\rightarrow$ Phase 3 (Operation)** without presenting the completed phase artifacts and obtaining **explicit user sign-off via `ask_question`**.

```
+===================================================================================+
|                     PHASE 1: INCEPTION (Intent Framing & Architecture)            |
|  - Elicit business intent, personas, goals/non-goals, greenfield vs. brownfield   |
|  - Check/discover brownfield baseline in specs/baseline/                          |
|  - Apply gcp-well-architected-saif: 6 WAF Pillars + AI/ML & FSI Perspectives      |
|  - Define Dual-Runtime Split, ADK Hierarchy, SAIF 2.0 Guardrails & Zero-Trust IAM |
|  - Offer companion skills: architecture-diagram, waf-saif review & cost-estimator |
+===================================================================================+
                                         │
                        [Interactive Gate 1: ask_question Sign-Off]
                                         ▼
+===================================================================================+
|                  PHASE 2: EXECUTION (Spec-Driven Development Cycle)               |
|  - SDD Step 0: Codify Brownfield Baseline (specs/baseline/) if applicable         |
|  - SDD Step 1: Author Feature Specification (specs/features/SPEC-YYYYMMDD-*.md)   |
|                with WAF 6-Pillar, ADR Trade-Off & SAIF 15-Risk Compliance Matrix  |
|  - SDD Step 2: Granular Implementation Plan + Unit Tests + PBT + DLP-Safe Eval    |
|  - SDD Step 3: Stakeholder Review & Alignment Sub-Gate (ask_question sign-off)    |
|  - SDD Step 4: Step-by-Step Code & Test Execution (4-Step RCA on any red test)    |
|  - SDD Step 5: Verification, Living Spec Sync & Progress Report (specs/plan/)     |
+===================================================================================+
                                         │
                        [Interactive Gate 2: ask_question Sign-Off]
                                         ▼
+===================================================================================+
|                PHASE 3: OPERATION (Repository Integration & Deployment)           |
|  - Pre-Merge Gate: Static Analysis + CodeMender SAST + SLSA/Binary Auth + .env    |
|  - Repo Integration: Multi-branch Git (main/develop -> PR to prod), clean tree    |
|  - Dual-Runtime Deploy (inside VPC-SC & CMEK):                                    |
|      1) ADK Agents -> Gemini Enterprise Agent Platform (agents-cli deploy)        |
|      2) Web UI / API Proxy -> Cloud Build + Terraform Infra Manager -> Cloud Run  |
|  - Post-Deploy Gate: Live /healthz, SLO alerts, DLP-safe live agents-cli eval     |
|    (>=95% precision, 1.000 groundedness), Observability check, specs/plan/ sync   |
+===================================================================================+
```

---

## 2. Spec-Driven Development (SDD) & Brownfield Protocol (Phase 2)

**Code is a downstream artifact derived from specification documents.** No feature implementation, architectural change, refactoring, or API modification may begin without an approved Specification Document under `specs/`.

### 2.1 Greenfield vs. Brownfield Triage & Two-Track Brownfield Protocol (Mandatory Baseline & Safety Net First)
In **Phase 1 (Step 1.1)**, always **inspect 3 signals first** (*workspace files*, *`specs/discovery/` or legacy manuals/prompt verbs*, and *`specs/baseline/`*) and **confirm Greenfield vs. Brownfield in the very first `ask_question` call** — never blindly ask before scanning, never silently assume an empty repo is Greenfield (it may be replacing an external legacy system/DB), and never silently assume prototype/boilerplate files are permanent baselines. When **Brownfield** is confirmed (see [`brownfield_assessment_playbook.md`](../skills/ai_sdlc/references/brownfield_assessment_playbook.md)):
1. **Classify & Reverse-Engineer Baseline First (`specs/baseline/`):**
   - Author `specs/baseline/system-overview.md` or `specs/baseline/<subsystem>-baseline.md` using `specs/templates/baseline-template.md` (scaffolded from [`_agents/skills/ai_sdlc/examples/specs/templates/baseline-template.md`](../skills/ai_sdlc/examples/specs/templates/baseline-template.md)).
   - **Track A — Legacy Enterprise / 3-Tier Apps (`.NET Framework`, ASP.NET WebForms/MVC, WCF/SOAP, SQL Server):** Map the Presentation, Business, and Data tiers; extract **hidden business logic** embedded in SQL Stored Procedures (`sp_*`/`usp_*`), Triggers, UI code-behind (`.aspx.cs`), stateful `Session`/`ViewState`, and `Web.config`/`App.config` settings.
   - **Track B — Modern Cloud-Native Code Lacking Docs & Tests:** Reverse-engineer undocumented route/API contracts, reconcile type drift across frontend/backend/DB schemas, and audit against the **13-Rule + WAF/SAIF Governance Gap Matrix** (flagging coupled LLM agents, regex/keyword routing, unauthenticated internal endpoints, missing Indirect Prompt Injection/DLP hooks, missing `/healthz`, or scattered `.env.*` files).
2. **Clarify Baseline Unknowns & Modernization Strategy (`ask_question`):**
   - Pause and use `ask_question` to: (a) decide whether ambiguous/quirky legacy behaviors are **Baseline Invariants** or **Defects to Remediate**, and (b) select the **Modernization Strategy** (*Strangler Fig / API Facade*, *Full Dual-Runtime Re-Architecture*, or *In-Place Cloud-Native Hardening*).
3. **Lock In Characterization Tests & Property-Based Tests (PBT) Before Touching Code:**
   - Backfill **Characterization Unit Tests** (Golden Master input/output parity) and **Generative Property-Based Tests (PBT)** verifying core baseline invariants before refactoring or migrating code.
4. **Baseline Before Delta:** Only after `specs/baseline/` and the characterization test safety net are established may feature specs (`specs/features/`) be drafted against them.

### 2.2 SDD Authoring, Section Completion & Step-by-Step Implementation Plan (`Regular App` vs. `AI Agent` / `Hybrid`)
1. **Enterprise Solution Design & Feature Specification (`specs/features/SPEC-<YYYYMMDD>-<TITLE>.md`):**
   - Author using `specs/templates/sdd-template.md` (scaffolded from [`_agents/skills/ai_sdlc/examples/specs/templates/sdd-template.md`](../skills/ai_sdlc/examples/specs/templates/sdd-template.md)), setting a single active **`Workload Type`** (`Regular App` | `AI Agent` | `Hybrid`) in **Document Control**:
     - **`Regular App` (Non-AI Workload):** Omit or mark `N/A` all subsections/rows tagged **`[AI-Agent Only]`**; enforces **Google Cloud WAF (6 Pillars)** and **Rules 1–10 & Rule 13** on `cloud_run` / GCP native services.
     - **`AI Agent` / `Hybrid` Workload:** Enforces **Dual-Runtime Separation** (`cloud_run` + `agent_runtime`), **Google Cloud WAF (6 Pillars)**, **Google SAIF / SAIF 2.0**, and **all Rules 1–13**.
   - **Section-by-Section Analysis & `ask_question` Completion (`Document Control` + Sections `1–10`):** Follow the Section Completion Matrix in [`phase_questionnaires_and_checklists.md`](../skills/ai_sdlc/references/phase_questionnaires_and_checklists.md) — first analyze requirements, codebase schemas/configs, and `specs/baseline/` to populate known fields, then invoke `ask_question` for any missing inputs across: (1) Executive Summary, Scope & SLAs, (2) Architecture, WAF 6-Pillar & Code Contracts, (3) Security, Privacy, Rules 1–13 & `[AI-Agent Only]` SAIF Alignment, (4) Resiliency, Timeouts, Idempotency & Graceful Degradation, (5) Observability & `[AI-Agent Only]` AgentOps, (6) Performance, FinOps & Sustainability (`CFE %`), (7) ADRs, (8) FMEA, (9) Step-by-Step Plan & Tests, and (10) Plan Progress Tracking. **Zero `TBD`, `[e.g., ...]`, `[Decision Title]`, or unselected union placeholders may remain.**
2. **Mandatory Testing Standards for EVERY Implementation Step:**
   - **Deterministic Unit Tests (Universal):** Concrete examples testing happy paths, boundary conditions, malformed payloads, and error handling.
   - **Generative Property-Based Tests (PBT — Universal):** Mathematical and logical invariants verified across randomized/fuzzed input spaces using `fast-check` (TypeScript/JS) or `hypothesis` (Python).
   - **`[AI-Agent Only]` DLP-Safe Live Environment Agent Evaluation (`agents-cli eval`):** When `Workload Type` is `AI Agent` or `Hybrid`, evaluate ADK agent steps against isolated, de-identified or synthetic-seeded Non-Prod live backends (inside VPC-SC + CMEK) verifying $\ge 95\%$ tool selection precision and $1.000$ ($100\%$) groundedness (see [`google_adk_and_agent_runtime.md`](./google_adk_and_agent_runtime.md)).
3. **Pre-Code Stakeholder Alignment Sub-Gate (`Zero Placeholders` Verified):**
   - Verify all required sections are 100% populated (`validate_sdlc_gate.py --phase execution`), review the authored SDD and step-by-step test plan with the user, and obtain explicit approval via `ask_question` before writing production code.

### 2.3 Living Specs & Plan Progress Tracking (`specs/plan/`)
1. **Zero Spec Drift:** Whenever code contracts, schemas, or behaviors change, update the corresponding SDD in `specs/` in the same change.
2. **Living Plan Progress Reports (`specs/plan/PROGRESS_REPORT_<YYYYMMDD>.md`):**
   - Continuously record linked SDD IDs, step-by-step completion matrices, unit/PBT/live-eval pass metrics, architectural decisions, RCA logs, and next actions.
   - Always update `specs/plan/` and synchronize `specs/README.md` before pausing development or transitioning between phases.

---

## 3. Mandatory 4-Step Root Cause Investigation (RCA), Zero Quick-Patch Standard & WAF Graceful Degradation Harmonization (Rule 13)

When **any** test fails (**Agent Evaluation (`agents-cli eval`)**, **Property-Based Tests (PBT)**, **Unit Tests**, or **Integration/Smoke Tests**), or when a user reports a defect or requests a bug fix:

**DEVELOPERS AND AI AGENTS ARE STRICTLY PROHIBITED FROM APPLYING QUICK FIXES, MOCKUP FALLBACK DATA, REGEX PATCHES, OR RULE-BASED CODE WORKAROUNDS.**

### 3.1 Strictly Prohibited Anti-Patterns (The "Quick-Fix" Trap) vs. Mandatory WAF Graceful Degradation
1. ❌ **Synthetic Mockup Data & Fake Fallback Dictionaries (PROHIBITED):** Injecting synthetic fallback dictionaries or offline mockup records into application code to mask missing/inconsistent database records or fake a passing test (e.g., `if not db_result: return {"id": "ITEM-123", "balance": 500.00}`).
   - ✅ **WAF Pillar 3 Harmonization (Mandatory Graceful Degradation — REQUIRED):** In compliance with the **Google Cloud Well-Architected Framework (Reliability Pillar — *Design for graceful degradation*)**, production services and tools **MUST** implement **circuit breakers, bounded request timeouts, retries with exponential backoff + jitter, Vertex AI Provisioned Throughput $\rightarrow$ PayGo spillover, and transparent degraded-mode responses**. When an upstream dependency is unavailable after retries, the system must return an **explicit, typed degraded-mode status** (`status: "UPSTREAM_UNAVAILABLE_DEGRADED"`) or serve **cryptographically verified, read-only cached static reference data stamped with an explicit `as_of_timestamp` and `is_cached_degraded: true`**, or route cleanly to a human escalation queue—**never** fabricating synthetic live records.
2. ❌ **Rule-Based Quick Patching & Special-Casing:** Writing prompt-specific `if/else` checks or hardcoding special-case answers for specific test inputs.
3. ❌ **Regex & Keyword Heuristics in Agents:** Adding regex matching or substring heuristics to patch agent intent classification or routing errors.
4. ❌ **Assertion Weakening / Test Deletion:** Modifying test assertions, deleting failing test cases, or widening tolerances simply to make a red test turn green.
5. ❌ **Hardcoding Domain Constants in Code:** Storing business rules, operational limits, or entity definitions in code constants instead of querying the live systems of record or externalized policy configuration.

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

- **Automatic Scaffolding on Skill Activation (`--init`):** Canonical templates for `specs/` (`discovery/`, `baseline/`, `features/`, `plan/`, `templates/`) and `docs/` reside in [`_agents/skills/ai_sdlc/examples/specs/`](../skills/ai_sdlc/examples/specs/) and [`_agents/skills/ai_sdlc/examples/docs/`](../skills/ai_sdlc/examples/docs/). When the `ai-sdlc` skill is activated, running `python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --init` automatically scaffolds `specs/` and `docs/` into the project root.
- **Optional Pre-Phase 1 (Discovery) Outputs:** Multi-modal stakeholder input consolidation (`specs/discovery/DISCOVERY-*.md`, 15 sections via [`requirements-discovery`](../skills/requirements_discovery/SKILL.md)), consumed directly by `ai-sdlc` alongside `ask_question`.
- **Phase 1 (Inception) Outputs:** Brownfield discovery in `specs/baseline/`, intent & WAF/SAIF architecture framing in `specs/features/SPEC-*.md` (Sections 1–2), and companion architecture/WAF-SAIF/cost reports in `docs/*-architecture.{md,html}`, `docs/waf-saif-review_*.md` & `docs/gcp_cost_estimate_*.md`.
- **Phase 2 (Execution / SDD) Outputs:** Complete feature SDD (`specs/features/SPEC-*.md`), production code (`app/`, `src/`, `server/`), Unit & Property-Based Tests (`tests/`, `evals/`), and living execution progress reports (`specs/plan/PROGRESS_REPORT_*.md`).
- **Phase 3 (Operation / Deploy) Outputs:** Pre-build CodeMender SAST reports (`docs/codemender-*.md`), CI/CD & IaC (`cloudbuild.yaml`, `terraform/`, `.env.example`), and final post-deploy verification updates in `specs/plan/PROGRESS_REPORT_*.md`.


