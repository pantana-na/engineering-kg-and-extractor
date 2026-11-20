# Agent Operating Manual & Executive Governance Router (`AGENTS.md`)

This repository operates under the **3-Phase AI-Driven Software Development Lifecycle (AI-SDLC)**, **Spec-Driven Development (SDD)**, a strict **Dual-Runtime Cloud Architecture**, and the **[Google Cloud Well-Architected Framework (WAF)](https://docs.cloud.google.com/architecture/framework)** + **[Google Secure AI Framework (SAIF / SAIF 2.0)](https://safety.google/intl/en/safety/saif/)**. To prevent context bloat, this file serves as the concise executive router; detailed directives live in [`_agents/rules/`](./_agents/rules/) and [`_agents/skills/`](./_agents/skills/).

> **Supreme Precedence Mandate:** In case of any conflict between legacy rules, templates, or heuristics and **Google Cloud WAF** or **Google SAIF**, **WAF and SAIF take strict precedence** ([`gcp-well-architected-saif`](./_agents/skills/gcp_well_architected_saif/SKILL.md)).

## 1. Master Hub Skill (`ai-sdlc`) & Consolidated Governance Rules (Rules 1–13)

Whenever a developer initiates or continues any solution design, feature, architecture change, bug fix, refactoring, or deployment, you **MUST** activate the **[`ai-sdlc` master hub skill](./_agents/skills/ai_sdlc/SKILL.md)**—which orchestrates all companion skills and enforces these three consolidated governance rules:

| Rule File & Owned Rules | Trigger | Core Scope & When to Read |
| :--- | :--- | :--- |
| **[`ai_sdlc_and_sdd_standards.md`](./_agents/rules/ai_sdlc_and_sdd_standards.md)**<br>*(Lifecycle, SDD & **Rule 13**)* | `always_on` | **3-Phase AI-SDLC, SDD, WAF/SAIF Precedence & 4-Step RCA:** Enforces optional Pre-Inception Discovery (`specs/discovery/`), Phase 1 (Inception) $\rightarrow$ Phase 2 (SDD Execution) $\rightarrow$ Phase 3 (Operation), **Dual-Input (`specs/discovery/` + repo analysis $\rightarrow$ `ask_question`) to complete every required section of `sdd-template.md` / `baseline-template.md` (zero `TBD` or unfilled placeholders)**, interactive phase gates, brownfield baselines (`specs/baseline/` + Manual-vs-Code drift check), feature specs (`specs/features/`), Unit Tests + Property-Based Tests (PBT) at every step, living progress reports (`specs/plan/`), and **Rule 13: 4-Step Root Cause Investigation** on any failing test/eval (zero fake mockups or regex workarounds; harmonized with WAF Graceful Degradation). |
| **[`google_adk_and_agent_runtime.md`](./_agents/rules/google_adk_and_agent_runtime.md)**<br>*(**Rules 11–12**)* | `model_decision` | **Conversational AI Agents & SAIF 2.0 (`agent_runtime`):** Read when designing, coding, evaluating, or deploying AI agents. Enforces official `google-adk` (`Agent`, `FunctionTool`), cognitive MECE Intent Topology (`OTHERS` included, zero regex/keyword routing), pinned model IDs + execution budgets (`DMS`), `User Auth` OAuth2 propagation (anti-Confused Deputy), externalized deterministic HITL gates (`RAC`), **4-point Model Armor + Cloud DLP callbacks** (`before_agent`, `before_model`, `after_tool` Indirect `PIJ`, `after_model`), `agents-cli deploy`, and DLP-safe live `agents-cli eval run` ($\ge 95\%$ precision, $1.000$ groundedness). |
| **[`devops_security_and_quality_standards.md`](./_agents/rules/devops_security_and_quality_standards.md)**<br>*(**Rules 1–10**)* | `model_decision` | **Cloud Run, WAF 6-Pillar DevSecOps & IaC (`cloud_run`):** Read when working on Git branches (`main`/`develop` $\rightarrow$ `prod`), static code quality, pre-build CodeMender SAST (`cm find/verify/fix`), Artifact Analysis + **SLSA Level 3 / Binary Authorization**, unified single-file `.env` (`NONPROD_*` / `PROD_*`) + Secret Manager/CMEK, Cloud Build (`cloudbuild.yaml`), Cloud Run (`/healthz` probe, SLO burn-rate alerts, OpenTelemetry Trace), Terraform Infrastructure Manager + **VPC-SC** + FinOps + Sustainability (`CFE %`), or **WAF Zero-Trust IAM/Ingress** (Pattern 1A ALB + Cloud Armor + IAP, Pattern 1B Direct Cloud Run IAP, or Pattern 2 OAuth2; zero `allUsers`). |

---

## 2. Workload Modes & Runtime Separation (`Regular App` vs. `AI Agent` / `Hybrid`)

Every specification declares **`Workload Type`** (`Regular App` | `AI Agent` | `Hybrid`) in **Document Control**:
- **`Regular App` (Non-AI Web, API, Microservice, or Data Workload):** Runs on **Google Cloud Run (`cloud_run`)** + managed GCP data services; governed by **Google Cloud WAF (6 Pillars)** and **Rules 1–10 & Rule 13** (omits `[AI-Agent Only]` sections and Rules 11–12).
- **`AI Agent` / `Hybrid` Workload:** Strictly decoupled across **Dual Runtimes** (`cloud_run` + `agent_runtime`); governed by **Google Cloud WAF (6 Pillars)**, **Google SAIF / SAIF 2.0**, and **all Rules 1–13**:

| Dimension | Web Frontend, Backend APIs & Policy Gate *(Universal)* | `[AI-Agent Only]` Conversational AI Agents & Reasoning Engine |
| :--- | :--- | :--- |
| **Target Runtime** | **Google Cloud Run (`cloud_run`)** | **Gemini Enterprise Agent Platform (`agent_runtime`)** |
| **Artifacts** | ALB + Cloud Armor + IAP *(or Direct Cloud Run IAP / OAuth2)*, React/Vite UI, REST/SSE APIs or streaming proxy, `/healthz` probe, deterministic policy/HITL gates. | ADK `OrchestratorAgent`, Read-Only vs. Action Subagents, 4-point Model Armor + Cloud DLP callbacks, `FunctionTool` registries (`User Auth` + HITL). |
| **Deployment** | Google Cloud Build (`cloudbuild.yaml` + SLSA L3/Binary Auth) + Terraform via Infrastructure Manager | `agents-cli deploy --deployment-target agent_runtime` (VPC-SC + CMEK) |
| **Governance Rule** | [`_agents/rules/devops_security_and_quality_standards.md`](./_agents/rules/devops_security_and_quality_standards.md) | [`_agents/rules/google_adk_and_agent_runtime.md`](./_agents/rules/google_adk_and_agent_runtime.md) |

---

## 3. Master Hub & Companion Skills (`_agents/skills/`) + Phase Output Map

- **Hub-and-Spoke Skill Registry (`_agents/skills/`):**
  - **[`ai-sdlc`](./_agents/skills/ai_sdlc/SKILL.md) *(Master Hub)*:** End-to-end 3-Phase AI-SDLC orchestrator wired to all rules and companion skills, workspace scaffolder (`validate_sdlc_gate.py --init`), dual-input consumer (`specs/discovery/` + `ask_question`), and workload-aware phase gate validator.
  - **[`requirements-discovery`](./_agents/skills/requirements_discovery/SKILL.md) *(Optional Pre-Inception Spoke)*:** Consolidates raw interview scripts, drawings/diagrams, emails, and manuals into a citation-grounded 15-section Discovery Document (`specs/discovery/DISCOVERY-*.md`, `validate_discovery.py`) that feeds directly into `ai-sdlc`.
  - **[`gcp-well-architected-saif`](./_agents/skills/gcp_well_architected_saif/SKILL.md) *(Supreme Precedence)*:** Google Cloud WAF (6 Pillars + AI/ML & FSI Perspectives) & Google SAIF / SAIF 2.0 architecture governance (`validate_waf_saif.py`, `docs/waf-saif-review_*.md`).
  - **[`architecture-diagram`](./_agents/skills/architecture_diagram/SKILL.md):** Interactive dark-themed technical & Zero-Trust architecture diagrams (`docs/*-architecture.md` & `.html`).
  - **[`codemender`](./_agents/skills/codemender/SKILL.md):** Pre-build SAST vulnerability discovery, sandbox PoC verification, and automated patching (`docs/codemender-*.md`).
  - **[`gcp-cost-estimator`](./_agents/skills/gcp_cost_estimator/SKILL.md):** Live Google Cloud Billing API cost estimation, FinOps unit economics & CUD/Provisioned Throughput BoM modeling (`docs/gcp_cost_estimate_*.md`).
- **Workspace Scaffolding & Phase Output Directories:**
  - **On `ai-sdlc` Activation (`--init`):** Scaffolds `specs/` (`discovery/`, `baseline/`, `features/`, `plan/`, `templates/`) and `docs/` into the project root from [`_agents/skills/ai_sdlc/examples/specs/`](./_agents/skills/ai_sdlc/examples/specs/README.md) and [`_agents/skills/ai_sdlc/examples/docs/`](./_agents/skills/ai_sdlc/examples/docs/README.md).
  - **Optional Pre-Phase 1 (Discovery):** `specs/discovery/DISCOVERY-*.md` (15-section consolidated requirements, conflicts & Phase 1 cut line).
  - **Phase 1 (Inception):** `specs/baseline/*.md` (brownfield baseline, Sections 1–8), `specs/features/SPEC-*.md` (Document Control + Sections 1–2), `docs/waf-saif-review_*.md`, `docs/*-architecture.{md,html}`, `docs/gcp_cost_estimate_*.md`.
  - **Phase 2 (Execution / SDD):** `specs/features/SPEC-*.md` (Document Control + Sections 1–10), `src/` & `server/` (`cloud_run`), `app/` (`[AI-Agent Only]` ADK agents), `tests/` *(+ `evals/` if AI Agent)*, `specs/plan/PROGRESS_REPORT_*.md`.
  - **Phase 3 (Operation / Deploy):** `docs/codemender-*.md` (SAST), `cloudbuild.yaml`, `terraform/`, `.env.example`, and final updates to `specs/plan/PROGRESS_REPORT_*.md`.

