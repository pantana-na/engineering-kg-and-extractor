# Implementation Progress Report: Unified Engineering OKF Workbench v2 (`PROGRESS_REPORT_20261120`)

- **Linked Feature SDD:** [`SPEC-20261120-UNIFIED-WORKBENCH-V2`](../features/SPEC-20261120-UNIFIED-WORKBENCH-V2.md)
- **Linked Baseline SDD:** [`BASELINE-20261120-EXTRACTER-AGENT-SYSTEM`](../baseline/system-overview.md)
- **Active Git Branch:** `upgrade-v2`
- **Target GCP Project:** `engineering-kg-demo` (`435347747480`, `asia-southeast1`)
- **Workload Type:** `Hybrid` (`cloud_run` Service + `cloud_run` Job + `agent_runtime`)
- **Current AI-SDLC Phase:** **Phase 3: Operation Completed — Live on `engineering-kg-demo` (`asia-southeast1`)**

---

## 1. Milestone & Step-by-Step Execution Matrix

| Step | Scope | Status | Unit Tests | PBT Tests | Verification Summary |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Phase 1** | Inception, `engineering-kg-gc` Diff, Dataplex/Spanner Analysis & Gate 1 Sign-Off | `Completed` | N/A | N/A | Gate 1 approved; Spanner Native `ML.PREDICT` + ANN Vector Index added. |
| **Step 2.0–2.3** | Sync `specs/templates/` to v2, update Baseline SDD, author `SPEC-20261120-UNIFIED-WORKBENCH-V2.md` | `Completed` | N/A | N/A | `validate_waf_saif.py`: `10/10 Passed`, `0 Warnings`, `0 Conflicts`. |
| **Step 1** | Upstream code sync from `engineering-kg-gc` (preserving `reference/`, `_agents/`, `AGENTS.md`, custom `docs/`) | `Completed` | `PASS` | `PASS` | 94 files synced; `git diff reference/` = empty (0 changes); `extracted_gc_knowledge_temp/` excluded. |
| **Step 2** | Core v2 models (`unified_web/models.py`), IAP JWT & HITL security (`unified_web/security.py`), Spanner DDL v2 (`ML.PREDICT` + ANN + 9 edge indexes) & lazy hierarchy | `Completed` | `PASS` | `PASS` | `tests/test_v2_models_and_spanner.py` (10/10 passed, incl. 3 Hypothesis PBTs). |
| **Step 3** | ADK Agent updates (dynamic Gemini 4 models, 4-point SAIF 2.0 callbacks, execution budgets) | `Completed` | `PASS` | `PASS` | `tests/test_v2_adk_guardrails.py` (7/7 passed, incl. 3 Hypothesis PBTs). |
| **Step 4** | Unified FastAPI (`unified_web/server.py`), GCS `_manifest.json` cache (`unified_web/manifest.py`), SSE streaming & Cloud Run Job (`scripts/pipeline_job_runner.py`, `unified_web/jobs.py`) | `Completed` | `PASS` | `PASS` | `tests/test_v2_unified_api_and_jobs.py` (7/7 passed, incl. Hypothesis PBT). |
| **Step 5** | Modernized Unified Zero-Build Vanilla ESM Workbench UI (`unified_web/static/`) | `Completed` | `PASS` | `PASS` | `tests/test_v2_ui_contracts.py` (3/3 passed, incl. Hypothesis PBT; all ESM imports verified). |
| **Step 6** | Unified non-root `Dockerfile`, Terraform IaC (`okf-engineering-workbench` + `okf-pipeline-job` + `google_project_service`), `deploy.sh`, `scripts/bootstrap_gcp_project.sh`, `.env.example` + `.env` (`engineering-kg-demo`) | `Completed` | `PASS` | `PASS` | `terraform validate`: Valid; `bash -n` + `--dry-run` PASS; full `pytest tests/` 100% green (`217 passed, 2 skipped`). |
| **Phase 3 (SAST & Bootstrap)** | Pre-build security audit (`docs/codemender-01-vulnerability-scan-report.md` + static review) & `scripts/bootstrap_gcp_project.sh` | `Completed` | `PASS` | `PASS` | 0 security findings across `unified_web/` + `scripts/pipeline_job_runner.py`; 20 GCP APIs enabled; VPC `default` + Cloud NAT + Artifact Registry + GCS (`11/11` raw PDFs) + Spanner Enterprise DDL v2 (`OkfTextEmbeddingModel` + `idx_okf_chunks_vec` + 9 secondary indexes) live. |
| **Phase 3 (Live Deploy)** | Deploy `okf-pipeline-job` & `okf-engineering-workbench` to `engineering-kg-demo` (`asia-southeast1`) + post-deploy smoke checks | `Completed` | `PASS` | `PASS` | Cloud Run Job `okf-pipeline-job` (build `a5a2ca4c-60b6-41ee-80e6-5fe97452a36e`) & Cloud Run Service `okf-engineering-workbench-00001-rw2` (build `36258d53-0dc0-489f-85f0-f82cfe441786`) live with Pattern 1B Native IAP (`x-goog-iap-generated-response: true`, zero `allUsers`). |

---

## 2. Live Deployment Summary (`engineering-kg-demo` / `asia-southeast1`)

| Resource | Live Identifier / Endpoint | Verification Status |
| :--- | :--- | :--- |
| **Unified Cloud Run Service (Pattern 1B IAP)** | `okf-engineering-workbench` (`okf-engineering-workbench-00001-rw2`)<br>- IAP Primary URL: `https://okf-engineering-workbench-435347747480.asia-southeast1.run.app`<br>- Run URL: `https://okf-engineering-workbench-nzqke34jza-as.a.run.app` | `Ready=True`, `run.googleapis.com/iap-enabled=true`, `HTTP 302` OAuth2 edge redirect (`x-goog-iap-generated-response: true`), **0 `allUsers` bindings**; IAP SA `service-435347747480@gcp-sa-iap.iam.gserviceaccount.com` holds `roles/run.invoker`; `admin@pantana.altostrat.com` granted `roles/iap.httpsResourceAccessor`. |
| **Cloud Run Pipeline Job** | `okf-pipeline-job` (`4 vCPU / 8Gi / 3600s timeout`, Direct VPC) | Deployed from `asia-southeast1-docker.pkg.dev/engineering-kg-demo/okf-workbench/okf-pipeline-job:latest` (Cloud Build `a5a2ca4c-60b6-41ee-80e6-5fe97452a36e`); supports `JOB_MODE=extract \| sync \| extract_and_sync`. |
| **Cloud Spanner Enterprise DB** | `okf-knowledge-spanner` (`100 PU`, `ENTERPRISE`) / `okf_knowledge_graph` | DDL v2 applied (`11/11`): `OkfTextEmbeddingModel` (`ML.PREDICT` + Spanner SA `roles/aiplatform.user`), `idx_okf_chunks_vec` ANN `VECTOR INDEX`, and 9 graph/filter secondary indexes. |
| **GCS Knowledge Bucket** | `gs://engineering-kg-demo-okf-knowledge` (`asia-southeast1`, UBLA) | `11/11` `reference/raw/` PDFs synced (`operating_manuals: 1`, `pid: 8`, `standards: 2`); local `reference/` untouched (`git diff reference/` = empty). |
| **Network & Artifact Registry** | VPC `default` / subnet `default` (`10.10.0.0/24`, PGA) + Cloud NAT `okf-nat-gw` + AR `okf-workbench` | Direct VPC egress (`all-traffic`) verified for both Cloud Run Service and Cloud Run Job. |
| **Live Backend Smoke Tests** | `/healthz`, `/api/models`, `/api/status`, `/api/extractor/files`, `/api/spanner/hierarchy/summary`, `/api/spanner/graph`, `/api/jobs` | All `HTTP 200`; Gemini defaults `gemini-4-carbon` (Extractor) & `gemini-4-hydrogen` (Query), allowlist `carbon/hydrogen/argon/neon`, `spanner_embedding_mode=native_ml_predict`. |

---

## 3. Root Cause Analysis (RCA) Log (Rule 13)
1. **Step 4 Dev Verification (`unified_web/jobs.py`):** `PipelineJobDispatcher.submit_job()` acquired a non-reentrant `threading.Lock()` and invoked `self.get_job()` during idempotency replay. Fixed cleanly by switching to `threading.RLock()` and releasing the lock before reading status heartbeats.
2. **Phase 3 Bootstrap (`scripts/bootstrap_gcp_project.sh`):** Brand-new project `engineering-kg-demo` had `compute.skipDefaultNetworkCreation` enabled (no `default` VPC). Added idempotent VPC `default` + subnet `default` (`10.10.0.0/24`, Private Google Access) + Cloud Router/NAT (`okf-nat-router`/`okf-nat-gw`) provisioning to `scripts/bootstrap_gcp_project.sh`.
3. **Phase 3 Cloud Run Deploy (`deploy.sh`):** `gcloud run deploy --set-env-vars` split `ALLOWED_GEMINI_MODELS=gemini-4-carbon,gemini-4-hydrogen,gemini-4-argon,gemini-4-neon` on unescaped commas. Fixed cleanly using gcloud's custom delimiter syntax `--set-env-vars="^|^KEY1=VAL1|..."`, verified via `bash -n`, `--dry-run`, `pytest tests/test_deploy_and_model_config.py` (`23/23 passed`), and live deployment.
4. **CodeMender CLI (`cm find`) Telemetry Note:** Initial `cm find` invocation encountered an upstream `StartSession` RPC deadline exceeded immediately after enabling `aiplatform.googleapis.com` in `engineering-kg-demo` (documented in [`docs/codemender-01-vulnerability-scan-report.md`](../../docs/codemender-01-vulnerability-scan-report.md)). Supplemented with comprehensive manual + automated static security review across all 7 Python and 8 JS files in `unified_web/` and `scripts/pipeline_job_runner.py` (0 findings).

---

## 4. Operational Next Steps (User-Driven)
- Open `https://okf-engineering-workbench-435347747480.asia-southeast1.run.app` in a browser signed in as `admin@pantana.altostrat.com` (IAP access already granted).
- To grant additional teammates browser access via Pattern 1B Native IAP:
  ```bash
  gcloud beta iap web add-iam-policy-binding \
    --resource-type=cloud-run \
    --region=asia-southeast1 \
    --service=okf-engineering-workbench \
    --project=engineering-kg-demo \
    --member="user:<teammate@domain.com>" \
    --role="roles/iap.httpsResourceAccessor"
  ```
- From the **Extractor Studio** tab, click **Run Batch Job** (`extract_and_sync`) to extract the 11 raw PDFs into GCS OKF bundles and synchronize them into Cloud Spanner (`okf_knowledge_graph`) using native `ML.PREDICT` embeddings.
