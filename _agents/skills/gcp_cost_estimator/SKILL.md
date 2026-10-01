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

Categorize every discovered component across our **Dual-Runtime Architecture** (`agent_runtime` + `cloud_run`) and supporting GCP service domains:
- **Conversational AI & Gemini Enterprise Agent Platform (`agent_runtime`)**:
  - **Multi-Hop Agent Trajectory Tokens**: Root `OrchestratorAgent` intent classification + Domain Subagent dispatch + `FunctionTool` schema/response payload tokens per user turn.
  - **Google Cloud Model Armor**: Pre-flight prompt & post-model response security screening invocations (`before_agent_callback` / `before_model_callback`).
  - **Continuous Live Agent Evaluation (`agents-cli eval`)**: Monthly evaluation dataset execution token volume across CI/CD and pre-release runs.
  - **Vertex AI Vector Search & Embeddings**: Text embedding generation + Vector Search index endpoint replicas.
- **Web Frontend, API Gateway & Streaming Proxies (`cloud_run`)**:
  - **Cloud Run Services (`NONPROD` & `PROD`)**: Separate profiles for Non-Prod (`NONPROD_MIN_INSTANCES=0`, scale-to-zero) and Prod (`PROD_MIN_INSTANCES>=1`, warm instances, vCPU, RAM, SSE/WebSocket streaming concurrency).
  - **GKE / Compute Engine (if applicable or in Brownfield "As-Is")**: Node machine types, persistent disks, licensing (e.g., Windows Server / SQL Server for legacy `.NET` workloads).
- **Databases & Caching**: Cloud SQL (PostgreSQL/MySQL/SQL Server engine, vCPU/RAM, HA multi-zone, storage, backups), Cloud Spanner (PUs/nodes), Firestore, Memorystore for Redis.
- **Storage**: Cloud Storage buckets (Standard, Nearline, Coldline, Archive), Persistent Disks (`pd-balanced`, `pd-ssd`, `hyperdisk`).
- **Analytics & Event Streaming**: BigQuery (on-demand vs capacity slots), Pub/Sub, Datastream, Dataflow.
- **Networking, IAM Ingress & DevSecOps Toolchain**:
  - **IAM Ingress Pattern**: Pattern 1 External HTTPS Application Load Balancer + Serverless NEG + IAP (forwarding rules + data processed) vs. Pattern 2/3 Direct Cloud Run Ingress.
  - **DevSecOps & Observability**: Google Cloud Build (build minutes), Artifact Registry (container image storage) + **Artifact Analysis** (automated container vulnerability scanning), Secret Manager (active secret versions + access operations), Cloud Logging & Cloud Monitoring ingestion.

---

## Phase 3: Comprehensive Workload Parameter Elicitation (Ask ALL Required Questions)

Identify every unknown runtime variable that cannot be determined with 100% certainty from static code, `specs/`, or `.env.example`.

> [!IMPORTANT]
> **Do NOT hold back questions to keep things brief.** Ask **all required questions (no matter how many questions are required)** using `ask_question` across each discovered component. Detailed calculations require complete workload parameters.

### Service-by-Service Questionnaire Checklist:

1. **General, Multi-Environment (`NONPROD` vs `PROD`) & Brownfield Baseline:**
   - What is the target deployment Google Cloud region(s) (`GCP_REGION` / `GENAI_LOCATION`)?
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

6. **Generative AI, ADK Agents (`agent_runtime`), Model Armor & Live Evaluation:**
   - Which foundation model(s) are used for the ADK `OrchestratorAgent` and domain subagents (e.g., Gemini 2.5 Pro, Gemini 2.5 Flash)?
   - How many user conversation turns occur per day/month?
   - **Agentic Multi-Hop Multiplier:** On average, how many LLM reasoning calls + `FunctionTool` invocations occur per user turn (e.g., 1 Orchestrator intent classification + 1–2 Subagent/Tool hops)?
   - What is the average input token context length (system instructions + `FunctionTool` declarations + retrieved tool data) and output token length per hop?
   - **Model Armor Guardrails:** Are both input prompts (`before_agent_callback`) and model outputs screened by Google Cloud Model Armor?
   - **Live Agent Evaluation (`agents-cli eval`):** How many test cases are in `evals/datasets/*.jsonl`, and how many `agents-cli eval run` executions occur per month in CI/CD?
   - For Vector Search: What is the embedding dimension, vector count, and deployed endpoint replica count?

7. **Networking, IAM Ingress Pattern & DevSecOps Toolchain:**
   - **IAM Ingress Pattern (Rule 10):** Which pattern is selected?
     - *Pattern 1 (IAP + External HTTPS Load Balancer + Serverless NEG)* $\rightarrow$ How many forwarding rules and GB processed?
     - *Pattern 2 (App-Level OAuth 2.0)* or *Pattern 3 (Direct Ingress `invoker-iam-disabled`)* $\rightarrow$ Zero Load Balancer base fee.
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
For services with specialized rates, model token pricing, or emerging features (e.g. Vertex AI Gemini model token pricing, Model Armor, Artifact Analysis):
- Query official Google Cloud pricing web pages in real time via `search_web` or `read_url_content`:
  - Vertex AI Gemini & Agent pricing: `https://cloud.google.com/vertex-ai/generative-ai/pricing`
  - Model Armor pricing: `https://cloud.google.com/security-command-center/pricing`
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
1. **Executive Summary Table (Non-Prod + Prod + Total)**: Monthly & Annual Run-Rates broken down by **Non-Prod (`NONPROD_*`)** and **Prod (`PROD_*`)** for On-Demand, 1-Year CUD (~28% discount), and 3-Year CUD (~52% discount), plus **Brownfield TCO Comparison** (if modernizing a legacy system).
2. **Visual Cost Distribution**: Mermaid pie chart and percentage breakdown across `agent_runtime` (Gemini/ADK/Model Armor/Evals), `cloud_run` (UI/Streaming Proxy), Databases, Storage, Networking/IAP, and DevSecOps CI/CD.
3. **Itemized Bill of Materials (BoM)**: Environment (`NONPROD`/`PROD`), Service name, SKU, sizing, monthly quantity, live unit rate, rate source (API SKU ID or live URL), monthly cost, and rationale.
4. **Confirmed Workload Parameters**: Exhaustive list of all parameters explicitly confirmed with the user (zero unverified assumptions).
5. **Sensitivity & Scale Analysis**: Cost progression at 0.5×, 1.0×, 2.0×, and 5.0× traffic.
6. **FinOps & Dual-Runtime Optimization Recommendations**: Actionable architectural recommendations (Gemini context caching, `NONPROD_MIN_INSTANCES=0` scale-to-zero, Cloud Run streaming concurrency tuning, CUD commitments, GCS lifecycle rules).

---

## Examples

To inspect a complete end-to-end example walkthrough:
[sample_cost_analysis.md](./examples/sample_cost_analysis.md)
