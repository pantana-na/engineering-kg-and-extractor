---
trigger: model_decision
description: "Load and enforce this rule whenever configuring Git branches, running static code quality analysis, executing CodeMender SAST (cm), managing .env parameters, writing Dockerfiles or Cloud Build pipelines (cloudbuild.yaml), configuring Cloud Run services (/healthz, logging, monitoring), writing Terraform Infrastructure Manager IaC, or designing IAM/Ingress authentication."
---

# Rule: DevOps, Quality, Security & Cloud Architecture Standards

## Core Mandate
In addition to the 3-Phase AI-SDLC and Spec-Driven Development (SDD) ([`ai_sdlc_and_sdd_standards.md`](./ai_sdlc_and_sdd_standards.md)), all software engineering, repository management, CI/CD pipeline automation, and cloud deployments must strictly adhere to the following 10 fundamental rules:

---

## Rule 1: Repository Management & Multi-Branch Environment Strategy
1. **Mandatory Single SCM Repository:** All source code, specifications, tests, configuration templates, and pipeline definitions must be version-controlled in a single **GitHub** repository.
2. **Branch-Based Multi-Environment Separation:**
   - The application manages **Non-Production (Non-Prod / Dev)** and **Production (Prod)** environments within the same repository using dedicated Git branches:
     - **Non-Prod Branch (`main` / `develop`):** Houses active development, feature integration, and continuous deployment to the Non-Prod environment.
     - **Prod Branch (`prod` / `release`):** Dedicated to stable, customer-facing production releases. Code is promoted to `prod` strictly via reviewed Pull Requests from the Non-Prod branch.
   - Commits must follow conventional commit standards with clear, descriptive scopes.
3. **Environment Promotion & Quality Gate:** No code may be merged to the `prod` branch without passing static code quality analysis, SAST, unit & property tests, and non-prod post-deployment verification.
4. **No Unversioned Artifacts:** No deployment or release shall occur from uncommitted or untracked local changes.

---

## Rule 2: Post-Commit Static Code Quality Analysis
1. **Automated Quality Inspection:** Automated static code quality analysis must run automatically on commits and pull requests.
2. **Detection Scope:**
   - Identification of bugs, logic flaws, and dead code.
   - Code smells, complexity thresholds, and maintainability issues.
   - Code duplication and styling conformance.
   - TypeScript / JavaScript type checking and strict linting.
3. **Quality Gate:** Code that fails static analysis quality gates or introduces critical code smells must be remediated prior to merge.

---

## Rule 3: Pre-Build & Pre-Deploy SAST (Static Application Security Testing via CodeMender)
1. **Mandatory SAST & Vulnerability Lifecycle:** Static Application Security Testing and vulnerability remediation must be executed prior to build and deployment using the **CodeMender skill** (`_agents/skills/codemender/SKILL.md`).
2. **Tooling & CodeMender (`cm` CLI) Workflow:**
   - **Discovery (`cm find`):** Scan source files and configs for software weaknesses (`cm find <target_path> -y --bypass-warning`), generating `docs/codemender-01-vulnerability-scan-report.md`.
   - **Verification & Triage (`cm verify`):** Synthesize and run isolated PoC exploits in local sandboxes to eliminate false positives (`cm verify <finding_id> -y --bypass-warning`), generating `docs/codemender-02-verification-report.md`.
   - **Automated Remediation (`cm fix`):** Refactor vulnerable code constructs and validate regression test suites (`cm fix <finding_id> -y --bypass-warning`), generating `docs/codemender-03-remediation-report.md`.
3. **Zero High/Critical Vulnerabilities:** Builds and deployments must fail if unaddressed High or Critical security vulnerabilities are detected in application code. Master security summary reports must be published to `docs/codemender-security-audit-summary.md`.

---

## Rule 4: Artifact Analysis & Open-Source Dependency Security
1. **Automated Vulnerability & License Compliance:** Use **Google Cloud Artifact Analysis** (Container Analysis) to scan all container images stored in Artifact Registry.
2. **Dependency Risk Management:**
   - Automatically analyze open-source packages (npm packages, Python libraries, OS base packages) for known CVEs (Common Vulnerabilities and Exposures).
   - Verify license compliance across all third-party dependencies to eliminate restrictive or incompatible licenses.
3. **Continuous Monitoring:** Container images in Artifact Registry must be continuously scanned for newly published vulnerabilities.

---

## Rule 5: Multi-Environment Cloud Build Automation & Artifact Registry Storage
1. **Branch-Aware Automated Builds:** Use **Google Cloud Build** (`cloudbuild.yaml`) as the automated build, test, and deployment engine mapped to the active branch:
   - Commits to the **Non-Prod branch** trigger automated builds and deployment targeting the **Non-Prod environment**.
   - Merges/tags on the **Prod branch** trigger production verification and deployment targeting the **Production environment**.
2. **Artifact Registry Repository & Environment Tagging:**
   - Container images and deployment packages are stored in **Google Cloud Artifact Registry**.
   - Container image tags must include immutable identifiers with environment tagging (e.g., `${_ENVIRONMENT}-${SHORT_SHA}`, semantic release tags).
3. **Isolated & Reproducible Builds:** Builds must execute within containerized Cloud Build steps without host-specific assumptions.

---

## Rule 6: Cloud Run Observability, Container Hardening & Streaming Proxy Standards
1. **Target Workloads & Streaming Reverse Proxy on Cloud Run:**
   - **Google Cloud Run** is the dedicated runtime for web frontend applications (React/Vite), API gateways, and thin streaming reverse proxies (`server/`). Conversational AI agent reasoning engines are decoupled and hosted on the **Gemini Enterprise Agent Platform (`agent_runtime`)** ([`google_adk_and_agent_runtime.md`](./google_adk_and_agent_runtime.md)).
   - **Streaming Proxy Configuration:** Cloud Run proxies forwarding SSE/WebSocket conversational streams from `agent_runtime` must configure explicit request timeouts (e.g., `timeout = "300s"` to `"900s"`), disable response buffering (`X-Accel-Buffering: no`, `Cache-Control: no-cache`), and remain strictly stateless (propagating `session_id` and verified user identity headers to `agent_runtime`).
2. **Container & Dockerfile Hardening:**
   - All Dockerfiles must use multi-stage builds, pin minimal/distroless base images, and execute the runtime process as a **non-root user (`USER nonroot` / UID $\ge 1000$)**.
3. **Liveness & Health Probes:**
   - Applications running on Cloud Run must expose a dedicated health endpoint (`/healthz` or `/api/health`) verifying downstream readiness.
   - Cloud Run service configuration must declare a **Liveness Probe** (and Startup Probe) pointing to this endpoint to detect unresponsiveness and auto-restart failed containers.
4. **Cloud Logging & Monitoring:**
   - Application logs must output structured JSON to `stdout`/`stderr` including `trace`, `spanId`, `session_id`, and `agent_runtime` invocation latency.
   - Configure Cloud Monitoring dashboards and alert policies for container health, CPU/memory utilization, request latency (p95/p99), 5xx error rates, and Gemini API quota consumption.

---

## Rule 7: Post-Deployment Integration & Smoke Testing
1. **Automated Post-Deploy Verification:** Immediately after deploying a new revision to Cloud Run, an automated integration/smoke test step must execute against the deployed service URL.
2. **Verification Scope:**
   - Liveness probe verification (`GET /healthz`).
   - Core API functionality verification (e.g. backend proxy connectivity, authentication handshake).
   - End-to-end sanity check ensuring the deployed revision is fully operational.
3. **Automated Rollback on Failure:** If post-deployment integration tests fail, deployment notifications must alert the team, and traffic shifting/rollback must be triggered.

---

## Rule 8: Centralized Multi-Environment `.env` Parameter Management & Secret Manager Boundary
1. **Zero Hardcoding:** No configurable parameters may be hardcoded in application source code, Dockerfiles, or client-side scripts.
2. **Unified Multi-Environment Configuration File:**
   - Non-sensitive configuration parameters for **both Non-Prod and Prod environments** must be maintained in the **same unified `.env` file** (with a documented template in `.env.example`).
   - The `.env` file structure organizes variables into:
     - **Shared / Core Section:** Base settings common to all environments (e.g., `GCP_PROJECT`, `GCP_REGION`, `GENAI_LOCATION`, `DEFAULT_MODEL`, `ARTIFACT_REGISTRY_REPO`, `GITHUB_REPO`).
     - **Non-Prod Configuration Block (`NONPROD_*`):** Non-prod specific values (e.g., `NONPROD_ENVIRONMENT_NAME=development`, `NONPROD_FRONTEND_SERVICE_NAME`, `NONPROD_BACKEND_SERVICE_NAME`, `NONPROD_AGENT_RESOURCE_NAME`, `NONPROD_DEPLOYMENT_ID`, `NONPROD_MIN_INSTANCES=0`, `NONPROD_MAX_INSTANCES=5`, service accounts).
     - **Prod Configuration Block (`PROD_*`):** Prod specific values (e.g., `PROD_ENVIRONMENT_NAME=production`, `PROD_FRONTEND_SERVICE_NAME`, `PROD_BACKEND_SERVICE_NAME`, `PROD_AGENT_RESOURCE_NAME`, `PROD_DEPLOYMENT_ID`, `PROD_MIN_INSTANCES=1`, `PROD_MAX_INSTANCES=10`, service accounts).
   - CI/CD pipelines, build scripts, and local runners resolve the appropriate configuration block dynamically based on the active Git branch or target environment selection.
3. **Secret Isolation & Google Cloud Secret Manager Boundary:**
   - Sensitive credentials (database passwords, OAuth client secrets, external API keys) must NEVER be committed to GitHub or passed in plaintext in `cloudbuild.yaml` / `.tf` files.
   - Local development uses `.env` (strictly ignored by `.gitignore`).
   - In Cloud Run and Agent Runtime, sensitive secrets must be stored in **Google Cloud Secret Manager** and injected at runtime via `secret_key_ref` (Terraform) with `roles/secretmanager.secretAccessor` granted only to the workload's dedicated Service Account.

---

## Rule 9: Multi-Environment IaC & Least-Privilege IAM via Terraform & Infrastructure Manager
1. **Infrastructure as Code (IaC) & Dedicated Service Accounts:**
   - Cloud infrastructure resources (Cloud Run services, Artifact Registry repositories, Secret Manager references, IAM roles, service accounts, monitoring alerts) are declaratively codified in **Terraform** (`terraform/` directory), parameterized to support multiple environment deployments from a single codebase.
   - **Strict Least-Privilege Service Accounts:** Every Cloud Run service and Agent Runtime workload must run under a dedicated, environment-scoped Service Account (`<service>-nonprod-sa@...`, `<service>-prod-sa@...`). Using the default Compute Engine Service Account (`*-compute@developer.gserviceaccount.com`) or granting primitive roles (`roles/editor`, `roles/owner`) is strictly prohibited.
2. **Independent Infrastructure Manager Deployments:**
   - Non-Prod and Prod environments are provisioned as independent **Google Cloud Infrastructure Manager** deployments (e.g., `<service>-nonprod` vs `<service>-prod`, or `app-nonprod` vs `app-prod`), ensuring complete isolation of Terraform state, service lifecycle, and scaling profiles.
3. **Reproducible & Tracked Deployments:**
   - Infrastructure Manager deployment revisions must be tied to specific Git commits/SHAs, branch names, and Cloud Build runs.
   - Drift detection and automated rollbacks must be supported through Infrastructure Manager deployment manifests.

---

## Rule 10: IAM Domain Restricted Sharing & Authentication Architecture Standards
1. **Organization Policy Constraint (Domain Restricted Sharing):**
   - The GCP organization enforces `constraints/iam.allowedPolicyMemberDomains`, which strictly forbids adding `allUsers`, `allAuthenticatedUsers`, or identities outside the permitted customer domains to IAM policies.
   - Agents and developers **MUST NEVER** attempt to write `allUsers` or `allAuthenticatedUsers` to Terraform `google_cloud_run_v2_service_iam_member` resources or GCP IAM policy bindings.
2. **Mandatory Authentication & Ingress Recommendations:**
   When designing, configuring, or reviewing authentication and ingress for applications, the agent must recommend the appropriate compliant architectural pattern:
   - **Pattern 1: Identity-Aware Proxy (IAP) (Recommended for Production-Grade Enterprise External Apps):**
     - Deploy Cloud Run behind an External HTTPS Application Load Balancer with Serverless Network Endpoint Group (Serverless NEG).
     - Restrict Cloud Run ingress to `INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER`.
     - Enforce Google OAuth 2.0 and central IAM / Google Workspace group authorization at the IAP gateway edge. Zero `allUsers` IAM binding required.
   - **Pattern 2: App-Level Google OAuth 2.0 (Recommended for Internal Apps / PoCs requiring Google User Context):**
     - Deploy Cloud Run with direct ingress and annotation `run.googleapis.com/invoker-iam-disabled = "true"` (empty IAM policy, zero Org Policy violations).
     - Embed Google Identity Services (Sign in with Google) / OAuth 2.0 Client ID in the web frontend, and verify user ID tokens inside the backend application code.
   - **Pattern 3: Direct Unauthenticated Ingress (Recommended for Public / Friction-Free Internal Web Tools):**
     - Deploy Cloud Run frontend service with `annotations = { "run.googleapis.com/invoker-iam-disabled" = "true" }` and `ingress = "INGRESS_TRAFFIC_ALL"`.
     - Zero IAM policy member bindings on the public frontend service (100% Org Policy compliant).
     - Backend API services remain strictly private (`roles/run.invoker` granted exclusively to the frontend Service Account).
