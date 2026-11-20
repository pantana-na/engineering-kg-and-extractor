# Brownfield Assessment Playbook: Legacy (.NET / 3-Tier) & Modern Cloud-Native Codebases

This playbook provides detailed technical procedures for **Phase 1 (Step 1.1)** and **Phase 2 (Step 2.0: Brownfield Baseline Discovery & Codification)** of the [`ai-sdlc` skill](../SKILL.md).

Whenever an agent activates [`ai-sdlc`](../SKILL.md), it must **inspect three signals first** (*1. Workspace code files*, *2. `specs/discovery/` or legacy manuals/prompt verbs*, *3. Existing `specs/baseline/`*) and **confirm Greenfield vs. Brownfield with the user in the very first `ask_question` call**:
- **Empty Repo $\neq$ Automatically Greenfield:** If the Git repo has zero code, confirm whether the team is actually replacing/strangling an **external legacy system or database** living in another repo/directory (if yes, treat as **Brownfield**: request read access/SQL dumps for `specs/baseline/` or consolidate legacy SOPs/drawings via [`requirements-discovery`](../../requirements_discovery/SKILL.md)).
- **Existing Code $\neq$ Automatically Production Baseline:** If the repo contains PoC/hackathon or starter boilerplate code, confirm via `ask_question` whether to **preserve it as a Brownfield baseline** (`specs/baseline/` + characterization tests) or **discard/replace it cleanly as Greenfield**.
- Once **Brownfield** is confirmed, classify the system into **Track A (Legacy Enterprise / 3-Tier / .NET Framework)**, **Track B (Modern Cloud-Native Lacking Docs & Tests)**, or a **Hybrid** of both, and produce a Baseline SDD in `specs/baseline/` using [`baseline-template.md`](../examples/specs/templates/baseline-template.md).

> [!IMPORTANT]
> **Brownfield Synergy with Optional [`requirements-discovery`](../../requirements_discovery/SKILL.md) (`specs/discovery/` $\leftrightarrow$ `specs/baseline/`):**
> - **`specs/discovery/DISCOVERY-*.md` (*Stakeholder & Artifact Truth — Optional*):** Consolidates legacy SOP manuals, Visio/whiteboard drawings, user interviews, and emails (what humans *think* the legacy system does + what modernization outcomes they want).
> - **`specs/baseline/<subsystem>-baseline.md` (*Executable Code Truth — Mandatory for Brownfield*):** Reverse-engineers actual source code, `Web.config`, routes, and SQL Stored Procedures (`sp_*` / triggers).
> - **Manual-vs-Code Drift Reconciliation (`ask_question`):** Whenever `specs/baseline/` reverse-engineering reveals that actual code/SQL contradicts a legacy manual, drawing, or interview statement in `specs/discovery/` (e.g., hidden stored-procedure overrides or undocumented batch jobs), log the discrepancy in **Baseline §7.1** (and **Discovery §10.1**) and use `ask_question` to confirm whether the **code behavior** or the **documented stakeholder rule** is the true requirement for `specs/features/SPEC-*.md`.

---

## 1. Track A: Legacy Enterprise & 3-Tier Application Assessment (e.g., .NET Framework)

Legacy 3-tier applications (such as `.NET Framework 4.x`, ASP.NET WebForms/MVC, WCF/ASMX SOAP services, Windows Services, and SQL Server / Oracle databases) rarely store all business logic in clean domain classes. Instead, critical logic is often split across **UI code-behind files**, **middle-tier service classes**, **`Web.config` files**, and **Database Stored Procedures / Triggers**.

### Step A1: Solution & Tier Topology Discovery
1. **Locate Solution & Project Manifests:**
   - Scan for `*.sln`, `*.csproj`, `*.vbproj`, `packages.config`, `Web.config`, `App.config`, and `Global.asax`.
   - Map project references (`<ProjectReference>`) to reconstruct the 3-tier dependency graph:
     - **Presentation Tier:** ASP.NET WebForms (`*.aspx`, `*.aspx.cs`, `*.master`), ASP.NET MVC (`Controllers/`, `Views/*.cshtml`), Classic Razor, or legacy AngularJS/jQuery scripts.
     - **Business Logic / Service Tier:** Class libraries (`*BLL*`, `*Services*`, `*Core*`), WCF services (`*.svc`, `[ServiceContract]`, `[OperationContract]`), ASMX web services (`*.asmx`), and background Windows Services / Quartz / Hangfire jobs.
     - **Data Access & Database Tier:** Entity Framework (`*.edmx` DB-first, `DbContext`), Dapper, raw `SqlConnection`/`SqlCommand` (`CommandType.StoredProcedure`), `DataSet`/`DataTable` adapters (`*.xsd`), and `.dacpac`/SQL scripts (`*.sql`).

### Step A2: Hidden Business Logic Extraction (UI, Config & SQL Tier)
Inspect and extract implicit business rules from the four places where legacy 3-tier apps hide logic:
1. **SQL Stored Procedures, Functions & Triggers:**
   - Search for `CREATE PROCEDURE`, `CREATE TRIGGER`, `CREATE FUNCTION`, ` sp_`, ` usp_`, and `CommandType.StoredProcedure`.
   - Document every multi-step transaction, conditional branching (`IF...BEGIN...END`), fee/pricing calculation, and audit side-effect inside **Section 2.4** (*Hidden Business Logic Extraction Matrix*) of `specs/baseline/<subsystem>-baseline.md`.
2. **UI Code-Behind & Stateful Session Coupling:**
   - Search for `HttpContext.Current.Session`, `ViewState[`, `TempData[`, `Application[`, and validation logic embedded directly inside button click handlers (`btnSubmit_Click`) or MVC controller actions.
   - Identify stateful assumptions that will break when migrating to stateless **Google Cloud Run (`cloud_run`)** containers or **`agent_runtime`**.
3. **Configuration & Infrastructure Bindings (`Web.config` / `App.config` / IIS):**
   - Extract all `<appSettings>`, `<connectionStrings>`, `<system.serviceModel>` (WCF bindings/endpoints), and `<system.web>` authentication modes (`Windows`, `Forms`, `None`).
   - Map every environment-specific setting to the target unified single-file `.env` (`NONPROD_*` and `PROD_*` blocks) per [`devops_security_and_quality_standards.md`](../../../rules/devops_security_and_quality_standards.md) Rule 8.
4. **Authentication, Identity & Perimeter Coupling (WAF Pillar 2 & SAIF 2.0):**
   - Identify legacy Active Directory / LDAP / Integrated Windows Authentication (`WindowsIdentity`, `[Authorize(Roles = ...)]`) and ask the user via `ask_question` how to map it to Google Cloud Run's Zero-Trust IAM/Ingress patterns (**Pattern 1A: ALB + Cloud Armor + IAP** `[Default for Tier-1, external/B2B & regulated apps]`, **Pattern 1B: Direct Cloud Run IAP (`--iap`)** `[Internal workforce, single-region & cost-optimized apps]`, **Pattern 2: App-Level OAuth 2.0/OIDC + Cloud Armor** `[Custom OIDC UX]`, or **Pattern 3: Direct Unauthenticated Ingress** `[STRICTLY restricted to approved anonymous public non-sensitive static/marketing pages]`).
   - Identify regulated data stores (PII, PCI, PHI, MNPI) requiring **VPC Service Controls (`VPC-SC`)**, **Private Service Connect (PSC)**, and **Cloud KMS (`CMEK` / HSM / EKM)**.

### Step A3: Modernization Strategy Selection (`ask_question`)
Present the discovered 3-tier inventory and ask the user via `ask_question` which modernization strategy to execute:
- **Option 1: Strangler Fig / API Facade Pattern (Incremental):** Keep the legacy database or core back-office tier running while extracting targeted bounded contexts into Cloud Run (`cloud_run`) and Gemini Enterprise Agent Platform (`agent_runtime`) behind a streaming proxy.
- **Option 2: Full Dual-Runtime Cloud-Native Re-Architecture:** Migrate the legacy 3-tier slice end-to-end into React/Vite + FastAPI/Express on Cloud Run (`cloud_run`) and Google ADK (`google-adk`) on `agent_runtime`, lifting hidden SQL Stored Procedure rules into tested domain services and `FunctionTool` registries.
- **Option 3: Targeted Subsystem Refactoring:** Refactor and harden the specific module in-place with Characterization Tests and Property-Based Tests before broader cloud migration.

---

## 2. Track B: Modern Cloud-Native Code Assessment (Undocumented & Untested)

Modern cloud-native applications (React/Next.js/Vite frontends, FastAPI/Express/Go/Node backends, containerized microservices, and early LLM/Agent prototypes) often suffer from a different brownfield problem: **they use modern stacks, but lack formal specifications, strict schema boundaries, deterministic unit tests, property-based tests, or clean Dual-Runtime separation.**

### Step B1: Reverse-Engineer Implicit Contracts from Code
1. **API & Route Discovery:**
   - Scan Express/FastAPI/Next.js/Go route definitions (`@app.get`, `@router.post`, `app.use`), GraphQL resolvers, and WebSocket/SSE streaming handlers.
   - Inspect request parsing, middleware chains, implicit status codes, and unhandled promise/exception paths that are not documented in any OpenAPI or SDD file.
2. **Data Model & Type Drift Audit:**
   - Compare frontend TypeScript types (`interface`, `type`, `zod`) against backend Python Pydantic models (`BaseModel`), ORM models (SQLAlchemy, Prisma, Drizzle), and actual database schemas.
   - Flag any "any"-typed payloads, unvalidated JSON dicts, or schema mismatches between frontend and backend.
3. **AI Agent, WAF & SAIF 2.0 Anti-Pattern Audit ([`google_adk_and_agent_runtime.md`](../../../rules/google_adk_and_agent_runtime.md) & [`gcp-well-architected-saif`](../../gcp_well_architected_saif/SKILL.md)):**
   - If the modern codebase includes AI/LLM features, inspect for prohibited anti-patterns:
     - ❌ **Runtime Coupling:** Are LLM/Agent reasoning loops running directly inside the Cloud Run web server instead of being decoupled into `agent_runtime`?
     - ❌ **Heuristic Routing:** Are there regex patterns (`re.search`), keyword lists, or `if/else` string checks routing user intents instead of cognitive ADK `OrchestratorAgent` reasoning?
     - ❌ **Missing `OTHERS` Intent:** Does intent classification lack an explicit `OTHERS` out-of-scope fallback?
     - ❌ **Missing SAIF 2.0 4-Point Guardrails (`PIJ`, `EDH`, `SDD`, `IMO`):** Does the agent lack `before_agent_callback`, `before_model_callback`, `after_tool_callback` (Indirect Prompt Injection screening on retrieved RAG/tool outputs), or `after_model_callback` (output DLP redaction & URL allowlist)?
     - ❌ **Confused Deputy / Excessive Agency (`RAC`):** Do tools execute under an ambient shared service account instead of propagating caller-scoped `User Auth` OAuth 2.0 tokens, or execute high-stakes mutations without externalized deterministic HITL confirmation and hard policy caps?
     - ❌ **Unpinned Models or Unbounded Loops (`DMS`):** Are floating model aliases (`-latest`) used or are `max_llm_calls` / token budgets missing?
     - ❌ **Weak Tool Docstrings:** Do tools lack explicit *"When to use"* and *"When NOT to use"* boundaries?
     - ❌ **Mockup Fallbacks:** Are there hardcoded fallback dictionaries (`if not result: return {"mock": ...}`) hiding data failures?

### Step B2: Backfill the "Characterization + Property-Based Test (PBT)" Safety Net
**Never refactor or add features to an untested modern codebase before locking in its current working behavior.**
1. **Write Characterization Unit Tests (Golden Master Tests):**
   - Capture the exact input $\rightarrow$ output behavior of existing endpoints, data transformers, and state reducers across representative happy paths and edge cases.
2. **Write Generative Property-Based Tests (PBT) (`hypothesis` / `fast-check`):**
   - Formulate mathematical and structural invariants over the reverse-engineered models (e.g., payload serialization round-trips, idempotency, pagination bounds, permission checks) and run fuzzed inputs against the existing code.
3. **Triage Failing PBT Counterexamples via `ask_question`:**
   - When PBT fuzzing uncovers an unhandled edge case in the existing untested code (e.g., empty strings, Unicode, boundary numbers causing a `500`), **do not silently change the behavior**. Present the counterexample to the user via `ask_question` and ask whether to preserve the current behavior or remediate it as a defect in the Feature SDD.

---

## 3. Mandatory Companion Skill Execution During Brownfield Discovery

During Brownfield Assessment (Phase 1 Step 1.4 / Phase 2 Step 2.0), proactively offer and execute these companion skills to establish a complete operational baseline in `docs/`:

1. **Google Cloud Well-Architected (WAF) & SAIF 2.0 Architecture Review ([`gcp-well-architected-saif`](../../gcp_well_architected_saif/SKILL.md)):**
   - Evaluate the brownfield baseline and target modernization design against the 6 WAF Pillars, AI/ML & FSI Perspectives, and 15 SAIF Risks (`docs/waf-saif-review_<project>.md`).
2. **Visual "As-Is vs. Target" Architecture Diagram ([`architecture-diagram`](../../architecture_diagram/SKILL.md)):**
   - Generate `docs/<project>-architecture.md` and `docs/<project>-architecture.html` illustrating:
     - The reverse-engineered **"As-Is"** topology (e.g., 3-Tier IIS/.NET/SQL Server or coupled Cloud-Native app), and
     - The **"Target"** Dual-Runtime topology (`cloud_run` + `agent_runtime`) with WAF Zero-Trust perimeters (ALB + Cloud Armor + IAP, VPC-SC, CMEK) and SAIF 2.0 4-point Model Armor/DLP guardrails clearly highlighted.
3. **Baseline SAST Vulnerability Audit ([`codemender`](../../codemender/SKILL.md)):**
   - Run `cm find` on the existing brownfield codebase to identify legacy security technical debt (SQL injection in legacy ADO.NET/stored procs, hardcoded credentials in `Web.config`, XSS, insecure deserialization, or SAIF risks) and output `docs/codemender-01-vulnerability-scan-report.md`.
4. **Cloud Modernization Cost & FinOps Model ([`gcp-cost-estimator`](../../gcp_cost_estimator/SKILL.md)):**
   - Model the running Google Cloud cost and unit economics of the modernized target architecture using live Google Cloud Billing API pricing in `docs/gcp_cost_estimate_<project>.md`.

