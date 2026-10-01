# Workload Parameter Elicitation Guide & Zero-Assumption Protocol

## Core Mandate: Zero Unilateral Assumptions
When estimating Google Cloud infrastructure costs:
**THE AGENT MUST NOT MAKE ITS OWN ASSUMPTIONS, INVENT WORKLOAD PARAMETERS, OR ADOPT SILENT DEFAULTS.**

Every single variable that influences the Bill of Materials (BoM) calculation must be explicitly elicited from the user, derived directly from verified codebase/IaC configurations, or confirmed through interactive clarification. The agent must ask **all required questions (no matter how many questions are required)** to achieve a thorough, detailed, and accurate cost calculation.

---

## 1. Comprehensive Parameter Elicitation Checklist

The agent must cross-reference every discovered architecture component against this questionnaire and ask the user for all missing values:

### 1.1 General & Infrastructure Fundamentals
- [ ] **Deployment Region**: In which Google Cloud region(s) will this workload run? (e.g., `us-central1`, `europe-west1`, `asia-southeast1`).
- [ ] **Operational Schedule**: Will resources run 24/7 continuously (730 hours/month), during business hours only (e.g., ~220 hours/month), or on a batch/scheduled basis?
- [ ] **High Availability / Disaster Recovery**: What are the multi-zone or multi-region redundancy requirements?

---

### 1.2 Compute & Containers (Cloud Run, GKE, Compute Engine)
- [ ] **Request Volume**: What is the anticipated monthly request count or average/peak queries per second (RPS)?
- [ ] **Execution Profile**: What is the expected average execution time / response latency per request (in milliseconds or seconds)?
- [ ] **Concurrency**: For Cloud Run, how many concurrent requests should a single container instance handle?
- [ ] **Instance Scaling**: What are the required minimum instances (`min_instances`) and maximum instances (`max_instances`)?
- [ ] **Hardware Sizing**: What are the allocated vCPU and RAM requirements per container or VM?
- [ ] **For GKE / Compute Engine**: What machine family is required (e.g., `e2-standard-4`, `n2-standard-8`, `c3-standard-4`)? Are Spot/Preemptible VMs acceptable for non-critical workloads?
- [ ] **Boot & Persistent Disks**: What disk capacity (GB) and type (`pd-standard`, `pd-balanced`, `pd-ssd`) are attached per instance?

---

### 1.3 Databases & Caching (Cloud SQL, Cloud Spanner, Firestore, Memorystore)
- [ ] **Database Engine & Version**: PostgreSQL, MySQL, SQL Server, or Cloud Spanner?
- [ ] **Instance Sizing**: How many dedicated vCPUs and GB of RAM are required for the primary database?
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

### 1.6 Generative AI & Vertex AI
- [ ] **Target Foundation Model**: Which exact model(s) will be deployed? (e.g., Gemini 3.7 Flash, Gemini 3.1 Pro, Gemini 2.0 Flash, Gemini 1.5 Pro).
- [ ] **Inference Turn Volume**: How many prompts, queries, or multi-turn interactions are expected per day or month?
- [ ] **Input Prompt Length**: What is the average input context length per turn (in tokens or characters), including system prompts, chat history, and retrieved RAG context?
- [ ] **Output Generation Length**: What is the average generated output length per turn (in tokens or characters)?
- [ ] **Multimodal Modalities**: Are image, audio, or video inputs processed? If so, what is the monthly volume/duration?
- [ ] **Context Caching**: Will prompt caching be enabled for repeated reference documents?
- [ ] **Vector Search (Matching Engine)**: What index dimension (e.g., 768 or 1536) and how many deployed endpoint replicas are needed?

---

### 1.7 Networking, Ingress & Security
- [ ] **Internet Egress**: How many GB or TB of outbound data transfer to the public internet are expected per month?
- [ ] **Egress Network Service Tier**: Google Cloud Premium Tier (global fiber backbone) or Standard Tier?
- [ ] **Application Load Balancing (ALB)**: How many forwarding rules and SSL certificates will be configured? How much data is processed by the ALB?
- [ ] **Cloud NAT**: How many Cloud NAT gateways are required for private subnet egress?
- [ ] **Cloud Armor**: How many security policies and custom WAF rules will be evaluated? What is the expected monthly query volume?

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
