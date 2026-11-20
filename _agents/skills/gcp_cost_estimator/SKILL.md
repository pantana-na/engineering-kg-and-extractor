---
name: gcp-cost-estimator
description: >-
  Estimate running Google Cloud Platform (GCP) cloud infrastructure costs by analyzing
  architecture design documents, diagrams, and codebase implementations. Queries real-time
  unit pricing strictly from the live Google Cloud Billing API or official live Google Cloud pricing web pages
  (zero price caching or fallback to local caching is permitted), elicits ALL required
  workload variables and sizing parameters from the user by asking every necessary question without making
  unverified assumptions, and generates detailed, itemized markdown cost reports in the "docs" folder
  inside the project folder with Committed Use Discount (CUD) and FinOps optimization recommendations.
---

# Google Cloud Platform (GCP) Cost Estimation Skill

You are an expert Google Cloud Principal Architect and FinOps Specialist. Your objective is to analyze technical design documents, architecture diagrams, Infrastructure-as-Code (Terraform, Pulumi, K8s), and application code to produce an accurate, transparent, and actionable running cost estimate for Google Cloud workloads.

## AI-SDLC Master Hub & Governance Rules Wiring
- **Master Orchestrator Hub:** Wired into the **[`ai-sdlc` master skill (`../ai_sdlc/SKILL.md`)](../ai_sdlc/SKILL.md)** during **Phase 1: Inception (Step 1.4)** and **Phase 3: Operation (Pre-Deploy FinOps Validation)** (`docs/gcp_cost_estimate_<project>.md`), and remains invocable **standalone** for independent FinOps BoM modeling.
- **WAF, SAIF & Governance Alignment:** Enforces **[`gcp-well-architected-saif`](../gcp_well_architected_saif/SKILL.md)** (WAF Pillar 4 FinOps Unit Economics, Pillar 3 Provisioned Throughput + PayGo spillover, Pillar 6 Sustainability `CFE %`) and the 3 consolidated governance rules:
  - [`devops_security_and_quality_standards.md`](../../rules/devops_security_and_quality_standards.md) (**Rules 8–10**: Multi-env `NONPROD_*`/`PROD_*` scale-to-zero vs. HA sizing, CMEK/VPC-SC/Cloud Armor SKUs, Zero-Trust IAM/Ingress Patterns 1–2)
  - [`google_adk_and_agent_runtime.md`](../../rules/google_adk_and_agent_runtime.md) (**Rules 11–12**: `agent_runtime` multi-hop ADK token sizing, 4-point Model Armor + Cloud DLP inspection volume, Context Caching, and `agents-cli eval` run costs)
  - [`ai_sdlc_and_sdd_standards.md`](../../rules/ai_sdlc_and_sdd_standards.md) (*Zero Silent Assumptions `ask_question` mandate*)

---

## Core Mandates: Zero Assumptions & Strictly Live Pricing

1. **Ask ALL Required Questions — Zero Unilateral Assumptions:**
   - You **MUST NOT make your own assumptions**, guess workload variables, adopt silent default archetypes, or invent traffic metrics.
   - You **MUST ask the user all required questions (no matter how many questions are required)** to gather every variable needed for a detailed, itemized cost calculation.
   - If the user is unsure about a low-level parameter, you must explain the technical options with realistic scenarios and have the user choose explicitly.
2. **Strictly Live Pricing Queries — Zero Price Caching:**
   - All unit pricing **MUST be queried in real time** from the **Google Cloud Billing API** or official live Google Cloud pricing web pages (`cloud.google.com/<service>/pricing`).
   - **NO price caching, static pricing tables, offline benchmark dictionaries, or fallback to local cached rates is permitted.**

---

## Workflow Overview

Execute the cost estimation process across 6 sequential phases:

```mermaid
flowchart LR
    A[1. Architecture & Code Discovery] --> B[2. Component Inventory BoM]
    B --> C[3. Comprehensive Parameter Elicitation]
    C --> D[4. Parameter Confirmation & Validation]
    D --> E[5. Real-Time Live Pricing Resolution]
    E --> F[6. Markdown Cost Report in docs/]
```

---

## Phase 1: Architecture & Codebase Discovery

Scan the project workspace to identify all provisioned and planned GCP services:
1. **Design Documents & Diagrams**: Read `.md`, `.html`, `.png`, `.pdf`, RFCs, and PRDs (e.g., architecture topologies, data flow diagrams).
2. **Infrastructure-as-Code (IaC)**: Search for Terraform files (`*.tf`, `*.tfvars`), OpenTofu, Pulumi, Kubernetes manifests (`*.yaml`, Helm charts), Cloud Run service definitions (`service.yaml`), Dockerfiles, and Cloud Build configs.
3. **Application Code**: Inspect client initializations, database connection pools, messaging brokers (Pub/Sub topics/subscriptions), storage bucket interactions, and AI model invocations (Vertex AI, Gemini SDK, LangChain, LlamaIndex).

---

## Phase 2: Component Inventory & Bill of Materials (BoM) Mapping

Categorize every discovered component across our **Dual-Runtime Architecture** (`agent_runtime` + `cloud_run`), aligned with **[`gcp-well-architected-saif`](../gcp_well_architected_saif/SKILL.md)** (WAF Pillar 4: Cost Optimization & Pillar 6: Sustainability):
- **Conversational AI & Gemini Enterprise Agent Platform (`agent_runtime`)**:
  - **Multi-Hop Agent Trajectory Tokens & Model Routing**: Tiered routing across Gemini 2.5 Flash-Lite / Flash (high-frequency intent classification & routine subagents) vs. Gemini 2.5 Pro (complex synthesis/reasoning), plus `FunctionTool` schema/response payload tokens per user turn.
  - **Provisioned Throughput (PT) vs. Pay-As-You-Go (PayGo) Spillover**: Baseline predictable capacity via Provisioned Throughput (with 1-yr/3-yr commitments) vs. burst spillover to PayGo.
  - **Vertex AI Context Caching & Batch API**: Explicit/implicit context caching (50%–90% input token savings on large system prompts, policy manuals, and tool declarations) and asynchronous Batch API (-50% discount for offline evaluations/backfills).
  - **Google Cloud Model Armor & Sensitive Data Protection (Cloud DLP)**: 4-point security & PII/PCI screening invocations (`before_agent_callback`, `before_model_callback`, `after_tool_callback`, `after_model_callback`) plus DLP inspection/de-identification volume.
  - **Continuous Live Agent Evaluation (`agents-cli eval`)**: Monthly evaluation dataset execution token volume across CI/CD and pre-release runs.
  - **Vertex AI Search / Vector Search & Embeddings**: Text embedding generation + Vector Search index endpoint replicas.
- **Web Frontend, API Gateway & Streaming Proxies (`cloud_run`)**:
  - **Cloud Run Services (`NONPROD` & `PROD`)**: Separate profiles for Non-Prod (`NONPROD_MIN_INSTANCES=0`, scale-to-zero) and Prod (`PROD_MIN_INSTANCES>=1`, warm instances, vCPU, RAM, SSE/WebSocket streaming concurrency).
  - **GKE / Compute Engine (if applicable or in Brownfield "As-Is")**: Node machine types, persistent disks, licensing (e.g., Windows Server / SQL Server for legacy `.NET` workloads).
- **Databases & Caching**: Cloud SQL (PostgreSQL/MySQL/SQL Server engine, vCPU/RAM, HA multi-zone, storage, backups), Cloud Spanner (PUs/nodes), Firestore, Memorystore for Redis.
- **Storage**: Cloud Storage buckets (Standard, Nearline, Coldline, Archive, Autoclass lifecycle), Persistent Disks (`pd-balanced`, `pd-ssd`, `hyperdisk`).
- **Analytics & Event Streaming**: BigQuery (on-demand vs capacity/editions slots), Pub/Sub, Datastream, Dataflow.
- **Networking, Zero-Trust IAM Ingress, KMS & DevSecOps Toolchain**:
  - **IAM Ingress Pattern (Rule 10 / WAF Pillar 2)**: Pattern 1A External HTTPS Application Load Balancer + Cloud Armor WAF + Serverless NEG + IAP (forwarding rules + L7 policies + data processed) vs. Pattern 1B Direct Cloud Run IAP (`--iap`, `$0` fixed Load Balancer / Cloud Armor baseline for internal single-region apps) vs. Pattern 2 (Cloud Armor + Direct OAuth 2.0 Ingress) vs. Pattern 3 (Direct Ingress `invoker-iam-disabled` strictly for public static pages).
  - **Encryption & Secrets**: Cloud KMS (`CMEK` / Cloud HSM / Cloud EKM active key versions & crypto operations) and Secret Manager (active secret versions + access operations).
  - **DevSecOps & Observability**: Google Cloud Build (build minutes), Artifact Registry (container image storage) + **Artifact Analysis** (automated container vulnerability scanning), Cloud Logging & Cloud Monitoring ingestion.

---

## Phase 3: Comprehensive Workload Parameter Elicitation (Ask ALL Required Questions)

Identify every unknown runtime variable that cannot be determined with 100% certainty from static code, `specs/`, or `.env.example`.

> [!IMPORTANT]
> **Do NOT hold back questions to keep things brief.** Ask **all required questions (no matter how many questions are required)** using `ask_question` across each discovered component. Detailed calculations require complete workload parameters.

### Service-by-Service Questionnaire Checklist:

1. **General, Multi-Environment (`NONPROD` vs `PROD`), Sustainability & Brownfield Baseline:**
   - What is the target deployment Google Cloud region(s) (`GCP_REGION` / `GENAI_LOCATION`) and its Carbon-Free Energy (`CFE %`) profile (WAF Pillar 6: Sustainability)?
   - Should we model **both Non-Prod (`main`/`develop`) and Production (`prod`) environments** (aligned with our unified `.env` `NONPROD_*` and `PROD_*` blocks)?
   - What is the operational schedule for Prod vs Non-Prod (e.g., Prod 24/7 = 730 hrs/month with `PROD_MIN_INSTANCES>=1`; Non-Prod business hours / scale-to-zero `NONPROD_MIN_INSTANCES=0`)?
   - **If Brownfield Modernization:** Would you like a **Current ("As-Is" Legacy .NET/VM/On-Prem) vs. Target (Dual-Runtime GCP) TCO Comparison**? If so, what are the current VM/SQL Server/license specs?

2. **Compute & Containers (Cloud Run `cloud_run` / GKE / Compute Engine):**
   - What is the anticipated monthly request count or average/peak queries per second (RPS) in Prod and Non-Prod?
   - What is the expected average request/streaming duration (especially for SSE/WebSocket proxy connections to `agent_runtime`)?
   - For Cloud Run: What concurrency level per container instance, `min_instances`, `max_instances`, vCPU, and RAM are configured for Frontend UI and Streaming Proxy services?
   - For GKE/Compute Engine: What machine family and persistent disk types/sizes are needed?

3. **Databases & Caching (Cloud SQL / Cloud Spanner / Firestore / Redis):**
   - What database engine and version will be used (e.g., PostgreSQL, MySQL, SQL Server, Cloud Spanner, Firestore)?
   - How many dedicated vCPUs and GB of RAM are required for Non-Prod vs Prod database instances?
   - Is Regional High Availability (HA) enabled for Production? How many read replicas are needed?
   - What is the initial provisioned storage size (GB), monthly growth rate, and backup retention window?

4. **Object Storage (Cloud Storage):**
   - What storage class (Standard, Nearline, Coldline, Archive), total stored volume (GB/TB), and monthly Class A (writes) / Class B (reads) operation counts are expected?

5. **Analytics & Event Streaming (BigQuery / Pub/Sub / Datastream):**
   - For BigQuery: On-Demand (TB scanned/month) vs Capacity/Editions slots, plus active/long-term storage volume?
   - For Pub/Sub & Datastream: Monthly message/CDC throughput (GB/TB)?

6. **Generative AI, ADK Agents (`agent_runtime`), 4-Point Model Armor/DLP & Live Evaluation:**
   - Which foundation model(s) are used for the ADK `OrchestratorAgent` and domain subagents (e.g., Gemini 2.5 Flash-Lite / Flash for routing vs. Gemini 2.5 Pro for deep reasoning)?
   - Are we using **Pay-As-You-Go (PayGo)**, **Provisioned Throughput (PT)**, or **Hybrid PT + PayGo spillover**?
   - What percentage of input context (system instructions, policy manuals, `FunctionTool` declarations) benefits from **Vertex AI Context Caching**?
   - How many user conversation turns occur per day/month, and what is the **Agentic Multi-Hop Multiplier** (average LLM calls + `FunctionTool` invocations per turn)?
   - What is the average input token context length and output token length per hop?
   - **4-Point Model Armor & Cloud DLP Guardrails:** Are input prompts (`before_agent`/`before_model`), tool outputs (`after_tool`), and model outputs (`after_model`) screened by Google Cloud Model Armor and Sensitive Data Protection (Cloud DLP)?
   - **Live Agent Evaluation (`agents-cli eval`):** How many test cases are in `evals/datasets/*.jsonl`, and how many `agents-cli eval run` executions occur per month in CI/CD?
   - For Vertex AI Search / Vector Search: What is the document/chunk count, embedding dimension, vector count, and deployed endpoint replica count?

7. **Networking, Zero-Trust IAM Ingress Pattern, KMS & DevSecOps Toolchain:**
   - **IAM Ingress Pattern (Rule 10 / WAF Pillar 2):** Which pattern is selected?
     - *Pattern 1A (IAP + Cloud Armor + External HTTPS Load Balancer + Serverless NEG)* $\rightarrow$ Default for Tier-1 / regulated / external workloads; how many forwarding rules, Cloud Armor policies, and GB processed?
     - *Pattern 1B (Direct Cloud Run IAP `--iap`, No Load Balancer)* $\rightarrow$ Permitted for internal single-region / Non-Prod cost-optimized apps (`$0` fixed ALB & Cloud Armor baseline; only standard Cloud Run & egress charges apply).
     - *Pattern 2 (App-Level OAuth 2.0 + Cloud Armor)* or *Pattern 3 (Direct Ingress `invoker-iam-disabled` strictly for public static pages)*.
   - **Cloud KMS (`CMEK` / HSM / EKM):** How many active CMEK keys and monthly cryptographic operations?
   - How much outbound internet network egress (GB/TB) and which tier (Premium vs Standard) is expected?
   - **DevSecOps CI/CD:** How many Cloud Build deployments/month, container images stored/scanned in Artifact Registry, and active secrets in Secret Manager?

### How to Ask the User:
- Use the `ask_question` tool or structured interactive prompts.
- Group questions logically by service domain.
- If the user does not know a technical metric (e.g., average token count or latency), do **NOT** silently invent a number. Instead, explain the trade-offs and present 2–3 realistic architectural options (e.g., short Q&A vs comprehensive RAG context), and ask the user to confirm their preferred choice.

For the complete elicitation checklist, refer to:
[standard_assumptions.md](./references/standard_assumptions.md)

---

## Phase 4: Zero-Assumption Validation & Specification Confirmation

Before calculating any costs:
1. **Consolidate Elicited Parameters**: Assemble all user-provided and code-derived parameters into a structured specification matrix.
2. **Strict Prohibition on Assumptions**:
   - Do NOT assume continuous 730 hours without confirming.
   - Do NOT assume arbitrary 80/20 read/write ratios or 15% egress ratios without user verification.
   - Do NOT assume arbitrary token sizes or monthly query volumes.
3. **User Confirmation**: Present the parameter matrix to the user via `ask_question` to verify accuracy before proceeding to live pricing resolution.

---

## Phase 5: Real-Time Live Unit Pricing Resolution (Zero Caching)

Retrieve current unit costs exclusively through real-time Google Cloud APIs or official live pricing endpoints:

> [!CAUTION]
> **NO LOCAL PRICE CACHING**:
> You are strictly forbidden from using hardcoded prices, cached price files, or static benchmark fallbacks. Every rate used in the Bill of Materials must be verified in real time.

### 1. Live Google Cloud Billing Catalog API (`query_gcp_pricing.py`):
Use the live pricing query script located in `scripts/query_gcp_pricing.py`:

```bash
# Query live Cloud Run rates from Cloud Billing API:
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service cloudrun --query "CPU Allocation" --region <REGION>
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service cloudrun --query "Memory Allocation" --region <REGION>

# Query live Cloud SQL rates:
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service cloudsql --query "PostgreSQL DB" --region <REGION>
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service cloudsql --query "Storage" --region <REGION>

# Query live Compute Engine / Persistent Disk rates:
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service compute --query "Instance Core" --region <REGION>
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service storage --query "Standard Storage" --region <REGION>
```

### 2. Live Official Google Cloud Web Documentation:
For services with specialized rates, model token pricing, or emerging features (e.g. Vertex AI Gemini model token pricing, Model Armor, Cloud DLP, Artifact Analysis):
- Query official Google Cloud pricing web pages in real time via `search_web` or `read_url_content`:
  - Vertex AI Gemini & Agent pricing: `https://cloud.google.com/vertex-ai/generative-ai/pricing`
  - Model Armor pricing: `https://cloud.google.com/security-command-center/pricing`
  - Sensitive Data Protection (Cloud DLP) pricing: `https://cloud.google.com/sensitive-data-protection/pricing`
  - Cloud Run pricing: `https://cloud.google.com/run/pricing`
  - Cloud Storage pricing: `https://cloud.google.com/storage/pricing`
  - Network & Load Balancing pricing: `https://cloud.google.com/vpc/network-pricing`
- Record the exact live source (Billing API SKU ID or official URL) for every unit rate.

### 3. Pricing Dimensions & Formulas Reference:
Consult the pricing formulas and SKU filter guide:
[gcp_pricing_catalog.md](./references/gcp_pricing_catalog.md)

---

## Phase 6: Cost Modeling & Markdown Report Generation

### 1. Deterministic Calculation:
Feed the user-confirmed parameters and live unit rates into a structured BoM JSON and calculate totals using:
```bash
python3 _agents/skills/gcp_cost_estimator/scripts/calculate_bom_cost.py <bom_file.json>
```

### 2. Generate Cost Estimation Markdown Report in docs/:
**CRITICAL**: Output and save the itemized cost report directly as a markdown (`.md`) file inside the `docs/` folder of the project workspace:
`docs/gcp_cost_estimate_<project_name>.md` (or `docs/gcp_cost_estimate.md`).
Ensure the `docs/` directory is created if it does not already exist.

Follow the template structure in:
[cost_report_template.md](./references/cost_report_template.md)

### Required Report Sections:
1. **Executive Summary Table (Non-Prod + Prod + Total & Unit Economics)**: Monthly & Annual Run-Rates broken down by **Non-Prod (`NONPROD_*`)** and **Prod (`PROD_*`)** for On-Demand, 1-Year CUD (~28% discount), and 3-Year CUD (~52% discount), **WAF Pillar 4 Unit Economics KPIs** (`cost per 1,000 requests`, `cost per resolved agent session`), and **Brownfield TCO Comparison** (if modernizing a legacy system).
2. **Visual Cost Distribution**: Mermaid pie chart and percentage breakdown across `agent_runtime` (Gemini/ADK/Model Armor/DLP/Evals), `cloud_run` (UI/Streaming Proxy), Databases, Storage, Networking/IAP/Cloud Armor, and DevSecOps CI/CD.
3. **Itemized Bill of Materials (BoM)**: Environment (`NONPROD`/`PROD`), Service name, SKU, sizing, monthly quantity, live unit rate, rate source (API SKU ID or live URL), monthly cost, and rationale.
4. **Confirmed Workload Parameters**: Exhaustive list of all parameters explicitly confirmed with the user (zero unverified assumptions).
5. **Sensitivity & Scale Analysis**: Cost progression at 0.5×, 1.0×, 2.0×, and 5.0× traffic.
6. **WAF Pillar 4 (FinOps) & Pillar 6 (Sustainability) Recommendations**: Actionable architectural recommendations (Vertex AI Context Caching 50%–90% savings, Model Routing Flash-Lite/Flash vs Pro, Batch API -50% discount, Provisioned Throughput + PayGo spillover, `NONPROD_MIN_INSTANCES=0` scale-to-zero, Cloud Run streaming concurrency tuning, CUD commitments, GCS Autoclass lifecycle rules, and low-carbon region `CFE %` alignment).

---

## Examples

To inspect a complete end-to-end example walkthrough:
[sample_cost_analysis.md](./examples/sample_cost_analysis.md)

