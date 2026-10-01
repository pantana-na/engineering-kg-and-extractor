# System Specifications & SDD Registry (`specs/`)

This directory serves as the **Single Source of Truth** for all formal specifications, baseline reverse-engineering documents, feature proposals, and implementation progress tracking under the **Spec-Driven Development (SDD)** mandate.

## Directory Structure

```
specs/
├── README.md                      # Index of all specifications and progress reports
├── templates/
│   ├── README.md                  # Specification authoring instructions and guidelines
│   └── sdd-template.md            # Standardized template with Implementation Plan & Testing sections
├── baseline/                      # Baseline SDDs for existing/brownfield code
│   └── README.md                  # Brownfield discovery protocol and baseline index
├── features/                      # Feature specifications and enhancement proposals
│   └── README.md                  # Feature specification drafting guide and active spec registry
└── plan/                          # Living implementation progress reports and milestone tracking
    └── README.md                  # Plan progress tracking protocol and execution logs index
```

---

## AI-SDLC & SDD Governance Principles

All work in this repository is governed by the rules codified in [`_agents/rules/`](../_agents/rules/) and orchestrated by the **[`ai-sdlc` skill](../_agents/skills/ai_sdlc/SKILL.md)**:

1. **3-Phase AI-SDLC & Interactive Phase Gates:** Development progresses through **Phase 1: Inception (Intent Framing & Architecture)** $\rightarrow$ **Phase 2: Execution (SDD Cycle)** $\rightarrow$ **Phase 3: Operation (Integrate & Deploy)**. Agents must ask clarification questions (`ask_question`) whenever unknown factors arise in any phase and obtain explicit user sign-off at every phase boundary ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../_agents/rules/ai_sdlc_and_sdd_standards.md)).
2. **Spec First, Code Second:** Code is a downstream artifact derived from specifications. Direct code changes without an approved specification and step-by-step implementation plan are strictly prohibited ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../_agents/rules/ai_sdlc_and_sdd_standards.md)).
3. **Brownfield Baseline First:** When modifying existing systems, reverse-engineer and document the "as-is" state under `specs/baseline/` before authoring feature changes.
4. **Mandatory Testing at Every Step:** Every implementation step must define and implement:
   - **Deterministic Unit Tests:** Happy paths, boundary conditions, error handling.
   - **Generative Property-Based Tests (PBT):** Mathematical and logical invariants tested across generative input spaces (e.g., `fast-check` in TS, `hypothesis` in Python).
5. **Runtime Separation of Responsibilities:**
   - **Conversational AI Agents & Tool Registries:** Built with official `google-adk` and deployed to the **Gemini Enterprise Agent Platform (`agent_runtime`)** ([`_agents/rules/google_adk_and_agent_runtime.md`](../_agents/rules/google_adk_and_agent_runtime.md)).
   - **Web Applications, API Proxies & Streaming Gateways:** Hosted on **Google Cloud Run (`cloud_run`)** ([`_agents/rules/devops_security_and_quality_standards.md`](../_agents/rules/devops_security_and_quality_standards.md)).
6. **Model-Driven Reasoning:** Agent intent routing and tool execution are strictly cognitive and model-driven; keyword heuristics, regex routing, and hardcoded fallback arrays are strictly forbidden.
7. **Live Environment Agent Evaluation:** Trajectory fidelity and tool selection precision ($\ge 95\%$) are continuously evaluated against the live environment via `agents-cli eval`.
8. **Mandatory Root Cause Investigation & Zero Quick-Patch Standard:** When tests or evals fail, developers/agents must execute the 4-step RCA protocol. Zero quick fixes, mockups, regex patches, or assertion weakening ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](../_agents/rules/ai_sdlc_and_sdd_standards.md)).
9. **Zero Spec Drift:** Synchronize specification files in `specs/` whenever code contracts or behaviors change.
10. **Living Plan Progress Tracking:** Continuous execution reports, test verification metrics, and milestone statuses are maintained under `specs/plan/`.

---

## Active Specifications Registry

### 1. Baseline Specifications ([`specs/baseline/`](./baseline/))
- Reverse-engineered models, API contracts, and system invariants reflecting current brownfield subsystems.

### 2. Feature Specifications ([`specs/features/`](./features/))
- Approved feature designs, architectural delta proposals, and implementation step plans.

### 3. Plan Progress Reports ([`specs/plan/`](./plan/))
- Living milestone execution logs, test pass rates, benchmark latency metrics, and next actions.

---

## Related Documentation
- **Agent Operating Manual:** [`AGENTS.md`](../AGENTS.md)
- **Governance Rules:** [`_agents/rules/`](../_agents/rules/)
- **Operational & Skill Reports:** [`docs/`](../docs/) (CodeMender SAST audits, GCP cost models, architecture diagrams)
