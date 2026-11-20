# System Specifications & SDD Registry (`specs/`)

This directory serves as the **Single Source of Truth** for all formal specifications, baseline reverse-engineering documents, feature proposals, and implementation progress tracking under the **Spec-Driven Development (SDD)** mandate.

## Directory Structure

```
specs/
├── README.md                      # Index of all specifications and progress reports
├── templates/
│   ├── README.md                  # Specification authoring instructions and guidelines
│   ├── discovery-template.md      # Optional Pre-Inception 15-Section Consolidated Discovery template
│   ├── baseline-template.md       # Brownfield Baseline & Modernization Assessment template
│   └── sdd-template.md            # Standardized Feature SDD template with Implementation Plan & Testing sections
├── discovery/                     # [Optional Pre-AI-SDLC] Consolidated multi-modal Discovery Documents
│   └── README.md                  # Multi-modal discovery consolidation & dual-input handoff guide
├── baseline/                      # Baseline SDDs for existing/brownfield code
│   └── README.md                  # Brownfield discovery protocol and baseline index
├── features/                      # Feature specifications and enhancement proposals
│   └── README.md                  # Feature specification drafting guide and active spec registry
└── plan/                          # Living implementation progress reports and milestone tracking
    └── README.md                  # Plan progress tracking protocol and execution logs index
```

---

## AI-SDLC, WAF/SAIF & SDD Governance Principles

All work in this repository is orchestrated by the **[`ai-sdlc` master skill](../_agents/skills/ai_sdlc/SKILL.md)**, governed by [`_agents/rules/`](../_agents/rules/), and anchored in the **[Google Cloud Well-Architected Framework (WAF)](https://docs.cloud.google.com/architecture/framework)** and **[Google Secure AI Framework (SAIF / SAIF 2.0)](https://safety.google/intl/en/safety/saif/)** ([`gcp-well-architected-saif`](../_agents/skills/gcp_well_architected_saif/SKILL.md), which takes strict precedence in case of conflict):

1. **3-Phase AI-SDLC, Optional Pre-Inception Discovery & Interactive Phase Gates:** Development optionally begins by consolidating raw stakeholder artifacts (transcripts, drawings, emails, manuals) into `specs/discovery/DISCOVERY-*.md` via [`requirements-discovery`](../_agents/skills/requirements_discovery/SKILL.md), then progresses through **Phase 1: Inception (Intent Framing, WAF & SAIF Architecture)** $\rightarrow$ **Phase 2: Execution (SDD Cycle)** $\rightarrow$ **Phase 3: Operation (Integrate & Deploy)**. Agents analyze `specs/discovery/` and repo files first, ask `ask_question` whenever unknown factors remain, and obtain explicit user sign-off at every phase boundary ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../_agents/rules/ai_sdlc_and_sdd_standards.md)).
2. **Spec First, Code Second:** Code is a downstream artifact derived from specifications. Direct code changes without an approved specification and step-by-step implementation plan are strictly prohibited ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../_agents/rules/ai_sdlc_and_sdd_standards.md)).
3. **Brownfield Baseline First:** When modifying existing systems, reverse-engineer and document the "as-is" state under `specs/baseline/` and lock in Characterization + Property-Based Tests before authoring feature changes.
4. **Mandatory Testing at Every Step:** Every implementation step must define and implement:
   - **Deterministic Unit Tests:** Happy paths, boundary conditions, auth/policy checks, and graceful degradation.
   - **Generative Property-Based Tests (PBT):** Mathematical and logical invariants tested across generative input spaces (`fast-check` in TS, `hypothesis` in Python).
5. **Dual-Runtime Separation of Responsibilities (VPC-SC + CMEK):**
   - **Conversational AI Agents & Tool Registries:** Built with official `google-adk` (Read-Only vs. Action subagents, 4-point Model Armor + Cloud DLP callbacks, `User Auth` OAuth2 propagation, pinned models, execution budgets) and deployed to the **Gemini Enterprise Agent Platform (`agent_runtime`)** ([`_agents/rules/google_adk_and_agent_runtime.md`](../_agents/rules/google_adk_and_agent_runtime.md)).
   - **Web Applications, API Proxies & Streaming Gateways:** Hosted on **Google Cloud Run (`cloud_run`)** behind Zero-Trust ALB + Cloud Armor + IAP *(Pattern 1A)*, Direct Cloud Run IAP *(Pattern 1B)*, or OAuth2 *(Pattern 2)* with externalized deterministic HITL confirmation and `/healthz` probes ([`_agents/rules/devops_security_and_quality_standards.md`](../_agents/rules/devops_security_and_quality_standards.md)).
6. **Model-Driven Reasoning:** Agent intent routing (with MECE intents + `OTHERS`) and tool execution are strictly cognitive and model-driven; keyword heuristics, regex routing, and hardcoded fallback arrays are strictly forbidden.
7. **DLP-Safe Live Environment Agent Evaluation:** Trajectory fidelity ($\ge 95\%$ precision), groundedness ($1.000$), and SAIF adversarial blocking ($100\%$) are continuously evaluated against isolated de-identified/synthetic Non-Prod live environments via `agents-cli eval`.
8. **Mandatory 4-Step RCA & WAF Graceful Degradation Harmonization (Rule 13):** When tests or evals fail, execute the 4-step RCA protocol. Zero quick fixes, synthetic fake data, regex patches, or assertion weakening—harmonized with transparent WAF graceful degradation (`UPSTREAM_UNAVAILABLE_DEGRADED`).
9. **Zero Spec Drift:** Synchronize specification files in `specs/` whenever code contracts or behaviors change.
10. **Living Plan Progress Tracking:** Continuous execution reports, test verification metrics, and milestone statuses are maintained under `specs/plan/`.

---

## Active Specifications Registry

### 0. Consolidated Discovery Documents ([`specs/discovery/`](./discovery/)) *(Optional Pre-Inception)*
- Citation-grounded 15-section Discovery Documents (`DISCOVERY-<YYYYMMDD>-<PROJECT>.md`) synthesizing transcripts, drawings, emails, and manuals into ranked requirements, conflicts, and open questions.

### 1. Baseline Specifications ([`specs/baseline/`](./baseline/))
- Reverse-engineered models, API contracts, hidden SQL/UI business logic, and system invariants reflecting current brownfield subsystems.

### 2. Feature Specifications ([`specs/features/`](./features/))
- Approved feature designs, WAF 6-Pillar & SAIF 15-Risk compliance matrices, and step-by-step implementation plans.

### 3. Plan Progress Reports ([`specs/plan/`](./plan/))
- Living milestone execution logs, test pass rates, DLP-safe live eval scores, RCA logs, and next actions.

---

## Related Documentation
- **Agent Operating Manual:** [`AGENTS.md`](../AGENTS.md)
- **Master AI-SDLC Orchestrator Skill:** [`_agents/skills/ai_sdlc/SKILL.md`](../_agents/skills/ai_sdlc/SKILL.md)
- **Optional Requirements Discovery Skill:** [`_agents/skills/requirements_discovery/SKILL.md`](../_agents/skills/requirements_discovery/SKILL.md)
- **WAF & SAIF Governance Skill:** [`_agents/skills/gcp_well_architected_saif/SKILL.md`](../_agents/skills/gcp_well_architected_saif/SKILL.md)
- **Governance Rules:** [`_agents/rules/`](../_agents/rules/)
- **Operational & Skill Reports:** [`docs/`](../docs/) (WAF/SAIF reviews, CodeMender SAST audits, GCP cost models, architecture diagrams)
