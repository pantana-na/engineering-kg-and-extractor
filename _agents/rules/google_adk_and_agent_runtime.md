---
trigger: model_decision
description: "Load and enforce this rule whenever designing, implementing, evaluating, or deploying conversational AI agents, LLM reasoning workflows, FunctionTool registries, Model Armor callbacks, or Gemini Enterprise Agent Platform (agent_runtime / agents-cli) workloads."
---

# Rule: Google Agent Development Kit (ADK), Agent Runtime & Model-Driven Reasoning Standards

## Core Mandate
All conversational AI agents, autonomous decision systems, and tool registries developed in this repository **MUST strictly adhere to the official Google Agent Development Kit (`google-adk`) standards**, execute on the **Gemini Enterprise Agent Platform (`agent_runtime`)**, and rely exclusively on **cognitive model-driven reasoning, structured tool execution (`FunctionTool`), semantic vector retrieval, and live database/service queries**.

Direct, unmanaged LLM orchestration scripts without ADK agent encapsulation are strictly prohibited for production runtime. All agent reasoning must be decoupled from the frontend, deploying to the managed Agent Platform runtime while the web application serves as a thin streaming proxy.

Under NO circumstances may an AI agent or orchestrator rely on hardcoded keyword lists, regular expressions, or static fallback heuristics to classify user intents, route requests, extract entities, or determine actions.

---

## 1. Google ADK Architectural Framework & Agent Boundaries

### 1.1 Standard Agent Hierarchy & Active Boundaries
To ensure modularity, maintainability, and clean isolation, all agents must operate within explicit boundaries:
1. **Root Coordinator Agent (`OrchestratorAgent`):**
   - Implemented as a `google.adk.agents.Agent` or `LlmAgent`.
   - Serves as the primary conversational coordinator, session owner, and router.
   - Executes pre-flight security checks (e.g. Model Armor callback), performs model-driven intent classification, and coordinates subagent dispatch or tool execution.
2. **Specialized Domain Subagents:**
   - Subagents are created for distinct bounded contexts or specialized functional domains (e.g. Information Retrieval / Knowledge Search, Analytical Processing / Domain Evaluation, Workflow Automation).
   - Each subagent operates with dedicated instructions, specialized domain tools, and isolated prompt contexts.
3. **Tool Encapsulation over Agent Sprawl:**
   - Avoid creating idle intermediate subagents for simple data operations. Direct database queries, vector searches, API mutations, and entity lookups should be declared as strongly typed ADK `FunctionTool` callables directly attached to the relevant agent.
4. **ADK App Container:**
   - All agents must be registered within an ADK application container `google.adk.apps.App(root_agent=..., name=...)` exported in the standard agent package (e.g., `app/agent.py`).

### 1.2 Strongly Typed, Resilient ADK FunctionTools & HITL Gate
1. **Callable Declaration:**
   - All tools interacting with external systems (Databases, Knowledge Catalogs, Object Storage, External APIs) must be registered as ADK tools using type-annotated Python callables with comprehensive Google-style docstrings, or wrapped using `google.adk.tools.FunctionTool`.
2. **Comprehensive Docstring Contracts:**
   - Tool docstrings must explicitly define:
     - Clear parameter descriptions and types.
     - **"When to use"** scenarios with concrete example queries.
     - **"When NOT to use"** negative constraints to prevent tool miscalling and overlapping scope.
3. **Type Safety & Data Models:**
   - Tool arguments and return types must use Python type hints and Pydantic models matching the specifications in `specs/`.
4. **Structured Error Returns (Zero Unhandled Crashes or Fake Fallbacks):**
   - When an upstream database or API call fails or returns empty results, a `FunctionTool` must return a structured, typed diagnostic payload (e.g., `{"status": "NOT_FOUND" | "UPSTREAM_ERROR", "error_code": "...", "details": "..."}`) so the ADK agent can reason transparently. Returning fake/mockup fallback data is strictly prohibited.
5. **Mutating / Destructive Tool HITL Gate:**
   - Any `FunctionTool` that performs state-mutating, financial, or destructive actions (e.g., deleting records, modifying production configurations, submitting external orders) must require explicit Human-in-the-Loop (HITL) user confirmation in the session state before executing the mutation, and must support idempotency keys.

### 1.3 Inline Security via ADK Callbacks (`Model Armor`)
1. **Lifecycle Hook Wiring:**
   - Security guardrails (Google Cloud Model Armor) must be wired directly into the ADK lifecycle via `before_agent_callback` or `before_model_callback` (and `after_model_callback` for output sanitization where required).
2. **Deterministic Interception:**
   - Any prompt flagged by Model Armor (`filterMatchState == "MATCH_FOUND"`) must abort model reasoning immediately with zero downstream tool invocations.

### 1.4 Session Management & Cloud Run $\leftrightarrow$ `agent_runtime` Proxy Contract
1. **Managed Session Store:**
   - Production session state must use managed storage (`--session_service_uri agentengine://...` or standard ADK database session stores).
2. **Multi-Turn Context Continuity:**
   - Clarification states, entity contexts, and user working memory must be preserved within the ADK `ToolContext` / `Session.state` across multi-turn dialogues.
3. **Stateless Cloud Run Streaming Proxy Handshake:**
   - The Cloud Run backend proxy (`cloud_run`) must authenticate to the Gemini Enterprise Agent Platform (`agent_runtime`) using Application Default Credentials (ADC) of its dedicated least-privilege Service Account (`roles/aiplatform.user`), forward the verified end-user identity context + `session_id`, and stream chunked ADK events (SSE/WebSocket) back to the React/Vite UI without duplicating agent reasoning in the web tier.

---

## 2. Mandatory Model-Driven Reasoning & Zero Hardcoded / Regex Logic

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
   - ✅ **MANDATED:** Dynamically query the database or search index (e.g. `db.query_candidates(...)`) to retrieve ALL valid matching entities in scope, ensuring the user is presented with every valid candidate.

4. **Hardcoded Outputs & Text Templates:**
   - ❌ **STRICTLY FORBIDDEN:** Generating synthetic text answers via hardcoded string interpolation or static lookup tables.
   - ✅ **MANDATED:** Ground dynamic synthesis on retrieved live records (Databases, Vector Stores, Knowledge Bases, External APIs) using Vertex AI Gemini.

### 2.2 Canonical Intent Topology & Classification Contract
Every multi-agent solution must define a formal, mutually exclusive, collectively exhaustive (MECE) Intent Topology tailored to its domain:
1. **Primary Domain Intents:** Distinct, strongly typed semantic categories representing the core operational capabilities of the agent system (e.g. Domain Information Q&A, Task/Workflow Execution, Analytical Evaluation).
2. **Fallback / Out-of-Scope Intent (`OTHERS`):** A dedicated category for inquiries outside the agent's defined scope. When classified as `OTHERS`, the agent must politely inform the user, explain its specialized capabilities, and provide helpful example queries.
3. **Structured Schema Validation:** Intent classification must output a validated enum matching the specification, guaranteeing deterministic routing without unhandled branches.

---

## 3. Live Environment Agent Evaluation (`agents-cli eval`)

Agent quality, reasoning fidelity, and trajectory correctness must be continuously verified using the official **Google Agents CLI (`agents-cli eval`)**.

### 3.1 Live Environment Evaluation Mandate
- When initiating agent evaluations, tests **MUST run against the live environment** (`agents-cli eval run` connecting to live database instances, knowledge catalogs, and live agent runtime backends).
- Offline mocks, synthetic hardcoded stubs, or simulated shortcuts are prohibited during formal agent evaluation, ensuring that trajectory execution, latency, and tool contracts reflect real-world operational truth.

### 3.2 Comprehensive Evaluation Criteria & Metrics
All evaluation suites must assess agent trajectories across the following six core dimensions:

1. **Tool Trajectory & Selection Accuracy (Target: $\ge 95\%$):**
   - **Precision & Recall:** Did the agent select the precise tool(s) required by the inquiry without calling extraneous tools?
   - **Parameter Fidelity:** Were tool arguments correctly extracted, typed, and normalized against live system entities and database identifiers?
   - **Trajectory Exact Match:** In multi-step workflows, did tool execution follow the required engineering sequence?

2. **Groundedness & Context Faithfulness (Target: 1.000 / 100%):**
   - Verifies that 100% of facts, parameters, operating limits, and citations in the agent's synthesized output are strictly derived from the tool responses retrieved from live data sources.
   - **Zero Hallucination / Zero Speculation:** Any claim not substantiated by retrieved tool data fails the evaluation.

3. **Negative Constraint Adherence (Target: 100%):**
   - Explicitly evaluates that prohibited tools are **NEVER** called for excluded inquiry types (e.g., verifying that unstructured document readers are never called for structured inventory counts, and vice versa).

4. **Security & Guardrail Efficacy (Target: 100%):**
   - Interception of adversarial attacks, prompt injections, and jailbreaks at the pre-flight callback, verifying 100% block rate and zero downstream tool execution on unsafe prompts.

5. **Ambiguity Resolution & Human-in-the-Loop (HITL) Clarification Rate (Target: 100%):**
   - Verifies that ambiguous or generic queries consistently trigger `clarification_requested` with live candidate options rather than arbitrary guesses.

6. **Trajectory Efficiency & Step Bounds:**
   - Step count must not exceed optimal bounds (e.g. maximum 1–2 tool hops for single-entity inquiries).
   - End-to-end wall-clock latency must remain within production SLA limits.

### 3.3 Comprehensive Evaluation Dataset Standard
Evaluation datasets (`evals/datasets/*.jsonl`) must be comprehensive and representative across all operational domains:
- **Broad Entity Coverage:** Golden datasets must cover the full breadth of domain entities, operational categories, and user personas (not just a single example asset or happy-path entity).
- **Diverse Query Types:** Must test happy paths, edge cases, multi-hop traversals, boundary violations, negative constraints, ambiguous prompts, and adversarial security attacks.
- **Golden Trajectories:** Each test case must specify expected tool calls, required arguments, and reference grounded outputs.

### 3.4 Strict Prohibition: Zero Hardcoded Logic on Failed Evals
- **IF AGENT EVALUATION FAILS, NEVER ATTEMPT TO PASS IT BY HARDCODING AGENT LOGIC.**
- Strictly prohibited:
  - Adding `if prompt == "..."` or regex heuristics to force the expected tool or answer.
  - Hardcoding static candidate lists or fallback values into tool functions.
  - Weakening eval criteria or deleting failing test cases to artificially inflate metrics.
- **Mandated Action on Eval Failure:**
  - Investigate the root cause in prompt instructions, tool docstrings, database records, or model temperature.
  - Follow the **Mandatory 4-Step Root Cause Investigation (RCA) Protocol** ([`_agents/rules/ai_sdlc_and_sdd_standards.md`](./ai_sdlc_and_sdd_standards.md)).

---

## 4. Deployment & Lifecycle Management

### 4.1 Runtime Separation of Responsibilities
To maintain strict architectural decoupling, the repository enforces a clear division between runtimes:
1. **Conversational AI Agents & Tool Registries -> Gemini Enterprise Agent Platform (`agent_runtime`):**
   - All Google ADK root coordinators, specialized subagents, cognitive reasoning logic, and `FunctionTool` registries deploy exclusively to the managed **Gemini Enterprise Agent Platform (`agent_runtime`)**.
   - Managed and deployed via `agents-cli deploy --deployment-target agent_runtime`.
2. **Web Applications, API Gateways & Thin Proxies -> Google Cloud Run (`cloud_run`):**
   - Frontend user interfaces (React/Vite), REST/WebSocket API gateways, and streaming reverse proxies deploy to **Google Cloud Run**.
   - Cloud Run services serve web client requests, handle ingress/IAP authentication, and act as thin streaming proxies forwarding conversational turns to the Agent Platform runtime.
   - Managed via Google Cloud Build container pipelines and Terraform Infrastructure Manager.

### 4.2 Project Manifest (`agents-cli-manifest.yaml`)
The repository root must maintain an accurate `agents-cli-manifest.yaml` specifying:
- `name`: Normalized lowercase hyphenated agent name.
- `agent_directory`: Directory containing `agent.py` and `app`.
- `region`: Target Google Cloud region (e.g., `us-central1`, `asia-southeast1`, `europe-west1`).
- `deployment_target`: `agent_runtime` (Gemini Enterprise Agent Platform for AI agents).
- `base_template`: `adk`.

### 4.3 Deployment via `agents-cli deploy`
Production agent deployments must be executable via:
```bash
agents-cli deploy --deployment-target agent_runtime --region <TARGET_REGION>
```
Automated deployment scripts (`scripts/deploy.sh`) must integrate with `agents-cli`.

---

## 5. Enforcement & Quality Gates

1. **Code Reviews:**
   - Pull requests introducing agent logic without ADK `Agent` encapsulation will be rejected.
   - Any PR introducing `re.search`, `re.match`, or hardcoded if/else keyword heuristics to determine agent routing or entity extraction will be rejected.
2. **Unit Testing:**
   - All new tools must have unit tests verifying tool schema reflection, parameter validation, and deterministic execution.
3. **Property-Based Testing (PBT):**
   - Property tests must verify that intent classification outputs strictly belong to the system's defined Canonical Intent Enum across arbitrary fuzz inputs.
   - Property tests must verify that ADK agents maintain safety invariants and state consistency across fuzzed inputs.
4. **Live Evaluation Gate:**
   - Agent evaluations must run against the live environment and achieve $\ge 95\%$ trajectory precision and 1.000 groundedness before promotion.
