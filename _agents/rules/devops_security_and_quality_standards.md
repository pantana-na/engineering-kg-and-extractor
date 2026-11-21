---
trigger: model_decision
description: "Load and enforce this rule whenever configuring Git branches, running static code quality analysis, executing CodeMender SAST (cm), managing .env and Secret Manager/CMEK parameters, writing Dockerfiles or Cloud Build pipelines (cloudbuild.yaml), configuring Cloud Run services (/healthz, logging, monitoring, SLOs, Cloud Armor, VPC-SC), writing Terraform Infrastructure Manager IaC, or designing Zero-Trust IAM/Ingress authentication."
---

# Rule: DevOps, Quality, WAF 6-Pillar Security & Cloud Architecture Standards

## Core Mandate (Rules 1–10 — Wired to `ai-sdlc` Master Hub)
Orchestrated by the **[`ai-sdlc` master skill (`../skills/ai_sdlc/SKILL.md`)](../skills/ai_sdlc/SKILL.md)** alongside the 3-Phase AI-SDLC and Spec-Driven Development (SDD) standard ([`ai_sdlc_and_sdd_standards.md`](./ai_sdlc_and_sdd_standards.md)), all software engineering, repository management, CI/CD pipeline automation, and cloud deployments must strictly adhere to the **[Google Cloud Well-Architected Framework (WAF — All 6 Pillars)](https://docs.cloud.google.com/architecture/framework)** and **[Google Secure AI Framework (SAIF)](https://safety.google/intl/en/safety/saif/)** (governed by [`_agents/skills/gcp_well_architected_saif/SKILL.md`](../skills/gcp_well_architected_saif/SKILL.md), which takes strict precedence in case of conflict) across **Rules 1 through 10** below:

---

## Rule 1: Repository Management & Multi-Branch Environment Strategy (WAF Design for Change)
1. **Mandatory Single SCM Repository:** All source code, specifications, tests, configuration templates, and pipeline definitions must be version-controlled in a single **GitHub** repository.
2. **Branch-Based Multi-Environment Separation:**
   - The application manages **Non-Production (Non-Prod / Dev)** and **Production (Prod)** environments within the same repository using dedicated Git branches:
     - **Non-Prod Branch (`main` / `develop`):** Houses active development, feature integration, and continuous deployment to the Non-Prod environment.
     - **Prod Branch (`prod` / `release`):** Dedicated to stable, customer-facing production releases. Code is promoted to `prod` strictly via reviewed Pull Requests from the Non-Prod branch.
   - Commits must follow conventional commit standards with clear, descriptive scopes.
3. **Environment Promotion & Quality Gate:** No code may be merged to the `prod` branch without passing static code quality analysis, SAST, unit & property tests, WAF/SAIF compliance checks, and non-prod post-deployment verification.
4. **No Unversioned Artifacts:** No deployment or release shall occur from uncommitted or untracked local changes.

---

## Rule 2: Post-Commit Static Code Quality Analysis (WAF Shift-Left Quality)
1. **Automated Quality Inspection:** Automated static code quality analysis must run automatically on commits and pull requests.
2. **Detection Scope:**
   - Identification of bugs, logic flaws, and dead code.
   - Code smells, complexity thresholds, and maintainability issues.
   - Code duplication and styling conformance.
   - TypeScript / JavaScript / Python type checking and strict linting.
3. **Quality Gate:** Code that fails static analysis quality gates or introduces critical code smells must be remediated prior to merge.

---

## Rule 3: Pre-Build & Pre-Deploy SAST (Static Application Security Testing via CodeMender — WAF Shift-Left & SAIF `MST`/`IIC`)
1. **Mandatory SAST & Vulnerability Lifecycle:** Static Application Security Testing and vulnerability remediation must be executed prior to build and deployment using the **CodeMender skill** (`_agents/skills/codemender/SKILL.md`).
2. **Tooling & CodeMender (`cm` CLI) Workflow:**
   - **Discovery (`cm find`):** Scan source files and configs for software weaknesses (`cm find <target_path> -y --bypass-warning`), generating `docs/codemender-01-vulnerability-scan-report.md`.
   - **Verification & Triage (`cm verify`):** Synthesize and run isolated PoC exploits in local sandboxes to eliminate false positives (`cm verify <finding_id> -y --bypass-warning`), generating `docs/codemender-02-verification-report.md`.
   - **Automated Remediation (`cm fix`):** Refactor vulnerable code constructs and validate regression test suites (`cm fix <finding_id> -y --bypass-warning`), generating `docs/codemender-03-remediation-report.md`.
3. **Zero High/Critical Vulnerabilities:** Builds and deployments must fail if unaddressed High or Critical security vulnerabilities are detected in application code. Master security summary reports must be published to `docs/codemender-security-audit-summary.md`.

---

## Rule 4: Artifact Analysis, Open-Source Dependency Security & Supply-Chain Attestation (SAIF `MST`/`MDT`)
1. **Automated Vulnerability & License Compliance:** Use **Google Cloud Artifact Analysis** (Container Analysis) to scan all container images stored in Artifact Registry.
2. **Dependency Risk Management:**
   - Automatically analyze open-source packages (npm packages, Python libraries, OS base packages) for known CVEs (`npm audit`, `pip-audit`, Artifact Analysis).
   - Verify license compliance across all third-party dependencies to eliminate restrictive or incompatible licenses.
3. **SLSA Level 3 Provenance & Binary Authorization:**
   - Generate verifiable **SLSA build provenance** in Cloud Build and enforce **Google Cloud Binary Authorization** policies so only cryptographically signed, attested container images built by trusted pipelines can deploy to Cloud Run.

---

## Rule 5: Multi-Environment Cloud Build Automation & Artifact Registry Storage (WAF Operational Excellence)
1. **Branch-Aware Automated Builds:** Use **Google Cloud Build** (`cloudbuild.yaml`) as the automated build, test, and deployment engine mapped to the active branch:
   - Commits to the **Non-Prod branch** trigger automated builds and deployment targeting the **Non-Prod environment**.
   - Merges/tags on the **Prod branch** trigger production verification, progressive canary revision traffic splitting, and deployment targeting the **Production environment**.
2. **Artifact Registry Repository & Environment Tagging:**
   - Container images and deployment packages are stored in **Google Cloud Artifact Registry** (encrypted with **CMEK** where required by compliance).
   - Container image tags must include immutable identifiers with environment tagging (`${_ENVIRONMENT}-${SHORT_SHA}`, semantic release tags) and deploy by immutable digest.
3. **Isolated & Reproducible Builds:** Builds must execute within containerized Cloud Build steps without host-specific assumptions.

---

## Rule 6: Cloud Run Observability, Reliability, Performance & Container Hardening (WAF Pillars 1, 3, 5)
1. **Target Workloads & Stateless Streaming Reverse Proxy on Cloud Run:**
   - **Google Cloud Run** is the dedicated stateless runtime for web frontend applications (React/Vite), API gateways, externalized deterministic HITL/policy verification endpoints, and thin streaming reverse proxies (`server/`). Conversational AI agent reasoning engines are decoupled and hosted on the **Gemini Enterprise Agent Platform (`agent_runtime`)** ([`google_adk_and_agent_runtime.md`](./google_adk_and_agent_runtime.md)).
   - **Streaming Proxy & Performance Configuration (WAF Pillar 5):** Cloud Run proxies forwarding SSE/WebSocket conversational streams from `agent_runtime` must configure explicit request timeouts (`timeout = "300s"` to `"900s"`), disable response buffering (`X-Accel-Buffering: no`, `Cache-Control: no-cache`), enable **Startup CPU Boost** (and `min-instances >= 1` in `prod` to eliminate cold starts on latency-critical paths), co-locate in the **same GCP region** as `agent_runtime` and data stores, and remain strictly stateless (propagating `session_id` and verified end-user `User Auth` identity headers to `agent_runtime`).
2. **Container & Dockerfile Hardening:**
   - All Dockerfiles must use multi-stage builds, pin minimal/distroless base images, and execute the runtime process as a **non-root user (`USER nonroot` / UID $\ge 1000$)**.
3. **Liveness Probes, Multi-Zone HA & Graceful Degradation (WAF Pillar 3):**
   - Applications running on Cloud Run must expose a dedicated health endpoint (`/healthz` or `/api/health`) verifying downstream readiness, wired to Cloud Run **Startup and Liveness Probes**.
   - Implement **bounded timeouts, retries with exponential backoff + jitter, circuit breakers, and transparent degraded-mode responses** (never returning synthetic/mockup fake records).
4. **Cloud Logging, Cloud Monitoring SLOs & Cloud Trace (WAF Pillar 1):**
   - Application logs must output structured JSON to `stdout`/`stderr` correlated with `logging.googleapis.com/trace`, `spanId`, `session_id`, and `agent_runtime` invocation latency (with PII/PCI tokenized via **Sensitive Data Protection / Cloud DLP**).
   - Enable **Cloud Trace** (OpenTelemetry) across UI proxy, Agent Engine, and databases, and configure **Cloud Monitoring Service Monitoring** dashboards, explicit **SLIs/SLOs (<100%)**, and **Error Budget multi-window burn-rate alerts** covering availability, p95/p99 latency, Time-to-First-Token (TTFT), 5xx error rates, and Vertex AI quota saturation.

---

## Rule 7: Post-Deployment Integration, Smoke Testing & Automated Rollback (WAF Reliability)
1. **Automated Post-Deploy Verification:** Immediately after deploying a new revision to Cloud Run (using progressive canary/revision traffic tags), an automated integration/smoke test step must execute against the deployed service URL.
2. **Verification Scope:**
   - Liveness probe verification (`GET /healthz` returns `200 OK`).
   - Core API functionality verification (backend proxy connectivity, Zero-Trust authentication handshake, Model Armor readiness).
   - End-to-end sanity check ensuring the deployed revision meets latency and health targets.
3. **Automated Rollback on Failure:** If post-deployment integration tests or SLO checks fail, deployment notifications must alert the team, and immediate revision traffic rollback must be triggered.

---

## Rule 8: Centralized `.env` Parameter Management, Secret Manager & Cloud KMS / CMEK Boundary (WAF Pillar 2 & SAIF Element 1)
1. **Zero Hardcoding & Pinned Model IDs:** No configurable parameters may be hardcoded in application source code, Dockerfiles, or client-side scripts. Model parameters (`DEFAULT_MODEL`) must specify explicit **version-pinned model IDs** (e.g., `gemini-2.5-pro-001`, never floating aliases).
2. **Unified Multi-Environment Configuration File:**
   - Non-sensitive configuration parameters for **both Non-Prod and Prod environments** must be maintained in the **same unified `.env` file** (with a documented template in `.env.example`).
   - The `.env` file structure organizes variables into:
     - **Shared / Core Section:** Base settings common to all environments (`GCP_PROJECT`, `GCP_REGION`, `GENAI_LOCATION`, `DEFAULT_MODEL`, `FAST_MODEL`, `ARTIFACT_REGISTRY_REPO`, `GITHUB_REPO`).
     - **Non-Prod Configuration Block (`NONPROD_*`):** Non-prod specific values (`NONPROD_ENVIRONMENT_NAME=development`, `NONPROD_FRONTEND_SERVICE_NAME`, `NONPROD_BACKEND_SERVICE_NAME`, `NONPROD_AGENT_RESOURCE_NAME`, `NONPROD_DEPLOYMENT_ID`, `NONPROD_MIN_INSTANCES=0`, `NONPROD_MAX_INSTANCES=5`, service accounts, Model Armor & KMS resource IDs).
     - **Prod Configuration Block (`PROD_*`):** Prod specific values (`PROD_ENVIRONMENT_NAME=production`, `PROD_FRONTEND_SERVICE_NAME`, `PROD_BACKEND_SERVICE_NAME`, `PROD_AGENT_RESOURCE_NAME`, `PROD_DEPLOYMENT_ID`, `PROD_MIN_INSTANCES=1`, `PROD_MAX_INSTANCES=10`, service accounts, Model Armor & KMS resource IDs).
3. **Secret Isolation, Google Cloud Secret Manager & Cloud KMS (CMEK):**
   - Sensitive credentials must NEVER be committed to GitHub or passed in plaintext in `cloudbuild.yaml` / `.tf` files. Local development uses `.env` (strictly ignored by `.gitignore`) or ADC.
   - In Cloud Run and Agent Runtime, sensitive secrets must be stored in **Google Cloud Secret Manager** and injected via `secret_key_ref` (Terraform) with `roles/secretmanager.secretAccessor` granted only to the workload's dedicated Service Account.
   - For regulated workloads (e.g., FSI/Healthcare), enforce **Customer-Managed Encryption Keys (CMEK)** via **Cloud KMS** (or **Cloud HSM / Cloud EKM**) with automated key rotation and separation of duties across Secret Manager, BigQuery, Cloud Storage, AlloyDB/Cloud SQL, Artifact Registry, Vertex AI, and Cloud Logging sinks.

---

## Rule 9: Multi-Environment Terraform IaC, VPC-SC, FinOps & Sustainability (WAF Pillars 1, 2, 4, 6)
1. **Infrastructure as Code (IaC) & Dedicated Least-Privilege Service Accounts:**
   - All GCP resources (Cloud Run, Load Balancers, Cloud Armor, IAP, VPC-SC perimeters, KMS keys, Artifact Registry, Secret Manager, IAM, monitoring SLO alerts) are declaratively codified in **Terraform** (`terraform/` directory).
   - **Strict Least-Privilege Service Accounts:** Every Cloud Run service and Agent Runtime workload must run under a dedicated, environment-scoped Service Account (`<service>-nonprod-sa@...`, `<service>-prod-sa@...`) with `constraints/iam.disableServiceAccountKeyCreation` enforced (zero exported JSON keys). Using the default Compute Engine Service Account or primitive roles (`roles/editor`, `roles/owner`) is strictly prohibited.
2. **VPC Service Controls (VPC-SC) & Private Networking (WAF Pillar 2 & SAIF `MXF`/`SDD`):**
   - Wrap sensitive data and AI services (`Vertex AI`, `Agent Runtime`, `BigQuery`, `Cloud Storage`, `AlloyDB/Cloud SQL`, `Secret Manager`, `Cloud KMS`) inside a **VPC Service Controls (VPC-SC)** perimeter and use **Private Service Connect (PSC)** / Serverless VPC Access to block unauthorized API data exfiltration.
3. **Independent Infrastructure Manager Deployments:**
   - Non-Prod and Prod environments are provisioned as independent **Google Cloud Infrastructure Manager** deployments (`<service>-nonprod` vs `<service>-prod`) tied to specific Git SHAs with drift detection.
4. **FinOps Cost Governance & Sustainability (WAF Pillars 4 & 6):**
   - **FinOps Labels & Budgets (Pillar 4):** Apply mandatory resource labels (`env`, `service`, `owner`, `cost_center`) across all Terraform resources; configure **Cloud Billing Budgets & Anomaly Alerts**, track **Unit Economics** (`$ / 1,000 turns` or `$ / resolved inquiry`), scale `nonprod` to zero (`min-instances = 0`), and enforce BigQuery `maximum_bytes_billed` + partition/cluster hygiene.
   - **Sustainability (Pillar 6):** Select low-carbon regions (**High CFE % / `Low CO2`** in the Google Cloud Region Picker) within regulatory data-residency (`constraints/gcp.resourceLocations`) and latency bounds; enforce storage/log TTL lifecycle rules to purge dark data; and enable **Carbon Footprint export to BigQuery**.

---

## Rule 10: WAF Zero-Trust IAM, Domain Restricted Sharing & Ingress Architecture Standards (WAF Pillar 2 & SAIF Principle 1)
1. **Organization Policy Constraint (Domain Restricted Sharing):**
   - The GCP organization enforces `constraints/iam.allowedPolicyMemberDomains`, which strictly forbids adding `allUsers`, `allAuthenticatedUsers`, or identities outside permitted domains to IAM policies.
   - Agents and developers **MUST NEVER** write `allUsers` or `allAuthenticatedUsers` to Terraform `google_cloud_run_v2_service_iam_member` resources or GCP IAM policy bindings.
2. **Mandatory WAF Zero-Trust Authentication & Ingress Patterns (*"Never Trust, Always Verify"*):**
   In strict compliance with the **Google Cloud Well-Architected Framework (Security Pillar — Zero Trust)** and **Google SAIF Principle 1 (*Well-Defined Human Controllers*)**, select the compliant pattern based on workload classification:
   - **Pattern 1A: Global External Application Load Balancer + Cloud Armor + Identity-Aware Proxy (IAP) *(Recommended Default for Tier-1 Production, Multi-Region, Custom-Domain, External/B2B & Regulated FSI/Healthcare Apps)*:**
     - Deploy Cloud Run behind a Global External HTTPS Application Load Balancer with Serverless NEG and **Google Cloud Armor** (OWASP Top 10 WAF rules, Adaptive L7 DDoS protection, rate limiting).
     - Restrict Cloud Run ingress to `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER` (blocking direct `*.run.app` bypass).
     - Enforce context-aware Zero-Trust authentication and Google Workspace / Workforce Identity Federation authorization (`roles/iap.httpsResourceAccessor`) at the **IAP** gateway edge, cryptographically verify `x-goog-iap-jwt-assertion`, and propagate verified user identity to Cloud Run and `agent_runtime`. Zero `allUsers` IAM binding required.
   - **Pattern 1B: Direct Cloud Run Identity-Aware Proxy (`--iap`, No Load Balancer) *(Permitted for Internal Workforce Tools, Back-Office Dashboards, Single-Region Apps, PoCs & Non-Prod / Cost-Optimized Workloads)*:**
     - Enable native Direct IAP directly on the Cloud Run service (`--iap` / `iap_enabled = true`) with `INGRESS_TRAFFIC_ALL` *(required by Google Cloud so Google's global IAP edge proxy can route to the service without an ALB)* and `--no-allow-unauthenticated` (granting `roles/run.invoker` exclusively to the project's IAP Service Agent `service-<PROJECT_NUMBER>@gcp-sa-iap.iam.gserviceaccount.com` + authorized internal SAs; zero `allUsers` or `allAuthenticatedUsers`).
     - **Mandatory WAF Compensating Safeguards & ADR Trade-Off:**
       1. Backend code **MUST** cryptographically validate the `x-goog-iap-jwt-assertion` JWT header (signature, issuer `https://cloud.google.com/iap`, and exact Cloud Run service audience) on every request — never trusting unverified `X-Goog-Authenticated-User-Email` headers alone.
       2. Compensate for omitting Cloud Armor by enforcing strict schema validation, parameterized queries, `max-instances` caps, and app-level per-user rate/token budgets, and isolate any Pub/Sub/Eventarc/Scheduler OIDC push endpoints onto a separate private Cloud Run service.
       3. Record the cross-pillar trade-off (*Cost Optimization `$0` idle baseline & simplicity vs. no Cloud Armor L7 WAF, single-region `*.run.app` endpoint, and no Cloud CDN*) in the **ADR Log (SDD §7)**. *Not permitted for external-facing portals or regulated workloads mandating edge L7 WAF.*
   - **Pattern 2: App-Level OAuth 2.0 / OIDC + Cloud Armor *(Permitted for Apps Requiring Custom OIDC / Google Sign-In UX)*:**
     - Front Cloud Run with **Cloud Armor** rate-limiting/WAF (or direct HTTPS with strict L7 rate limiting) and `run.googleapis.com/invoker-iam-disabled = "true"` (empty IAM policy, zero Org Policy violations).
     - Authenticate every user request via OAuth 2.0 / OIDC (Google Identity Services / Customer IdP) in the frontend and **cryptographically verify the ID/access token on every backend API/streaming request** before invoking `agent_runtime` or data stores.
   - **Pattern 3: Restricted Public Anonymous Ingress (`invoker-iam-disabled = "true"`) *(STRICTLY RESTRICTED to Approved Anonymous Public Non-Sensitive Static/Marketing Frontends ONLY)*:**
     - **WAF + SAIF Restriction:** Pattern 3 (`run.googleapis.com/invoker-iam-disabled = "true"` with unauthenticated access) is **STRICTLY PROHIBITED for internal enterprise tools, employee portals, regulated workloads, or any endpoint that directly invokes AI agents or accesses internal data**.
     - Where explicitly approved by stakeholders for a public anonymous non-sensitive frontend, it must still be fronted by **Cloud Armor DDoS/rate-limiting**, and all backend API/agent services must remain strictly private (`INGRESS_TRAFFIC_INTERNAL_ONLY` with `roles/run.invoker` granted exclusively to the frontend Service Account plus session/CAPTCHA abuse controls).

