# Agent Governance, Rules & Skills Framework (`_agents/`)

This directory houses the foundational rules, operational guidelines, and specialized skills governing autonomous AI agents and human developers operating within this repository.

## Directory Structure

```
_agents/
├── README.md                      # Index and framework overview
├── rules/                         # Repository governance and engineering rules
│   ├── README.md                  # Rules catalog and enforcement summary
│   ├── ai_sdlc_and_sdd_standards.md # [always_on] 3-Phase AI-SDLC, SDD Cycle, Unit/PBT & 4-Step RCA Standard
│   ├── google_adk_and_agent_runtime.md # [model_decision] Google ADK, Agent Runtime, Model Reasoning & Live Eval
│   └── devops_security_and_quality_standards.md # [model_decision] 10 DevOps, CI/CD, CodeMender SAST & Cloud Run IaC rules
└── skills/                        # Specialized agent skill toolkits
    ├── README.md                  # Skills catalog and operational workflows
    ├── ai_sdlc/                   # End-to-end 3-Phase AI-SDLC orchestrator (Inception -> Execution -> Operation)
    ├── architecture_diagram/      # Professional technical/cloud architecture diagrams & HTML assets
    ├── codemender/                # Pre-build SAST vulnerability discovery, triage, and patching
    └── gcp_cost_estimator/        # Real-time GCP cloud cost estimation using live Billing API rates
```

---

## The Three Consolidated Governance Rules (Hybrid Trigger Architecture)

All agent and developer workflows comply with three consolidated rule files in [`_agents/rules/`](./rules/):

1. **3-Phase AI-SDLC, Spec-Driven Development (SDD) & 4-Step RCA (`trigger: always_on`):** Orchestrated by the [`ai-sdlc` skill](./skills/ai_sdlc/SKILL.md) across **Phase 1: Inception**, **Phase 2: Execution (SDD)**, and **Phase 3: Operation**. Enforces `ask_question` clarification on any unknowns, interactive phase gates, brownfield baselines (`specs/baseline/`), feature specs (`specs/features/`), Unit + Property-Based Tests (PBT) at every step, continuous progress tracking (`specs/plan/`), and the **Mandatory 4-Step RCA Protocol** on failing tests/evals (zero quick patches, mockups, or regex workarounds) ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](./rules/ai_sdlc_and_sdd_standards.md)).
2. **Google ADK & Agent Platform Runtime (`trigger: model_decision`):** Conversational AI agents and reasoning engines built with official Google ADK (`google-adk`) and deployed exclusively to the Gemini Enterprise Agent Platform (`agent_runtime`) via `agents-cli deploy`. Strictly cognitive model-driven reasoning and structured FunctionTools; zero hardcoded keywords or regex routing. Live evaluation via `agents-cli eval` ($\ge 95\%$ tool selection precision, 1.000 groundedness) ([`_agents/rules/google_adk_and_agent_runtime.md`](./rules/google_adk_and_agent_runtime.md)).
3. **DevOps, Security & Cloud Run Services (`trigger: model_decision`):** Single GitHub repository with multi-branch promotion. Pre-build SAST with CodeMender. Cloud Build CI/CD, Cloud Run hosting for web frontends and streaming API proxies with `/healthz` liveness probes, unified single-file `.env` parameter management, Infrastructure Manager Terraform IaC, and Domain Restricted Sharing (zero `allUsers`) ([`_agents/rules/devops_security_and_quality_standards.md`](./rules/devops_security_and_quality_standards.md)).

---

## Runtime Separation Architecture

| Workload Dimension | Conversational AI Agents & Reasoning Engine | Web Frontend, API Gateway & Streaming Proxies |
| :--- | :--- | :--- |
| **Target Runtime** | **Gemini Enterprise Agent Platform (`agent_runtime`)** | **Google Cloud Run (`cloud_run`)** |
| **Artifacts** | ADK Root Coordinator, Subagents, Model Armor hooks, `FunctionTool` registries. | React/Vite UI, Express/FastAPI proxy, WebSocket/SSE endpoints. |
| **Deployment** | `agents-cli deploy --deployment-target agent_runtime` | Cloud Build (`cloudbuild.yaml`) + Terraform via Infrastructure Manager |
| **Governance Rule** | [`_agents/rules/google_adk_and_agent_runtime.md`](./rules/google_adk_and_agent_runtime.md) | [`_agents/rules/devops_security_and_quality_standards.md`](./rules/devops_security_and_quality_standards.md) |

---

## Related Documentation
- **Operating Manual:** [`AGENTS.md`](../AGENTS.md)
- **Specifications Registry Template (Scaffolded on `ai-sdlc` activation):** [`skills/ai_sdlc/examples/specs/README.md`](./skills/ai_sdlc/examples/specs/README.md)
- **Operational Reports Template (Scaffolded on `ai-sdlc` activation):** [`skills/ai_sdlc/examples/docs/README.md`](./skills/ai_sdlc/examples/docs/README.md)

