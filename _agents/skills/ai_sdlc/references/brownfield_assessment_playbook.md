# Brownfield Assessment Playbook: Legacy (.NET / 3-Tier) & Modern Cloud-Native Codebases

This playbook provides detailed technical procedures for **Phase 1 (Step 1.1)** and **Phase 2 (Step 2.0: Brownfield Baseline Discovery & Codification)** of the [`ai-sdlc` skill](../SKILL.md).

Whenever an agent assesses an existing codebase, it must first classify the codebase into **Track A (Legacy Enterprise / 3-Tier / .NET Framework)**, **Track B (Modern Cloud-Native Lacking Docs & Tests)**, or a **Hybrid** of both, and produce a comprehensive Baseline SDD in `specs/baseline/` using [`baseline-template.md`](../examples/specs/templates/baseline-template.md).

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
   - Document every multi-step transaction, conditional branching (`IF...BEGIN...END`), fee/pricing calculation, and audit side-effect inside Section 3.2 (*Hidden Business Logic Extraction Matrix*) of `specs/baseline/<subsystem>-baseline.md`.
2. **UI Code-Behind & Stateful Session Coupling:**
   - Search for `HttpContext.Current.Session`, `ViewState[`, `TempData[`, `Application[`, and validation logic embedded directly inside button click handlers (`btnSubmit_Click`) or MVC controller actions.
   - Identify stateful assumptions that will break when migrating to stateless **Google Cloud Run (`cloud_run`)** containers or **`agent_runtime`**.
3. **Configuration & Infrastructure Bindings (`Web.config` / `App.config` / IIS):**
   - Extract all `<appSettings>`, `<connectionStrings>`, `<system.serviceModel>` (WCF bindings/endpoints), and `<system.web>` authentication modes (`Windows`, `Forms`, `None`).
   - Map every environment-specific setting to the target unified single-file `.env` (`NONPROD_*` and `PROD_*` blocks) per [`devops_security_and_quality_standards.md`](../../../rules/devops_security_and_quality_standards.md) Rule 8.
4. **Authentication & Identity Coupling:**
   - Identify legacy Active Directory / LDAP / Integrated Windows Authentication (`WindowsIdentity`, `[Authorize(Roles = ...)]`) and ask the user via `ask_question` how to map it to Google Cloud Run's 3 compliant IAM/Ingress patterns (Pattern 1: IAP, Pattern 2: App-Level Google OAuth 2.0, or Pattern 3: Direct Unauthenticated Ingress).

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
3. **AI Agent & LLM Anti-Pattern Audit ([`google_adk_and_agent_runtime.md`](../../../rules/google_adk_and_agent_runtime.md)):**
   - If the modern codebase includes AI/LLM features, inspect for prohibited anti-patterns:
     - ❌ **Runtime Coupling:** Are LLM/Agent reasoning loops running directly inside the Cloud Run web server instead of being decoupled into `agent_runtime`?
     - ❌ **Heuristic Routing:** Are there regex patterns (`re.search`), keyword lists, or `if/else` string checks routing user intents instead of cognitive ADK `OrchestratorAgent` reasoning?
     - ❌ **Missing `OTHERS` Intent:** Does intent classification lack an explicit `OTHERS` out-of-scope fallback?
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

1. **Visual "As-Is vs. Target" Architecture Diagram ([`architecture-diagram`](../../architecture_diagram/SKILL.md)):**
   - Generate `docs/<project>-architecture.md` and `docs/<project>-architecture.html` illustrating:
     - The reverse-engineered **"As-Is"** topology (e.g., 3-Tier IIS/.NET/SQL Server or coupled Cloud-Native app), and
     - The **"Target"** Dual-Runtime topology (`cloud_run` + `agent_runtime`) with the migration boundary clearly highlighted.
2. **Baseline SAST Vulnerability Audit ([`codemender`](../../codemender/SKILL.md)):**
   - Run `cm find` on the existing brownfield codebase to identify legacy security technical debt (SQL injection in legacy ADO.NET/stored procs, hardcoded credentials in `Web.config`, XSS, insecure deserialization, or vulnerable dependencies) and output `docs/codemender-01-vulnerability-scan-report.md`.
3. **Cloud Modernization Cost Model ([`gcp-cost-estimator`](../../gcp_cost_estimator/SKILL.md)):**
   - Model the running Google Cloud cost of the modernized target architecture using live Google Cloud Billing API pricing in `docs/gcp_cost_estimate_<project>.md`.
