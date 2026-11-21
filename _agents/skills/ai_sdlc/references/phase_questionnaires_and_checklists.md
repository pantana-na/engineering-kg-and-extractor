# AI-SDLC Phase Clarification Questionnaires & Gate Checklists

This reference guide provides the structured clarification question banks (`ask_question`) and gate verification checklists for each phase of the **AI-Driven Software Development Lifecycle (`ai-sdlc`)**.

> [!IMPORTANT]
> **Dual-Input & Zero-Assumptions Policy (`specs/discovery/` + `ask_question`):**
> - **Input Source 1 (Optional Consolidated Discovery Doc):** If `specs/discovery/DISCOVERY-*.md` exists (generated via [`requirements-discovery`](../../requirements_discovery/SKILL.md)), extract all verified answers from Sections `2–7` & `11–14` **first**, and focus `ask_question` strictly on **§2.5 Top 3 Blockers**, **§3.1 Stakeholder Tensions**, **§8 Blocking Open Questions**, **§10.1 Contradictions**, and any remaining SDD gaps.
> - **Input Source 2 (Direct Interactive Elicitation):** When no Discovery Document exists, inspect the user prompt and repository files first, then invoke `ask_question` whenever any variable below is unknown or underspecified.

---

## Phase 1: Inception (Intent Framing & Architecture)

### 1.1 Clarification Question Bank (Phase 1)

*(If raw interview scripts, drawings, emails, or manuals were provided without a Discovery Doc, first offer to consolidate them into `specs/discovery/DISCOVERY-<YYYYMMDD>-<PROJECT>.md` via [`requirements-discovery`](../../requirements_discovery/SKILL.md).)* Use `ask_question` to resolve any unknowns not already answered in `specs/discovery/` or repo files across these 5 categories:

#### Category A: Greenfield vs. Brownfield Confirmation (Ask First After 3-Signal Repo Scan), Business Intent & Scope
- **Greenfield vs. Brownfield Scope (`Inspect First -> Confirm in First ask_question`):** Scan workspace files, `specs/discovery/`, and prompt verbs first, then confirm in the very first `ask_question` call (never blindly ask without scanning, and never silently assume an empty repo is Greenfield):
  - *When repo has no application code:* Confirm whether this is **(a) True Greenfield** (net-new system from scratch $\rightarrow$ skip `specs/baseline/`) or **(b) External-Legacy Brownfield** (new repo created to migrate/strangle/replace an existing legacy app or DB living elsewhere $\rightarrow$ link legacy repo/SQL schemas for `specs/baseline/` or run [`requirements-discovery`](../../requirements_discovery/SKILL.md)).
  - *When repo already contains code:* Confirm whether existing files are **(a) Brownfield Baseline to Preserve/Extend** (*Track A* or *Track B* $\rightarrow$ codify `specs/baseline/` + characterization tests first), **(b) Throwaway Prototype / Starter Boilerplate** to replace cleanly (**Greenfield** SDD), or **(c) Existing Monorepo + Net-New Bounded Service** alongside existing services.
- **Problem & Objective:** What is the core problem statement and measurable success criteria for this feature/system?
- **Target Personas:** Who are the primary users (e.g., internal enterprise employees, external customers, operations engineers, or automated API consumers)?
- **Non-Goals:** Which adjacent features or integrations should be explicitly excluded from this iteration?

#### Category B: Workload Type (`Regular App` vs. `AI Agent` / `Hybrid`) & Runtime Allocation
- **Workload Type Selection:** Is this a **`Regular App`** (standard web/API/microservice/data workload on `cloud_run` — omitting `[AI-Agent Only]` controls), an **`AI Agent`**, or a **`Hybrid`** Dual-Runtime solution?
- **`[AI-Agent Only]` Conversational AI & Reasoning Workloads (`agent_runtime`):** *(Skip if `Regular App`)*
  - What is the **Canonical MECE Intent Topology** (primary domain intents + `OTHERS` out-of-scope intent)?
  - How are subagents partitioned between **Read-Only Informational/RAG Subagents** and **Bounded Action Subagents**?
  - Which state-mutating or financial tools require **`User Auth` OAuth 2.0 propagation**, **deterministic policy caps**, and **externalized HITL confirmation** (`SAIF RAC`)?
- **Web Frontend & Backend API / Streaming Workloads (`cloud_run`):**
  - What client and backend interfaces are needed (React/Vite UI, REST/gRPC APIs, background jobs, or `[AI-Agent Only]` SSE/WebSocket streaming proxy + HITL approval endpoints)?

#### Category C: WAF Zero-Trust IAM, Domain Restricted Sharing & Ingress Architecture (Rule 10 & SAIF Principle 1)
Always ask the user to select a WAF Zero-Trust compliant pattern (`allUsers` is strictly forbidden, and internal/AI workloads must authenticate the human controller):
- **Option 1A:** `(Recommended Default for Tier-1 Prod, Multi-Region, Custom-Domain, External/B2B & Regulated FSI/Healthcare Apps) Pattern 1A: Global External HTTPS Load Balancer + Cloud Armor WAF/DDoS + Identity-Aware Proxy (IAP) + Serverless NEG (INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER)`
- **Option 1B:** `(Recommended for Internal Workforce Tools, Single-Region Apps, PoCs & Non-Prod / $0-Baseline Cost Optimization) Pattern 1B: Direct Cloud Run IAP (--iap, No Load Balancer) with INGRESS_TRAFFIC_ALL + --no-allow-unauthenticated + mandatory backend x-goog-iap-jwt-assertion verification + documented ADR trade-off`
- **Option 2:** `(Recommended for Custom OIDC / Google Sign-In UX) Pattern 2: App-Level OAuth 2.0 / OIDC + Cloud Armor with invoker-iam-disabled="true" and mandatory backend cryptographic ID token validation`
- **Option 3:** `(Restricted Exception ONLY for Approved Anonymous Public Non-Sensitive Static/Marketing Pages) Pattern 3: Direct Unauthenticated Ingress with invoker-iam-disabled="true" + Cloud Armor on public frontend and private IAM-protected backend (Strictly prohibited for internal tools or direct AI/data access)`

#### Category D: Data Stores, WAF 6-Pillar Targets (Reliability, Performance, FinOps, Sustainability) & Security Perimeters
- Which live databases (AlloyDB, Cloud SQL, Spanner, Firestore, BigQuery), vector stores (Vertex AI Search / Vector Search), or external APIs will serve as the system of record?
- What are the target **Reliability SLOs** (availability %, RTO, RPO), **Performance SLOs** (p95 latency; plus TTFT if AI Agent), **Security/Compliance controls** (VPC-SC, CMEK/HSM/EKM, Cloud DLP, Assured Workloads data residency), **FinOps Unit Economics KPIs**, and **Sustainability (`High CFE %` region)** preferences?

#### Category E: Companion Skills Selection
- Should we run a comprehensive **Google Cloud Well-Architected Framework (6 Pillars) [& SAIF (15 Risks)]** review using [`gcp-well-architected-saif`](../../gcp_well_architected_saif/SKILL.md)?
- Should we generate an interactive dark-themed architecture diagram in `docs/<project>-architecture.md` and `.html` using the [`architecture-diagram`](../../architecture_diagram/SKILL.md) skill?
- Should we generate a real-time Google Cloud cost estimate & FinOps unit-economics model in `docs/gcp_cost_estimate_<project>.md` using the [`gcp-cost-estimator`](../../gcp_cost_estimator/SKILL.md) skill?

### 1.2 Phase 1 Gate Checklist (`Gate 1: Inception -> Execution`)
- [ ] **Workload Type** (`Regular App` | `AI Agent` | `Hybrid`), business problem, goals, and non-goals confirmed by user.
- [ ] Brownfield vs. Greenfield status identified (`specs/baseline/` checked).
- [ ] Runtime boundary (`cloud_run` for `Regular App`; `cloud_run` + `agent_runtime` for `AI Agent` / `Hybrid`) and **WAF 6-Pillar** targets defined.
- [ ] **`[AI-Agent Only]`** *(Skip if `Regular App`)* Google ADK Agent Hierarchy, Canonical Intent Topology (`OTHERS` included), and **SAIF 2.0 4-Point Model Armor + Cloud DLP guardrails** defined.
- [ ] WAF Zero-Trust IAM & Ingress pattern (Pattern 1A ALB+Cloud Armor+IAP, Pattern 1B Direct Cloud Run IAP, or Pattern 2 OAuth2; zero `allUsers`) and VPC-SC/CMEK perimeter selected by user.
- [ ] Optional companion skills (`gcp-well-architected-saif`, `architecture-diagram`, `gcp-cost-estimator`) offered/executed.
- [ ] **Explicit user sign-off obtained via `ask_question` to enter Phase 2 (SDD Execution).**


---

## Phase 2: Execution (The Spec-Driven Development Cycle)

### 2.1 Section-by-Section SDD Analysis & `ask_question` Completion Matrix (`Document Control` + Sections `1–10`)

Before requesting Step 2.3 stakeholder approval on `specs/features/SPEC-<YYYYMMDD>-<TITLE>.md`, audit **every required section** of [`sdd-template.md`](../examples/specs/templates/sdd-template.md) using the **Two-Step Completion Rule**:
1. **Analyze First:** Extract all known facts from user prompts, Phase 1 decisions, `specs/baseline/`, and existing codebase/configs/schemas (never re-ask what is already known).
2. **Ask on Gaps (`ask_question`):** For any required field still missing or ambiguous (omitting `[AI-Agent Only]` items when `Workload Type: Regular App`), invoke `ask_question` with `(Recommended)` WAF/SAIF-aligned defaults so **zero `TBD` or `[e.g., ...]` placeholders** remain:

| SDD Section | Step A: Analyze & Derive From Requirements / Repo First | Step B: Clarify via `ask_question` If Unspecified |
| :--- | :--- | :--- |
| **`Document Control`** | Infer `Spec ID`, `Date`, `Baseline Reference` (`N/A` vs. `specs/baseline/*.md`), and initial `Workload Type` (`Regular App` \| `AI Agent` \| `Hybrid`) from repo/prompt. | Confirm exact **`Workload Type`** (if hybrid boundary is unclear) and **Author / Owner** metadata; select single active enum values (remove `\|` unions). |
| **`1. Executive Summary & Problem Framing`** *(§1.1–§1.3)* | Extract stated problem, personas, in-scope workflows, non-goals, and any SLA/traffic targets from Phase 1 & baseline metrics. | Ask for missing **role-gated/maker-checker boundaries** (§1.2), **`[AI-Agent Only]` autonomous vs. externalized HITL scope** (§1.2), and concrete **Availability SLO %, p95 latency/RPS, RTO/RPO** *(+ TTFT if AI Agent)* (§1.3). |
| **`2. System Architecture, Topology & Code Contracts`** *(§2.1–§2.4)* | Derive service topology, existing DB DDL / ORM / TypeScript / Pydantic types, route signatures, and UI states from repo & Phase 1 runtime split. | Ask for unresolved **DTO field nullability/enums/pagination**, **HTTP error codes (`400`/`401`/`403`/`404`/`429`/`503`)**, and **`[AI-Agent Only]` MECE intents (`OTHERS`), pinned models, `FunctionTool` positive/negative constraints & live clarification queries** (§2.2–§2.4). |
| **`3. Security, Privacy, Compliance & [AI-Agent Only] SAIF`** *(§3.1–§3.4)* | Map org IAM constraints, existing auth middleware, sensitive PII/PCI fields in schemas, `.env` keys, and applicability of Rules 1–13. | Ask for **Zero-Trust Ingress Pattern** (Pattern 1A ALB+Cloud Armor+IAP vs. Pattern 1B Direct Cloud Run IAP vs. Pattern 2 OAuth2), **PII/DLP classification & data residency (`Assured Workloads`)**, **VPC-SC/CMEK scope**, and **`[AI-Agent Only]` 4-point Model Armor/DLP + `User Auth` propagation rules**. |
| **`4. Resiliency, Reliability & State Integrity`** *(§4.1–§4.3)* | Inspect existing HTTP/DB client timeouts, retry policies, queue DLQs, transaction boundaries, and HA topology. | Ask for **request/DB timeouts & rate limits** (§4.1), **`[AI-Agent Only]` ADK `max_iterations`/token budgets** (§4.1), **mutating `X-Idempotency-Key` & policy-cap rules** (§4.2), and **degraded-mode behavior** (`503 UPSTREAM_UNAVAILABLE_DEGRADED` vs. signed stale read-only reference cache; plus Provisioned Throughput $\rightarrow$ PayGo spillover if AI Agent) (§4.3). |
| **`5. Observability, Operations & [AI-Agent Only] AgentOps`** *(§5.1–§5.3)* | Check existing health endpoints, OpenTelemetry setup, structured logger format, and CI/CD test runners. | Confirm **`GET /healthz` dependency checks & SLO burn-rate alert paging** (§5.1), **audit log retention**, and **`[AI-Agent Only]` Non-Prod DLP-safe live evaluation dataset scope** (`>= 95%` precision, `1.000` groundedness) (§5.3). |
| **`6. Performance, FinOps & Sustainability`** *(§6.1–§6.2)* | Analyze hot read paths, static assets, query indexes, Phase 1 cost estimate (`docs/gcp_cost_estimate_*.md`), and target GCP region `CFE %`. | Ask for **CDN / Memorystore caching TTLs**, **`prod` `min-instances` vs. `nonprod` scale-to-zero**, **Unit Economics KPI** (e.g., `$ / 1k requests` or `$ / 1k turns`), **cost allocation labels**, and **compliant High-`CFE %` region** (§6.1–§6.2). |
| **`7. Architectural Decision Records (ADRs)`** | Identify cross-pillar tensions surfaced during architecture framing (Security vs. Latency, HA vs. Cost, Sustainability `CFE %` vs. Residency/RTT, Custom vs. Managed). | Present competing architectural options with trade-offs via `ask_question` whenever multiple valid designs exist, then record concrete **ADR titles, context, decisions, and consequences** (replace all `[Decision Title]` placeholders). |
| **`8. Failure Mode & Effects Analysis (FMEA)`** | Enumerate failure modes for every external dependency, database, auth edge, CI/CD rollout *(and `[AI-Agent Only]` RAG/tool `PIJ` & Vertex quota)* in §2.1. | Clarify acceptable **blast-radius handling or human escalation queues** for domain-critical failure modes where automated fallback policy is business-sensitive. |
| **`9–10. Step-by-Step Plan, Tests & Progress Tracking`** | Decompose §2–§8 into ordered implementation steps with **Unit Tests + PBT (`hypothesis`/`fast-check`)** *(+ `agents-cli eval` if AI Agent; mark Step 2 `N/A` if `Regular App`)* and link `specs/plan/PROGRESS_REPORT_<YYYYMMDD>.md`. | Ask for domain-specific **mathematical/business invariants** for Property-Based Tests (e.g., balance conservation, state machine monotonicity) if not self-evident, then obtain **Step 2.3 pre-code approval via `ask_question`**. |

### 2.2 Brownfield Ambiguity & 4-Step RCA Question Patterns (Steps 2.0 & 2.4)
- **Brownfield Baseline Triage (Step 2.0):** When reverse-engineering uncovers undocumented edge cases, schema drift, or suspected legacy bugs, ask via `ask_question`: *"Should we codify this existing behavior as a **Baseline Invariant** in `specs/baseline/`, or classify it as a **Legacy Defect** to remediate in `specs/features/`?"*
- **Mandatory 4-Step RCA Decisions on Test/Eval Failures (Step 2.4):** Whenever a Unit Test, Property-Based Test (PBT), or `agents-cli eval` fails, present the diagnostic root cause report and ask via `ask_question`:
  - `Option A: [Data Tier / Schema Resolution] — with pros, cons, and blast radius`
  - `Option B: [Cognitive Prompt / FunctionTool Docstring Refinement] — with pros, cons, and blast radius`
  - `Option C: [API / Architecture Contract Adjustment] — with pros, cons, and blast radius`

### 2.3 Phase 2 Gate Checklist (`Gate 2: Execution -> Operation`)
- [ ] Brownfield Baseline SDD (`specs/baseline/`, Sections 1–8) created or updated with zero unresolved ambiguities (if brownfield).
- [ ] Feature SDD (`specs/features/SPEC-<YYYYMMDD>-<TITLE>.md`) authored with **Document Control + all 10 sections** from [`specs/templates/sdd-template.md`](../examples/specs/templates/sdd-template.md) (omitting `[AI-Agent Only]` items when `Workload Type: Regular App`).
- [ ] **Zero unfilled placeholders** (`[SPEC-YYYYMMDD-TITLE]`, `[e.g., ...]`, `[Decision Title]`, `YYYY-MM-DD`, `TBD`, or unselected `Workload Type`/`Status` unions) remain in `SPEC-*.md` (`validate_sdlc_gate.py --phase execution` passes).
- [ ] Stakeholder approval obtained via `ask_question` on the completed SDD & Implementation Plan prior to coding (Step 2.3).
- [ ] Every implementation step completed with passing **Deterministic Unit Tests** and **Generative Property-Based Tests (PBT)** *(plus DLP-safe live `agents-cli eval` if `AI Agent`/`Hybrid`)*.
- [ ] Zero fake fallback dictionaries, regex routing, or quick-fix workarounds (Rule 13).
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
