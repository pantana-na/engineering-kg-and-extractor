# Google Cloud Pricing Dimensions, Billing SKUs & Calculation Formulas

> [!IMPORTANT]
> **ZERO PRICE CACHING POLICY**:
> This catalog contains **mathematical formulas, billing dimensions, and live SKU query descriptors ONLY**.
> Unit prices are **NEVER hardcoded or cached** in this repository. All rates must be resolved in real time via the **Google Cloud Billing API** (`query_gcp_pricing.py`) or official live Google Cloud pricing pages (`cloud.google.com/<service>/pricing`).

---

## 1. Compute & Containers

### Cloud Run (Fully Managed Serverless)
- **Billing Dimensions**:
  - vCPU Allocation Time (`vCPU-seconds`)
  - Memory Allocation Time (`GiB-seconds`)
  - Request Count (Millions of invocations)
  - Idle CPU for Minimum Instances (`vCPU-seconds`)
- **Calculation Formula**:
  $$\text{Active Seconds} = \frac{\text{Monthly Requests} \times (\text{Avg Latency ms} / 1000)}{\text{Concurrency Level}}$$
  $$\text{Compute Cost} = (\text{vCPUs} \times \text{Active Seconds} \times \text{Live\_vCPU\_Rate}) + (\text{GiB} \times \text{Active Seconds} \times \text{Live\_Mem\_Rate})$$
  $$\text{Request Cost} = \max(0, \text{Monthly Requests} - \text{Live\_Free\_Tier}) \times \frac{\text{Live\_Req\_Rate}}{1,000,000}$$
  $$\text{Idle Min Instance Cost} = \text{Min Instances} \times \text{vCPU} \times \text{Idle Seconds} \times \text{Live\_Idle\_Rate}$$
- **Live Query**:
  ```bash
  python3 scripts/query_gcp_pricing.py --service cloudrun --query "CPU Allocation" --region <REGION>
  python3 scripts/query_gcp_pricing.py --service cloudrun --query "Memory Allocation" --region <REGION>
  python3 scripts/query_gcp_pricing.py --service cloudrun --query "Requests"
  ```
- **Live Documentation**: `https://cloud.google.com/run/pricing`

---

### Compute Engine (GCE) & GKE Nodes
- **Billing Dimensions**:
  - Core vCPU (`vCPU-hours`)
  - Memory (`GiB-hours`)
  - Persistent Disk Capacity (`GB-months` for `pd-standard`, `pd-balanced`, `pd-ssd`, or `hyperdisk`)
- **Calculation Formula**:
  $$\text{Monthly Instance Cost} = \text{Instances} \times \text{Operating Hours} \times [(\text{vCPUs} \times \text{Live\_Core\_Rate}) + (\text{RAM GB} \times \text{Live\_RAM\_Rate})]$$
  $$\text{Storage Cost} = \text{Provisioned Disk GB} \times \text{Live\_Disk\_Rate}$$
- **Live Query**:
  ```bash
  python3 scripts/query_gcp_pricing.py --service compute --query "Instance Core" --region <REGION>
  python3 scripts/query_gcp_pricing.py --service compute --query "Instance Ram" --region <REGION>
  python3 scripts/query_gcp_pricing.py --service compute --query "Storage Balanced SSD" --region <REGION>
  ```
- **Live Documentation**: `https://cloud.google.com/compute/all-pricing`

---

### Google Kubernetes Engine (GKE)
- **Billing Dimensions**:
  - GKE Cluster Management Fee ($/cluster-hour; 1 free zonal/Autopilot cluster per billing account)
  - Autopilot Pod vCPU, Memory, and Ephemeral Storage (`vCPU-hours`, `GB-hours`)
  - Standard GKE: Underlying Compute Engine VMs + Management Fee
- **Live Query**:
  ```bash
  python3 scripts/query_gcp_pricing.py --service compute --query "Kubernetes"
  ```
- **Live Documentation**: `https://cloud.google.com/kubernetes-engine/pricing`

---

## 2. Databases & Storage

### Cloud SQL (PostgreSQL, MySQL, SQL Server)
- **Billing Dimensions**:
  - Dedicated vCPU (`vCPU-hours`)
  - Dedicated Memory (`GiB-hours`)
  - SSD / HDD Storage (`GB-months`)
  - High Availability (Regional HA primary + standby replica multiplier)
  - Automated Backup Storage beyond DB size (`GB-months`)
- **Calculation Formula**:
  $$\text{Compute Cost} = [(\text{vCPUs} \times \text{Live\_vCPU\_Rate}) + (\text{RAM GiB} \times \text{Live\_Mem\_Rate})] \times \text{Monthly Hours} \times (\text{2 if Regional HA else 1})$$
  $$\text{Storage Cost} = \text{Provisioned SSD GB} \times \text{Live\_Storage\_Rate} \times (\text{2 if Regional HA else 1})$$
- **Live Query**:
  ```bash
  python3 scripts/query_gcp_pricing.py --service cloudsql --query "PostgreSQL DB" --region <REGION>
  python3 scripts/query_gcp_pricing.py --service cloudsql --query "Storage" --region <REGION>
  ```
- **Live Documentation**: `https://cloud.google.com/sql/pricing`

---

### Cloud Spanner
- **Billing Dimensions**:
  - Spanner Processing Units (`PUs` or `Nodes`, where 1,000 PUs = 1 Node)
  - Database Storage (`GB-months`)
  - Network egress & backup storage
- **Live Query**:
  ```bash
  python3 scripts/query_gcp_pricing.py --service spanner --query "Processing Units" --region <REGION>
  python3 scripts/query_gcp_pricing.py --service spanner --query "Storage" --region <REGION>
  ```
- **Live Documentation**: `https://cloud.google.com/spanner/pricing`

---

### Cloud Storage (GCS)
- **Billing Dimensions**:
  - Data Storage Tier: Standard, Nearline, Coldline, Archive (`GB-months`)
  - Class A Operations (Inserts, Uploads, List, Rewrite: per 10,000 ops)
  - Class B Operations (Downloads, Reads: per 10,000 ops)
  - Data Retrieval Fees (Nearline, Coldline, Archive per GB)
  - Inter-region & Internet Network Egress
- **Calculation Formula**:
  $$\text{Total Storage Cost} = (\text{Volume GB} \times \text{Live\_Tier\_Rate}) + \left(\frac{\text{Class A Ops}}{10,000} \times \text{Live\_ClassA\_Rate}\right) + \left(\frac{\text{Class B Ops}}{10,000} \times \text{Live\_ClassB\_Rate}\right)$$
- **Live Query**:
  ```bash
  python3 scripts/query_gcp_pricing.py --service storage --query "Standard Storage" --region <REGION>
  python3 scripts/query_gcp_pricing.py --service storage --query "Nearline" --region <REGION>
  python3 scripts/query_gcp_pricing.py --service storage --query "Operations"
  ```
- **Live Documentation**: `https://cloud.google.com/storage/pricing`

---

## 3. Analytics & Event Ingestion

### BigQuery
- **Billing Dimensions**:
  - Analysis: On-Demand ($/TB scanned) vs Capacity / Editions ($/slot-hour for Standard/Enterprise)
  - Storage: Active ($/GB-mo) vs Long-term untouched >90 days ($/GB-mo)
- **Live Query**:
  ```bash
  python3 scripts/query_gcp_pricing.py --service bigquery --query "Analysis"
  python3 scripts/query_gcp_pricing.py --service bigquery --query "Storage"
  ```
- **Live Documentation**: `https://cloud.google.com/bigquery/pricing`

---

### Cloud Pub/Sub
- **Billing Dimensions**:
  - Message Throughput Volume (`TiB ingested and delivered`)
  - Message Storage beyond retention window
- **Live Query**:
  ```bash
  python3 scripts/query_gcp_pricing.py --service pubsub --query "Throughput"
  ```
- **Live Documentation**: `https://cloud.google.com/pubsub/pricing`

---

### Datastream (CDC)
- **Billing Dimensions**:
  - Changed data capture volume processed (`GB of changed data`)
- **Live Query**:
  ```bash
  python3 scripts/query_gcp_pricing.py --service datastream --query "Volume"
  ```
- **Live Documentation**: `https://cloud.google.com/datastream/pricing`

---

## 4. Generative AI & Vertex AI

### Gemini Models (Vertex AI Model-as-a-Service)
- **Billing Dimensions**:
  - Input Context Tokens ($/1M tokens, differentiated by context length <=128K vs >128K)
  - Output / Generated Tokens ($/1M tokens)
  - Audio / Video / Image input modalities
  - Fine-tuning & Context Caching ($/1M cached tokens/hour)
- **Calculation Formula**:
  $$\text{Monthly Cost} = \text{Monthly Turns} \times \left[\left(\frac{\text{Avg Input Tokens}}{1,000,000} \times \text{Live\_Input\_Rate}\right) + \left(\frac{\text{Avg Output Tokens}}{1,000,000} \times \text{Live\_Output\_Rate}\right)\right]$$
- **Live Sourcing**:
  - Query live rates directly from official Vertex AI documentation using `search_web` or `read_url_content`:
    `https://cloud.google.com/vertex-ai/generative-ai/pricing`

---

### Vector Search (Matching Engine)
- **Billing Dimensions**:
  - Deployed Index Endpoint Replica ($/replica-hour by machine size)
  - Index storage and shard counts
- **Live Sourcing**:
  - Query official Vertex AI Vector Search pricing page via `search_web`:
    `https://cloud.google.com/vertex-ai/pricing#vectorsearch`

---

## 5. Networking, Load Balancing & Security

- **Internet Egress**: Premium Tier vs Standard Tier ($/GB transferred outbound). Query `https://cloud.google.com/vpc/network-pricing`.
- **Application Load Balancer (ALB)**: Forwarding rules ($/rule-hour) + Data processing fee ($/GB processed).
- **Cloud NAT**: Gateway hourly charge ($/gateway-hour) + Data processing ($/GB).
- **Cloud Armor**: Policy fee ($/policy-mo) + Rules ($/rule-mo) + Request inspection ($/million queries). Query `https://cloud.google.com/armor/pricing`.
