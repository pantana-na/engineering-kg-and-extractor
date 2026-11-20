# Google Cloud Well-Architected Framework (WAF): 6 Core Pillars & AI/ML + FSI Perspectives Reference

**Authoritative Primary Sources:**
- **Framework Hub:** `https://docs.cloud.google.com/architecture/framework` (`https://cloud.google.com/architecture/framework`)
- **AI and ML Perspective:** `https://docs.cloud.google.com/architecture/framework/perspectives/ai-ml`
- **Financial Services (FSI) Perspective:** `https://docs.cloud.google.com/architecture/framework/perspectives/fsi`
- **Official Google Cloud WAF Agent Skills:** `https://github.com/google/skills/tree/main/skills/cloud`

---

## 1. Foundational Cross-Pillar Core Principles

1. **Design for Change:** Architect systems and pipelines for small, frequent, low-risk, reversible deployments with rapid telemetry feedback, optimizing DORA metrics (Deployment Frequency, Lead Time for Changes, Change Failure Rate, Mean Time to Recovery).
2. **Simplify Your Design and Use Fully Managed Services:** Start with a clear MVP, avoid speculative over-engineering, and prioritize serverless/managed services (`Cloud Run`, `Vertex AI / Gemini Enterprise Agent Platform`, `BigQuery`, `Spanner`, `AlloyDB`, `Pub/Sub`) to eliminate patching and infrastructure toil.
3. **Decouple Your Architecture:** Decompose workloads along clear domain, security, and scaling boundaries so frontend proxies, cognitive reasoning engines, ingestion pipelines, and transactional APIs evolve and scale independently without cascading failures.
4. **Use a Stateless Architecture:** Keep compute tiers (`Cloud Run`, `Agent Runtime`) stateless by externalizing session state, memory, and workflow checkpoints into managed stores (`agentengine://`, `Memorystore`, `AlloyDB`, `Spanner`, `Firestore`).
5. **Automate Everything:** Manage 100% of infrastructure via declarative IaC (`Terraform` + `Google Cloud Infrastructure Manager`), automate CI/CD (`Cloud Build`), and enforce automated shift-left security and policy gates.
6. **Document Your Architecture & Test Continuously:** Maintain living specifications (`specs/`), architecture diagrams (`docs/`), ADRs, and continuous automated testing (unit, property-based, load, chaos/DR failover, and live agent evaluation).

---

## 2. Detailed Catalog of the Six (6) Core Pillars

### Pillar 1: Operational Excellence
**Canonical URL:** `https://docs.cloud.google.com/architecture/framework/operational-excellence`

| Principle | Key Design Practices & Google Cloud Implementation |
| :--- | :--- |
| **1. Ensure operational readiness and performance using CloudOps** | - Define user-centric **SLIs**, pragmatic **SLOs (<100%)**, and written **Error Budget** policies in **Cloud Monitoring Service Monitoring**.<br>- Emit structured JSON logs to **Cloud Logging** correlated via `logging.googleapis.com/trace`, `spanId`, and `session_id`; trace distributed requests via **Cloud Trace** (OpenTelemetry).<br>- Plan compute and AI capacity proactively (quotas, **Vertex AI Provisioned Throughput**, Future Reservations, MIG/GKE spillover). |
| **2. Automate and manage change** | - Provision all resources via **Terraform** managed by **Google Cloud Infrastructure Manager** with isolated state per environment (`nonprod` vs. `prod`).<br>- Use **Cloud Build** for immutable container builds (`${_ENVIRONMENT}-${SHORT_SHA}`), automated test gates, and progressive **Cloud Run revision traffic splitting** (canary rollouts with 1-click rollback). |
| **3. Manage incidents and problems** | - Configure multi-window SLO burn-rate alerts routed to incident response workflows.<br>- Maintain actionable runbooks, clear Incident Commander roles, and conduct **blameless postmortems (RCAs)** for all P0/P1 incidents or test/eval regressions. |
| **4. Manage and optimize cloud resources** | - Apply **Active Assist / Recommender** insights for right-sizing and idle resource cleanup; enforce organization-wide resource labeling. |
| **5. Continuously improve and innovate** | - Track DORA metrics, conduct periodic Well-Architected reviews, and feed production evaluation insights back into golden test suites. |

---

### Pillar 2: Security, Privacy, and Compliance
**Canonical URL:** `https://docs.cloud.google.com/architecture/framework/security`

| Principle | Key Design Practices & Google Cloud Implementation |
| :--- | :--- |
| **1. Implement security by design** | - Apply defense-in-depth, least privilege, and Organization Policy constraints (`constraints/iam.allowedPolicyMemberDomains`, `constraints/iam.disableServiceAccountKeyCreation`, `constraints/gcp.resourceLocations`) from Day 1. |
| **2. Implement zero trust** | - *"Never trust, always verify."* Enforce identity- and context-aware ingress via **Pattern 1A: Global External Application Load Balancer + Cloud Armor + Identity-Aware Proxy (IAP)**, **Pattern 1B: Direct Cloud Run IAP (`--iap` + `INGRESS_TRAFFIC_ALL` + `x-goog-iap-jwt-assertion` JWT verification — for internal workforce, single-region & cost-optimized apps)**, or **Pattern 2: Verified OAuth 2.0/OIDC tokens**.<br>- Wrap sensitive APIs (`Vertex AI`, `Agent Runtime`, `BigQuery`, `Cloud Storage`, `Cloud KMS`, `Secret Manager`) inside **VPC Service Controls (VPC-SC)** perimeters and connect privately via **Private Service Connect (PSC)**.<br>- Disable default VPC networks and default Compute Engine service accounts. |
| **3. Implement shift-left security** | - Run pre-build SAST via **CodeMender (`cm find/verify/fix`)**, dependency/container scanning via **Artifact Analysis**, IaC policy checks, and enforce **SLSA Level 3 provenance + Binary Authorization** so only signed, verified images deploy. |
| **4. Implement preemptive cyber-defense** | - Deploy **Cloud Armor** (OWASP Top 10 preconfigured WAF rules, Adaptive Protection L7 DDoS defense, rate limiting) on ALB-fronted services *(or enforce strict app-layer schema validation, `max-instances` caps, and per-user rate/token budgets when using Pattern 1B Direct Cloud Run IAP with a documented ADR)*, and monitor posture continuously with **Security Command Center (SCC) Premium / Enterprise** (including **SCC AI Protection**). |
| **5. Use AI securely and responsibly** | - Enforce **Google Secure AI Framework (SAIF)** controls: inline **Model Armor** guardrails, **Sensitive Data Protection (Cloud DLP)** de-identification/tokenization, **Confidential Computing** for sensitive workloads, and verifiable RAG citations. |
| **6. Meet regulatory, compliance, and privacy needs** | - Use **Assured Workloads** for regulated regimes, **Cloud KMS (CMEK / Cloud HSM / Cloud EKM)** for cryptographic control, immutable **Cloud Audit Logs** (with `Bucket Lock` for WORM compliance), and automated privacy redaction / crypto-shredding for DSRs (GDPR/CCPA). |

---

### Pillar 3: Reliability
**Canonical URL:** `https://docs.cloud.google.com/architecture/framework/reliability`

| Principle | Key Design Practices & Google Cloud Implementation |
| :--- | :--- |
| **1. Define reliability based on user-experience goals** | - Measure SLIs at the user journey boundary: end-to-end streaming availability, p95/p99 response latency, Time-to-First-Token (TTFT), and answer groundedness. |
| **2. Set realistic targets for reliability** | - Calculate **composite availability SLA** across chained dependencies ($SLA_{total} = \prod SLA_i$ for serial components). Set realistic SLOs (e.g., `99.9%` or `99.95%`) with explicit **RTO** and **RPO** targets balanced against cost and data residency. |
| **3. Build highly available systems through resource redundancy** | - Eliminate Single Points of Failure (SPOFs): use regional multi-zone services (`Cloud Run`, `BigQuery`, `AlloyDB` HA, `Spanner`) or multi-region active-active behind a Global External ALB for mission-critical Tier-1 workloads. |
| **4. Take advantage of horizontal scalability** | - Keep compute tiers stateless; configure autoscaling (`max-instances`), concurrency bounds, rate limiting, and **Vertex AI Provisioned Throughput with automatic PayGo spillover** to prevent `429 RESOURCE_EXHAUSTED` quota stockouts. |
| **5. Detect potential failures by using observability** | - Monitor the **Four Golden Signals** (Latency, Traffic, Errors, Saturation) plus synthetic blackbox probers against `/healthz` and core API paths. |
| **6. Design for graceful degradation** | - Implement **circuit breakers, bounded request timeouts, retries with exponential backoff + jitter**, and **transparent degraded-mode responses** (e.g., serving read-only cached policy with explicit staleness metadata or routing to human queues when a downstream API fails—*strictly never returning synthetic/mockup fake records*). |
| **7. Perform testing for recovery from failures & data loss** | - Rehearse automated revision rollbacks, regional/zonal disconnect drills, and backup/restore verification (BigQuery Time Travel / Cross-Region Replication, PITR) within target RTO/RPO. |

---

### Pillar 4: Cost Optimization
**Canonical URL:** `https://docs.cloud.google.com/architecture/framework/cost-optimization`

| Principle | Key Design Practices & Google Cloud Implementation |
| :--- | :--- |
| **1. Align cloud spending with business value (FinOps)** | - Define **Unit Economics** metrics (e.g., `$ / resolved customer inquiry`, `$ / 1,000 agent turns`, `$ / dispute processed`) so cloud spend scales predictably with business value. |
| **2. Foster a culture of cost awareness** | - Enforce 100% resource labeling (`env`, `service`, `owner`, `cost_center`) in Terraform; enable **Cloud Billing Detailed Export to BigQuery**, FinOps Hub, Looker Studio dashboards, **Cloud Billing Budgets**, and **Cost Anomaly Detection**. |
| **3. Optimize resource usage & optimize continuously** | - **Compute:** Scale `nonprod` Cloud Run to zero (`min-instances = 0`) with request-based CPU billing; reserve `min-instances >= 1` and Committed Use Discounts (CUDs) for steady `prod` traffic.<br>- **Data & Storage:** Partition and cluster BigQuery tables; enforce `maximum_bytes_billed` per query; configure Cloud Storage Autoclass / lifecycle tiering (Standard $\rightarrow$ Nearline $\rightarrow$ Coldline $\rightarrow$ Archive) and log exclusions.<br>- **GenAI & Agents:** Use **Model Routing** (Gemini Flash / Flash-Lite for intent classification & extraction; Gemini Pro for complex reasoning), **Vertex AI Context Caching** (50%–90% savings on repeated system prompts/corpora), **Batch API** (~50% discount for asynchronous evals/enrichment), and right-sized **Provisioned Throughput** baselines with PayGo burst spillover. |

---

### Pillar 5: Performance Optimization
**Canonical URL:** `https://docs.cloud.google.com/architecture/framework/performance-optimization`

| Principle | Key Design Practices & Google Cloud Implementation |
| :--- | :--- |
| **1. Plan resource allocation** | - Co-locate `Cloud Run`, `Agent Runtime`, `Model Armor`, `Cloud KMS`, `Vertex AI Vector Search`, and `BigQuery`/`AlloyDB` in the **same GCP region** to eliminate cross-region RTT overhead.<br>- Match storage to access patterns: `AlloyDB`/`Cloud SQL` or `Spanner` for sub-10ms OLTP transactions; `Vertex AI Search / Vector Search` for sub-100ms semantic retrieval; `BigQuery` with partitioning/clustering + BI Engine for analytics. |
| **2. Take advantage of elasticity** | - Configure Cloud Run **Startup CPU Boost**, tuned container concurrency, and warm `min-instances` on latency-critical production paths. |
| **3. Promote modular design** | - Stream responses end-to-end using **Server-Sent Events (SSE) / WebSockets** (`X-Accel-Buffering: no`) to minimize perceived **Time-to-First-Token (TTFT)**.<br>- Execute independent ADK `FunctionTool` calls in parallel and offload non-blocking side effects (audit export, analytics, notifications) to **Pub/Sub** / **Cloud Tasks**. |
| **4. Continuously monitor and improve performance** | - Multi-layer caching: **Cloud CDN** for static UI assets, **Memorystore (Redis/Valkey)** for hot session/reference lookups, and **Vertex AI Context Caching** for repeated prompt prefixes.<br>- Continuously profile p50/p95/p99 latency waterfalls via **Cloud Trace** and **Cloud Profiler**. |

---

### Pillar 6: Sustainability
**Canonical URL:** `https://docs.cloud.google.com/architecture/framework/sustainability`

| Principle | Key Design Practices & Google Cloud Implementation |
| :--- | :--- |
| **1. Use regions that consume low-carbon energy** | - After filtering by regulatory data-residency (`constraints/gcp.resourceLocations`) and user latency SLOs, select the GCP region with the highest **Carbon-Free Energy (CFE %)** and `Low CO2` indicator using the **Google Cloud Region Picker**. |
| **2. Optimize AI and ML workloads (`ai-ml-efficiency`)** | - Maximize **useful AI work per watt**: route simple tasks to smaller distilled models (**Gemini Flash**), enable **Vertex AI Context Caching** to avoid recomputing KV-caches across turns, and run offline evaluations via **Batch API** during low-carbon windows. |
| **3. Optimize resource usage, software & data storage** | - Scale idle `nonprod` services to zero; prefer event-driven (`Pub/Sub` / `Eventarc`) over continuous polling; enforce strict TTL lifecycle policies on staging tables, temp buckets, and verbose logs to eliminate dark data. |
| **4. Continuously measure and improve** | - Enable **Google Cloud Carbon Footprint export to BigQuery** mapped to project labels/folders (Scope 1, 2, and 3 market- and location-based emissions aligned with the GHG Protocol). |

---

## 3. Cross-Pillar Perspectives Summary

### 3.1 AI and ML Perspective (`/architecture/framework/perspectives/ai-ml`)
1. **Six Decoupled Agentic Concerns:** Architect agent systems cleanly across (1) **Models** (pinned version IDs, tiered routing), (2) **Tools** (strongly typed `FunctionTool` callables with strict schemas), (3) **Grounding** (RAG over authoritative stores with source ACLs and citations), (4) **Memory & State** (externalized short-term session state + long-term memory), (5) **Orchestration** (ADK `OrchestratorAgent` + domain subagents + deterministic HITL gates), and (6) **Managed Runtime** (`agent_runtime` / Vertex AI Agent Engine).
2. **Capacity Assurance (`Provisioned Throughput` + `PayGo Spillover`):** Size reserved GSUs for steady production baseline traffic to guarantee consistent latency and avoid noisy-neighbor throttling, while enabling automatic PayGo spillover for traffic spikes.
3. **Continuous EvalOps & 3-Layer Drift Monitoring:** Run automated evaluation suites (`agents-cli eval` / Vertex AI Evaluation) on every prompt/tool/model change, and monitor production for (a) Infrastructure SLIs, (b) Retrieval/Embedding Skew, and (c) Output Quality/Groundedness Drift.

### 3.2 Financial Services (FSI) Perspective (`/architecture/framework/perspectives/fsi`)
1. **3-Layer FSI Defense-in-Depth Landing Zone:**
   - **Layer 1 — Sovereignty & Regulatory Governance:** `Assured Workloads`, `constraints/gcp.resourceLocations`, `Access Transparency`, and `Access Approval`.
   - **Layer 2 — Zero-Trust Network & API Perimeter:** Shared VPC micro-segmentation + `VPC Service Controls (VPC-SC)` + `Private Service Connect` + `Cloud Armor` + `IAP`.
   - **Layer 3 — Cryptographic Control & Immutable Auditability:** `Cloud KMS (CMEK / Cloud HSM / Cloud EKM)` with separation of duties between Key Admins and Workload Admins + immutable WORM `Cloud Audit Logs` (`Bucket Lock`) + `Sensitive Data Protection (DLP)` tokenization.
2. **Systemic Operational Resilience (DORA / Banking Regulators):** Explicit composite availability calculation across all dependencies, multi-zone/multi-region HA, deterministic circuit breakers, and scheduled chaos/regional-failover game days verifying RTO and RPO.
