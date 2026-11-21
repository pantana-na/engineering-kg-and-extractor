# Workload Parameter Elicitation Guide & Zero-Assumption Protocol

## Core Mandate: Zero Unilateral Assumptions
When estimating Google Cloud infrastructure costs:
**THE AGENT MUST NOT MAKE ITS OWN ASSUMPTIONS, INVENT WORKLOAD PARAMETERS, OR ADOPT SILENT DEFAULTS.**

Every single variable that influences the Bill of Materials (BoM) calculation must be explicitly elicited from the user, derived directly from verified codebase/IaC configurations, or confirmed through interactive clarification. The agent must ask **all required questions (no matter how many questions are required)** to achieve a thorough, detailed, and accurate cost calculation.

---

## 1. Comprehensive Parameter Elicitation Checklist

The agent must cross-reference every discovered architecture component against this questionnaire and ask the user for all missing values:

### 1.1 General, Multi-Environment (`NONPROD` vs `PROD`), Sustainability & Brownfield Fundamentals
- [ ] **Deployment Region & Sustainability (`CFE %` — WAF Pillar 6)**: In which Google Cloud region(s) (`GCP_REGION` / `GENAI_LOCATION`) will this workload run (e.g., `us-central1`, `europe-west1`, `asia-southeast1`), and what are your data residency vs. Carbon-Free Energy (`CFE %`) requirements?
- [ ] **Multi-Environment Scope (`NONPROD_*` vs `PROD_*`)**: Should we model both Non-Prod (`main`/`develop` branch) and Production (`prod` branch) environments per the unified `.env` configuration?
- [ ] **Operational Schedule**: Will resources run 24/7 continuously in Prod (730 hours/month with `PROD_MIN_INSTANCES>=1`) while scaling to zero (`NONPROD_MIN_INSTANCES=0`) or running business hours (~220 hours/month) in Non-Prod?
- [ ] **High Availability / Disaster Recovery**: What are the multi-zone or multi-region redundancy, RTO, and RPO requirements?
- [ ] **Brownfield TCO Comparison (if applicable)**: Are we comparing against an existing "As-Is" legacy system (e.g., Windows Server / `.NET Framework` VMs, SQL Server licenses) to calculate modernization ROI?

---

### 1.2 Compute & Containers (Cloud Run `cloud_run`, GKE, Compute Engine)
- [ ] **Request Volume**: What is the anticipated monthly request count or average/peak queries per second (RPS) in Prod and Non-Prod?
- [ ] **Execution & Streaming Profile**: What is the expected average execution time / response latency per request (including SSE/WebSocket streaming proxy hold durations to `agent_runtime`)?
- [ ] **Concurrency**: For Cloud Run, how many concurrent requests/streams should a single container instance handle?
- [ ] **Instance Scaling**: What are the required minimum instances (`NONPROD_MIN_INSTANCES`, `PROD_MIN_INSTANCES`) and maximum instances (`NONPROD_MAX_INSTANCES`, `PROD_MAX_INSTANCES`)?
- [ ] **Hardware Sizing**: What are the allocated vCPU and RAM requirements per container or VM for Frontend UI and Streaming Proxy services?
- [ ] **For GKE / Compute Engine**: What machine family is required (e.g., `e2-standard-4`, `n2-standard-8`, `c3-standard-4`)? Are Spot/Preemptible VMs acceptable for non-critical workloads?
- [ ] **Boot & Persistent Disks**: What disk capacity (GB) and type (`pd-standard`, `pd-balanced`, `pd-ssd`) are attached per instance?

---

### 1.3 Databases & Caching (Cloud SQL, Cloud Spanner, Firestore, Memorystore)
- [ ] **Database Engine & Version**: PostgreSQL, MySQL, SQL Server, AlloyDB, or Cloud Spanner?
- [ ] **Instance Sizing**: How many dedicated vCPUs and GB of RAM are required for Non-Prod vs Prod database instances?
- [ ] **High Availability (HA)**: Is Regional High Availability (standby failover instance in a second zone) required for production?
- [ ] **Read Replicas**: How many read replicas are needed to handle query load?
- [ ] **Storage Sizing**: What is the initial provisioned database storage size (GB), and what is the expected monthly growth rate?
- [ ] **Storage Media**: SSD Persistent Disk or Standard HDD?
- [ ] **Backup Policy**: How many days/months of automated backups and point-in-time recovery logs must be retained?
- [ ] **For Cloud Spanner**: How many Processing Units (PUs) or Nodes are required to meet latency SLAs?
- [ ] **For In-Memory Cache (Redis/Memcached)**: What cache capacity (GB) is required? Basic (single-node) or Standard (HA multi-zone)?

---

### 1.4 Object Storage (Cloud Storage)
- [ ] **Storage Class**: Standard (hot/active), Nearline (30-day retention), Coldline (90-day retention), or Archive (365-day)?
- [ ] **Data Volume**: What is the total stored asset volume (GB or TB)?
- [ ] **Monthly Ingestion**: How much new data is uploaded or ingested per month (GB/month)?
- [ ] **Operations Count**:
  - Class A Operations (Uploads, inserts, list, rewrite): How many monthly operations?
  - Class B Operations (Downloads, gets, metadata reads): How many monthly operations?
- [ ] **Lifecycle Policies**: Will older files automatically transition to lower storage classes after a specific retention window?

---

### 1.5 Analytics & Event Streaming (BigQuery, Pub/Sub, Datastream)
- [ ] **BigQuery Billing Model**: On-Demand (pay-per-TB scanned) or Editions (dedicated/autoscaled slot commitments)?
- [ ] **Data Scanned per Month**: For on-demand, how many TB of data will queries scan each month?
- [ ] **Active vs. Long-Term Table Storage**: How much data is stored in active tables (<90 days old) vs long-term storage (>90 days untouched)?
- [ ] **Cloud Pub/Sub Message Throughput**: What is the total volume of messages published and delivered per month (GB or TB)?
- [ ] **Message Retention**: Are messages retained beyond the default 7-day retention window?
- [ ] **Datastream (CDC)**: How many GB of change data capture records will be ingested and processed monthly?

---

### 1.6 Generative AI, Google ADK (`agent_runtime`), SAIF 2.0 Guardrails & Live Evaluation
- [ ] **Target Pinned Foundation Model(s)**: Which pinned model(s) will be deployed for the ADK `OrchestratorAgent` and domain subagents (e.g., `gemini-2.5-flash-001` for routing/extraction vs. `gemini-2.5-pro-001` for complex multi-hop reasoning), and will **Provisioned Throughput (GSUs) + PayGo spillover** be used?
- [ ] **Inference Turn Volume**: How many user conversation turns are expected per day or month?
- [ ] **Agentic Multi-Hop Multiplier**: On average, how many LLM reasoning calls + `FunctionTool` invocations occur per user turn (e.g., 1 Orchestrator intent classification + 1–2 Subagent/Tool hops)?
- [ ] **Input Prompt Length**: What is the average input context length per hop (in tokens), including system prompts, `FunctionTool` declarations, chat history, and retrieved tool outputs?
- [ ] **Output Generation Length**: What is the average generated output length per hop (in tokens)?
- [ ] **SAIF 2.0 4-Point Guardrails (Model Armor + Cloud DLP)**: What volume of tokens/bytes passes through **Google Cloud Model Armor** (`before_agent`, `before_model`, `after_tool`, `after_model`) and **Sensitive Data Protection (Cloud DLP)** bidirectional tokenization/scrubbing?
- [ ] **Continuous DLP-Safe Live Evaluation (`agents-cli eval`)**: How many golden test cases are in `evals/`, and how many `agents-cli eval run` executions (or Vertex AI Batch API offline evals) occur per month across Non-Prod and Prod gates?
- [ ] **Multimodal Modalities & Context Caching**: Are image, audio, or video inputs processed? Will **Vertex AI Context Caching** be enabled for repeated system instructions and tool schemas?
- [ ] **Vector Search / Vertex AI Search**: What index dimension (e.g., 768) and how many deployed endpoint replicas or search queries/GB indexed are needed?

---

### 1.7 Networking, WAF Zero-Trust Ingress Pattern (Rule 10), Crypto & DevSecOps Toolchain
- [ ] **WAF Zero-Trust IAM & Ingress Pattern (Rule 10 — Zero `allUsers`)**:
  - **Pattern 1A (Default for Tier-1 / Regulated / External)**: Identity-Aware Proxy (IAP) behind Global External HTTPS Application Load Balancer + **Cloud Armor** WAF/DDoS + Serverless NEG (How many forwarding rules, Cloud Armor policies/requests, and GB processed?)
  - **Pattern 1B (Internal Workforce / Single-Region / Cost-Optimized)**: Direct Cloud Run IAP (`--iap`, No Load Balancer — `$0` fixed ALB & Cloud Armor baseline; confirm single-region & ADR trade-off)
  - **Pattern 2**: App-Level OAuth 2.0 / OIDC behind External ALB + **Cloud Armor** (or direct ingress where approved) with `invoker-iam-disabled="true"`
  - **Pattern 3**: Direct Unauthenticated Ingress (`invoker-iam-disabled="true"`) — *strictly restricted to approved anonymous public non-sensitive static/marketing pages (prohibited for internal or AI workloads)*
- [ ] **Internet Egress & Perimeter**: How many GB or TB of outbound data transfer to the public internet (Premium vs Standard Tier) and Private Service Connect (PSC) endpoints inside **VPC-SC** are expected per month?
- [ ] **Cloud NAT, Cloud Armor & Cloud KMS (`CMEK`)**: How many Cloud NAT gateways, Cloud Armor security policies/rules, active **Cloud KMS (`CMEK` / HSM / EKM)** key versions, and monthly cryptographic operations?
- [ ] **DevSecOps CI/CD & Observability**: How many monthly Google Cloud Build minutes, container images stored/scanned in Artifact Registry (Artifact Analysis + Binary Authorization), active secret versions in Secret Manager, and GB of Cloud Logging/Monitoring/Trace telemetry?

---

## 2. Guided Collaborative Resolution (When the User Is Uncertain)

If the user does not possess an exact low-level parameter (e.g., *"I'm not sure what my average prompt token count will be"* or *"I don't know the exact database IOPS"*):

1. **NEVER make a silent assumption.**
2. **Explain the options clearly:** Provide 2–3 concrete, realistic options based on their use case.
   - *Example prompt:*
     > *"For your conversational RAG agent, token costs depend heavily on the context injected. Which of these typical patterns matches your design?*
     > *1. Short / Targeted Q&A: ~800 input tokens, ~300 output tokens per query.*
     > *2. Comprehensive RAG Retrieval: ~3,500 input tokens (including 3 retrieved document chunks), ~800 output tokens per query.*
     > *3. Long-Document Analysis: ~20,000+ input tokens per query.*
     > *Please indicate which profile you'd like us to calculate, or specify custom numbers."*
3. **Await explicit user confirmation** before incorporating the chosen parameter into the Bill of Materials.
