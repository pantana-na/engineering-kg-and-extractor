# Agent Governance, Rules & Skills Framework (`_agents/`)

This directory houses the foundational rules, operational guidelines, and specialized skills governing autonomous AI agents and human developers operating within this repository, strictly aligned with the **[Google Cloud Well-Architected Framework (WAF)](https://docs.cloud.google.com/architecture/framework)** and **[Google Secure AI Framework (SAIF / SAIF 2.0)](https://safety.google/intl/en/safety/saif/)**.

> **Supreme Precedence Mandate:** In case of any conflict between legacy rules/templates and the **Google Cloud Well-Architected Framework** or **Google Secure AI Framework (SAIF)**, **WAF and SAIF take strict precedence** ([`skills/gcp_well_architected_saif/SKILL.md`](./skills/gcp_well_architected_saif/SKILL.md)).

## Directory Structure

```
_agents/
├── README.md                              # Index and framework overview
├── rules/                                 # Repository governance and engineering rules
│   ├── README.md                          # Rules catalog and enforcement summary
│   ├── ai_sdlc_and_sdd_standards.md       # [always_on] 3-Phase AI-SDLC, SDD, WAF/SAIF Precedence & 4-Step RCA
│   ├── google_adk_and_agent_runtime.md    # [model_decision] Google ADK, Agent Runtime, SAIF 2.0 Guardrails & Eval
│   └── devops_security_and_quality_standards.md # [model_decision] WAF 6-Pillar DevSecOps, Zero Trust, SAST & Cloud Run IaC
└── skills/                                # Specialized agent skill toolkits
    ├── README.md                          # Skills catalog and operational workflows
    ├── ai_sdlc/                           # [MASTER HUB SKILL] 3-Phase AI-SDLC orchestrator wired to all rules & skills
    ├── requirements_discovery/            # [OPTIONAL PRE-INCEPTION] Multi-modal inputs -> 15-section Discovery Doc
    ├── gcp_well_architected_saif/         # [SUPREME PRECEDENCE] Google Cloud WAF (6 Pillars) & Google SAIF / SAIF 2.0
    ├── architecture_diagram/              # Professional technical/cloud architecture diagrams & HTML assets
    ├── codemender/                        # Pre-build SAST vulnerability discovery, triage, and patching
    └── gcp_cost_estimator/                # Real-time GCP cloud cost estimation & FinOps unit economics via live Billing API
```

---

## Master Hub Wiring (`ai-sdlc`) & The Three Consolidated Governance Rules (Rules 1–13)

The **[`ai-sdlc` skill (`skills/ai_sdlc/SKILL.md`)](./skills/ai_sdlc/SKILL.md)** serves as the **central orchestrator hub** wiring all **5 companion skills** and **3 consolidated governance rules (Rules 1–13)** under [`_agents/rules/`](./rules/), anchored by [`gcp-well-architected-saif`](./skills/gcp_well_architected_saif/SKILL.md):

1. **3-Phase AI-SDLC, Spec-Driven Development (SDD), WAF/SAIF Precedence & Rule 13: 4-Step RCA (`trigger: always_on`):** Orchestrated by the [`ai-sdlc` master skill](./skills/ai_sdlc/SKILL.md) and [`gcp-well-architected-saif` skill](./skills/gcp_well_architected_saif/SKILL.md) across **Phase 1: Inception**, **Phase 2: Execution (SDD)**, and **Phase 3: Operation**. Enforces `ask_question` clarification on any unknowns, interactive phase gates, WAF 6-Pillar & SAIF 15-Risk compliance, brownfield baselines (`specs/baseline/`), feature specs (`specs/features/`), Unit + Property-Based Tests (PBT) at every step, continuous progress tracking (`specs/plan/`), and **Rule 13: Mandatory 4-Step RCA Protocol** (harmonizing WAF Graceful Degradation with zero fake/mockup data) ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](./rules/ai_sdlc_and_sdd_standards.md)).
2. **Google ADK, Agent Platform Runtime & SAIF 2.0 Agentic Security — Rules 11–12 (`trigger: model_decision`):** Conversational AI agents built with official Google ADK (`google-adk`) and deployed to the Gemini Enterprise Agent Platform (`agent_runtime`) via `agents-cli deploy`. Enforces **Rule 11** (**SAIF 2.0** controls: `User Auth` OAuth2 identity propagation against Confused Deputy, read-only vs. deterministic externalized HITL action boundaries, 4-point inline **Model Armor + Sensitive Data Protection [Cloud DLP]** callbacks including `after_tool_callback` Indirect Prompt Injection screening, pinned model versions, execution budgets) and **Rule 12** (DLP-safe live evaluation via `agents-cli eval` requiring $\ge 95\%$ tool selection precision and $1.000$ groundedness) ([`_agents/rules/google_adk_and_agent_runtime.md`](./rules/google_adk_and_agent_runtime.md)).
3. **DevOps, WAF 6-Pillar Security & Cloud Run Services — Rules 1–10 (`trigger: model_decision`):** Single GitHub repository with multi-branch promotion (**Rule 1**), static code quality (**Rule 2**), pre-build SAST with CodeMender (**Rule 3**), Artifact Analysis & **SLSA Level 3 / Binary Authorization** (**Rule 4**), Cloud Build CI/CD (**Rule 5**), Cloud Run hosting with `/healthz` probes & SLO burn-rate alerts (**Rule 6**), post-deploy smoke tests (**Rule 7**), unified `.env` + Secret Manager/CMEK (**Rule 8**), Infrastructure Manager Terraform IaC + **VPC-SC** + FinOps + Sustainability `CFE %` (**Rule 9**), and **WAF Zero-Trust IAM/Ingress** (Pattern 1A ALB + Cloud Armor + IAP, Pattern 1B Direct Cloud Run IAP, or Pattern 2 OAuth2; zero `allUsers`) (**Rule 10**) ([`_agents/rules/devops_security_and_quality_standards.md`](./rules/devops_security_and_quality_standards.md)).

---

## Runtime Separation Architecture

| Workload Dimension | Conversational AI Agents & Reasoning Engine | Web Frontend, API Gateway & Streaming Proxies |
| :--- | :--- | :--- |
| **Target Runtime** | **Gemini Enterprise Agent Platform (`agent_runtime`)** | **Google Cloud Run (`cloud_run`)** |
| **Artifacts** | ADK Root Coordinator, Read-Only vs. Action Subagents, 4-point Model Armor + DLP hooks, `FunctionTool` registries. | ALB + Cloud Armor + IAP *(or Direct Cloud Run IAP / OAuth2)*, React/Vite UI, Express/FastAPI proxy, `/healthz`, deterministic HITL APIs. |
| **Deployment** | `agents-cli deploy --deployment-target agent_runtime` (VPC-SC + CMEK) | Cloud Build (`cloudbuild.yaml` + SLSA/Binary Auth) + Terraform via Infrastructure Manager |
| **Governance Rule** | [`_agents/rules/google_adk_and_agent_runtime.md`](./rules/google_adk_and_agent_runtime.md) | [`_agents/rules/devops_security_and_quality_standards.md`](./rules/devops_security_and_quality_standards.md) |

---

## Related Documentation
- **Operating Manual & Executive Router:** [`AGENTS.md`](../AGENTS.md)
- **Master AI-SDLC Hub Skill:** [`skills/ai_sdlc/SKILL.md`](./skills/ai_sdlc/SKILL.md)
- **Well-Architected & SAIF Skill:** [`skills/gcp_well_architected_saif/SKILL.md`](./skills/gcp_well_architected_saif/SKILL.md)
- **Specifications Registry Template (Scaffolded on `ai-sdlc` activation):** [`skills/ai_sdlc/examples/specs/README.md`](./skills/ai_sdlc/examples/specs/README.md)
- **Operational Reports Template (Scaffolded on `ai-sdlc` activation):** [`skills/ai_sdlc/examples/docs/README.md`](./skills/ai_sdlc/examples/docs/README.md)


