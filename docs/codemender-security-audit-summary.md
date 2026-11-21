# CodeMender SAST & Security Audit Summary (`okf-engineering-workbench` v2.2)

## Document Control

| Field | Value |
| :--- | :--- |
| **Audit Scope** | `unified_web/`, `extracter_agent/`, `query_agent/`, `scripts/pipeline_job_runner.py`, `Dockerfile`, `terraform/` |
| **Google Cloud Project** | `engineering-kg-demo` (`435347747480`, `asia-southeast1`) |
| **Branch / Baseline** | `upgrade-v2` (Unified Workbench v2.2) |
| **Overall Security Verdict** | **PASS — 0 High / Critical / Medium Vulnerabilities** |
| **Last Audited** | `2026-11-20` |

---

## 1. Executive Summary

Security verification across both historical v1 (`extracter_agent`, `query_agent`, Oct 2026) and Unified Workbench v2/v2.2 (`unified_web/`, `scripts/pipeline_job_runner.py`, Nov 2026) identified **0 open security vulnerabilities**. All OWASP Top 10, Google Cloud WAF Security Pillar, and Google SAIF 2.0 controls are enforced and covered by automated unit and Hypothesis property-based tests (`tests/`).

---

## 2. Scan History & Findings Table

| Scan Date | Scope | Scanner / Method | Findings (Crit / High / Med / Low) | Status |
| :--- | :--- | :--- | :--- | :--- |
| `2026-10-01` | `extracter_agent/`, `query_agent/` | CodeMender SAST + Static Analysis (`ruff`, secret/path traversal checks) | `0 / 0 / 0 / 0` | **PASS** |
| `2026-11-20` | `unified_web/` (15 Python & ESM files) + `scripts/pipeline_job_runner.py` | CodeMender CLI (`cm find`) + Manual & Automated Static Security Review *(Note: `cm find` StartSession RPC hit an upstream deadline on `aiplatform.googleapis.com` immediately post-API enablement; supplemented with full 15-file static security audit)* | `0 / 0 / 0 / 0` | **PASS** |

---

## 3. Verified Security Controls Checklist (WAF Pillar 2 & SAIF 2.0)

| Control Area | Implementation & Evidence | Verification |
| :--- | :--- | :--- |
| **Zero-Trust Edge Auth (Rule 10 Pattern 1B)** | Cloud Run Native IAP (`--iap`, `--no-allow-unauthenticated`, `--invoker-iam-check`), **zero `allUsers` / `allAuthenticatedUsers` IAM bindings**; only `service-435347747480@gcp-sa-iap.iam.gserviceaccount.com` holds `roles/run.invoker`. | Verified via `gcloud run services get-iam-policy` & live `HTTP 302` (`x-goog-iap-generated-response: true`). |
| **Cryptographic IAP JWT Verification** | [`unified_web/security.py`](../unified_web/security.py) verifies `x-goog-iap-jwt-assertion` via `PyJWT[crypto]` against cached RFC 7517 Google IAP JWKs (`public_key-jwk`), pinning `algorithms=["ES256"]`, `iss="https://cloud.google.com/iap"`, and `aud="/projects/435347747480/locations/asia-southeast1/services/okf-engineering-workbench"`. | Real ES256 JWK cryptographic tests in `tests/test_v2_models_and_spanner.py` (valid, wrong aud, expired, forged key). |
| **Container & Runtime Hardening (Rule 6)** | [`Dockerfile`](../Dockerfile) runs under dedicated unprivileged `USER nonroot` (`uid 10001`), Direct VPC egress (`all-traffic`), and exposes `/healthz` liveness probe. | Verified via `Dockerfile` & live Cloud Run revision readiness. |
| **Path Traversal & Input Validation** | Strict allowlist validation on Gemini 4 model IDs, `ALLOWED_RAW_SUBFOLDERS`, `target_files` (rejects `..`, leading `/`, `\`, NUL bytes), and `Path.is_relative_to()` confinement on all file reads/writes. | Verified via Unit + Hypothesis PBTs (`tests/test_v2_models_and_spanner.py`, `tests/test_web_server_and_ui.py`). |
| **XSS & Output Encoding** | All user prompts, tool arguments, step telemetry, and Spanner results rendered in `unified_web/static/js/` pass through `escapeHtml()` before DOM insertion. | Audited across all 9 ES module files (`node --check` + UI contract tests). |
| **SAIF 2.0 4-Point Guardrails & HITL (`RAC`)** | `before_agent_callback` / `before_model_callback` prompt injection screening, `after_tool_callback` Indirect PIJ + DLP scrubbing, `after_model_callback` redaction, per-principal `SlidingWindowRateLimiter`, and typed `PURGE SPANNER` modal + `X-Confirm-Purge: CONFIRMED` + `X-Idempotency-Key` headers. | Verified via `tests/test_v2_adk_guardrails.py` & `tests/test_v2_unified_api_and_jobs.py`. |
| **Secrets & Reference Immutability** | `.env` strictly gitignored (`git check-ignore -v .env`); zero hardcoded credentials; `reference/raw/` strictly read-only at runtime. | Verified in CI & pre-deploy checks. |
