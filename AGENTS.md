# Agent Operating Manual & Executive Governance Router (`AGENTS.md`)

This repository operates under the **3-Phase AI-Driven Software Development Lifecycle (AI-SDLC)**, **Spec-Driven Development (SDD)**, and a strict **Dual-Runtime Cloud Architecture**. To prevent context bloat, this file serves as the concise executive router; detailed directives live in [`_agents/rules/`](./_agents/rules/) and [`_agents/skills/`](./_agents/skills/).

## 1. Mandatory Lifecycle Workflow & Rule Routing

Whenever a developer initiates or continues any feature, architecture design, bug fix, refactoring, or deployment, you **MUST** activate the **[`ai-sdlc` skill](./_agents/skills/ai_sdlc/SKILL.md)** and enforce these three consolidated governance rules:

| Rule File | Trigger | Core Scope & When to Read |
| :--- | :--- | :--- |
| **[`ai_sdlc_and_sdd_standards.md`](./_agents/rules/ai_sdlc_and_sdd_standards.md)** | `always_on` | **3-Phase AI-SDLC, SDD & 4-Step RCA:** Enforces Phase 1 (Inception) $\rightarrow$ Phase 2 (SDD Execution) $\rightarrow$ Phase 3 (Operation), mandatory `ask_question` clarification on any unknowns, interactive phase gates, brownfield baselines (`specs/baseline/`), feature specs (`specs/features/`), Unit Tests + Property-Based Tests (PBT) at every step, living progress reports (`specs/plan/`), and the 4-Step Root Cause Investigation protocol on any failing test/eval (zero quick fixes, mockups, or regex workarounds). |
| **[`google_adk_and_agent_runtime.md`](./_agents/rules/google_adk_and_agent_runtime.md)** | `model_decision` | **Conversational AI Agents (`agent_runtime`):** Read when designing, coding, evaluating, or deploying AI agents. Enforces official `google-adk` (`Agent`, `FunctionTool`, `before_agent_callback` Model Armor hooks), cognitive model-driven reasoning with Canonical MECE Intent Topology (`OTHERS` included, zero regex/keyword routing), `agents-cli deploy`, and live `agents-cli eval run` ($\ge 95\%$ precision, $1.000$ groundedness). |
| **[`devops_security_and_quality_standards.md`](./_agents/rules/devops_security_and_quality_standards.md)** | `model_decision` | **Cloud Run, DevSecOps & IaC (`cloud_run`):** Read when working on Git branches (`main`/`develop` $\rightarrow$ `prod`), static code quality, pre-build CodeMender SAST (`cm find/verify/fix`), unified single-file `.env` (`NONPROD_*` / `PROD_*`), Cloud Build (`cloudbuild.yaml`), Cloud Run (`/healthz` liveness probe, Logging/Monitoring), Terraform Infrastructure Manager, or IAM Domain Restricted Sharing (zero `allUsers`). |

---

## 2. Dual-Runtime Separation of Responsibilities

| Dimension | Conversational AI Agents & Reasoning Engine | Web Frontend, API Gateway & Streaming Proxies |
| :--- | :--- | :--- |
| **Target Runtime** | **Gemini Enterprise Agent Platform (`agent_runtime`)** | **Google Cloud Run (`cloud_run`)** |
| **Artifacts** | ADK `OrchestratorAgent`, Domain Subagents, Model Armor callbacks, `FunctionTool` registries. | React/Vite UI, Express/FastAPI streaming reverse proxy, `/healthz` probe, auxiliary jobs. |
| **Deployment** | `agents-cli deploy --deployment-target agent_runtime` | Google Cloud Build (`cloudbuild.yaml`) + Terraform via Infrastructure Manager |
| **Governance Rule** | [`_agents/rules/google_adk_and_agent_runtime.md`](./_agents/rules/google_adk_and_agent_runtime.md) | [`_agents/rules/devops_security_and_quality_standards.md`](./_agents/rules/devops_security_and_quality_standards.md) |

---

## 3. Specialized Agent Skills & Phase Output Map

- **Skills (`_agents/skills/`):**
  - **[`ai-sdlc`](./_agents/skills/ai_sdlc/SKILL.md):** Master 3-Phase AI-SDLC orchestrator, workspace scaffolder (`validate_sdlc_gate.py --init`), and gate validator.
  - **[`architecture-diagram`](./_agents/skills/architecture_diagram/SKILL.md):** Interactive dark-themed technical architecture diagrams (`docs/*-architecture.md` & `.html`).
  - **[`codemender`](./_agents/skills/codemender/SKILL.md):** Pre-build SAST vulnerability discovery, sandbox PoC verification, and automated patching (`docs/codemender-*.md`).
  - **[`gcp-cost-estimator`](./_agents/skills/gcp_cost_estimator/SKILL.md):** Live Google Cloud Billing API cost estimation & BoM modeling (`docs/gcp_cost_estimate_*.md`).
- **Workspace Scaffolding & Phase Output Directories:**
  - **On `ai-sdlc` Activation (`--init`):** Scaffolds `specs/` and `docs/` into the project root from [`_agents/skills/ai_sdlc/examples/specs/`](./_agents/skills/ai_sdlc/examples/specs/README.md) and [`_agents/skills/ai_sdlc/examples/docs/`](./_agents/skills/ai_sdlc/examples/docs/README.md).
  - **Phase 1 (Inception):** `specs/baseline/*.md` (brownfield baseline), `specs/features/SPEC-*.md` (Sections 1–2), `docs/*-architecture.{md,html}`, `docs/gcp_cost_estimate_*.md`.
  - **Phase 2 (Execution / SDD):** `specs/features/SPEC-*.md` (Sections 1–8), `app/` (ADK agents), `src/` & `server/` (Cloud Run UI/proxy), `tests/` & `evals/`, `specs/plan/PROGRESS_REPORT_*.md`.
  - **Phase 3 (Operation / Deploy):** `docs/codemender-*.md` (SAST), `cloudbuild.yaml`, `terraform/`, `.env.example`, and final updates to `specs/plan/PROGRESS_REPORT_*.md`.

