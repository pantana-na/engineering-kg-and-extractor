# Example: End-to-End Cost Estimation Walkthrough (Zero-Assumption & Live Pricing)

This example demonstrates how the `gcp-cost-estimator` skill analyzes an architecture document and codebase, systematically asks all required sizing questions, confirms every parameter with the user (zero unverified assumptions), queries live Google Cloud pricing, and generates a fully itemized cost estimate.

---

## Scenario: Real-time CDC & GenAI Analytics Architecture

### Discovered Architecture Components:
1. **Source OLTP Database:** Cloud SQL for PostgreSQL (`db-custom-4-16384` HA, CMEK-encrypted inside VPC-SC)
2. **Change Data Capture:** Datastream streaming CDC events from PostgreSQL to Cloud Storage.
3. **Data Lake & Warehouse:** Cloud Storage (Standard Bucket) + BigQuery (Data analytics & partitioned queries).
4. **Web UI & Streaming Proxy (`cloud_run`):** Cloud Run (2 vCPU, 4 GB RAM, stateless React UI + FastAPI SSE streaming proxy with `/healthz` probe).
5. **AI Agent Runtime (`agent_runtime`):** Gemini Enterprise Agent Platform running Google ADK (`google-adk`) with pinned `gemini-2.5-flash-001`, 4-point **Model Armor + Cloud DLP** callbacks, and `agents-cli eval` CI/CD gates.
6. **Zero-Trust Edge & Ingress (Pattern 1A):** Global External Application Load Balancer + **Cloud Armor** WAF + **Identity-Aware Proxy (IAP)**.

---

### Step 1: Comprehensive Parameter Elicitation (Asking ALL Required Questions)

The agent formulates targeted questions covering every discovered component without making unilateral assumptions:

**Agent Questions to User:**
> 1. **Deployment Region & Sustainability (`CFE %`)**: Which Google Cloud region will host these services?
> 2. **Multi-Environment Operational Schedule**: Will Prod operate 24/7 (730 hours/month with `PROD_MIN_INSTANCES=1`) while Non-Prod scales to zero (`NONPROD_MIN_INSTANCES=0`)?
> 3. **Cloud Run Streaming Proxy Traffic**: How many monthly API/SSE requests do you expect, what is the average stream duration, and what concurrency level is configured per container?
> 4. **Cloud SQL Storage & Sizing**: Is Regional High Availability required in Prod? What is the initial database storage size (GB), and what is the expected monthly growth rate?
> 5. **Datastream CDC**: How many gigabytes of changed records will be captured and streamed per month?
> 6. **Cloud Storage Volume & Ops**: What total volume of data will be stored, and how many monthly Class A (upload) / Class B (read) operations are expected?
> 7. **BigQuery Queries**: How many TB of data will queries scan each month under the on-demand model?
> 8. **ADK Agent Runtime (`agent_runtime`), Guardrails & Live Evals**: Which pinned Gemini model (`gemini-2.5-flash-001` vs. `gemini-2.5-pro-001`) will be used? How many user turns and multi-hop tool calls per month do you anticipate, what is your average input/output token count per hop, is Context Caching enabled, and how many `agents-cli eval` runs occur monthly?
> 9. **Zero-Trust Edge (ALB + Cloud Armor + IAP vs. Direct Cloud Run IAP), KMS & Egress**: Which Zero-Trust ingress pattern applies (Pattern 1A ALB + Cloud Armor + IAP vs. Pattern 1B Direct Cloud Run IAP `$0` fixed LB baseline), and how many ALB forwarding rules, Cloud Armor policies, CMEK keys, and GB of outbound internet data transfer will be served monthly?

**User Confirms Exact Values:**
- **Region**: `us-central1`
- **Schedule**: Prod continuous 24/7 (730 hours/month, `PROD_MIN_INSTANCES=1`); Non-Prod scale-to-zero (`NONPROD_MIN_INSTANCES=0`).
- **Cloud Run Traffic**: 15,000,000 requests/month in Prod, average proxy duration 100ms, concurrency=40 => ~1,040 active vCPU-hours/month.
- **Cloud SQL**: Regional HA confirmed in Prod, 200 GB SSD storage, automated daily backups, CMEK enabled.
- **Datastream**: 50 GB changed CDC data per month.
- **Cloud Storage**: 500 GB-months Standard storage, 50,000 Class A ops, 200,000 Class B ops.
- **BigQuery**: 2 TB scanned queries/month (on-demand), 200 GB active storage.
- **ADK Agent Runtime & Guardrails**: Pinned `gemini-2.5-flash-001` on `agent_runtime`, 50,000 turns/month × 2 hops/turn, average 1,500 input tokens / 500 output tokens per hop, 4-point Model Armor + Cloud DLP enabled, 10 `agents-cli eval` runs/month (100 golden cases).
- **Load Balancer, Cloud Armor & Egress**: Pattern 1A (1 ALB forwarding rule + Cloud Armor policy + IAP), 150 GB Premium internet egress.

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

# Live check for Vertex AI pinned gemini-2.5-flash-001, Model Armor, and Cloud DLP rates:
# Verified on https://cloud.google.com/vertex-ai/generative-ai/pricing via live web query
```

---

### Step 3: Calculation & BoM Breakdown

The agent passes the user-confirmed parameters and live unit rates into `calculate_bom_cost.py` to generate the exact, deterministic cost estimate without using cached or assumed numbers.
