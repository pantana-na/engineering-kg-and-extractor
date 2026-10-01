# Example: End-to-End Cost Estimation Walkthrough (Zero-Assumption & Live Pricing)

This example demonstrates how the `gcp-cost-estimator` skill analyzes an architecture document and codebase, systematically asks all required sizing questions, confirms every parameter with the user (zero unverified assumptions), queries live Google Cloud pricing, and generates a fully itemized cost estimate.

---

## Scenario: Real-time CDC & GenAI Analytics Architecture

### Discovered Architecture Components:
1. **Source OLTP Database:** Cloud SQL for PostgreSQL (`db-custom-4-16384` HA)
2. **Change Data Capture:** Datastream streaming CDC events from PostgreSQL to Cloud Storage.
3. **Data Lake & Warehouse:** Cloud Storage (Standard Bucket) + BigQuery (Data analytics & continuous queries).
4. **Agentic API & Frontend:** Cloud Run (2 vCPU, 4 GB RAM, container running FastAPI + LangChain).
5. **AI Inference:** Vertex AI Gemini 3.7 Flash for summarizing change data and answering queries.
6. **Network & Ingress:** Cloud Application Load Balancer with SSL termination.

---

### Step 1: Comprehensive Parameter Elicitation (Asking ALL Required Questions)

The agent formulates targeted questions covering every discovered component without making unilateral assumptions:

**Agent Questions to User:**
> 1. **Deployment Region**: Which Google Cloud region will host these services?
> 2. **Operational Schedule**: Will Cloud SQL and Cloud Run operate 24/7 (730 hours/month), or are there scheduled down periods?
> 3. **Cloud Run Traffic**: How many monthly API requests do you expect, what is the average latency, and what concurrency level is configured per container?
> 4. **Cloud SQL Storage & Sizing**: Is Regional High Availability required? What is the initial database storage size (GB), and what is the expected monthly growth rate?
> 5. **Datastream CDC**: How many gigabytes of changed records will be captured and streamed per month?
> 6. **Cloud Storage Volume & Ops**: What total volume of data will be stored, and how many monthly Class A (upload) / Class B (read) operations are expected?
> 7. **BigQuery Queries**: How many TB of data will queries scan each month under the on-demand model?
> 8. **Vertex AI GenAI Turns & Tokens**: Which Gemini model will you use? How many inference turns per month do you anticipate, and what is your average input and output token count per turn?
> 9. **Internet Egress**: How many GB of outbound internet data transfer will the API / Load Balancer serve monthly?

**User Confirms Exact Values:**
- **Region**: `us-central1`
- **Schedule**: Continuous 24/7 (730 hours/month)
- **Cloud Run Traffic**: 15,000,000 requests/month, average latency 100ms, concurrency=40 => ~1,040 active vCPU-hours/month. Min instances = 1.
- **Cloud SQL**: Regional HA confirmed, 200 GB SSD storage, automated daily backups.
- **Datastream**: 50 GB changed CDC data per month.
- **Cloud Storage**: 500 GB-months Standard storage, 50,000 Class A ops, 200,000 Class B ops.
- **BigQuery**: 2 TB scanned queries/month (on-demand), 200 GB active storage.
- **Vertex AI**: Gemini 3.7 Flash, 50,000 turns/month, average 1,500 input tokens / 500 output tokens per turn.
- **Load Balancer & Egress**: 1 ALB forwarding rule, 150 GB Premium internet egress.

---

### Step 2: Live Price Lookups via `query_gcp_pricing.py` & Live Documentation

The agent queries live unit rates directly from the live Google Cloud Billing Catalog API and official documentation:

```bash
# Query live Cloud Run rates from Billing API:
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service cloudrun --query "CPU Allocation" --region us-central1
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service cloudrun --query "Memory Allocation" --region us-central1

# Query live Cloud SQL rates:
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service cloudsql --query "PostgreSQL DB" --region us-central1
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service cloudsql --query "Storage" --region us-central1

# Query live Storage and Datastream rates:
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service storage --query "Standard Storage US" --region us
python3 _agents/skills/gcp_cost_estimator/scripts/query_gcp_pricing.py --service datastream --query "Volume"

# Live check for Vertex AI Gemini 3.7 Flash token rates:
# Verified on https://cloud.google.com/vertex-ai/generative-ai/pricing via web query
```

---

### Step 3: Calculation & BoM Breakdown

The agent passes the user-confirmed parameters and live unit rates into `calculate_bom_cost.py` to generate the exact, deterministic cost estimate without using cached or assumed numbers.
