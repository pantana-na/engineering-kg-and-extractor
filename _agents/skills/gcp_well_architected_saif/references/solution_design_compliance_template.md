# Solution Design & SDD Compliance Template: Google Cloud Well-Architected Framework (WAF) & Secure AI Framework (SAIF)

Use this template to embed a complete **WAF + SAIF Architecture & Governance Section** inside any Solution Design document (e.g., Task 2 Solution Design), Feature Specification (`specs/features/SPEC-*.md`), or standalone architecture audit report (`docs/waf-saif-review_<project>.md`).

---

## 1. Google Cloud Well-Architected Framework (WAF) 6-Pillar Alignment Matrix

| WAF Pillar | Target Architectural Principles Applied | Concrete Google Cloud Services & Configurations | Quantified Target / Verification Gate |
| :--- | :--- | :--- | :--- |
| **1. Operational Excellence** | CloudOps readiness; IaC & CI/CD automation; incident management via SLOs; blameless RCA. | - **Terraform + Infrastructure Manager** (`nonprod` / `prod` isolation)<br>- **Cloud Build** (`cloudbuild.yaml`) canary rollouts + auto-rollback<br>- **Cloud Logging** (structured JSON + trace correlation), **Cloud Monitoring** (SLO burn-rate alerts), **Cloud Trace** (OpenTelemetry) | - 100% IaC coverage (zero ClickOps)<br>- Automated rollback on `/healthz` or eval failure |
| **2. Security, Privacy, and Compliance** | Zero Trust (*never trust, always verify*); Shift-left security; Defense-in-depth perimeter & encryption; SAIF alignment; Regulatory compliance. | - **Pattern 1A (Global External ALB + Cloud Armor + IAP)**, **Pattern 1B (Direct Cloud Run IAP `--iap` + `x-goog-iap-jwt-assertion` check + ADR trade-off)**, or **Pattern 2 (Verified OAuth 2.0/OIDC + Cloud Armor)**<br>- **VPC Service Controls (VPC-SC)** + **Private Service Connect**<br>- **Cloud KMS (CMEK / HSM / EKM)** + **Secret Manager**<br>- **CodeMender** SAST + **Artifact Analysis** + **SLSA Level 3 / Binary Authorization**<br>- **Assured Workloads** + `constraints/gcp.resourceLocations` + immutable **Cloud Audit Logs** (`Bucket Lock`) | - Zero `allUsers` IAM bindings<br>- Zero High/Critical SAST/CVE findings<br>- 100% CMEK & VPC-SC coverage on stateful/AI services |
| **3. Reliability** | User-experience SLIs; realistic SLOs (<100%) + Error Budgets; multi-zone/multi-region redundancy; horizontal scalability; graceful degradation; DR drills. | - Multi-zone **Cloud Run** + regional HA **AlloyDB/Spanner/BigQuery** + cross-region DR replication<br>- **Vertex AI Provisioned Throughput** with automatic **PayGo spillover**<br>- Bounded timeouts, retries with exponential backoff + jitter, circuit breakers, and transparent degraded-mode responses (zero fake/mockup data) | - Composite Availability SLO: `[e.g., 99.95%]`<br>- RTO: `[e.g., <= 15 min]` / RPO: `[e.g., <= 5 min]` |
| **4. Cost Optimization** | FinOps lifecycle (*Inform $\rightarrow$ Optimize $\rightarrow$ Operate*); Unit Economics; right-sizing & commitments; continuous waste elimination. | - Mandatory cost labels (`env`, `service`, `owner`, `cost_center`) + **BigQuery Billing Export** + Budgets & Anomaly Alerts<br>- `nonprod` Cloud Run scale-to-zero (`min-instances=0`)<br>- **Vertex AI Context Caching**, **Model Routing** (Gemini Flash vs. Pro), **Batch API** (-50% for offline evals), and CUDs / Provisioned Throughput baselines | - Unit Economics KPI: `[e.g., $X.XX per 1,000 turns / resolved case]`<br>- 50%–90% cached input token savings |
| **5. Performance Optimization** | Co-located resource allocation; elastic scaling; modular streaming & parallel fan-out; continuous latency profiling. | - Co-located single-region compute, Agent Engine, Model Armor, KMS, and data stores<br>- End-to-end SSE/WebSocket streaming (`X-Accel-Buffering: no`)<br>- **Cloud CDN**, **Memorystore**, **Vertex AI Context Caching**, parallel `FunctionTool` execution, Cloud Run **Startup CPU Boost** + `prod` `min-instances` | - TTFT: `[e.g., p95 <= 800ms]`<br>- End-to-End Latency: `[e.g., p95 <= 2.5s]` |
| **6. Sustainability** | Low-carbon (`High CFE %`) region selection; AI work-per-watt efficiency; storage/log TTL hygiene; carbon measurement. | - **Google Cloud Region Picker** high-CFE region within residency/latency bounds<br>- Tiered Flash/Pro routing + Context Caching + scale-to-zero idle compute<br>- BigQuery/Cloud Storage TTL lifecycles + **Carbon Footprint export to BigQuery** | - Selected Region CFE % documented<br>- 100% staging/log buckets have TTL rules |

---

## 2. Cross-Pillar Architectural Trade-Off & ADR Matrix

| ADR ID | Competing WAF Pillars / Constraints | Architectural Tension | Selected Resolution & Justification |
| :--- | :--- | :--- | :--- |
| **ADR-01** | **Security & Compliance** vs. **Performance (Latency)** | Inline Model Armor + Cloud DLP tokenization + CMEK/VPC-SC inspection adds per-turn latency vs. strict p95 response budget. | Co-locate Cloud Run, Agent Runtime, Model Armor, DLP, KMS, and databases in the **same GCP region**; use **Vertex AI Context Caching** and end-to-end SSE token streaming to keep p95 within SLA while enforcing 100% inline security. |
| **ADR-02** | **Reliability (HA / Quota Assurance)** vs. **Cost Optimization** | Reserving peak GenAI capacity (`Provisioned Throughput`) and multi-region active-active compute 24/7 increases baseline cost. | Size **Provisioned Throughput (GSUs)** for steady baseline load with automatic **PayGo spillover** for burst peaks; enforce multi-zone/multi-region HA in `prod` while scaling `nonprod` to zero (`min-instances = 0`). |
| **ADR-03** | **Sustainability & Cost** vs. **Data Sovereignty & Latency** | Lowest-carbon or lowest-cost region may sit outside regulatory residency boundaries or far from end users. | Filter candidate regions first by hard **Assured Workloads / Data Residency (`gcp.resourceLocations`)** and user RTT bounds, then select the highest **CFE %** region within that compliant set. |

---

## 3. Google Secure AI Framework (SAIF & SAIF 2.0) 15-Risk Mitigation Matrix

| SAIF Risk ID & Name | Lifecycle Layer | Architectural Control & Native Google Cloud Mitigation | Verification Method |
| :--- | :--- | :--- | :--- |
| **`DP` — Data Poisoning** | Data | Locked ingestion IAM (`roles/storage.objectCreator` only for verified pipeline SA), SHA-256 document checksums, versioned corpus promotion gate. | Integration test & IAM policy audit |
| **`UTD` — Unauthorized Training Data** | Data | Zero customer-data training policy on Vertex AI; pre-ingestion **Sensitive Data Protection (Cloud DLP)** classification & redaction. | Org Policy & DLP scan report |
| **`EDH` — Excessive Data Handling** | Data / App | Bidirectional **Cloud DLP** de-identification/tokenization in `before_agent_callback` before prompts reach LLM, context cache, `agentengine://`, or Cloud Logging. | Unit + Property-Based Test (PBT) verifying zero raw PAN/SSN in logs/prompts |
| **`MST` — Model Source Tampering** | Infrastructure | Pre-build **CodeMender** SAST (`cm find/verify/fix`), **Artifact Analysis**, **SLSA Level 3 provenance**, and **Binary Authorization**. | Cloud Build gate & Binary Auth policy |
| **`MXF` — Model Exfiltration** | Infrastructure | **VPC Service Controls (VPC-SC)** perimeter around Vertex AI, Agent Runtime, BigQuery, and Cloud Storage; **CMEK** encryption. | VPC-SC dry-run/enforced policy check |
| **`MDT` — Model Deployment Tampering** | Infrastructure | Immutable container digests (`${_ENVIRONMENT}-${SHORT_SHA}`), Binary Authorization, declarative Terraform via **Infrastructure Manager**. | Terraform state & drift check |
| **`DMS` — Denial of ML Service** | Infra / App | **Cloud Armor** edge rate limiting *(or app-layer per-user rate caps under Pattern 1B)*, per-session ADK step/turn ceiling (`max_steps`) & token timeout budget, **Provisioned Throughput + PayGo spillover**. | Load test & PBT step-bound check |
| **`MRE` — Model Reverse Engineering** | Model / Infra | Per-user rate throttling, hardened system prompt boundaries, **SCC AI Protection** anomalous query detection. | Cloud Armor / app rate-limit & SCC alert policy |
| **`IIC` — Insecure Integrated Component** | Model / App | Dependency CVE scanning, strict `FunctionTool` registry allowlist, **SCC AI Protection** agent/MCP discovery, zero raw SQL/shell execution tools. | `pip-audit` / `npm audit` & CodeMender |
| **`PIJ` — Prompt Injection (Direct & Indirect)** | Model / App | **Model Armor** screening on `before_agent_callback` (Direct `PIJ`) AND `after_tool_callback` on all untrusted RAG chunks/tool outputs (Indirect `PIJ`). | `agents-cli eval` 100% adversarial block rate |
| **`MEV` — Model Evasion** | Model | Input canonicalization/normalization before Model Armor inspection + continuous red-team dataset regression in CI/CD. | Red-team eval suite in `evals/datasets/` |
| **`SDD` — Sensitive Data Disclosure** | Model / App | **`User Auth`** OAuth2 propagation enforcing per-user RAG/DB ACLs + `after_model_callback` **Cloud DLP** output scrubbing & URL allowlisting. | Cross-tenant isolation test & DLP output PBT |
| **`ISD` — Inferred Sensitive Data** | Model / App | Strict caller-scoped query filtering (zero cross-customer aggregation) and output granularity bounds. | Authorization boundary unit tests |
| **`IMO` — Insecure Model Output** | Application | $1.000$ groundedness verification against authoritative citations, Pydantic schema validation, safe UI escaping, and outbound URL allowlist. | `agents-cli eval` ($1.000$ groundedness) |
| **`RAC` — Rogue Actions (Agentic Risk)** | Application | Read-only retrieval subagent principals; **`User Auth`** propagation; deterministic microservice policy/monetary caps; **externalized signed HITL gate**; idempotency keys. | PBT & integration test verifying unconfirmed/over-cap mutations are deterministically rejected |

---

## 4. SAIF 2.0 Autonomous Agent Trust-Boundary Checklist

- [ ] **Human Controller Authentication:** Cloud Run ingress uses **Pattern 1A (ALB + Cloud Armor + IAP)**, **Pattern 1B (Direct Cloud Run IAP `--iap` + `x-goog-iap-jwt-assertion` verification for internal single-region apps)**, or **Pattern 2 (App-Level OAuth 2.0/OIDC + Cloud Armor)**. Pattern 3 (`invoker-iam-disabled`) is **not** used for internal or AI endpoints.
- [ ] **Anti-Confused-Deputy (`User Auth` + `Agent Identity`):** Down-scoped end-user OAuth2 identity is propagated to downstream tools and RAG stores alongside attested Agent Identity.
- [ ] **Read-Only vs. Mutating Subagent Separation:** Informational/RAG subagents run with strictly read-only IAM permissions.
- [ ] **Externalized Deterministic HITL Gate:** State-mutating, financial, or destructive tools enforce hard policy caps in deterministic code and verify an external human confirmation signature outside the LLM context window.
- [ ] **4-Point Model Armor + Cloud DLP Hooks:** Wired across `before_agent_callback`, `before_model_callback`, `after_tool_callback` (Indirect Prompt Injection), and `after_model_callback` (output DLP + URL allowlist).
- [ ] **Pinned Model IDs & Execution Budgets:** Production uses explicit version-pinned model IDs and enforces per-session turn, recursion, timeout, and token ceilings.
