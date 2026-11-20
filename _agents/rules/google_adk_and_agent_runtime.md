---
trigger: model_decision
description: "Load and enforce this rule whenever designing, implementing, evaluating, or deploying conversational AI agents, LLM reasoning workflows, FunctionTool registries, Model Armor/Cloud DLP callbacks, or Gemini Enterprise Agent Platform (agent_runtime / agents-cli) workloads."
---

# Rule: Google Agent Development Kit (ADK), Agent Runtime, SAIF 2.0 Security & WAF AI/ML Standards

## Core Mandate (Rules 11–12 — Wired to `ai-sdlc` Master Hub)
Orchestrated by the **[`ai-sdlc` master skill (`../skills/ai_sdlc/SKILL.md`)](../skills/ai_sdlc/SKILL.md)** and [`ai_sdlc_and_sdd_standards.md`](./ai_sdlc_and_sdd_standards.md), all conversational AI agents, autonomous decision systems, and tool registries developed in this repository **MUST strictly adhere to the official Google Agent Development Kit (`google-adk`) standards**, the **[Google Secure AI Framework (SAIF & SAIF 2.0 for Autonomous Agents)](https://safety.google/intl/en/safety/saif/)**, and the **[Google Cloud Well-Architected Framework (AI & ML Perspective)](https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml)** (governed by [`_agents/skills/gcp_well_architected_saif/SKILL.md`](../skills/gcp_well_architected_saif/SKILL.md), which takes strict precedence in case of conflict).

This consolidated file enforces **Rule 11** (*Google ADK Architectural Framework, Cognitive Reasoning & SAIF 2.0 4-Point Guardrails*) and **Rule 12** (*DLP-Safe Live Environment Agent Evaluation & Quality Gates*). All agents execute on the **Gemini Enterprise Agent Platform (`agent_runtime`)** inside a **VPC Service Controls (VPC-SC)** and **CMEK** perimeter, and rely on **cognitive model-driven reasoning paired with deterministic externalized security & policy enforcement**. Under NO circumstances may an AI agent or orchestrator rely on hardcoded keyword lists, regular expressions, or static fallback heuristics to classify user intents, route requests, extract entities, or determine actions.

---

## 1. Google ADK Architectural Framework, SAIF 2.0 Boundaries & Runtime (Rule 11)

### 1.1 Standard Agent Hierarchy, Least-Privilege Subagent Partitioning & Pinned Models
To ensure modularity, blast-radius containment (SAIF Principle 2: *Carefully Limited Powers*), and clean isolation:
1. **Root Coordinator Agent (`OrchestratorAgent`):**
   - Implemented as a `google.adk.agents.Agent` or `LlmAgent`.
   - Serves as the primary conversational coordinator, session owner, and router bound to a cryptographically authenticated human controller (SAIF Principle 1: *Well-Defined Human Controllers*).
   - Executes pre-flight security checks (`before_agent_callback` / `before_model_callback`), performs model-driven intent classification, and coordinates subagent dispatch.
2. **Risk-Partitioned Specialized Domain Subagents (Read-Only vs. Bounded Action):**
   - Partition subagents by operational risk and IAM privilege:
     - **Informational & RAG Retrieval Subagents:** Operate under **strictly read-only IAM principals** (`roles/bigquery.dataViewer`, `roles/discoveryengine.viewer`) with zero write/mutation permissions.
     - **Workflow / Action Subagents:** Isolated to invoke only narrow, schema-validated deterministic action tools behind externalized policy and HITL gates.
3. **Tool Encapsulation & Anti-Confused-Deputy Identity Propagation (`User Auth` + `Agent Identity`):**
   - Avoid creating idle intermediate subagents for simple operations, and **NEVER** allow an agent to query multi-tenant data stores or mutate records using an over-privileged shared backend Service Account on behalf of a user (**Confused Deputy** anti-pattern).
   - Every `FunctionTool` interacting with user-scoped data or enterprise APIs **MUST propagate the authenticated end-user's down-scoped OAuth 2.0 identity (`User Auth`)** alongside the attested **`Agent Identity`** so downstream RAG stores and APIs enforce row- and document-level ACLs.
4. **Version-Pinned Foundation Models & Execution Budgets (SAIF `DMS` Mitigation):**
   - Production agents **MUST pin explicit, immutable foundation model versions** (e.g., `gemini-2.5-pro-001`, `gemini-2.5-flash-001` — never floating aliases).
   - Use **WAF Model Routing** (Gemini Flash for low-latency intent classification/extraction; Gemini Pro for complex multi-step reasoning) and **Vertex AI Context Caching** for repeated system instructions/corpora.
   - Enforce hard per-session **execution budgets** (max agent turns/steps, max subagent delegation depth, wall-clock timeout, and max token ceiling) to prevent runaway loops and Denial of ML Service (`DMS`).
5. **ADK App Container:**
   - All agents must be registered within `google.adk.apps.App(root_agent=..., name=...)` exported in the standard agent package (e.g., `app/agent.py`).

### 1.2 Strongly Typed, Resilient ADK FunctionTools & Externalized Deterministic HITL Gate
1. **Callable Declaration & Narrow Deterministic Scope:**
   - All tools interacting with external systems must be registered as type-annotated Python callables with comprehensive Google-style docstrings wrapped via `google.adk.tools.FunctionTool`.
   - Expose **narrow, domain-specific deterministic tools** (e.g., `submit_provisional_credit_request(...)`), **never** raw generic execution primitives (`execute_raw_sql(...)` or `run_shell(...)`).
2. **Comprehensive Docstring Contracts:**
   - Tool docstrings must explicitly define parameter types, **"When to use"** scenarios with concrete examples, and **"When NOT to use"** negative constraints.
3. **Type Safety & Strict Schema Validation:**
   - Tool arguments and return types must use Python type hints and strict Pydantic models matching `specs/`, validated deterministically **before** invoking backend logic.
4. **Structured Error Returns & WAF Graceful Degradation (Zero Fake/Mockup Fallbacks):**
   - Implement **bounded timeouts, retries with exponential backoff + jitter, and circuit breakers** on all external tool calls.
   - When an upstream database or API call fails or returns empty results, a `FunctionTool` must return a structured diagnostic payload (e.g., `{"status": "NOT_FOUND" | "UPSTREAM_UNAVAILABLE_DEGRADED", "error_code": "...", "details": "..."}`) or verified read-only cached policy stamped with `as_of_timestamp`. Returning fabricated/mockup records is strictly prohibited.
5. **Mutating / Financial / Destructive Tool Gate (SAIF `RAC` — Externalized Deterministic HITL + Policy Caps):**
   - Probabilistic LLM reasoning cannot be trusted to self-enforce financial caps or self-approve mutations. Any state-mutating, financial, or destructive action **MUST**:
     1. Enforce **deterministic policy/monetary caps** in non-LLM backend code (e.g., rejecting amounts above tier limits regardless of prompt state).
     2. Require an **externalized, cryptographically verified Human-in-the-Loop (HITL) approval token** confirmed by the authenticated human controller in the trusted UI/API layer *outside* the LLM's context window (preventing an indirect prompt injection from flipping a session flag to self-approve a mutation).
     3. Enforce **idempotency keys** to prevent duplicate execution on retries.

### 1.3 4-Point Inline Security via ADK Callbacks (`Model Armor` + `Sensitive Data Protection / Cloud DLP`)
To mitigate SAIF risks `PIJ` (Direct & Indirect Prompt Injection), `EDH` (Excessive Data Handling), `SDD` (Sensitive Data Disclosure), and `IMO` (Insecure Model Output), wire security callbacks across **all four ADK lifecycle boundaries**:
1. **`before_agent_callback` / `before_model_callback` (Inbound Firewall & PII Tokenization):**
   - Screen raw user prompts via **Google Cloud Model Armor** (Prompt Injection, Jailbreak, Malicious URLs, CSAM/RAI). Any `filterMatchState == "MATCH_FOUND"` must abort execution immediately with zero LLM or tool calls.
   - De-identify or cryptographically tokenize sensitive PII/PCI/PHI (PAN, CVV, SSN, Account Numbers) via **Sensitive Data Protection (Cloud DLP)** *before* prompts reach the foundation model, Vertex AI Context Cache, `agentengine://` session store, or Cloud Logging.
2. **`after_tool_callback` (Indirect Prompt Injection Screening on Untrusted Data):**
   - Screen all untrusted retrieved RAG chunks, uploaded customer documents, and external tool responses via **Model Armor** for **Indirect Prompt Injection (`PIJ`)** before feeding tool outputs back into the model's reasoning context.
3. **`after_model_callback` (Outbound DLP Scrubbing & Zero-Click Exfiltration Prevention):**
   - Scrub model outputs via **Model Armor + Cloud DLP** to prevent Sensitive Data Disclosure (`SDD`), and enforce a strict **outbound URL/origin allowlist** (stripping unauthorized Markdown images/links `![...](https://...)` to block zero-click data exfiltration).
4. **Immutable Audit & Trajectory Telemetry (SAIF Principle 3):**
   - Emit structured OpenTelemetry / Cloud Logging traces capturing `session_id`, authenticated `user_principal`, `agent_id`, prompt/response SHA-256 hashes, retrieved document version IDs, Model Armor verdicts, tool trajectories, and HITL signatures to CMEK-encrypted audit sinks.

### 1.4 Session Management & Cloud Run $\leftrightarrow$ `agent_runtime` Proxy Contract
1. **Managed Session Store (CMEK + DLP Safe):**
   - Production session state must use managed storage (`--session_service_uri agentengine://...` or CMEK-encrypted ADK database session stores) storing only DLP-tokenized/redacted context.
2. **Multi-Turn Context Continuity:**
   - Clarification states, entity contexts, and user working memory must be preserved within the ADK `ToolContext` / `Session.state` across multi-turn dialogues.
3. **Stateless Cloud Run Streaming Proxy Handshake:**
   - The Cloud Run backend proxy (`cloud_run`) authenticates to the Gemini Enterprise Agent Platform (`agent_runtime`) over private networking (**VPC-SC / Private Service Connect**) using ADC of its dedicated least-privilege Service Account (`roles/aiplatform.user`), forwards the verified end-user OAuth2 identity (`User Auth`) + `session_id`, and streams chunked ADK events (SSE/WebSocket) back to the React/Vite UI.

---

## 2. Mandatory Model-Driven Reasoning & Zero Hardcoded / Regex Logic (Rule 11 Continued)

### 2.1 Prohibited Anti-Patterns in AI Agents

1. **Regex Intent Classification & Keyword Routing:**
   - ❌ **STRICTLY FORBIDDEN:** `if re.search(r"keyword1|keyword2", prompt): return "INTENT_A"`
   - ❌ **STRICTLY FORBIDDEN:** `if any(k in prompt.lower() for k in ["tag", "id"]): ...`
   - ✅ **MANDATED:** Call Gemini LLM (`classify_intent_with_model`) using a structured JSON schema / Pydantic model to categorize intent based on conversational context and domain semantics.

2. **Hardcoded Entity Fallbacks & Defaults:**
   - ❌ **STRICTLY FORBIDDEN:** `target_entity = entity_match or "DEFAULT_ID"`
   - ✅ **MANDATED:** Use model entity extraction or prompt the user for clarification if the target entity or required parameter is missing or ambiguous.

3. **Incomplete / Hardcoded Clarification Choices:**
   - ❌ **STRICTLY FORBIDDEN:** Hardcoding a static array of 2–3 options (e.g. `candidates = [{"id": "ITEM-1"}, {"id": "ITEM-2"}]`).
   - ✅ **MANDATED:** Dynamically query the database or search index (scoped to the caller's `User Auth` ACLs) to retrieve ALL valid matching entities in scope.

4. **Hardcoded Outputs & Text Templates:**
   - ❌ **STRICTLY FORBIDDEN:** Generating synthetic text answers via hardcoded string interpolation or static lookup tables.
   - ✅ **MANDATED:** Ground dynamic synthesis on retrieved live records (Databases, Vector Stores, Knowledge Bases, External APIs) using Vertex AI Gemini with verifiable source citations.

### 2.2 Canonical Intent Topology & Classification Contract
Every multi-agent solution must define a formal, mutually exclusive, collectively exhaustive (MECE) Intent Topology tailored to its domain:
1. **Primary Domain Intents:** Distinct, strongly typed semantic categories representing the core operational capabilities of the agent system (e.g. Domain Information Q&A, Task/Workflow Execution, Analytical Evaluation).
2. **Fallback / Out-of-Scope Intent (`OTHERS`):** A dedicated category for inquiries outside the agent's defined scope. When classified as `OTHERS`, the agent must politely inform the user, explain its specialized capabilities, and provide helpful example queries.
3. **Structured Schema Validation:** Intent classification must output a validated enum matching the specification, guaranteeing deterministic routing without unhandled branches.

---

## 3. DLP-Safe Live Environment Agent Evaluation (`agents-cli eval`) (Rule 12)

Agent quality, reasoning fidelity, SAIF guardrail resilience, and trajectory correctness must be continuously verified using the official **Google Agents CLI (`agents-cli eval`)**.

### 3.1 DLP-Safe Live Environment Evaluation Mandate (WAF Privacy & SAIF `EDH`/`SDD` Alignment)
- When initiating agent evaluations, tests **MUST run against a live deployed environment** (`agents-cli eval run` connecting to live database instances, vector catalogs, and live agent runtime backends).
- Offline mocks, synthetic hardcoded stubs, or simulated shortcuts in application code are prohibited during formal agent evaluation.
- **Data Privacy Protection in Live Evals:** In regulated or PII/PCI-sensitive workloads, live evaluations **MUST run against an isolated, de-identified or synthetic-seeded Non-Prod live environment** (or a DLP-masked read-only replica inside a VPC-SC + CMEK boundary)—**never** exposing raw production customer PII/PANs in evaluation logs.

### 3.2 Comprehensive Evaluation Criteria & Metrics
All evaluation suites must assess agent trajectories across the following six core dimensions:

1. **Tool Trajectory & Selection Accuracy (Target: $\ge 95\%$):**
   - **Precision & Recall:** Did the agent select the precise tool(s) required by the inquiry without calling extraneous tools?
   - **Parameter Fidelity:** Were tool arguments correctly extracted, typed, and normalized against live system entities and database identifiers?
   - **Trajectory Exact Match:** In multi-step workflows, did tool execution follow the required engineering sequence?

2. **Groundedness, Context Faithfulness & Verifiable Citations (Target: 1.000 / 100%):**
   - Verifies that 100% of facts, parameters, operating limits, effective dates, and citations in the agent's synthesized output are strictly derived from the tool responses retrieved from live authoritative data sources.
   - **Zero Hallucination / Zero Speculation:** Any claim not substantiated by retrieved tool data fails the evaluation.

3. **Negative Constraint & Least-Privilege Adherence (Target: 100%):**
   - Explicitly evaluates that prohibited or mutating tools are **NEVER** called for excluded inquiry types, and that unconfirmed or over-cap mutations are deterministically blocked (`RAC`).

4. **SAIF Security & 4-Point Guardrail Efficacy (Target: 100%):**
   - Evaluates interception of **Direct Prompt Injections**, **Indirect Prompt Injections** embedded in retrieved RAG/tool payloads (`PIJ`), **PII/PCI redaction/tokenization** (`EDH`/`SDD`), and **jailbreak/evasion attempts** (`MEV`), verifying 100% block/redaction rate and zero unauthorized downstream tool execution.

5. **Ambiguity Resolution & Human-in-the-Loop (HITL) Clarification Rate (Target: 100%):**
   - Verifies that ambiguous queries consistently trigger `clarification_requested` with live candidate options, and state-mutating actions consistently require externalized HITL confirmation.

6. **Trajectory Efficiency, TTFT & Execution Budget Bounds:**
   - Step count must not exceed optimal bounds (e.g. maximum 1–2 tool hops for single-entity inquiries) and must strictly respect per-session turn/token budgets (`DMS`).
   - Time-to-First-Token (TTFT) and end-to-end p95 latency must remain within production SLO targets.

### 3.3 Comprehensive Evaluation Dataset & Continuous Feedback Loop (SAIF Element 5)
- Evaluation datasets (`evals/datasets/*.jsonl`) must cover the full breadth of domain entities, personas, happy paths, edge cases, multi-hop traversals, negative constraints, ambiguous prompts, and adversarial direct/indirect prompt injection attacks.
- Production HITL overrides and red-team findings must be continuously fed back into `evals/datasets/*.jsonl` as regression test cases.

### 3.4 Strict Prohibition: Zero Hardcoded Logic on Failed Evals
- **IF AGENT EVALUATION FAILS, NEVER ATTEMPT TO PASS IT BY HARDCODING AGENT LOGIC.**
- Strictly prohibited: adding `if prompt == "..."` or regex heuristics, hardcoding static candidate lists, or weakening eval criteria.
- **Mandated Action on Eval Failure:** Follow the **Mandatory 4-Step Root Cause Investigation (RCA) Protocol** ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](./ai_sdlc_and_sdd_standards.md)).

---

## 4. Deployment, Capacity Assurance & Lifecycle Management

### 4.1 Runtime Separation of Responsibilities
1. **Conversational AI Agents & Tool Registries $\rightarrow$ Gemini Enterprise Agent Platform (`agent_runtime`):**
   - All Google ADK root coordinators, specialized subagents, 4-point Model Armor/DLP callbacks, and `FunctionTool` registries deploy exclusively to the managed **Gemini Enterprise Agent Platform (`agent_runtime`)** via `agents-cli deploy --deployment-target agent_runtime`.
   - For mission-critical production workloads, size **Vertex AI Provisioned Throughput (GSUs)** for baseline load with automatic **PayGo spillover** to prevent `429 RESOURCE_EXHAUSTED` quota outages.
2. **Web Applications, API Gateways & Thin Proxies $\rightarrow$ Google Cloud Run (`cloud_run`):**
   - Frontend user interfaces (React/Vite), REST/SSE/WebSocket API gateways, and externalized deterministic HITL/policy verification endpoints deploy to **Google Cloud Run** behind **Pattern 1A (Global External ALB + Cloud Armor + IAP)**, **Pattern 1B (Direct Cloud Run IAP for internal single-region workforce apps)**, or **Pattern 2 (App-Level OAuth2 + Cloud Armor)**, managed via Cloud Build and Terraform Infrastructure Manager.

### 4.2 Project Manifest (`agents-cli-manifest.yaml`) & Atomic Versioning
- Maintain `agents-cli-manifest.yaml` (`name`, `agent_directory`, `region`, `deployment_target: agent_runtime`, `base_template: adk`).
- Version system prompts, `FunctionTool` schemas, pinned model IDs, and golden eval datasets atomically in Git so any regression can be rolled back in one command.

### 4.3 Deployment via `agents-cli deploy`
```bash
agents-cli deploy --deployment-target agent_runtime --region <TARGET_REGION>
```

---

## 5. Enforcement & Quality Gates

1. **Code & Architecture Reviews (`validate_waf_saif.py`):**
   - Rejects any agent logic lacking ADK `Agent` encapsulation, 4-point Model Armor + Cloud DLP hooks, `User Auth` propagation, or externalized HITL gates on mutating tools.
   - Rejects any PR introducing `re.search`, `re.match`, or hardcoded keyword heuristics for intent routing or entity extraction.
2. **Unit Testing:**
   - All tools and callbacks must have unit tests verifying schema reflection, `User Auth` checks, deterministic policy cap enforcement, and graceful degradation.
3. **Property-Based Testing (PBT):**
   - Property tests must verify that intent classification outputs strictly belong to the Canonical Intent Enum, that Cloud DLP tokenization leaves zero raw PII/PAN patterns across fuzzed inputs, and that unconfirmed/over-cap mutations are 100% rejected.
4. **DLP-Safe Live Evaluation Gate:**
   - Agent evaluations must run against the live environment and achieve $\ge 95\%$ trajectory precision, $1.000$ groundedness, and $100\%$ SAIF adversarial block rate before promotion.

