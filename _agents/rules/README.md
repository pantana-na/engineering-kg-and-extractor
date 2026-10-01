# Agent Behavioral & Engineering Rules (`_agents/rules/`)

This directory contains the authoritative, non-negotiable governance rules that all autonomous AI agents and developers must strictly follow when operating in this repository.

## Rules Catalog

| Rule File | Trigger | Rule Title | Core Mandate & Enforcement Scope |
| :--- | :--- | :--- | :--- |
| **[`ai_sdlc_and_sdd_standards.md`](./ai_sdlc_and_sdd_standards.md)** | `always_on` | **3-Phase AI-SDLC, Spec-Driven Development (SDD) & Root Cause Investigation** | Orchestrates the [`ai-sdlc` skill](../skills/ai_sdlc/SKILL.md) across Phase 1 (Inception), Phase 2 (SDD Execution), and Phase 3 (Operation). Mandates `ask_question` clarification on any unknowns, interactive phase gates, brownfield baselines (`specs/baseline/`), feature specs (`specs/features/`), Unit Tests + Property-Based Tests (PBT) at every step, living progress tracking (`specs/plan/`), and the **Mandatory 4-Step RCA Protocol** on failing tests/evals (zero quick fixes, mockups, or regex workarounds). |
| **[`google_adk_and_agent_runtime.md`](./google_adk_and_agent_runtime.md)** | `model_decision` | **Google ADK, Agent Runtime, Model-Driven Reasoning & Live Evaluation** | Conversational AI agents built with official `google-adk` (`Agent`, `FunctionTool`, `before_agent_callback`) and deployed to the Gemini Enterprise Agent Platform (`agent_runtime`) via `agents-cli deploy`. Purely cognitive model-driven reasoning; zero regex or hardcoded routing. Continuous live evaluation (`agents-cli eval`) requiring $\ge 95\%$ precision and 1.000 groundedness. |
| **[`devops_security_and_quality_standards.md`](./devops_security_and_quality_standards.md)** | `model_decision` | **DevOps, Security, Quality & Cloud Run Standards** | 10 enterprise rules: Multi-branch promotion (`main`/`develop` $\rightarrow$ `prod`), pre-build CodeMender SAST (`cm`), automated Cloud Build CI/CD, Cloud Run hosting for web apps/proxies with `/healthz` liveness probes, post-deploy smoke tests, unified `.env` parameter management, Infrastructure Manager Terraform IaC, and Domain Restricted Sharing (zero `allUsers`). |

---

## Runtime Separation Matrix

This project strictly delineates workloads across two execution runtimes:

```
+-------------------------------------------------------------+
|                      Client Workloads                       |
|           (Web UI, Streaming Audio/Video, Mobile)           |
+-------------------------------------------------------------+
                              │
               HTTPS / WSS    ▼
+-------------------------------------------------------------+
|               Google Cloud Run (cloud_run)                  |
|  - React / Vite Web Frontends                               |
|  - Reverse Proxies & Streaming API Gateways                 |
|  - Health Probes (/healthz) & Observability                 |
|  - Deployed via Cloud Build + Terraform IaC                 |
+-------------------------------------------------------------+
                              │
              Session Stream  ▼
+-------------------------------------------------------------+
|      Gemini Enterprise Agent Platform (agent_runtime)       |
|  - ADK Orchestrator & Domain Subagents                      |
|  - Cognitive Model-Driven Reasoning (Zero Regex/Heuristics) |
|  - Model Armor Safety Callbacks                             |
|  - FunctionTool Registries & External Backend Integrations  |
|  - Evaluated via agents-cli eval (>= 95% precision, 1.000 G)|
|  - Deployed via agents-cli deploy                           |
+-------------------------------------------------------------+
```

---

## Enforcement & Compliance
- **Automated Validation:** Rules are enforced by CI/CD quality gates, pre-commit checks, and evaluation suites.
- **Specification Linkage:** Every specification authored in [`specs/features/`](../../specs/features/) must verify compliance against each rule using Section 6 of [`specs/templates/sdd-template.md`](../../specs/templates/sdd-template.md).
