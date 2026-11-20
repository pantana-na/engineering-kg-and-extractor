# Agent Behavioral & Engineering Rules (`_agents/rules/`)

This directory contains the authoritative, non-negotiable governance rules (**Rules 1–13**) that all autonomous AI agents and developers must strictly follow when operating in this repository. All rules are orchestrated by the **[`ai-sdlc` master skill (`../skills/ai_sdlc/SKILL.md`)](../skills/ai_sdlc/SKILL.md)** and anchored in the **[Google Cloud Well-Architected Framework (WAF)](https://docs.cloud.google.com/architecture/framework)** and **[Google Secure AI Framework (SAIF / SAIF 2.0)](https://safety.google/intl/en/safety/saif/)** (via [`_agents/skills/gcp_well_architected_saif/SKILL.md`](../skills/gcp_well_architected_saif/SKILL.md)), which take strict precedence in case of any conflict.

## Rules Catalog (Rules 1–13)

| Rule File | Trigger | Owned Rules & Title | Core Mandate & Enforcement Scope |
| :--- | :--- | :--- | :--- |
| **[`ai_sdlc_and_sdd_standards.md`](./ai_sdlc_and_sdd_standards.md)** | `always_on` | **Lifecycle, SDD & Rule 13:**<br>*3-Phase AI-SDLC, SDD, WAF/SAIF Precedence & 4-Step RCA* | Orchestrates [`ai-sdlc`](../skills/ai_sdlc/SKILL.md) and [`gcp-well-architected-saif`](../skills/gcp_well_architected_saif/SKILL.md) across Phase 1 (Inception), Phase 2 (SDD Execution), and Phase 3 (Operation). Mandates WAF 6-Pillar & SAIF 15-Risk alignment, `ask_question` clarification on any unknowns, interactive phase gates, brownfield baselines (`specs/baseline/`), feature specs (`specs/features/`), Unit Tests + Property-Based Tests (PBT) at every step, living progress tracking (`specs/plan/`), and **Rule 13: Mandatory 4-Step RCA Protocol** (harmonizing WAF Graceful Degradation with zero fake/mockup data). |
| **[`google_adk_and_agent_runtime.md`](./google_adk_and_agent_runtime.md)** | `model_decision` | **Rules 11–12:**<br>*Google ADK, Agent Runtime, SAIF 2.0 Security & DLP-Safe Live Evaluation* | Enforces **Rule 11** (official `google-adk` `Agent` & `FunctionTool` on `agent_runtime`, cognitive MECE intent topology with `OTHERS`, `User Auth` OAuth2 anti-Confused-Deputy propagation, read-only vs. deterministic externalized HITL action boundaries, 4-point inline **Model Armor + Cloud DLP** callbacks including `after_tool_callback` Indirect `PIJ` scan, pinned model IDs, execution budgets) and **Rule 12** (DLP-safe live `agents-cli eval` requiring $\ge 95\%$ precision and $1.000$ groundedness). |
| **[`devops_security_and_quality_standards.md`](./devops_security_and_quality_standards.md)** | `model_decision` | **Rules 1–10:**<br>*DevOps, WAF 6-Pillar Security, Quality & Cloud Run Standards* | Enforces **Rules 1–10** aligned with WAF & SAIF: Multi-branch promotion (`main`/`develop` $\rightarrow$ `prod`), static code quality, pre-build CodeMender SAST (`cm`), Artifact Analysis + **SLSA Level 3 / Binary Authorization**, automated Cloud Build CI/CD, Cloud Run hosting with `/healthz` probes & SLO burn-rate alerts, smoke tests, unified `.env` + Secret Manager/CMEK, Infrastructure Manager Terraform IaC + **VPC-SC** + FinOps + Sustainability (`CFE %`), and **WAF Zero-Trust IAM/Ingress** (Pattern 1A ALB + Cloud Armor + IAP, Pattern 1B Direct Cloud Run IAP, or Pattern 2 OAuth2; zero `allUsers`). |

---

## Runtime Separation Matrix (WAF + SAIF Zero-Trust Topology)

This project strictly delineates workloads across two execution runtimes inside a VPC Service Controls & CMEK perimeter:

```
+-------------------------------------------------------------------+
|                   Authenticated Human Controller                  |
|            (Web UI, Streaming Audio/Video, Enterprise SSO)        |
+-------------------------------------------------------------------+
                                 │
    HTTPS / WSS (ALB + Cloud Armor + IAP | Direct Cloud Run IAP | OAuth2)
                                 ▼
+-------------------------------------------------------------------+
|                  Google Cloud Run (cloud_run)                     |
|  - React / Vite Web Frontends & Stateless Streaming API Proxies   |
|  - Propagates Verified End-User Identity (User Auth) + Session ID |
|  - Externalized Deterministic HITL Approval & Policy Cap Gate     |
|  - Health Probes (/healthz), OpenTelemetry Trace & SLO Alerts     |
|  - Deployed via Cloud Build (SLSA/Binary Auth) + Terraform IaC    |
+-------------------------------------------------------------------+
                                 │
          Private Session Stream │ (VPC-SC + Private Service Connect)
                                 ▼
+-------------------------------------------------------------------+
|        Gemini Enterprise Agent Platform (agent_runtime)           |
|  - ADK Orchestrator & Read-Only vs. Action Domain Subagents       |
|  - Pinned Foundation Model IDs + Per-Session Execution Budgets    |
|  - 4-Point Model Armor + Cloud DLP Callbacks (Direct/Indirect PIJ)|
|  - FunctionTool Registries with User Auth Row/Doc ACL Enforcement |
|  - Evaluated via DLP-Safe Live agents-cli eval (>=95% P, 1.000 G) |
|  - Deployed via agents-cli deploy (CMEK Encrypted)                |
+-------------------------------------------------------------------+
```

---

## Enforcement & Compliance
- **Automated Validation:** Rules are enforced by workload-aware `validate_sdlc_gate.py` and `validate_waf_saif.py` (`Regular App` vs. `AI Agent` / `Hybrid`), CI/CD quality gates, and evaluation suites.
- **Specification Linkage:** Every specification authored in `specs/features/` and `specs/baseline/` must declare `Workload Type` in **Document Control** and verify compliance against each applicable rule and WAF[/SAIF] control using **Section 3.4** of [`sdd-template.md`](../skills/ai_sdlc/examples/specs/templates/sdd-template.md) and [`baseline-template.md`](../skills/ai_sdlc/examples/specs/templates/baseline-template.md).

