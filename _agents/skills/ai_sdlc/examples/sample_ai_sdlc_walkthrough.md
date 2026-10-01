# End-to-End AI-SDLC Walkthrough Example

This walkthrough demonstrates how the **[`ai-sdlc` skill](../SKILL.md)** guides a developer from an initial feature request through **Phase 1 (Inception)**, **Phase 2 (Execution / SDD)**, and **Phase 3 (Operation / Deploy)** with proactive clarification questions (`ask_question`) and interactive phase gates.

---

## Scenario: Adding a Real-Time Order Dispute Resolution Agent & Portal

**Developer Prompt:**
> *"We need to build an order dispute resolution feature where users can submit a dispute in the web app and chat with an AI agent to check order status and process refunds."*

---

## Phase 1: Inception (Intent Framing & Architecture)

### Step 1.1: Workspace & Brownfield Discovery
The agent inspects the workspace (`specs/baseline/`, `src/`, `server/`, `app/`) and detects an existing brownfield web portal and order database without a baseline specification in `specs/baseline/`.

### Step 1.2 & 1.3: Interactive Clarification via `ask_question`
Because several functional and architectural factors are unspecified, the agent pauses and invokes `ask_question`:
1. **Scope & Refund Policy Boundaries:** What is the maximum automatic refund threshold the AI agent can approve vs. escalating to a human specialist?
2. **Systems of Record:** Which database stores order and refund records (e.g., Cloud SQL PostgreSQL vs. Spanner)?
3. **IAM & Ingress Pattern (Rule 10 — Zero `allUsers`):**
   - `(Recommended) Pattern 1: Identity-Aware Proxy (IAP) behind External HTTPS Load Balancer + Serverless NEG`
   - `Pattern 2: App-Level Google OAuth 2.0 with invoker-iam-disabled="true"`
   - `Pattern 3: Direct Unauthenticated Ingress with invoker-iam-disabled="true"`
4. **Companion Inception Deliverables:** Would you like to generate a visual architecture diagram (`docs/order-dispute-architecture.md` & `.html`) and/or a live GCP cost estimate (`docs/gcp_cost_estimate_order_dispute.md`) before moving to Phase 2?

**Developer Response:**
- Auto-refunds up to $100; above $100 escalates to human review.
- Cloud SQL PostgreSQL is the system of record.
- Selects **Pattern 1 (IAP)**.
- Selects generating the architecture diagram in `docs/`.

### Step 1.4 & Gate 1 Sign-Off
1. The agent frames the **Dual-Runtime Architecture**:
   - **Cloud Run (`cloud_run`):** React/Vite Dispute UI + FastAPI SSE streaming proxy (`/healthz` liveness probe) behind IAP.
   - **Gemini Enterprise Agent Platform (`agent_runtime`):** ADK `OrderDisputeOrchestrator` + `FunctionTool` callables (`lookup_order_status`, `submit_refund_request`, `escalate_dispute`) + Canonical Intent Enum (`ORDER_STATUS_INQUIRY`, `REFUND_REQUEST`, `DISPUTE_ESCALATION`, `OTHERS`) + Model Armor `before_agent_callback`.
2. The agent executes the `architecture-diagram` skill to write `docs/order-dispute-architecture.md` and `docs/order-dispute-architecture.html`.
3. The agent runs `python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase inception` and calls `ask_question` for **Gate 1 Sign-Off** to enter Phase 2.

---

## Phase 2: Execution (The Spec-Driven Development Cycle)

### Step 2.0: Brownfield Baseline Codification
The agent reverse-engineers the existing order database schema and auth middleware, creating `specs/baseline/order-portal-baseline.md`.

### Step 2.1 & 2.2: Feature SDD & Step-by-Step Test Plan Authoring
Using [`specs/templates/sdd-template.md`](../../../../specs/templates/sdd-template.md), the agent creates `specs/features/SPEC-20260930-ORDER-DISPUTE-AGENT.md` containing:
- Sections 1–6: Problem Statement, Dual-Runtime Sequence Diagram, Pydantic/TypeScript Schemas, API Contracts, UI State Machine, and 13-Rule Governance Checklist.
- Section 7: 6-step implementation plan where **every step** specifies deterministic **Unit Tests** (`pytest` / `vitest`), generative **Property-Based Tests** (`hypothesis` / `fast-check`), and **Live Agent Evaluations** (`agents-cli eval`).

### Step 2.3: SDD Review Sub-Gate (`ask_question`)
The agent presents `specs/features/SPEC-20260930-ORDER-DISPUTE-AGENT.md` and requests explicit user sign-off via `ask_question` before writing production code.

### Step 2.4: Step-by-Step Implementation & 4-Step RCA in Action
- **Step 1 (Data Models):** Implemented with 100% passing unit tests and Hypothesis round-trip property tests.
- **Step 2 (ADK Agent & Tools):** During `agents-cli eval run`, tool selection precision scores `91%` (below the $\ge 95\%$ threshold) because queries asking *"Why was I charged twice?"* occasionally trigger `lookup_order_status` instead of `submit_refund_request`.
- **Mandatory 4-Step RCA Triggered:**
  1. **Deep RCA:** The agent inspects the tool docstrings and identifies overlapping scope between `lookup_order_status` and `submit_refund_request` for billing discrepancy inquiries.
  2. **Transparent Explanation:** Explains the exact failing eval trajectory to the developer.
  3. **Architectural Options:** Presents Option A (Refine ADK `FunctionTool` docstrings with explicit *"When to use"* vs. *"When NOT to use"* billing rules) and Option B (Introduce a dedicated `BILLING_DISCREPANCY` intent in the Canonical Intent Enum).
  4. **User Decision via `ask_question`:** Developer selects Option A. The agent updates the tool docstring and SDD contract; re-running `agents-cli eval run` achieves **98.5% precision** and **1.000 groundedness**.
- **Steps 3 & 4 (Cloud Run Streaming Proxy + `/healthz` & React UI):** Implemented with all unit and `fast-check` property tests passing.

### Step 2.5 & Gate 2 Sign-Off
The agent synchronizes `specs/features/SPEC-20260930-ORDER-DISPUTE-AGENT.md`, writes `specs/plan/PROGRESS_REPORT_20260930.md`, runs `validate_sdlc_gate.py --phase execution`, and obtains **Gate 2 Sign-Off** via `ask_question`.

---

## Phase 3: Operation (Integrate Code into Repository & Deploy)

### Step 3.0 & 3.1: Pre-Merge Quality, CodeMender SAST & `.env` Gate
1. The agent asks via `ask_question` to confirm deploying to **Non-Prod (`main` branch)** first.
2. Runs static analysis (`ruff`, `mypy`, `tsc --noEmit`).
3. Orchestrates the [`codemender`](../../codemender/SKILL.md) skill:
   - `cm find` $\rightarrow$ generates `docs/codemender-01-vulnerability-scan-report.md` (0 Critical/High findings).
   - Generates `docs/codemender-security-audit-summary.md`.
4. Validates unified `.env` and `.env.example` (`Shared`, `NONPROD_*`, and `PROD_*` blocks).

### Step 3.2 & 3.3: Git Integration & Dual-Runtime Deployment
1. Commits all code, tests, `specs/`, and `docs/` to `main` with a clean working tree.
2. Deploys the ADK agent to Gemini Enterprise Agent Platform:
   ```bash
   agents-cli deploy --deployment-target agent_runtime --region us-central1
   ```
3. Triggers Google Cloud Build (`cloudbuild.yaml`) and provisions the `order-dispute-nonprod` Infrastructure Manager Terraform deployment on Google Cloud Run.

### Step 3.4: Post-Deployment Verification & Closure
1. **Smoke Test:** Verifies `GET https://<cloud-run-url>/healthz` returns `200 OK` and streaming proxy connects to `agent_runtime`.
2. **Live Agent Eval:** Executes `agents-cli eval run` against the deployed Non-Prod environment ($\ge 95\%$ precision, $1.000$ groundedness, $100\%$ Model Armor block rate).
3. **Final Plan Sync:** Updates `specs/plan/PROGRESS_REPORT_20260930.md` with deployment revision IDs and live verification metrics.
