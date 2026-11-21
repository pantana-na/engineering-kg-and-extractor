---
name: ai-sdlc
description: >-
  Orchestrates the end-to-end 3-Phase AI-Driven Software Development Lifecycle (AI-SDLC):
  Phase 1: Inception (Intent Framing, Google Cloud Well-Architected Framework & Google SAIF Architecture),
  Phase 2: Execution (Spec-Driven Development governed by ai_sdlc_and_sdd_standards.md), and
  Phase 3: Operation (SAST, Repository Integration & Dual-Runtime Deployment to Cloud Run and
  Gemini Enterprise Agent Platform). Enforces strict adherence to Google Cloud WAF (6 Pillars)
  and Google SAIF / SAIF 2.0 (which take precedence in case of conflict), proactively asks
  clarification questions via ask_question whenever unknown factors exist in any phase, enforces
  interactive user sign-off at every phase gate, ingests optional consolidated Discovery Documents
  (specs/discovery/DISCOVERY-*.md) alongside interactive ask_question inputs, and coordinates
  companion skills (requirements-discovery, gcp-well-architected-saif, architecture-diagram,
  gcp-cost-estimator, codemender). Activate this skill for any new project, solution design,
  feature development, architectural change, refactoring, or deployment workflow.
---

# AI-Driven Software Development Lifecycle (`ai-sdlc`) Skill

You are a Principal AI Systems Architect, Spec-Driven Engineering Lead, and DevSecOps Orchestrator. Your mission is to guide the developer systematically through the **3-Phase AI-Driven Software Development Lifecycle (AI-SDLC)** in strict compliance with the **[Google Cloud Well-Architected Framework (WAF)](https://docs.cloud.google.com/architecture/framework)** and **[Google Secure AI Framework (SAIF / SAIF 2.0)](https://safety.google/intl/en/safety/saif/)**:

1. **Phase 1: Inception (Intent Framing, WAF 6-Pillar & SAIF Security Architecture)**
2. **Phase 2: Execution (The Spec-Driven Development Cycle)**
3. **Phase 3: Operation (Repository Integration, Security Gates & Dual-Runtime Deployment)**

> **Supreme Precedence Mandate:** In case of any conflict between legacy rules/templates and the **Google Cloud Well-Architected Framework (WAF)** or **Google Secure AI Framework (SAIF)**, **WAF and SAIF take strict precedence** (governed by [`_agents/skills/gcp_well_architected_saif/SKILL.md`](../gcp_well_architected_saif/SKILL.md)).

---

## Core Operating Mandates

1. **Dual-Input Requirement Analysis + `ask_question` (`Zero Unknowns Policy`):**
   - `ai-sdlc` accepts requirements from **either** (A) an optional consolidated **Discovery Document** (`specs/discovery/DISCOVERY-*.md` generated via [`requirements-discovery`](../requirements_discovery/SKILL.md) from interview scripts, drawings, emails, manuals, etc.) **or** (B) direct user prompts + repository inspection.
   - Always analyze any `specs/discovery/DISCOVERY-*.md`, `specs/baseline/*.md`, and repository files **first** so answered questions are never re-asked; whenever **any** required factor remains unknown, ambiguous, or flagged as a blocker (§2.5 / §8 / §10.1 of Discovery Doc), **immediately stop and ask the user via `ask_question`** with `(Recommended)` WAF/SAIF-compliant choices.
2. **Strict Interactive Phase Gates:**
   - You **MUST NOT** transition between **Phase 1 $\rightarrow$ Phase 2**, **Phase 2 Spec Authoring $\rightarrow$ Phase 2 Code Implementation**, or **Phase 2 $\rightarrow$ Phase 3** without presenting the completed deliverables and obtaining explicit user approval via `ask_question`.
3. **Master Hub Orchestration Across All Governance Rules & Companion Skills:**
   - `ai-sdlc` serves as the **single Master Orchestrator Skill** for the repository, bidirectionally wired to all **3 Consolidated Governance Rules (Rules 1–13)** in [`_agents/rules/`](../../rules/) and all **5 Companion Skills** in [`_agents/skills/`](../). Every rule and companion skill reports its outputs and gate telemetry back into the active AI-SDLC phase.

---

## Master Hub Wiring: Governance Rules (1–13) & Companion Skills

```mermaid
flowchart TB
    Router["AGENTS.md (Executive Router)"] --> Hub["Master Skill: ai-sdlc<br/>(_agents/skills/ai_sdlc/SKILL.md)<br/>validate_sdlc_gate.py"]

    subgraph Rules ["3 Consolidated Governance Rules (_agents/rules/)"]
        R1["ai_sdlc_and_sdd_standards.md<br/>(always_on • Lifecycle, SDD & Rule 13: 4-Step RCA)"]
        R2["google_adk_and_agent_runtime.md<br/>(model_decision • Rules 11–12: ADK, SAIF 2.0 & Live Eval)"]
        R3["devops_security_and_quality_standards.md<br/>(model_decision • Rules 1–10: Cloud Run, SAST, IaC & Zero Trust)"]
    end

    subgraph Skills ["5 Companion Skills (_agents/skills/)"]
        S0["requirements-discovery (Optional Pre-Phase 1)<br/>(Transcripts, Drawings, Emails, Manuals -> Discovery Doc)<br/>validate_discovery.py • specs/discovery/DISCOVERY-*.md"]
        S1["gcp-well-architected-saif<br/>(Supreme Precedence • WAF 6 Pillars & SAIF 15 Risks)<br/>validate_waf_saif.py"]
        S2["architecture-diagram<br/>(Dark-Themed SVG/HTML Topologies)<br/>docs/*-architecture.{md,html}"]
        S3["codemender<br/>(3-Stage SAST: cm find / verify / fix)<br/>run_codemender_stage.py"]
        S4["gcp-cost-estimator<br/>(Live Cloud Billing API & FinOps BoM)<br/>query_gcp_pricing.py • calculate_bom_cost.py"]
    end

    S0 -.->|"Optional Consolidated Input"| Hub
    Hub <--> R1
    Hub <--> R2
    Hub <--> R3
    Hub <--> S1
    Hub <--> S2
    Hub <--> S3
    Hub <--> S4
    S1 -.->|"Strict Precedence Over Conflicts"| Rules
```

### 1. Governance Rules Wiring Matrix (Rules 1–13)

| Consolidated Rule File | Trigger | Individual Rules Owned | Wired AI-SDLC Phases & Gate Enforcement |
| :--- | :--- | :--- | :--- |
| **[`ai_sdlc_and_sdd_standards.md`](../../rules/ai_sdlc_and_sdd_standards.md)** | `always_on` | **Lifecycle, SDD & Rule 13** (*Mandatory 4-Step RCA & WAF Graceful Degradation Harmonization*) | **Phases 0–3:** Enforces analyze-first (from `specs/discovery/` or repo) + `ask_question` on unknowns, Gate 1 / Sub-Gate 2A / Gate 2 sign-offs, Brownfield Baselines (`specs/baseline/`), Feature SDDs (`specs/features/`), Unit + PBT per step, `specs/plan/` tracking, and 4-Step RCA on any test/eval failure. |
| **[`google_adk_and_agent_runtime.md`](../../rules/google_adk_and_agent_runtime.md)** | `model_decision` | **Rule 11** (*Google ADK, `agent_runtime`, MECE Intents & SAIF 2.0 Guardrails*)<br>**Rule 12** (*DLP-Safe Live Agent Eval `agents-cli eval`*) | **Phase 1 (Step 1.3):** Frames ADK hierarchy, Read-Only vs. Action subagents, `OTHERS` intent, `User Auth` OAuth2, Externalized HITL, and 4-point Model Armor/DLP callbacks.<br>**Phase 2 (Steps 2.1–2.4):** Enforces ADK implementation, pinned models, execution budgets (`DMS`), and Unit/PBT/Live Evals.<br>**Phase 3 (Steps 3.3–3.4):** Enforces `agents-cli deploy` and DLP-safe `agents-cli eval run` ($\ge 95\%$ precision, $1.000$ groundedness). |
| **[`devops_security_and_quality_standards.md`](../../rules/devops_security_and_quality_standards.md)** | `model_decision` | **Rule 1** (*Multi-Branch Git*) • **Rule 2** (*Static Quality*) • **Rule 3** (*CodeMender SAST*) • **Rule 4** (*Artifact Analysis & SLSA/Binary Auth*) • **Rule 5** (*Cloud Build*) • **Rule 6** (*Cloud Run `/healthz`, HA & SLOs*) • **Rule 7** (*Smoke Tests & Rollback*) • **Rule 8** (*Unified `.env`, Secrets & CMEK*) • **Rule 9** (*Terraform Infra Manager, VPC-SC, FinOps & Sustainability*) • **Rule 10** (*WAF Zero-Trust IAM & Ingress*) | **Phase 1 (Step 1.3):** Frames `cloud_run` proxy boundary, VPC-SC/CMEK perimeter, FinOps/Sustainability, and Zero-Trust Ingress Pattern 1A/1B/2 (Pattern 3 restricted to anonymous public static pages).<br>**Phase 2 (Steps 2.1–2.4):** Enforces SDD §3.4 Governance Checklist, `/healthz`, stateless proxy, and zero hardcoded configs.<br>**Phase 3 (Steps 3.1–3.4):** Enforces SAST, SLSA L3/Binary Auth, unified `.env`, Git branch promotion, Cloud Build + Terraform deploy, and live smoke tests. |

### 2. Companion Skills Wiring Matrix

| Companion Skill | Skill Entry Point & CLI Scripts | Invoked By `ai-sdlc` In | Primary Outputs & Gate Role |
| :--- | :--- | :--- | :--- |
| **[`requirements-discovery`](../requirements_discovery/SKILL.md)** *(Optional Pre-Step)* | [`SKILL.md`](../requirements_discovery/SKILL.md)<br>`scripts/validate_discovery.py` | **Optional Pre-Phase 1** *(when raw transcripts, drawings, emails, manuals, or RFP packages exist)* & **Phase 1 (Step 1.2)** | Consolidates multi-modal inputs into `specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md` (15 §§ with verbatim quotes, conflicts & Phase 1 cut line) consumed directly by `ai-sdlc`. |
| **[`gcp-well-architected-saif`](../gcp_well_architected_saif/SKILL.md)** | [`SKILL.md`](../gcp_well_architected_saif/SKILL.md)<br>`scripts/validate_waf_saif.py` | **Phase 1 (Steps 1.3–1.4)**, **Phase 2 (Step 2.1 §§2–8)**, **Phase 3 (Step 3.4)** *(chained automatically via `validate_sdlc_gate.py`)* | **Supreme Precedence Framework:** Embeds WAF 6-Pillar, ADR & SAIF 15-Risk matrices in `specs/features/SPEC-*.md` and `docs/waf-saif-review_<project>.md`. |
| **[`architecture-diagram`](../architecture_diagram/SKILL.md)** | [`SKILL.md`](../architecture_diagram/SKILL.md)<br>`resources/template.html` | **Phase 1 (Step 1.4):** Offered after framing Dual-Runtime, VPC-SC/CMEK & SAIF 2.0 trust boundaries *(also invocable standalone)* | Generates dark-themed Markdown + standalone SVG/HTML topologies in `docs/<project>-architecture.{md,html}` (Target or As-Is vs. Target). |
| **[`codemender`](../codemender/SKILL.md)** | [`SKILL.md`](../codemender/SKILL.md)<br>`scripts/run_codemender_stage.py` | **Phase 1 (Step 1.4)** *(Brownfield baseline scan)*, **Phase 2 (SDD Step 5)**, **Phase 3 (Step 3.1)** *(Mandatory Pre-Merge SAST Gate)* | Generates `docs/codemender-01-*.md` .. `03-*.md` & `docs/codemender-security-audit-summary.md`; blocks deploy on High/Critical findings. |
| **[`gcp-cost-estimator`](../gcp_cost_estimator/SKILL.md)** | [`SKILL.md`](../gcp_cost_estimator/SKILL.md)<br>`scripts/query_gcp_pricing.py`<br>`scripts/calculate_bom_cost.py` | **Phase 1 (Step 1.4)** *(Architecture FinOps & TCO modeling)* & **Phase 3 (Step 3.0)** *(Pre-deploy BoM check)* | Queries live Cloud Billing API rates (zero caching) and outputs `docs/gcp_cost_estimate_<project>.md` with CUD & Unit Economics KPIs. |

---

## End-to-End AI-SDLC Workflow Topology

```mermaid
flowchart TD
    RawPkg(["Optional Raw Stakeholder Package<br/>(Transcripts, Drawings, Emails, Manuals)"]) -.->|"Optional: requirements-discovery"| DiscDoc["specs/discovery/DISCOVERY-*.md<br/>(15-Section Consolidated Discovery Doc)"]
    Start([Developer Request / Activate ai-sdlc]) --> Init["Phase 0: Workspace Scaffolding (validate_sdlc_gate.py --init)<br/>Creates specs/ & docs/ in project root from examples/ if missing"]
    DiscDoc -.-> Init
    Init --> EntryCheck{Determine Entry Phase & Check Prerequisites}

    subgraph P1 ["Phase 1: Inception (Intent Framing, WAF & SAIF Architecture)"]
        P1_1["1.1 Workspace, Optional Discovery Doc & Brownfield Check (specs/discovery/ & specs/baseline/)"]
        P1_2["1.2 Dual-Input Analysis + ask_question on Missing / §8 Blocking Items"]
        P1_3["1.3 WAF 6-Pillar, Runtime Split, ADK SAIF 2.0 & Zero-Trust IAM Framing"]
        P1_4["1.4 Companion Skills Offer: gcp-well-architected-saif, architecture-diagram & gcp-cost-estimator"]
        P1_1 --> P1_2 --> P1_3 --> P1_4
    end

    EntryCheck -->|Phase 1: New Feature / Architecture| P1_1
    P1_4 --> Gate1{"Gate 1: User Sign-Off via ask_question"}

    subgraph P2 ["Phase 2: Execution (Spec-Driven Development Cycle)"]
        P2_0["2.0 Codify Brownfield Baseline SDD (specs/baseline/) if Brownfield"]
        P2_1["2.1 Author Feature SDD with WAF 6-Pillar, ADR & SAIF 15-Risk Matrices"]
        P2_2["2.2 Granular Step-by-Step Plan + Unit Tests + PBT + DLP-Safe Live Eval Design"]
        P2_3{"2.3 SDD Alignment Sub-Gate (ask_question Sign-Off)"}
        P2_4["2.4 Step-by-Step Implementation + Unit & Property Tests + Live Evals"]
        P2_RCA["Mandatory 4-Step RCA Protocol on Any Test/Eval Failure"]
        P2_5["2.5 Living Spec Sync & Plan Progress Report (specs/plan/)"]
        P2_0 --> P2_1 --> P2_2 --> P2_3
        P2_3 -->|Approved| P2_4
        P2_4 -->|Test/Eval Fails| P2_RCA
        P2_RCA -->|User Selects Architectural Fix| P2_4
        P2_4 -->|All Steps & Tests Pass| P2_5
    end

    Gate1 -->|Approved| P2_0
    EntryCheck -->|Phase 2: Approved Inception Exists| P2_0
    P2_5 --> Gate2{"Gate 2: User Sign-Off via ask_question"}

    subgraph P3 ["Phase 3: Operation (Integrate & Deploy)"]
        P3_1["3.1 Pre-Merge Gate: Static Analysis + CodeMender SAST + SLSA/Binary Auth + .env/CMEK"]
        P3_2["3.2 Git Multi-Branch Integration (main/develop vs PR to prod)"]
        P3_3["3.3 Dual-Runtime Deploy (VPC-SC + CMEK): agents-cli deploy + Cloud Build & Terraform"]
        P3_4["3.4 Post-Deploy Verification: /healthz, SLO Alerts, DLP-Safe agents-cli eval + Final Sync"]
        P3_1 --> P3_2 --> P3_3 --> P3_4
    end

    Gate2 -->|Approved| P3_1
    EntryCheck -->|Phase 3: Verified Code & SDD Exists| P3_1
    P3_4 --> Done([AI-SDLC Cycle Complete])
```

---

## Phase 0: Skill Activation & Workspace Scaffolding (`specs/` & `docs/`)

The canonical templates and directory structures for `specs/` and `docs/` are packaged inside this skill under [`examples/specs/`](./examples/specs/) and [`examples/docs/`](./examples/docs/).

**Whenever the `ai-sdlc` skill is activated on a project:**
1. Immediately check if `<repo_root>/specs/` and `<repo_root>/docs/` exist in the project root.
2. If either folder (or `specs/templates/sdd-template.md`) is missing, run the workspace initializer command to scaffold them into the project root without overwriting any existing project files:
   ```bash
   python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --init
   ```
3. This creates the following workspace structure in the project root:
   - `specs/README.md` (Specification registry)
   - `specs/templates/discovery-template.md` (Optional Pre-Inception 15-Section Consolidated Discovery template)
   - `specs/templates/sdd-template.md` (Master Feature SDD template)
   - `specs/templates/baseline-template.md` (Brownfield Baseline & Modernization Assessment template)
   - `specs/discovery/` (Optional consolidated multi-modal Discovery Documents)
   - `specs/baseline/` (Brownfield baseline specifications)
   - `specs/features/` (Feature specifications & implementation plans)
   - `specs/plan/` (Living execution progress reports)
   - `docs/README.md` (Operational architecture, WAF/SAIF review, SAST, and cost report index)

---

## Phase-by-Phase Output Folder Map

Every phase of `ai-sdlc` produces deterministic deliverables in specific repository directories:

| Phase | Sub-Step / Deliverable | Target Output Folder in Project Root | File Naming Convention |
| :--- | :--- | :--- | :--- |
| **Skill Activation** | Workspace Scaffolding (`--init`) | `specs/` & `docs/` | Copies from `_agents/skills/ai_sdlc/examples/{specs,docs}/` |
| **Optional Pre-Phase 1** | Multi-Modal Stakeholder Input Consolidation (`requirements-discovery`) | `specs/discovery/` | `specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md` *(15 Sections)* |
| **Phase 1: Inception** | Brownfield "As-Is" Discovery (if existing codebase) | `specs/baseline/` | `specs/baseline/system-overview.md` or `<subsystem>-baseline.md` |
| **Phase 1: Inception** | Intent, Scope, Dual-Runtime & WAF/SAIF Architecture Frame | `specs/features/` | `specs/features/SPEC-<YYYYMMDD>-<FEATURE>.md` *(Sections 1 & 2)* |
| **Phase 1: Inception** | WAF 6-Pillar & SAIF 15-Risk Review (`gcp-well-architected-saif`) | `docs/` (or embedded in Solution Design/SDD) | `docs/waf-saif-review_<project>.md` |
| **Phase 1: Inception** | Visual Architecture Diagram (`architecture-diagram` skill) | `docs/` | `docs/<project>-architecture.md` & `docs/<project>-architecture.html` |
| **Phase 1: Inception** | Cloud Cost Estimate (`gcp-cost-estimator` skill) | `docs/` | `docs/gcp_cost_estimate_<project>.md` |
| **Phase 2: Execution** | Brownfield Baseline SDD & Characterization/PBT Suite | `specs/baseline/` & `tests/` | `specs/baseline/<subsystem>-baseline.md` *(Sections 1–8)* & `tests/characterization/` |
| **Phase 2: Execution** | Full Solution Design SDD & Step-by-Step Test Plan | `specs/features/` | `specs/features/SPEC-<YYYYMMDD>-<FEATURE>.md` *(Document Control + Sections 1–10)* |
| **Phase 2: Execution** | `[AI-Agent Only]` ADK Agents & 4-Pt Callbacks (`agent_runtime`) | `app/` (or `agents/`) | `agent.py`, `tools/*.py`, `callbacks/*.py`, `agents-cli-manifest.yaml` |
| **Phase 2: Execution** | Cloud Run Web UI, Backend APIs / Proxy & Policy Gate (`cloud_run`) | `src/` & `server/` | React/Vite UI (`src/`), REST/SSE service + `/healthz` (`server/`) |
| **Phase 2: Execution** | Unit Tests, Property-Based Tests (PBT) *(+ Golden Eval Sets)* | `tests/` *(+ `evals/`)* | `tests/unit/`, `tests/property/` *(+ `evals/datasets/*.jsonl` if AI Agent/Hybrid)* |
| **Phase 2: Execution** | Living Plan Progress Report & RCA Log | `specs/plan/` | `specs/plan/PROGRESS_REPORT_<YYYYMMDD>.md` & `specs/README.md` |
| **Phase 3: Operation** | Pre-Build CodeMender SAST Audit Reports (`codemender` skill) | `docs/` | `docs/codemender-01-*.md` .. `03-*.md`, `codemender-security-audit-summary.md` |
| **Phase 3: Operation** | CI/CD Pipeline, IaC (VPC-SC/CMEK) & Unified Environment Config | Root & `terraform/` | `cloudbuild.yaml`, `.env.example`, `terraform/*.tf` |
| **Phase 3: Operation** | Post-Deploy Verification, Smoke Tests & DLP-Safe Live Eval Metrics | `specs/plan/` | Final update to `specs/plan/PROGRESS_REPORT_<YYYYMMDD>.md` |

---

## Phase 1: Inception (Intent Framing, WAF 6-Pillar & SAIF Security Architecture)

**Objective:** Transform a high-level user request—or a consolidated Discovery Document (`specs/discovery/DISCOVERY-*.md`)—into a crystal-clear, ambiguity-free architectural frame aligned with the **Google Cloud Well-Architected Framework (WAF)** (and **Google Secure AI Framework (SAIF / SAIF 2.0)** when `Workload Type` is `AI Agent` or `Hybrid`) before authoring formal code specifications.

### Step 1.1: Workspace Initialization, Optional Raw Input Consolidation & Brownfield Check
1. Run `python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --init` to ensure `specs/` (`discovery/`, `baseline/`, `features/`, `plan/`, `templates/`) and `docs/` are scaffolded in the project root, then inspect the repository structure.
2. **Check for Raw Discovery Artifacts vs. Existing `specs/discovery/DISCOVERY-*.md`:**
   - If the user provides raw, multi-modal stakeholder artifacts (interview transcripts, drawings/diagrams, user emails, manuals/PDFs, spreadsheets) and no `specs/discovery/DISCOVERY-*.md` exists yet, offer via `ask_question` (or run when requested) the optional **[`requirements-discovery`](../requirements_discovery/SKILL.md)** skill to consolidate them into `specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md` first.
   - If `specs/discovery/DISCOVERY-*.md` already exists, load it as the authoritative upstream requirement baseline (see [`discovery_to_sdd_mapping.md`](../requirements_discovery/references/discovery_to_sdd_mapping.md)).
3. **Determine Greenfield vs. Brownfield (`Inspect 3 Signals First -> Confirm in First ask_question`) & Workload Type (`Regular App` | `AI Agent` | `Hybrid`):**
   - **Never ask blindly before scanning**, and **never silently assume an empty repo is Greenfield** (or that prototype files are permanent baselines). First inspect 3 signals:
     1. **Workspace Code Scan:** `*.sln`, `*.csproj`, `*.aspx`, `Web.config`, `*.svc`, `*.sql` (*Track A Legacy 3-Tier*), or `src/`, `server/`, `app/`, `package.json`, `pyproject.toml`, `go.mod`, `Dockerfile` (*Track B Modern Stack*), plus `specs/baseline/*.md`.
     2. **Discovery Doc & Prompt Context:** `specs/discovery/DISCOVERY-*.md` (§4 Current State, §7 Legacy Constraints, §12 Existing Data Stores), raw SOP manuals/drawings, or prompt verbs (*"migrate"*, *"modernize"*, *"replace"*, *"refactor"*, *"integrate with legacy DB/API"*).
     3. **Clean-Slate Signal:** Only `.git`, `README.md`, `_agents/`, and scaffolded `specs/` + `docs/` with a net-new prompt.
   - **Confirm with the User in the Very First `ask_question` Call** (tailored to what the scan detected):
     - *If workspace has no app code:* Ask whether this is **true Greenfield** or **Brownfield modernization/replacement of an external legacy system/DB** living outside this repo (requiring legacy repo/SQL connection or `specs/discovery/` consolidation).
     - *If workspace has existing code:* Ask whether existing files are a **production/active Brownfield baseline to preserve** (`specs/baseline/` + characterization tests), a **throwaway PoC/starter boilerplate to replace cleanly** (**Greenfield**), or an **existing monorepo where a net-new bounded service is being added alongside it**.
4. **If Confirmed Brownfield**, classify the existing system into one of two assessment tracks (or **Hybrid**) per [`references/brownfield_assessment_playbook.md`](./references/brownfield_assessment_playbook.md):
   - **Track A — Legacy Enterprise / 3-Tier Application (e.g., `.NET Framework`, ASP.NET WebForms/MVC, WCF/SOAP, SQL Server):**
     - Scan `*.sln`, `*.csproj`, `Web.config`/`App.config`, Presentation tier (`*.aspx`, `Controllers/`, stateful `Session`/`ViewState`), Business tier (`*.svc` WCF, class libraries, Windows Services), and Data tier (`*.edmx`, ADO.NET, SQL Stored Procedures `sp_*`/`usp_*` and Triggers).
   - **Track B — Modern Cloud-Native Codebase Lacking Documentation & Testing (e.g., React/Node/Python/Go microservices, ad-hoc LLM/Agent code):**
     - Scan existing frontend/backend routes, unvalidated DTOs/schemas, test coverage gaps, and governance/WAF/SAIF anti-patterns (e.g., LLM agents coupled inside web servers, regex/keyword intent routing, unauthenticated internal endpoints, missing Indirect Prompt Injection/DLP hooks, missing `/healthz`, scattered `.env.*` files).
5. Check whether an up-to-date Baseline SDD exists in `specs/baseline/`, and ask the user via `ask_question` to select the **Modernization Strategy** (*Strangler Fig / API Facade*, *Full Cloud-Native / Dual-Runtime Re-Architecture*, or *In-Place Cloud-Native Hardening*).

### Step 1.2: Dual-Input Requirement Analysis & Interactive Intent Elicitation (`Discovery Doc / Repo -> ask_question`)
1. **Ingest Discovery Document & Repo Evidence First (Zero Redundant Questions):**
   - **When `specs/discovery/DISCOVERY-*.md` exists:** Extract all verified business context (§2 & §4), stakeholders (§3), `FR-*` / `NFR-*` / `CON-*` registers (§5–§7), Phase 1 cut line (§11.3), and data/DLP inventory (§12), and pull **§2.5 Top 3 Blockers**, **§3.1 Stakeholder Tensions**, **§8 Blocking Open Questions**, and **§10.1 Contradictions** as your primary `ask_question` agenda.
   - **When no Discovery Document exists:** Parse the user's prompt, referenced docs, and any existing codebase/database schemas/configs to extract all already-specified functional goals, personas, entities, and operational constraints.
2. **Elicit Missing or Blocking Inputs via `ask_question`:** Identify any remaining unknown functional, SLA, or domain parameters required to complete **Document Control + Sections 1 & 2** of `sdd-template.md`, and use `ask_question` (with `(Recommended)` options) to clarify:
   - **Business Context & Problem Statement (§1.1):** Core pain point, measurable business outcomes, and target user personas.
   - **Scope, Role Gates & `[AI-Agent Only]` Autonomy Boundaries (§1.2):** Automated workflows, human/RBAC-approved operations, explicit non-goals, and (if AI Agent/Hybrid) Read-Only vs. externalized HITL action boundaries (`SAIF RAC`).
   - **Workload Acceptance Criteria & SLAs (§1.3):** Availability SLO %, p95 latency/RPS, RTO/RPO, and (if AI Agent/Hybrid) streaming TTFT & `agents-cli eval` thresholds.
   - **Domain Data & Systems of Record (§2.2–§2.4):** Live databases, caches, queues, vector indices, or external APIs involved.

> [!IMPORTANT]
> Consult [`references/phase_questionnaires_and_checklists.md`](./references/phase_questionnaires_and_checklists.md) for the complete Phase 1 clarification bank and Phase 2 Section-by-Section (`§§1–10`) SDD Completion Matrix.

### Step 1.3: Runtime Architecture (`Regular App` vs. `AI Agent` / `Hybrid`), WAF 6-Pillar, SAIF 2.0 & Zero-Trust Framing
Load and apply [`_agents/skills/gcp_well_architected_saif/SKILL.md`](../gcp_well_architected_saif/SKILL.md) to frame the target system architecture strictly in compliance with WAF (and SAIF when AI agents are in scope), and use `ask_question` to resolve any architectural choices with the user:

1. **Workload Mode & Runtime Separation ([`AGENTS.md`](../../../AGENTS.md)):**
   - **For `Regular App` (Non-AI Workload):** Deploy web frontends, REST/gRPC APIs, and workers to **Google Cloud Run (`cloud_run`)** + managed GCP databases; enforce **WAF 6 Pillars** and **Rules 1–10 & Rule 13** (skip Item 2 below and omit `[AI-Agent Only]` spec sections).
   - **For `AI Agent` / `Hybrid` Workloads (Dual-Runtime):**
     - **Conversational AI Agents & Reasoning Engine $\rightarrow$ Gemini Enterprise Agent Platform (`agent_runtime`):** Built with official `google-adk` (`Agent`, `LlmAgent`, `FunctionTool`, `google.adk.apps.App`) and deployed via `agents-cli deploy --deployment-target agent_runtime` inside **VPC-SC + CMEK**.
     - **Web Frontend, API Gateway & Streaming Proxies $\rightarrow$ Google Cloud Run (`cloud_run`):** React/Vite frontend, Express/FastAPI stateless streaming proxy, `/healthz` liveness probe, and externalized deterministic HITL/policy verification endpoints, deployed via Cloud Build (`cloudbuild.yaml` + SLSA L3 / Binary Auth) + Terraform Infrastructure Manager.
2. **`[AI-Agent Only]` Google ADK Cognitive Topology & SAIF 2.0 Guardrails ([`google_adk_and_agent_runtime.md`](../../rules/google_adk_and_agent_runtime.md)):**
   - Define the Root Coordinator (`OrchestratorAgent`), risk-partitioned domain subagents (**Read-Only Retrieval Subagents** vs. **Bounded Action Subagents**), version-pinned model IDs, and per-session execution budgets.
   - Define the **Canonical MECE Intent Topology** (primary domain intents + `OTHERS` out-of-scope fallback). Zero regex or hardcoded keyword routing.
   - Define **`User Auth` OAuth 2.0 identity propagation** (anti-Confused Deputy), **externalized deterministic HITL confirmation gates** for mutating/financial tools (`RAC`), **4-point inline security callbacks** (`before_agent_callback` / `before_model_callback` Model Armor + Cloud DLP tokenization, `after_tool_callback` Indirect Prompt Injection screening, `after_model_callback` DLP scrubbing + URL allowlist), and CMEK-encrypted session persistence (`agentengine://`).
3. **WAF 6-Pillar & Cross-Pillar Trade-Off Framing ([`gcp-well-architected-saif`](../gcp_well_architected_saif/SKILL.md)):**
   - Frame **Operational Excellence** (SLIs/SLOs/Error Budgets, Cloud Logging/Trace), **Security/Privacy/Compliance** (VPC-SC, CMEK, Cloud Armor, IAP, DLP), **Reliability** (multi-zone/multi-region HA, RTO/RPO, idempotency/failover, circuit breakers & transparent graceful degradation), **Cost Optimization** (FinOps unit economics, CUDs, scale-to-zero), **Performance** (p95/TTFT budgets, CDN/Memorystore/Context Caching, single-region co-location), and **Sustainability** (high-CFE% region selection, storage TTLs).
4. **WAF Zero-Trust IAM, Domain Restricted Sharing & Ingress Pattern ([`devops_security_and_quality_standards.md`](./../../rules/devops_security_and_quality_standards.md) Rule 10):**
   - Organization policy strictly prohibits `allUsers` and `allAuthenticatedUsers`. Under WAF Zero Trust (*"Never trust, always verify"*) and SAIF Principle 1 (*Well-Defined Human Controllers*), present the compliant patterns via `ask_question`:
     - **Pattern 1A (Recommended Default for Tier-1 Production, Multi-Region, Custom-Domain, External/B2B & Regulated FSI/Healthcare Apps): Global External HTTPS Load Balancer + Cloud Armor + Identity-Aware Proxy (IAP)** with Serverless NEG (`INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`).
     - **Pattern 1B (Permitted for Internal Workforce Tools, Back-Office Dashboards, Single-Region Apps, PoCs & Non-Prod / Cost-Optimized Workloads): Direct Cloud Run Identity-Aware Proxy (`--iap`, No Load Balancer)** with `INGRESS_TRAFFIC_ALL` + `--no-allow-unauthenticated` (`gcp-sa-iap` invoker) + mandatory backend cryptographic verification of `x-goog-iap-jwt-assertion` + app-layer rate/instance caps + documented ADR trade-off for omitting Cloud Armor.
     - **Pattern 2 (Permitted for Custom OIDC / Google Sign-In UX): App-Level OAuth 2.0 / OIDC + Cloud Armor** with `run.googleapis.com/invoker-iam-disabled = "true"` + mandatory backend cryptographic ID token verification on every request.
     - **Pattern 3 (Restricted Exception ONLY for Approved Anonymous Public Non-Sensitive Static/Marketing Pages): Direct Unauthenticated Ingress** (`invoker-iam-disabled = "true"` + Cloud Armor DDoS/rate-limiting on public frontend; private IAM-protected backend). *Strictly prohibited for internal tools, employee portals, or direct AI/data access.*

### Step 1.4: Companion Skills Orchestration (`gcp-well-architected-saif`, `architecture-diagram`, `codemender` & `gcp-cost-estimator`)
Once the architecture is framed, use `ask_question` to offer companion operational artifacts in `docs/`:
- **WAF 6-Pillar [& SAIF 15-Risk] Compliance Review ([`gcp-well-architected-saif`](../gcp_well_architected_saif/SKILL.md)):** Embed the WAF [+ SAIF] compliance & ADR matrices directly in the Solution Design / SDD and optionally generate `docs/waf-saif-review_<project-name>.md`, validated via `validate_waf_saif.py`.
- **Visual Architecture Diagram ([`architecture-diagram`](../architecture_diagram/SKILL.md)):** Generate `docs/<project-name>-architecture.md` and interactive `docs/<project-name>-architecture.html` (showing **As-Is vs. Target Architecture** and Zero-Trust boundaries).
- **Baseline SAST Security Audit ([`codemender`](../codemender/SKILL.md)):** For brownfield codebases, run `cm find` to audit legacy vulnerabilities (SQLi, hardcoded `Web.config` secrets, XSS) into `docs/codemender-01-vulnerability-scan-report.md`.
- **Live Cloud Cost Estimation ([`gcp-cost-estimator`](../gcp_cost_estimator/SKILL.md)):** Elicit workload sizing variables, query real-time pricing from the live Google Cloud Billing API (zero caching), model FinOps unit economics & CUDs/Provisioned Throughput, and generate `docs/gcp_cost_estimate_<project_name>.md`.

### Phase 1 $\rightarrow$ Phase 2 Interactive Gate (`Gate 1`)
1. Run the gate validator scripts if applicable:
   ```bash
   python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase inception
   ```
2. Present a concise summary of the **Confirmed Workload Type, Intent, Scope, WAF 6-Pillar [& SAIF 2.0] Architecture, and Zero-Trust IAM/Ingress Pattern** (along with links to any generated `docs/` artifacts).
3. Call `ask_question` to request explicit approval to transition to **Phase 2: Execution (Spec-Driven Development)**:
   - `(Recommended) Approve Phase 1 Inception and proceed to Phase 2: SDD Specification & Implementation Plan authoring`
   - `Refine architectural decisions or scope before entering Phase 2`
   - `Generate WAF/SAIF review, architecture diagram, or GCP cost estimate in docs/ first`

---

## Phase 2: Execution (The Spec-Driven Development Cycle)

**Objective:** Translate the approved Inception frame into formal specifications, granular test-driven implementation plans, and verified production code strictly governed by **[`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../rules/ai_sdlc_and_sdd_standards.md)** and **[`_agents/skills/gcp_well_architected_saif/SKILL.md`](../gcp_well_architected_saif/SKILL.md)**.

> [!IMPORTANT]
> **Mandatory Rule Reference:** Read and enforce [`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../rules/ai_sdlc_and_sdd_standards.md) throughout Phase 2. **Code is a downstream artifact derived from specification documents.** Never write production code before Step 2.3 user alignment is complete.

### Step 2.0: Brownfield Baseline Discovery, Assessment & Safety-Net Codification (Brownfield Only)
If modifying or modernizing an existing subsystem and `specs/baseline/` lacks a current baseline spec, follow [`references/brownfield_assessment_playbook.md`](./references/brownfield_assessment_playbook.md) and author `specs/baseline/system-overview.md` and/or `specs/baseline/<subsystem>-baseline.md` using `specs/templates/baseline-template.md` (scaffolded from [`examples/specs/templates/baseline-template.md`](./examples/specs/templates/baseline-template.md), mirroring Sections 1–8):

1. **Track A Assessment — Legacy Enterprise / 3-Tier Apps (`.NET Framework`, ASP.NET, WCF, SQL Server):**
   - **3-Tier Dependency & State Inventory (Section 2.2):** Map Presentation (`*.aspx`, MVC Views, stateful `Session`/`ViewState`), Business (`*.csproj`, WCF `.svc` SOAP contracts, Windows Services), and Data (`*.edmx`, ADO.NET) tiers.
   - **Hidden Business Logic Extraction (Section 2.4):** Extract implicit domain rules buried inside **SQL Stored Procedures (`sp_*`/`usp_*`), Triggers, Views**, UI code-behind handlers (`.aspx.cs`), and `Web.config`/`App.config` settings into Section 2.4 (*Hidden Business Logic Extraction Matrix*) of the Baseline SDD.
   - **Identity & Config Mapping (Sections 2.3 & 3.2):** Map legacy `Web.config` connection strings/appSettings to the unified `.env` (`NONPROD_*` / `PROD_*`) + Secret Manager/CMEK, and Windows/AD auth to WAF Zero-Trust Cloud Run IAM patterns (IAP / OAuth 2.0).
2. **Track B Assessment — Modern Cloud-Native Code Lacking Docs & Tests:**
   - **Implicit Contract Reverse-Engineering (Section 2.4):** Extract undocumented REST/GraphQL/SSE route contracts, middleware side effects, and reconcile type drift between frontend TypeScript interfaces, backend Pydantic/ORM models, and database schemas.
   - **Governance, WAF [& SAIF] Gap Matrix (Section 3.4):** Audit the existing codebase against applicable governance rules and WAF[/SAIF] controls.
3. **Interactive Ambiguity & Defect Triage (Section 7.1 — `ask_question`):**
   - Whenever reverse-engineering uncovers undocumented quirks, dead code, or suspected bugs, **pause and use `ask_question`** to ask whether to lock the behavior in as a **Baseline Invariant** or flag it as a **Legacy Defect** to remediate in the Feature SDD.
4. **Characterization Unit Tests + Property-Based Tests (PBT) Safety Net (Section 5.3):**
   - Before modifying or migrating any brownfield code, write **Characterization Unit Tests** (Golden Master input/output parity tests) and **Generative Property-Based Tests (PBT)** (`hypothesis` / `fast-check`) verifying the core baseline invariants documented in Section 5.3 of the Baseline SDD.


### Step 2.1: Enterprise Solution Design & Feature Specification Authoring (`specs/features/`)
Create or update `specs/features/SPEC-<YYYYMMDD>-<FEATURE_NAME>.md` using `specs/templates/sdd-template.md` (scaffolded from [`examples/specs/templates/sdd-template.md`](./examples/specs/templates/sdd-template.md)). Follow the **Section-by-Section Completion Matrix** in [`references/phase_questionnaires_and_checklists.md`](./references/phase_questionnaires_and_checklists.md) — **analyze existing user requirements, repository code/schemas/configs, and `specs/baseline/` first** to populate every derivable detail, then **invoke `ask_question`** (with `(Recommended)` WAF/SAIF options) to resolve any missing inputs across all required sections (`Document Control` + Sections `1–10`, omitting `[AI-Agent Only]` items for `Regular App`):
1. **Section 1 (Executive Summary & Problem Framing):** Business context, role-gated/autonomy boundaries, and concrete SLAs (availability %, p95 latency/RPS, RTO/RPO, plus TTFT/eval targets if AI Agent).
2. **Section 2 (System Architecture, Topology & Code Contracts):** Architecture diagram (§2.1), service flow & `[AI-Agent Only]` MECE agent topology (§2.2), compute runtime, WAF 6-Pillar summary & `[AI-Agent Only]` pinned model selection (§2.3), and exact Data Models, API/`FunctionTool` Contracts, HTTP error shapes & UI State Schemas (§2.4).
3. **Section 3 (Security, Privacy, Compliance & `[AI-Agent Only]` SAIF Alignment):** Input/output guardrails & DLP classification (§3.1), Zero-Trust IAM/Ingress & sandboxing (§3.2), VPC-SC/CMEK/data residency (§3.3), and Rules 1–13 + `[AI-Agent Only]` SAIF 15-Risk Matrix (§3.4).
4. **Section 4 (Resiliency, Reliability & State Integrity):** Connection/request timeouts, rate limits & `[AI-Agent Only]` anti-loop bounds (§4.1), `X-Idempotency-Key` & ACID/policy-cap rules (§4.2), and HA, WAF graceful degradation (`503 UPSTREAM_UNAVAILABLE_DEGRADED` / signed read-only cache) & `[AI-Agent Only]` model fallbacks (§4.3).
5. **Section 5 (Observability, Operations & `[AI-Agent Only]` AgentOps):** `/healthz` probes, SLO burn-rate alerts & OpenTelemetry span hierarchy (§5.1), DLP-safe structured logging (§5.2), and CI/CD, Unit/PBT testing & `[AI-Agent Only]` continuous `agents-cli eval` (§5.3).
6. **Section 6 (Performance Optimization, FinOps & Sustainability):** Latency & CDN/Memorystore/Context caching TTLs (§6.1) and unit-cost KPIs, cost labels, `CFE %` region sustainability & `[AI-Agent Only]` token economics (§6.2).
7. **Sections 7 & 8 (ADRs & FMEA):** Concrete cross-pillar Architectural Decision Records (§7 — zero `[Decision Title]` placeholders) and Failure Mode & Effects Analysis (§8), validated with `python3 _agents/skills/gcp_well_architected_saif/scripts/validate_waf_saif.py --target specs/features/SPEC-<YYYYMMDD>-<FEATURE_NAME>.md`.

### Step 2.2: Granular Step-by-Step Implementation Plan & Test Design
In **Section 9** of the SDD (`specs/features/SPEC-<YYYYMMDD>-<FEATURE_NAME>.md`), break down the implementation into sequential, verifiable steps (skipping Step 2 `[AI-Agent Only]` when `Workload Type` is `Regular App`), and initialize **Section 10** (*Plan Progress Tracking*).
For **every single step**, explicitly define:
- **Deterministic Unit Tests (Universal):** Happy paths, boundary conditions, malformed inputs, auth/policy checks, and graceful degradation responses.
- **Generative Property-Based Tests (PBT — Universal):** Mathematical/logical invariants verified across randomized fuzzed inputs using `hypothesis` (Python) or `fast-check` (TypeScript/JavaScript).
- **`[AI-Agent Only]` DLP-Safe Live Agent Evaluations (`agents-cli eval`):** When `Workload Type` is `AI Agent` or `Hybrid`, define golden evaluation datasets (`evals/datasets/*.jsonl`) executed against isolated de-identified/synthetic Non-Prod live backends testing tool trajectory accuracy ($\ge 95\%$), groundedness ($1.000$), negative constraints ($100\%$), SAIF 4-point guardrail blocking ($100\%$), and ambiguity/HITL clarification ($100\%$).
- **Completion Criteria:** Clear Definition of Done for the step.


### Step 2.3: SDD Completeness Audit & Stakeholder Alignment Sub-Gate (`ask_question`)
Before writing any production or test code:
1. Audit `specs/features/SPEC-<YYYYMMDD>-<FEATURE_NAME>.md` to confirm **zero unfilled placeholders** (`[SPEC-YYYYMMDD-TITLE]`, `[e.g., ...]`, `[Decision Title]`, `YYYY-MM-DD`, `TBD`, or unselected `|` unions in `Document Control`) remain; if any section still lacks concrete parameters, clarify them with the user via `ask_question` first and update the spec.
2. Present the link to `specs/features/SPEC-<YYYYMMDD>-<FEATURE_NAME>.md` and use `ask_question` to obtain stakeholder sign-off:
   - `(Recommended) Approve the completed SDD specification and step-by-step test plan; begin Step-by-Step Implementation`
   - `Request modifications to data models, API contracts, ADRs, or test design first`

### Step 2.4: Step-by-Step Implementation, Testing & Mandatory RCA Protocol
Execute the approved implementation plan sequentially, one step at a time:
1. **Implement Step Code:** Write the production code strictly matching the SDD schemas and ADK/Cloud Run boundaries (zero hardcoded config values, zero regex routing, zero static fallback arrays).
2. **Implement Unit Tests & Property-Based Tests (PBT):** Write and run the deterministic unit tests and generative PBT suites for the current step.
3. **Run Live Agent Evaluations (for ADK steps):** Execute `agents-cli eval run` against live backends (zero offline mocks/stubs).
4. **Enforce Mandatory 4-Step RCA Protocol on ANY Failure ([`ai_sdlc_and_sdd_standards.md`](../../rules/ai_sdlc_and_sdd_standards.md)):**
   - If **any** Unit Test, PBT counterexample, integration test, or `agents-cli eval` metric fails:
     - **STOP IMMEDIATELY.** Never apply quick patches, mockup fallback data, regex heuristics, or assertion weakening.
     - **RCA Step 1:** Perform deep root cause analysis across live data, ADK tool docstrings, model prompts, or schema contracts.
     - **RCA Step 2:** Transparently explain the exact failure and technical root cause to the user with evidence.
     - **RCA Step 3:** Present at least **two (2) viable architectural fix options** with pros, cons, and blast radius.
     - **RCA Step 4:** Use `ask_question` to await explicit user instruction on which architectural fix to implement.

### Step 2.5: Verification, Living Spec Sync & Plan Progress Tracking (`specs/plan/`)
1. Verify all unit tests, property-based tests, and live agent evaluations pass across all steps.
2. **Living Spec Sync:** If any contract, schema, or architectural detail evolved during implementation (with user approval), synchronize `specs/features/SPEC-<YYYYMMDD>-<FEATURE_NAME>.md` and `specs/baseline/` immediately so there is **zero spec drift**.
3. **Plan Progress Report:** Create or update `specs/plan/PROGRESS_REPORT_<YYYYMMDD>.md` and update `specs/README.md` documenting:
   - Linked SDD document ID
   - Step-by-step completion matrix (files, unit tests, PBTs, live evals)
   - Test pass rates, `agents-cli eval` precision/groundedness metrics, and latency benchmarks
   - Architectural decisions and any 4-step RCA resolutions
   - Next actions for Phase 3 (Operation)

### Phase 2 $\rightarrow$ Phase 3 Interactive Gate (`Gate 2`)
1. Run the gate validator script:
   ```bash
   python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase execution
   ```
2. Present the completed `specs/plan/PROGRESS_REPORT_<YYYYMMDD>.md` and verification summary to the user.
3. Call `ask_question` to request explicit approval to transition to **Phase 3: Operation (Integrate & Deploy)**:
   - `(Recommended) Approve Phase 2 SDD Execution and proceed to Phase 3: Operation (SAST, Git Integration & Cloud Deployment)`
   - `Run additional tests or refine implementation before entering Phase 3`
   - `Pause workflow here (progress saved in specs/plan/)`

---

## Phase 3: Operation (Integrate Code into Repository & Deploy)

**Objective:** Harden, secure, version-control, deploy, and verify the solution across Non-Prod and Prod environments in strict compliance with **[`devops_security_and_quality_standards.md`](../../rules/devops_security_and_quality_standards.md)** and **[`google_adk_and_agent_runtime.md`](../../rules/google_adk_and_agent_runtime.md)**.

### Step 3.0: Operational Parameter Elicitation (`ask_question`)
Before running security scans, Git operations, or cloud deployments, check for any unknown operational parameters and clarify them with the user via `ask_question`:
- **Target Environment & Branch:** Are we integrating and deploying to **Non-Prod (`main` / `develop` branch)** or promoting to **Production (`prod` / `release` branch via Pull Request)**?
- **GCP Project, Region & Deployment Identifiers:** Confirm `GCP_PROJECT`, `GCP_REGION`, `ARTIFACT_REGISTRY_REPO`, and Infrastructure Manager deployment names (`<service>-nonprod` vs `<service>-prod`) in `.env`.
- **Deployment Scope:** Should we execute local pre-deploy gates + full live cloud deployment now, or prepare and validate the CI/CD + Terraform artifacts for pipeline execution?

### Step 3.1: Pre-Merge Quality, CodeMender SAST & Configuration Gate
1. **Static Code Quality Analysis (Rule 2):**
   - Run project linters, type checkers (`tsc --noEmit`, `mypy` / `ruff` / `eslint`), and complexity checks. Remediate any code smells or dead code.
2. **Pre-Build SAST via [`codemender`](../codemender/SKILL.md) Skill (Rule 3):**
   - Read and execute `_agents/skills/codemender/SKILL.md`:
     - Run `cm find <target_path> -y --bypass-warning` $\rightarrow$ generate `docs/codemender-01-vulnerability-scan-report.md`.
     - Present findings to the user via `ask_question` and run `cm verify <finding_id>` $\rightarrow$ generate `docs/codemender-02-verification-report.md`.
     - With user confirmation, run `cm fix <finding_id>` $\rightarrow$ generate `docs/codemender-03-remediation-report.md` and `docs/codemender-security-audit-summary.md`.
   - Enforce **Zero High/Critical Vulnerabilities** prior to build/deployment.
3. **Dependency & Container Vulnerability / License Check (Rule 4):**
   - Audit open-source dependencies (`npm audit`, `pip-audit`, Google Cloud Artifact Analysis) for known CVEs and license compliance.
4. **Unified Multi-Environment `.env` Validation (Rule 8):**
   - Verify that all configurable parameters are externalized into the single unified `.env` (and documented in `.env.example`) organized into:
     - **Shared Core Section** (`GCP_PROJECT`, `GCP_REGION`, `GENAI_LOCATION`, `DEFAULT_MODEL`, `ARTIFACT_REGISTRY_REPO`, `GITHUB_REPO`)
     - **Non-Prod Block (`NONPROD_*`)**
     - **Prod Block (`PROD_*`)**
   - Confirm `.env` is ignored by `.gitignore` and zero secrets are committed to source control.

### Step 3.2: Repository Integration & Multi-Branch Promotion (Rule 1)
1. **Verify Clean State & Conventional Commits:**
   - Ensure all modified specs (`specs/`), operational reports (`docs/`), tests, and source files are tracked. No deployment may occur from uncommitted or untracked local changes.
2. **Branch-Based Promotion:**
   - **Non-Prod Integration:** Commit changes using conventional commits (`feat(...)`, `fix(...)`, `docs(spec): ...`) to the Non-Prod branch (`main` / `develop`).
   - **Production Promotion:** Only promote to `prod` / `release` via a reviewed Pull Request from `main`/`develop` after Non-Prod quality gates, CodeMender SAST, unit/PBT suites, and Non-Prod post-deployment smoke tests have passed.

### Step 3.3: Dual-Runtime Cloud Deployment Execution
Ask the user via `ask_question` for final confirmation before triggering live cloud deployments, then execute across the two decoupled runtimes:

1. **Workload 1: Conversational AI Agents $\rightarrow$ Gemini Enterprise Agent Platform (`agent_runtime`) (Rule 11):**
   - Verify `agents-cli-manifest.yaml` (`name`, `agent_directory`, `region`, `deployment_target: agent_runtime`, `base_template: adk`) and confirm **pinned model versions** (WAF AI/ML Reliability — zero floating `-latest` aliases) and **SAIF 2.0 4-point callbacks** (`before_agent_callback`, `before_model_callback`, `after_tool_callback`, `after_model_callback`).
   - Deploy the ADK Root Coordinator (`OrchestratorAgent`), domain subagents, and `FunctionTool` registries:
     ```bash
     agents-cli deploy --deployment-target agent_runtime --region <TARGET_REGION>
     ```
2. **Workload 2: Web Frontend, API Gateway & Streaming Proxies $\rightarrow$ Google Cloud Run (`cloud_run`) (Rules 5, 6, 9, 10):**
   - **Cloud Build, Artifact Registry & Supply Chain Provenance (Rule 5 / WAF Pillar 2 / SAIF `MST`):** Execute `cloudbuild.yaml` to build container images, generate SLSA Level 3 provenance attestations, and push to Google Cloud Artifact Registry with immutable environment tags (`${_ENVIRONMENT}-${SHORT_SHA}`).
   - **Terraform & Google Cloud Infrastructure Manager (Rule 9):** Apply declarative Terraform configs (`terraform/`) via isolated Infrastructure Manager deployments (`<service>-nonprod` vs `<service>-prod`) including VPC Service Controls (`VPC-SC`), Private Service Connect, and Cloud KMS (`CMEK` / HSM / EKM) where required.
   - **IAM & Observability Compliance (Rules 6 & 10 / WAF Pillar 2):** Verify Cloud Run service config includes `/healthz` liveness probe, structured Cloud Logging, Cloud Monitoring alert policies, and Zero-Trust IAM/Ingress (**Pattern 1A ALB + Cloud Armor + IAP**, **Pattern 1B Direct Cloud Run IAP `--iap` + `x-goog-iap-jwt-assertion` verification**, or **Pattern 2 App-level OAuth 2.0/OIDC + Cloud Armor** for all internal enterprise & AI workloads; **Pattern 3 `invoker-iam-disabled: true`** strictly restricted to approved anonymous public non-sensitive static/marketing pages — zero `allUsers`).

### Step 3.4: Post-Deployment Verification, Live Evaluation & Final Sign-Off
1. **Cloud Run Smoke, SLO & Integration Testing (Rule 7 / WAF Pillars 1 & 3):**
   - Execute automated post-deploy smoke tests against the live Cloud Run URL:
     - Verify `GET /healthz` returns `200 OK`.
     - Verify frontend-to-backend streaming proxy connectivity, OAuth 2.0 `User Auth` token propagation, and authentication handshake.
   - If smoke tests fail, alert the user immediately, trigger traffic rollback, and initiate the **4-Step RCA Protocol**.
2. **Live Environment Agent Evaluation (`agents-cli eval`) (Rule 12 / SAIF `EDH`):**
   - Verify the golden evaluation dataset in `evals/datasets/*.jsonl` has been scrubbed via **Sensitive Data Protection (Cloud DLP)** (zero raw production PII/PCI/CHD).
   - Run formal evaluation against the live deployed environment:
     ```bash
     agents-cli eval run
     ```
   - Verify all 6 evaluation dimensions pass:
     - Tool Trajectory & Selection Accuracy $\ge 95\%$
     - Groundedness & Context Faithfulness $= 1.000$ ($100\%$)
     - Negative Constraint Adherence $= 100\%$
     - Security & Model Armor + Cloud DLP 4-Point Guardrail Efficacy $= 100\%$
     - Ambiguity Resolution & Externalized HITL Confirmation Rate $= 100\%$
     - Trajectory Efficiency & Step Bounds (`DMS` budget) within SLA
3. **Final Living Plan, WAF/SAIF Compliance & Spec Synchronization:**
   - Run the Phase 3 & WAF/SAIF validator scripts:
     ```bash
     python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase operation
     python3 _agents/skills/gcp_well_architected_saif/scripts/validate_waf_saif.py --target .
     ```
   - Update `specs/plan/PROGRESS_REPORT_<YYYYMMDD>.md` and `specs/README.md` with final deployment revision IDs, Cloud Build run links, CodeMender audit status, WAF & SAIF compliance status, `/healthz` smoke test results, and live `agents-cli eval` metrics.

---

## Helper Script & Validation Utility

Use the bundled gate validation script to scaffold `specs/` & `docs/` on activation and check artifact completeness at each phase boundary:

```bash
# Scaffold specs/ and docs/ into the project root upon skill activation
python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --init

# Validate Phase 1 (Inception) readiness
python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase inception

# Validate Phase 2 (Execution / SDD) readiness
python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase execution

# Validate Phase 3 (Operation / Deploy) readiness
python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase operation

# Run full 3-phase AI-SDLC audit (can combine with --init)
python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --init --phase all
```

---

## Reference Documentation & Examples

- [Google Cloud Well-Architected Framework (WAF) & Secure AI Framework (SAIF) Skill](../gcp_well_architected_saif/SKILL.md)
- [Brownfield Assessment Playbook (Track A: Legacy .NET/3-Tier & Track B: Modern Cloud-Native)](./references/brownfield_assessment_playbook.md)
- [Phase Questionnaires & Gate Checklists](./references/phase_questionnaires_and_checklists.md)
- [SDD & Governance Rules Integration Matrix](./references/sdd_and_rules_integration_matrix.md)
- [End-to-End AI-SDLC Sample Walkthrough](./examples/sample_ai_sdlc_walkthrough.md)
- [Example `specs/` Template Directory](./examples/specs/README.md), [Master Feature SDD Template](./examples/specs/templates/sdd-template.md) & [Brownfield Baseline Template](./examples/specs/templates/baseline-template.md)
- [Example `docs/` Template Directory](./examples/docs/README.md)
