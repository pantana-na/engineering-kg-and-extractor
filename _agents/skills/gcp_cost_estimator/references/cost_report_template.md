# GCP Cloud Cost Estimation Report Template

Use the following markdown structure when generating the cost estimation report file (saved in `docs/gcp_cost_estimate_<workload_name>.md` inside the project folder).

---

```markdown
# 💰 Google Cloud Cost Estimation: [Workload / Project Name]

**Date:** [YYYY-MM-DD]  
**Target Region:** [e.g., us-central1 / europe-west1 / asia-southeast1]  
**Architecture Source:** [e.g., architecture design document / terraform/ / main.py]  
**Workload Profile:** [e.g., Confirmed with user: ~100k MAU, ~10 RPS peak, 24/7 continuous operation]

---

## 📊 Executive Summary

| Pricing Model | Monthly Run-Rate (USD) | Annual Run-Rate (USD) | Projected Savings |
| :--- | :--- | :--- | :--- |
| **On-Demand (Pay-As-You-Go)** | **$[Total_Monthly_OnDemand]** | **$[Total_Annual_OnDemand]** | Baseline |
| **1-Year Committed Use (CUD)** | $[Monthly_1Yr_CUD] | $[Annual_1Yr_CUD] | ~25-35% on steady compute/DB |
| **3-Year Committed Use (CUD)** | $[Monthly_3Yr_CUD] | $[Annual_3Yr_CUD] | ~50-55% on steady compute/DB |

> [!NOTE]
> All unit prices are sourced live directly from the **Google Cloud Billing API** or official live Google Cloud pricing documentation in `[Target Region]`. Zero local price caching or benchmark defaults were used. Free tier allowances have been credited where applicable.

---

## 🧩 Cost Distribution by Service Category

```mermaid
pie title Monthly Cost by Service Category (Total: $[Total_Monthly_OnDemand])
    "Compute & Containers" : [Compute_Cost]
    "Databases & Storage" : [Database_Cost]
    "AI & Machine Learning" : [AI_Cost]
    "Analytics & Streaming" : [Analytics_Cost]
    "Networking & Security" : [Network_Cost]
```

| Category | Monthly Cost (USD) | % of Total Bill |
| :--- | :--- | :--- |
| **Compute & Containers** | $[Compute_Cost] | [Compute_Pct]% |
| **Databases & Storage** | $[Database_Cost] | [Database_Pct]% |
| **AI & Machine Learning** | $[AI_Cost] | [AI_Pct]% |
| **Analytics & Streaming** | $[Analytics_Cost] | [Analytics_Pct]% |
| **Networking & Security** | $[Network_Cost] | [Network_Pct]% |
| **Total** | **$[Total_Monthly_OnDemand]** | **100.0%** |

---

## 📋 Itemized Bill of Materials (BoM)

| Service | Resource / SKU | Sizing & Specifications | Monthly Usage | Live Unit Rate | Rate Sourcing (Live API / URL) | Monthly Cost | Sizing Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Cloud Run** | App Service | 2 vCPU, 4 GB RAM | [usage] vCPU-hrs | $[rate] / vCPU-hr | Billing API (`[SKU-ID]`) | $[cost] | Confirmed: [concurrency], [latency] ms |
| **Cloud SQL** | PostgreSQL DB | `db-custom-4-16384` HA | 730 hours (HA) | $[rate] / hr total | Billing API (`[SKU-ID]`) | $[cost] | Confirmed: Regional HA, [size] GB SSD |
| **Cloud Storage** | GCS Bucket | Standard Storage | [usage] GB-months | $[rate] / GB-mo | Billing API (`[SKU-ID]`) | $[cost] | Confirmed: [volume] GB, [ops] ops |
| **Vertex AI** | Gemini 3.7 Flash | [in] in / [out] out tokens | [turns] turns | $[rate] / 1M in/out | cloud.google.com/vertex-ai/generative-ai/pricing | $[cost] | Confirmed: [model], [tokens] tokens/turn |
| **Networking** | ALB & Egress | Premium Tier Egress | [usage] GB egress | $[rate] / GB | cloud.google.com/vpc/network-pricing | $[cost] | Confirmed: [volume] GB egress, 1 rule |
| **Total** | | | | | | **$[Total_Monthly_OnDemand]** | |

---

## 📝 Confirmed Workload Parameters & Specifications

> [!IMPORTANT]
> Zero unverified assumptions were used in this estimate. All parameters below were explicitly confirmed by the user or extracted from version-controlled Infrastructure-as-Code files:

### 1. User-Confirmed Workload Variables:
- **Deployment Region:** [e.g., us-central1]
- **Operational Schedule:** [e.g., 24/7 continuous operation = 730 hours/month]
- **Traffic Volume:** [e.g., 15,000,000 requests/month, average latency 120ms, concurrency 40]
- **Database Specifications:** [e.g., Cloud SQL PostgreSQL db-custom-4-16384 HA, 250 GB SSD storage, daily automated snapshots]
- **Object Storage:** [e.g., 500 GB Standard storage, 50,000 Class A ops, 200,000 Class B ops]
- **AI / LLM Volume:** [e.g., 50,000 turns/month, Gemini 3.7 Flash, average 1,500 input tokens / 500 output tokens]
- **Network Egress:** [e.g., 250 GB outbound internet egress on Premium Tier]

---

## 📈 Sensitivity & Scale Analysis

How monthly infrastructure costs scale if traffic varies:

| Scale Factor | Monthly Request Volume | AI Turn Volume | Estimated Monthly Cost | Delta vs Baseline |
| :--- | :--- | :--- | :--- | :--- |
| **0.5× (Low Traffic)** | [Half_Reqs] | [Half_Turns] | $[Cost_Half] | -[Pct]% |
| **1.0× (Confirmed Baseline)** | [Base_Reqs] | [Base_Turns] | **$[Total_Monthly_OnDemand]** | **0%** |
| **2.0× (2x Growth)** | [2x_Reqs] | [2x_Turns] | $[Cost_2x] | +[Pct]% |
| **5.0× (5x Peak)** | [5x_Reqs] | [5x_Turns] | $[Cost_5x] | +[Pct]% |

---

## 💡 FinOps & Cost Optimization Recommendations

1. **Commitment Discounts (CUD):** If running steady-state compute or database instances, purchasing a 1-year or 3-year Flexible CUD can yield **28% to 55% in savings** on baseline resources.
2. **Cloud Run Concurrency & Sizing:** Calibrate container concurrency to maximize CPU utilization during active requests, and configure `min-instances=0` in non-prod environments.
3. **Storage Lifecycle Policies:** Transition GCS objects to Nearline storage after 30 days and Coldline after 90 days to reduce storage costs by up to **80%**.
4. **BigQuery Slot vs On-Demand Optimization:** Ensure tables are partitioned by day/month and clustered by commonly filtered columns to prevent full-table scans.
```
