# GCP Cloud Cost Estimation Report Template

Use the following markdown structure when generating the cost estimation report file (saved in `docs/gcp_cost_estimate_<workload_name>.md` inside the project folder).

---

```markdown
# 💰 Google Cloud Cost Estimation: [Workload / Project Name]

**Date:** [YYYY-MM-DD]  
**Target Region & Sustainability (WAF Pillar 6):** [e.g., us-central1 / europe-west1 — Documented Region CFE % & Low-CO2 justification]  
**Architecture Source:** [e.g., docs/*-architecture.md / specs/features/SPEC-*.md / terraform/]  
**Environments Modeled:** `NONPROD` (`main`/`develop`) & `PROD` (`prod`)  
**Workload Profile:** [e.g., Confirmed with user: ~100k MAU, ~10 RPS peak in Prod (24/7), scale-to-zero in Non-Prod]

---

## 📊 Executive Summary & FinOps Unit Economics (WAF Pillar 4)

| Pricing Model | Non-Prod Monthly (USD) | Prod Monthly (USD) | Total Monthly Run-Rate (USD) | Total Annual Run-Rate (USD) | Projected Savings |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **On-Demand (Pay-As-You-Go)** | $[NonProd_Monthly] | $[Prod_Monthly] | **$[Total_Monthly_OnDemand]** | **$[Total_Annual_OnDemand]** | Baseline |
| **1-Year CUD + Provisioned Throughput** | $[NonProd_1Yr] | $[Prod_1Yr] | $[Monthly_1Yr_CUD] | $[Annual_1Yr_CUD] | ~28% on steady compute/DB/GSUs |
| **3-Year CUD + Context Caching** | $[NonProd_3Yr] | $[Prod_3Yr] | $[Monthly_3Yr_CUD] | $[Annual_3Yr_CUD] | ~52% on steady compute/DB |

- **FinOps Unit Economics KPIs:** **`$[Unit_Cost_Per_1k_Reqs]` per 1,000 API requests** • **`$[Unit_Cost_Per_Session]` per resolved AI agent session**

> [!NOTE]
> All unit prices are sourced live directly from the **Google Cloud Billing API** or official live Google Cloud pricing documentation in `[Target Region]`. Zero local price caching or benchmark defaults were used. Free tier allowances have been credited where applicable.

---

## 🧩 Cost Distribution by Service & Runtime Category

```mermaid
pie title Monthly Cost by Service Category (Total: $[Total_Monthly_OnDemand])
    "AI Agents & ADK (agent_runtime)" : [AI_Cost]
    "Compute & Containers (cloud_run)" : [Compute_Cost]
    "Databases & Storage" : [Database_Cost]
    "Analytics & Streaming" : [Analytics_Cost]
    "Networking, IAP & DevSecOps" : [Network_Cost]
```

| Category | Monthly Cost (USD) | % of Total Bill |
| :--- | :--- | :--- |
| **AI Agents & ADK (`agent_runtime`)** | $[AI_Cost] | [AI_Pct]% |
| **Compute & Containers (`cloud_run`)** | $[Compute_Cost] | [Compute_Pct]% |
| **Databases & Storage** | $[Database_Cost] | [Database_Pct]% |
| **Analytics & Streaming** | $[Analytics_Cost] | [Analytics_Pct]% |
| **Networking, IAP & DevSecOps** | $[Network_Cost] | [Network_Pct]% |
| **Total** | **$[Total_Monthly_OnDemand]** | **100.0%** |

---

## 📋 Itemized Bill of Materials (BoM)

| Env | Service | Resource / SKU | Sizing & Specifications | Monthly Usage | Live Unit Rate | Rate Sourcing (Live API / URL) | Monthly Cost | Sizing Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `PROD` | **Cloud Run (`cloud_run`)** | UI & Streaming Proxy | 2 vCPU, 4 GB RAM, `min=1` | [usage] vCPU-hrs | $[rate] / vCPU-hr | Billing API (`[SKU-ID]`) | $[cost] | Confirmed: [concurrency], [latency] ms |
| `NONPROD` | **Cloud Run (`cloud_run`)** | UI & Streaming Proxy | 1 vCPU, 2 GB RAM, `min=0` | [usage] vCPU-hrs | $[rate] / vCPU-hr | Billing API (`[SKU-ID]`) | $[cost] | Confirmed: scale-to-zero (`NONPROD_MIN_INSTANCES=0`) |
| `PROD` | **Cloud SQL** | PostgreSQL DB | `db-custom-4-16384` HA | 730 hours (HA) | $[rate] / hr total | Billing API (`[SKU-ID]`) | $[cost] | Confirmed: Regional HA, [size] GB SSD |
| `PROD` | **Vertex AI (`agent_runtime`)** | Gemini + ADK Multi-Hop | [in] in / [out] out tokens | [turns] turns × [hops] hops | $[rate] / 1M in/out | cloud.google.com/vertex-ai/generative-ai/pricing | $[cost] | Confirmed: [model], [hops] hops/turn + Model Armor |
| `SHARED` | **Vertex AI (`agents-cli eval`)** | Live Eval Runs | [cases] cases × [runs] runs/mo | [eval_tokens] tokens | $[rate] / 1M tokens | cloud.google.com/vertex-ai/generative-ai/pricing | $[cost] | Confirmed: CI/CD live evaluation gate |
| `PROD` | **Networking & Security** | Pattern 1A ALB+IAP / 1B Direct IAP / Egress | Premium Tier Egress | [usage] GB egress | $[rate] / GB | cloud.google.com/vpc/network-pricing | $[cost] | Confirmed: IAM Ingress Pattern [1A/1B/2/3] |
| **Total** | | | | | | | **$[Total_Monthly_OnDemand]** | |

---

## 📝 Confirmed Workload Parameters & Specifications

> [!IMPORTANT]
> Zero unverified assumptions were used in this estimate. All parameters below were explicitly confirmed by the user or extracted from version-controlled Infrastructure-as-Code / `.env.example` files:

### 1. User-Confirmed Workload Variables:
- **Deployment Region:** [e.g., us-central1]
- **Multi-Environment Schedule (`NONPROD_*` vs `PROD_*`):** [e.g., Prod 24/7 = 730 hours/month with `PROD_MIN_INSTANCES=1`; Non-Prod scale-to-zero `NONPROD_MIN_INSTANCES=0`]
- **Traffic Volume (`cloud_run`):** [e.g., 15,000,000 requests/month, average streaming duration/latency, concurrency 40]
- **Database Specifications:** [e.g., Cloud SQL PostgreSQL db-custom-4-16384 HA in Prod, db-custom-1-3840 zonal in Non-Prod]
- **Object Storage:** [e.g., 500 GB Standard storage, 50,000 Class A ops, 200,000 Class B ops]
- **AI / ADK Agent Runtime (`agent_runtime`):** [e.g., 50,000 turns/month, 2 reasoning/tool hops per turn, average 1,500 input / 500 output tokens per hop, Model Armor enabled, `agents-cli eval` runs/month]
- **IAM Ingress Pattern & Egress:** [e.g., Pattern 1A (ALB + Cloud Armor + IAP) / Pattern 1B (Direct Cloud Run IAP, $0 ALB) / Pattern 2 / Pattern 3, 250 GB outbound internet egress on Premium Tier]

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

## 💡 FinOps & Dual-Runtime Optimization Recommendations

1. **Commitment Discounts (CUD):** Purchasing a 1-year or 3-year Flexible CUD yields **28% to 52% in savings** on steady-state Cloud Run, GKE, and Cloud SQL production resources.
2. **Cloud Run Scale-to-Zero & Streaming Concurrency:** Enforce `NONPROD_MIN_INSTANCES=0` in Non-Prod to eliminate idle compute charges, and tune SSE/WebSocket concurrency on the Cloud Run streaming proxy.
3. **ADK Context Caching & Tool Payload Trimming:** Enable Gemini context caching for repeated system instructions/`FunctionTool` schemas and return concise projections from tools to reduce multi-hop input token costs.
4. **Storage Lifecycle Policies:** Transition GCS objects and Artifact Registry container images using lifecycle cleanup policies to reduce storage costs by up to **80%**.
```
