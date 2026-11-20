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
Because several functional, WAF, and SAIF 2.0 factors are unspecified, the agent pauses and invokes `ask_question`:
1. **Scope, Externalized HITL & Refund Policy Caps (SAIF 2.0 `RAC`):** What is the deterministic maximum per-transaction refund cap enforced by the external policy gateway (paired with signed Human-in-the-Loop confirmation) vs. routing directly to a Tier-2 dispute specialist queue?
2. **Systems of Record & Data Classification:** Which database stores order and refund records (e.g., Cloud SQL PostgreSQL vs. Spanner), and does it hold PII/PCI data requiring **VPC Service Controls (`VPC-SC`) + Cloud KMS (`CMEK`)**?
3. **WAF Zero-Trust IAM & Ingress Pattern (Rule 10 — Zero `allUsers`):**
   - `(Recommended for Regulated PCI/Dispute Prod) Pattern 1A: Identity-Aware Proxy (IAP) behind External Application Load Balancer + Cloud Armor WAF + Serverless NEG`
   - `Pattern 1B: Direct Cloud Run IAP (--iap, No Load Balancer — for internal single-region / Non-Prod cost-optimized workloads)`
   - `Pattern 2: App-Level OAuth 2.0 / OIDC behind External ALB + Cloud Armor WAF with invoker-iam-disabled="true"`
   - *(Note: Pattern 3 Direct Unauthenticated Ingress is strictly prohibited for AI/dispute endpoints and restricted solely to anonymous non-sensitive static pages.)*
4. **Companion Inception Deliverables:** Would you like to generate a WAF & SAIF Architecture Review (`docs/waf-saif-review_order_dispute.md`), a visual architecture diagram (`docs/order-dispute-architecture.md` & `.html`), and/or a live GCP cost estimate (`docs/gcp_cost_estimate_order_dispute.md`) before moving to Phase 2?

**Developer Response:**
- Deterministic policy cap of $100 per refund with mandatory signed user/agent HITL confirmation before execution; disputes above $100 route to the Tier-2 specialist queue.
- Cloud SQL PostgreSQL is the system of record inside a **VPC-SC** perimeter encrypted with **CMEK**.
- Selects **Pattern 1A (ALB + Cloud Armor + IAP)** for PCI/dispute production *(with Pattern 1B Direct Cloud Run IAP optional for Non-Prod)*.
- Selects generating the WAF/SAIF review and architecture diagram in `docs/`.

### Step 1.4 & Gate 1 Sign-Off
1. The agent frames the **WAF & SAIF 2.0 Dual-Runtime Architecture**:
   - **Cloud Run (`cloud_run`):** React/Vite Dispute UI + FastAPI SSE streaming proxy (`/healthz` liveness probe, `99.9%` SLO) behind External ALB + Cloud Armor + IAP.
   - **Gemini Enterprise Agent Platform (`agent_runtime`):** ADK `OrderDisputeOrchestrator` (pinned `gemini-2.5-flash-001`, bounded `max_llm_calls`) + Read-Only vs. Action Subagent split + `FunctionTool` callables (`lookup_order_status`, `submit_refund_request` with `User Auth` OAuth2 propagation & externalized deterministic HITL gate, `escalate_dispute`) + Canonical Intent Enum (`ORDER_STATUS_INQUIRY`, `REFUND_REQUEST`, `DISPUTE_ESCALATION`, `OTHERS`) + **4-Point Model Armor & Cloud DLP callbacks** (`before_agent_callback`, `before_model_callback`, `after_tool_callback`, `after_model_callback`).
2. The agent executes [`gcp-well-architected-saif`](../../gcp_well_architected_saif/SKILL.md) to write `docs/waf-saif-review_order_dispute.md` and [`architecture-diagram`](../../architecture_diagram/SKILL.md) to write `docs/order-dispute-architecture.md` and `docs/order-dispute-architecture.html`.
3. The agent runs `python3 _agents/skills/ai_sdlc/scripts/validate_sdlc_gate.py --phase inception` and calls `ask_question` for **Gate 1 Sign-Off** to enter Phase 2.

---

## Phase 2: Execution (The Spec-Driven Development Cycle)

### Step 2.0: Brownfield Baseline Codification
The agent reverse-engineers the existing order database schema and auth middleware, creating `specs/baseline/order-portal-baseline.md` and locking in Characterization Unit Tests + Property-Based Tests.

### Step 2.1 & 2.2: Feature SDD & Step-by-Step Test Plan Authoring
Using [`specs/templates/sdd-template.md`](./specs/templates/sdd-template.md) (`Workload Type: Hybrid`), the agent creates `specs/features/SPEC-20260930-ORDER-DISPUTE-AGENT.md` containing:
- **Document Control & Sections 1–8:** Executive Summary & Autonomy/HITL Scope (§1), Dual-Runtime Sequence Diagram, WAF 6-Pillar & Data/API/`FunctionTool` Contracts (§2), Zero-Trust Security, Rules 1–13 & SAIF 15-Risk Matrix (§3), Resiliency & Graceful Degradation (§4), Observability & AgentOps (§5), Latency, FinOps & `CFE %` Token Economics (§6), Cross-Pillar ADRs (§7), and FMEA (§8).
- **Sections 9–10:** 6-step implementation plan (§9) where **every step** specifies deterministic **Unit Tests** (`pytest` / `vitest`), generative **Property-Based Tests** (`hypothesis` / `fast-check`), and **DLP-Safe Live Agent Evaluations** (`agents-cli eval`), plus Plan Progress Tracking (§10).

### Step 2.3: SDD Review Sub-Gate (`ask_question`)
The agent presents `specs/features/SPEC-20260930-ORDER-DISPUTE-AGENT.md` and requests explicit user sign-off via `ask_question` before writing production code.

### Step 2.4: Step-by-Step Implementation & 4-Step RCA in Action
- **Step 1 (Data Models):** Implemented with 100% passing unit tests and Hypothesis round-trip property tests.
- **Step 2 (ADK Agent, 4-Point Guardrails & Tools):** During DLP-safe Non-Prod `agents-cli eval run`, tool selection precision scores `91%` (below the $\ge 95\%$ threshold) because queries asking *"Why was I charged twice?"* occasionally trigger `lookup_order_status` instead of `submit_refund_request`.
- **Mandatory 4-Step RCA Triggered (Rule 13):**
  1. **Deep RCA:** The agent inspects the tool docstrings and identifies overlapping scope between `lookup_order_status` and `submit_refund_request` for billing discrepancy inquiries.
  2. **Transparent Explanation:** Explains the exact failing eval trajectory to the developer.
  3. **Architectural Options:** Presents Option A (Refine ADK `FunctionTool` docstrings with explicit *"When to use"* vs. *"When NOT to use"* billing rules) and Option B (Introduce a dedicated `BILLING_DISCREPANCY` intent in the Canonical Intent Enum).
  4. **User Decision via `ask_question`:** Developer selects Option A. The agent updates the tool docstring and SDD contract; re-running DLP-safe `agents-cli eval run` achieves **98.5% precision**, **1.000 groundedness**, and **100% 4-point SAIF adversarial block rate**.
- **Steps 3 & 4 (Cloud Run Streaming Proxy + `/healthz` & React UI):** Implemented with all unit and `fast-check` property tests passing (including WAF graceful degradation and HITL confirmation state transitions).

### Step 2.5 & Gate 2 Sign-Off
The agent synchronizes `specs/features/SPEC-20260930-ORDER-DISPUTE-AGENT.md`, writes `specs/plan/PROGRESS_REPORT_20260930.md`, runs `validate_sdlc_gate.py --phase execution` (which also chains `validate_waf_saif.py`), and obtains **Gate 2 Sign-Off** via `ask_question`.

---

## Phase 3: Operation (Integrate Code into Repository & Deploy)

### Step 3.0 & 3.1: Pre-Merge Quality, CodeMender SAST, Supply Chain & `.env` Gate
1. The agent asks via `ask_question` to confirm deploying to **Non-Prod (`main` branch)** first.
2. Runs static analysis (`ruff`, `mypy`, `tsc --noEmit`) and dependency vulnerability audits (`pip-audit`, `npm audit`).
3. Orchestrates the [`codemender`](../../codemender/SKILL.md) skill:
   - `cm find` $\rightarrow$ generates `docs/codemender-01-vulnerability-scan-report.md` (0 Critical/High findings across code & SAIF risks).
   - Generates `docs/codemender-security-audit-summary.md`.
4. Validates unified `.env` and `.env.example` (`Shared`, `NONPROD_*`, and `PROD_*` blocks backed by Secret Manager + CMEK).

### Step 3.2 & 3.3: Git Integration & Dual-Runtime Deployment (Inside VPC-SC + CMEK)
1. Commits all code, tests, `specs/`, and `docs/` to `main` with a clean working tree.
2. Deploys the ADK agent to Gemini Enterprise Agent Platform inside the VPC-SC + CMEK perimeter:
   ```bash
   agents-cli deploy --deployment-target agent_runtime --region us-central1
   ```
3. Triggers Google Cloud Build (`cloudbuild.yaml` with SLSA Level 3 provenance + Binary Authorization attestation) and provisions the `order-dispute-nonprod` Infrastructure Manager Terraform deployment on Google Cloud Run.

### Step 3.4: Post-Deployment Verification & Closure
1. **Smoke Test & SLO Check:** Verifies `GET https://<cloud-run-url>/healthz` returns `200 OK`, Cloud Armor + IAP enforce Zero-Trust auth, SLO burn-rate alerts are active, and streaming proxy connects to `agent_runtime`.
2. **DLP-Safe Live Agent Eval:** Executes `agents-cli eval run` against the isolated, de-identified Non-Prod environment ($\ge 95\%$ precision, $1.000$ groundedness, $100\%$ 4-point Model Armor/DLP block rate & HITL confirmation enforcement).
3. **Final Plan Sync:** Updates `specs/plan/PROGRESS_REPORT_20260930.md` with deployment revision IDs and live verification metrics, and runs `validate_sdlc_gate.py --phase operation`.
