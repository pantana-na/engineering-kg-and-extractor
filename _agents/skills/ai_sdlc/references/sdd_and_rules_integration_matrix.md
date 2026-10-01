# AI-SDLC Integration Matrix: SDD Standard, Governance Rules & Companion Skills

This reference explains how the **[`ai-sdlc` skill](../SKILL.md)** integrates with [`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../../rules/ai_sdlc_and_sdd_standards.md), the repository's governance rules, and companion skills across the 3-Phase lifecycle.

---

## 1. How `ai-sdlc` Integrates with `ai_sdlc_and_sdd_standards.md`

The **Spec-Driven Development (SDD)** standard ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../../rules/ai_sdlc_and_sdd_standards.md)) forms the core engine of **Phase 2 (Execution)** while linking directly into **Phase 1 (Inception)** upstream and **Phase 3 (Operation)** downstream:

| AI-SDLC Phase | SDD Lifecycle Mapping (`ai_sdlc_and_sdd_standards.md`) | Primary Artifacts & Directories | Interactive Gate (`ask_question`) |
| :--- | :--- | :--- | :--- |
| **Phase 1: Inception**<br>*(Intent Framing & Architecture)* | **Pre-SDD Framing & SDD Phase 0 Discovery:**<br>- Elicits business intent, personas, goals/non-goals.<br>- Identifies brownfield vs. greenfield scope.<br>- Establishes Dual-Runtime split (`agent_runtime` vs `cloud_run`), ADK hierarchy, and IAM/Ingress pattern.<br>- Triggers companion architecture & cost skills. | - `docs/*-architecture.md` & `.html`<br>- `docs/gcp_cost_estimate_*.md`<br>- Feeds Sections 1 & 2 of SDD | **Gate 1:** Clarify all intent/architecture unknowns & obtain sign-off before authoring SDD. |
| **Phase 2: Execution**<br>*(Spec-Driven Development Cycle)* | **SDD Phases 0 through 5:**<br>- **SDD Phase 0:** Brownfield Baseline (`specs/baseline/`).<br>- **SDD Phase 1:** Specification Authoring (`specs/features/`).<br>- **SDD Phase 2:** Granular Step-by-Step Implementation Plan + Unit Tests + PBT + Live Agent Eval design.<br>- **SDD Phase 3:** Stakeholder Review & Alignment.<br>- **SDD Phase 4:** Step-by-Step Implementation + Testing + 4-Step RCA on failures.<br>- **SDD Phase 5:** Verification, Living Spec Sync & Plan Progress Tracking. | - `specs/baseline/*.md`<br>- `specs/features/SPEC-YYYYMMDD-*.md`<br>- `src/`, `server/`, `app/`, `tests/`, `evals/`<br>- `specs/plan/PROGRESS_REPORT_*.md` | **Sub-Gate 2A (SDD Phase 3):** Approve SDD & Test Plan before coding.<br>**Sub-Gate 2B (RCA):** Select architectural fix if any test/eval fails.<br>**Gate 2:** Approve completed SDD execution before Operation. |
| **Phase 3: Operation**<br>*(Integrate & Deploy)* | **Post-Implementation DevSecOps & Runtime Promotion:**<br>- Executes Step 5 & Step 6 of the SDD Implementation Plan in live cloud environments.<br>- Synchronizes final operational telemetry back into `specs/plan/`. | - `docs/codemender-*.md`<br>- `.env` / `.env.example`<br>- `cloudbuild.yaml`, `terraform/`, `agents-cli-manifest.yaml`<br>- `specs/plan/PROGRESS_REPORT_*.md` | **Sub-Gate 3A:** CodeMender SAST verify/fix confirmation.<br>**Sub-Gate 3B:** Confirm target branch & live cloud deployment.<br>**Final Sign-Off:** Operational closure. |

---

## 2. Hybrid Trigger Architecture: `AGENTS.md` + 3 Consolidated Rules + `ai-sdlc` Skill

To enforce strict lifecycle compliance while minimizing context token consumption across turns, this repository uses a 3-layer customization design:
1. **Executive Router ([`AGENTS.md`](../../../../AGENTS.md)):** A concise (~45-line) workspace root index that routes the agent to the `ai-sdlc` skill and the 3 consolidated rules without duplicating detailed text.
2. **Always-On Lifecycle, SDD & RCA Rule ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../../../rules/ai_sdlc_and_sdd_standards.md) — `trigger: always_on`):**
   - Unconditionally active on every turn so the agent never skips **Phase 1 (Inception)**, **Phase 2 (SDD Execution)**, or **Phase 3 (Operation)**, always asks clarification questions (`ask_question`) on unknowns, enforces interactive phase gates, and executes the **4-Step RCA Protocol** on any failing test/eval.
3. **Domain-Specific Rules (`trigger: model_decision`) & On-Demand Skills:**
   - [`google_adk_and_agent_runtime.md`](../../../rules/google_adk_and_agent_runtime.md) and [`devops_security_and_quality_standards.md`](../../../rules/devops_security_and_quality_standards.md) use `trigger: model_decision` with rich descriptions so they load automatically when working on ADK agents (`agent_runtime`) or Cloud Run/DevSecOps (`cloud_run`), saving context tokens when not needed.

---

## 3. Mapping the 3 Consolidated Governance Rules Across AI-SDLC Phases

| Governance Rule File | Trigger | Phase 1: Inception | Phase 2: Execution (SDD) | Phase 3: Operation |
| :--- | :--- | :--- | :--- | :--- |
| **[`ai_sdlc_and_sdd_standards.md`](../../../rules/ai_sdlc_and_sdd_standards.md)** | `always_on` | Mandates Intent & Architecture framing, brownfield baseline check (`specs/baseline/`), zero-assumption `ask_question` elicitation, and Gate 1 sign-off. | Enforces SDD Steps 0–5: Baseline SDD, Feature SDD, Step-by-Step Plan, Unit Tests + PBT at every step, **Mandatory 4-Step RCA Protocol** on any red test/eval, Zero Spec Drift, `specs/plan/` tracking, and Gate 2 sign-off. | Synchronizes final deployment & live verification metrics into `specs/plan/PROGRESS_REPORT_<DATE>.md` and enforces 4-Step RCA if post-deploy checks fail. |
| **[`google_adk_and_agent_runtime.md`](../../../rules/google_adk_and_agent_runtime.md)** | `model_decision` | Frames Agent Platform (`agent_runtime`) boundary, ADK Agent hierarchy, Canonical Intent Topology (`OTHERS`), and Model Armor hooks. | Enforces `google-adk` `Agent`/`FunctionTool` implementation, comprehensive tool docstrings, zero regex/keyword routing, and unit/PBT intent tests. | Enforces `agents-cli deploy --deployment-target agent_runtime` and live environment `agents-cli eval run` ($\ge 95\%$ precision, $1.000$ groundedness). |
| **[`devops_security_and_quality_standards.md`](../../../rules/devops_security_and_quality_standards.md)** | `model_decision` | Frames Cloud Run (`cloud_run`) boundary, `/healthz` requirement, and IAM/Ingress Pattern (Rules 6 & 10). | Enforces Section 6 Governance Checklist in SDD and zero hardcoded config parameters in code (Rule 8). | Enforces Rules 1–10: Multi-branch Git (`main` $\rightarrow$ `prod`), static quality, CodeMender SAST, Artifact Analysis, Cloud Build, Cloud Run `/healthz` + Logging/Monitoring, smoke tests, unified `.env`, and Terraform Infrastructure Manager. |

---

## 4. Companion Skills Orchestration Map

| Companion Skill | Skill Path | Triggered In | Output Artifacts in `docs/` |
| :--- | :--- | :--- | :--- |
| **`architecture-diagram`** | [`_agents/skills/architecture_diagram/SKILL.md`](../../architecture_diagram/SKILL.md) | **Phase 1 (Inception):** Step 1.4 after framing runtime split & component topology. | `docs/<project>-architecture.md`<br>`docs/<project>-architecture.html` |
| **`gcp-cost-estimator`** | [`_agents/skills/gcp_cost_estimator/SKILL.md`](../../gcp_cost_estimator/SKILL.md) | **Phase 1 (Inception):** Step 1.4 (or Phase 3 pre-deploy) to model live GCP Billing API run-rates. | `docs/gcp_cost_estimate_<project>.md` |
| **`codemender`** | [`_agents/skills/codemender/SKILL.md`](../../codemender/SKILL.md) | **Phase 2 (Step 5) / Phase 3 (Step 3.1):** Pre-build SAST discovery (`cm find`), PoC triage (`cm verify`), and patching (`cm fix`). | `docs/codemender-01-vulnerability-scan-report.md`<br>`docs/codemender-02-verification-report.md`<br>`docs/codemender-03-remediation-report.md`<br>`docs/codemender-security-audit-summary.md` |
