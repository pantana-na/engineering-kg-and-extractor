# AI-SDLC Phase Clarification Questionnaires & Gate Checklists

This reference guide provides the structured clarification question banks (`ask_question`) and gate verification checklists for each phase of the **AI-Driven Software Development Lifecycle (`ai-sdlc`)**.

> [!IMPORTANT]
> **Zero Assumptions Policy:** Whenever any variable listed below is not explicitly known from the user's prompt or existing repository files, the agent **MUST** invoke `ask_question` before proceeding.

---

## Phase 1: Inception (Intent Framing & Architecture)

### 1.1 Clarification Question Bank (Phase 1)

Use the `ask_question` tool to resolve any unknowns across these 5 categories:

#### Category A: Business Intent, Personas & Scope
- **Problem & Objective:** What is the core problem statement and measurable success criteria for this feature/system?
- **Target Personas:** Who are the primary users (e.g., internal enterprise employees, external customers, operations engineers, or automated API consumers)?
- **Greenfield vs. Brownfield Scope:** Is this a brand-new capability or an enhancement/refactoring of an existing subsystem (requiring a `specs/baseline/` reverse-engineering baseline first)?
- **Non-Goals:** Which adjacent features or integrations should be explicitly excluded from this iteration?

#### Category B: Dual-Runtime Allocation (`agent_runtime` vs `cloud_run`)
- **Conversational AI & Reasoning Workloads (`agent_runtime`):**
  - Does this feature require autonomous LLM reasoning, multi-turn conversation state (`agentengine://`), or tool execution?
  - What is the **Canonical MECE Intent Topology** (primary domain intents + `OTHERS` out-of-scope intent)?
  - Does it require a single `OrchestratorAgent` with `FunctionTool` callables, or specialized domain subagents?
- **Web Frontend & API Streaming Workloads (`cloud_run`):**
  - What client interfaces are needed (React/Vite UI, SSE/WebSocket streaming proxy, REST endpoints, background jobs)?

#### Category C: IAM Domain Restricted Sharing & Ingress Architecture (Rule 10)
Always ask the user to select one of the three Org-Policy-compliant patterns (since `allUsers` is strictly forbidden):
- **Option 1:** `(Recommended for External Prod Apps) Pattern 1: Identity-Aware Proxy (IAP) behind External HTTPS Load Balancer + Serverless NEG (INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER)`
- **Option 2:** `(Recommended for Internal User-Context Apps) Pattern 2: App-Level Google OAuth 2.0 with invoker-iam-disabled="true" and backend ID token validation`
- **Option 3:** `(Recommended for Public / Friction-Free Internal Tools) Pattern 3: Direct Unauthenticated Ingress with invoker-iam-disabled="true" on frontend and private IAM-protected backend`

#### Category D: Data Stores, Knowledge Catalogs & External Integrations
- Which live databases (Cloud SQL, Spanner, Firestore, BigQuery), vector stores (Vertex AI Vector Search), or external APIs will serve as the system of record?
- Are there specific latency SLAs, rate limits, or data residency/region constraints (e.g., `us-central1`, `asia-southeast1`, `europe-west1`)?

#### Category E: Companion Skills Selection
- Should we generate an interactive dark-themed architecture diagram in `docs/<project>-architecture.md` and `.html` using the [`architecture-diagram`](../../architecture_diagram/SKILL.md) skill?
- Should we generate a real-time Google Cloud cost estimate in `docs/gcp_cost_estimate_<project>.md` using the [`gcp-cost-estimator`](../../gcp_cost_estimator/SKILL.md) skill?

### 1.2 Phase 1 Gate Checklist (`Gate 1: Inception -> Execution`)
- [ ] Business problem, measurable goals, and explicit non-goals confirmed by user.
- [ ] Brownfield vs. Greenfield status identified (`specs/baseline/` checked).
- [ ] Dual-Runtime boundary (`agent_runtime` vs. `cloud_run`) defined.
- [ ] Google ADK Agent Hierarchy & Canonical Intent Topology (`OTHERS` included) defined (if AI agent workload is present).
- [ ] Compliant IAM & Ingress pattern (Pattern 1, 2, or 3; zero `allUsers`) selected by user.
- [ ] Optional companion skills (`architecture-diagram`, `gcp-cost-estimator`) offered/executed.
- [ ] **Explicit user sign-off obtained via `ask_question` to enter Phase 2 (SDD Execution).**

---

## Phase 2: Execution (The Spec-Driven Development Cycle)

### 2.1 Clarification Question Bank (Phase 2)

Use `ask_question` whenever any specification, testing, or debugging ambiguity arises:

#### Category A: Brownfield Baseline Ambiguities (Step 2.0)
- If reverse-engineering existing code reveals undocumented edge cases, inconsistent schemas, or apparent bugs: *"Should we codify this existing behavior as a baseline invariant in `specs/baseline/`, or treat it as a defect to be remediated in the feature spec?"*

#### Category B: Data Models, API Contracts & Tool Schemas (Steps 2.1 – 2.3)
- What are the exact validation rules, nullable fields, enums, and pagination limits for the TypeScript/Pydantic schemas?
- What HTTP error status codes (`400`, `401`, `403`, `404`, `429`, `500`) and error payload shapes should the API return?
- For ADK `FunctionTool` definitions: What are the exact *"When to use"* positive scenarios and *"When NOT to use"* negative constraints?
- For ambiguous user queries to the ADK agent: Which live database query should populate dynamic clarification options (zero hardcoded candidate arrays)?

#### Category C: Mandatory 4-Step RCA Decisions on Test/Eval Failures (Step 2.4)
Whenever a Unit Test, Property-Based Test (PBT), or `agents-cli eval` fails:
- Present the diagnostic root cause report and ask via `ask_question`:
  - `Option A: [Data Tier / Schema Resolution] — with pros, cons, and blast radius`
  - `Option B: [Cognitive Prompt / FunctionTool Docstring Refinement] — with pros, cons, and blast radius`
  - `Option C: [API / Architecture Contract Adjustment] — with pros, cons, and blast radius`

### 2.2 Phase 2 Gate Checklist (`Gate 2: Execution -> Operation`)
- [ ] Brownfield Baseline SDD (`specs/baseline/`) created or updated (if brownfield).
- [ ] Feature SDD (`specs/features/SPEC-<YYYYMMDD>-<TITLE>.md`) authored with all 8 sections from [`specs/templates/sdd-template.md`](../../../../specs/templates/sdd-template.md).
- [ ] Stakeholder approval obtained via `ask_question` on the SDD & Implementation Plan prior to coding.
- [ ] Every implementation step completed with passing **Deterministic Unit Tests** and **Generative Property-Based Tests (PBT)**.
- [ ] Zero hardcoded regex routing, keyword heuristics, or static fallback arrays in ADK agents.
- [ ] Any test or eval failures resolved strictly via the **4-Step RCA Protocol** with user sign-off.
- [ ] SDD synchronized with final implementation (**Zero Spec Drift**).
- [ ] Living progress report updated in `specs/plan/PROGRESS_REPORT_<YYYYMMDD>.md` and indexed in `specs/README.md`.
- [ ] **Explicit user sign-off obtained via `ask_question` to enter Phase 3 (Operation).**

---

## Phase 3: Operation (Repository Integration & Deployment)

### 3.1 Clarification Question Bank (Phase 3)

Use `ask_question` to clarify operational, security remediation, and deployment choices:

#### Category A: Target Environment & Git Branch Strategy
- Are we integrating and deploying to **Non-Production (`main` / `develop` branch)**, or promoting a verified Non-Prod release to **Production (`prod` / `release` branch via Pull Request)**?
- What are the exact values for any missing variables in the unified `.env` file (`GCP_PROJECT`, `GCP_REGION`, `NONPROD_*`, `PROD_*`)?

#### Category B: CodeMender SAST Triage & Remediation (Rule 3)
- After `cm find`: Which discovered findings should be verified in the sandbox via `cm verify`?
- After `cm verify`: Confirm applying automated patches via `cm fix` for confirmed exploitable vulnerabilities.
- After `cm fix`: Confirm staging and committing the remediated diff after regression tests pass.

#### Category C: Cloud & Agent Runtime Deployment Execution
- Should we trigger live deployment now (`agents-cli deploy --deployment-target agent_runtime` and Cloud Build / Terraform Infrastructure Manager `<service>-nonprod` or `<service>-prod`), or run a dry-run (`terraform plan`) first?
- If post-deployment smoke tests (`/healthz`) or live evaluations (`agents-cli eval run`) fail, which architectural fix option from the 4-Step RCA should be executed after traffic rollback?

### 3.2 Phase 3 Gate Checklist (`Final Operational Sign-Off`)
- [ ] Static code quality analysis (linting, strict type checking, maintainability) passed.
- [ ] Pre-build SAST executed via [`codemender`](../../codemender/SKILL.md) (`cm find`, `cm verify`, `cm fix`) with zero High/Critical vulnerabilities; reports saved in `docs/codemender-*.md`.
- [ ] Dependency CVE & license compliance verified.
- [ ] Unified `.env` and `.env.example` validated (`Shared`, `NONPROD_*`, `PROD_*` blocks; zero hardcoded secrets).
- [ ] All code, specs (`specs/`), and operational reports (`docs/`) committed to the appropriate Git branch with clean working tree.
- [ ] ADK Agents deployed to Gemini Enterprise Agent Platform (`agent_runtime`) via `agents-cli deploy`.
- [ ] Web UI & Streaming Proxy deployed to Cloud Run (`cloud_run`) via Cloud Build (`${_ENVIRONMENT}-${SHORT_SHA}`) and Terraform Infrastructure Manager (`<service>-nonprod` / `<service>-prod`).
- [ ] Post-deployment smoke tests (`GET /healthz`, API proxy check, Cloud Logging & Cloud Monitoring) verified live.
- [ ] Live Environment Agent Evaluation (`agents-cli eval run`) passed with $\ge 95\%$ tool trajectory accuracy and $1.000$ ($100\%$) groundedness.
- [ ] Final operational telemetry and milestone closure recorded in `specs/plan/PROGRESS_REPORT_<YYYYMMDD>.md`.
