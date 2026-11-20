# Feature Specification: Unified Workbench v2.1 — Streamlined 2-Button Extractor UX, GCS Sync & Live Tool/Latency Telemetry (`SPEC-20261120-WORKBENCH-UX-TELEMETRY-V21`)

## Document Control

| Field | Value |
| :--- | :--- |
| **Specification ID** | `SPEC-20261120-WORKBENCH-UX-TELEMETRY-V21` |
| **Parent Specification** | [`SPEC-20261120-UNIFIED-WORKBENCH-V2`](./SPEC-20261120-UNIFIED-WORKBENCH-V2.md) |
| **Baseline Specification** | [`BASELINE-20261120-EXTRACTER-AGENT-SYSTEM`](../baseline/system-overview.md) |
| **Workload Type** | `Hybrid` |
| **Status** | `Implemented` |
| **Author** | Platform Engineering & AI-SDLC Agent |
| **Target Branch** | `upgrade-v2` |
| **Target GCP Project** | `engineering-kg-demo` (`435347747480`, `asia-southeast1`) |
| **Last Updated** | `2026-11-20` |

---

## 1. Executive Summary, Scope & SLAs

### 1.1 Business Context & Problem Statement
Following the live deployment of Unified Engineering OKF Workbench v2 (`okf-engineering-workbench` + `okf-pipeline-job`), user testing surfaced three UX and observability friction points:
1. **Toolbar Clutter & Ambiguity:** Five overlapping pipeline buttons (`Sync OKF -> Spanner`, `Batch Extract (Job)`, `Extract + Sync`, `Purge & Reload`, `Extract This Document`) forced users to memorize differences between batch vs. interactive flows and how to scope all documents vs. specific document types.
2. **Extra Manual Step on Interactive Extract:** Clicking `Extract This Document` only pre-filled the chat box instead of immediately executing extraction and syncing to GCS + Cloud Spanner.
3. **Opaque Execution Latency in Both Chats:** Extractor Assistant ran as a blocking non-streaming POST call with no live tool-call visibility, while Query Chat hid its telemetry inside a collapsed `<details>` block with plain text lines and duplicate step/tool lines.

### 1.2 Scope, Non-Goals & Autonomy Boundaries
- **In Scope:**
  1. **Identical Persistent 3-Action Extractor Toolbar** across both **Raw Docs** and **OKF Bundle** views:
     - **`Batch Extract + Sync (Job)`** — opens an interactive **Batch Launcher Modal** explaining what it does, how to target **All Documents** vs **Particular Document Types** (`pid`, `standards`, `operating_manuals`, `data_sheets`, `pfd`, `moc`), allowing interactive selection of scope + Spanner Sync Mode (`FULL_MIRROR` | `INCREMENTAL`), plus an expandable **Advanced** section for `Sync Existing OKF -> Spanner Only` and HITL-gated `Purge & Reload` (`PURGE SPANNER` typed confirmation).
     - **`Extract + Sync (Interactive)`** + clickable **`?` Info Popover** — executes **immediately on click without pressing Enter**, opening the Extraction Assistant drawer, streaming real-time tool calls, steps, and per-step latency (`ms`) via a new SSE endpoint (`POST /api/extractor/chat/stream`), exporting updated OKF `.md` files to GCS, refreshing `_manifest.json`, and synchronizing updated concepts to Cloud Spanner (`INCREMENTAL` non-destructive sync).
     - **`Sync GCS`** — triggers `POST /api/gcs/sync` to pull the latest raw documents & OKF `.md` bundle from GCS (`gs://engineering-kg-demo-okf-knowledge`), rebuild `_manifest.json`, invalidate server caches, and refresh the UI file list and KPI counters.
     - Keep compact `Assistant` toggle in the toolbar; in **OKF Bundle View** viewer actions, retain `Raw YAML`, `Sync OKF -> Spanner`, and `Inspect in Graph ->`.
  2. **Unified Live Execution Trace Timeline Card (`telemetry-card.js`)** shared by **both** Extractor Assistant chat and Knowledge Graph & Query chat:
     - **Auto-expanded while running**, displaying live model pill, running elapsed timer, animated active step/tool badge (`RUNNING` -> `COMPLETED` / `ERROR` / `GUARDRAIL`), arguments/detail summary, and exact **per-step latency (`ms`)** updated in place (zero duplicate rows).
     - **Collapsible once completed** with concise summary (`<model> · <N> tool call(s) · <total_ms> ms`).
- **Non-Goals:**
  - Zero modifications to `reference/` raw PDFs (Reference Immutability Invariant).
  - No changes to Cloud Spanner DDL v2 schema, IAM bindings, or Pattern 1B Native IAP architecture.

### 1.3 Acceptance Criteria & SLAs
- **Extractor Toolbar Clutter Reduction:** Exactly 2 extract buttons (`Batch Extract + Sync (Job)`, `Extract + Sync (Interactive)`) plus `Sync GCS` and `Assistant` toggle persisted across both Raw Docs and OKF Bundle views.
- **Zero-Enter Interactive Run:** Clicking `Extract + Sync (Interactive)` initiates streaming execution within `<= 250 ms` without requiring Enter or form submission.
- **SSE Telemetry Responsiveness:** First SSE `start` + `STEP 0 // GUARDRAIL` event delivered in `<= 300 ms`; per-tool `RUNNING` and `COMPLETED` latency updates rendered in place with `0` duplicate DOM rows per `call_index`.
- **Availability & Backward Compatibility:** Existing `/api/chat/extract`, `/api/jobs/run`, and `/api/query/chat/stream` endpoints remain 100% backward compatible.

---

## 2. Architecture, WAF 6-Pillar Alignment & API Contracts

### 2.1 Dual-Runtime & Component Topology
- **Cloud Run Service (`okf-engineering-workbench`):** Serves the Zero-Build Vanilla ES Modules UI (`unified_web/static/`) + FastAPI SSE endpoints (`/api/extractor/chat/stream`, `/api/query/chat/stream`) + GCS sync endpoint (`/api/gcs/sync`) + Cloud Run Job dispatcher (`/api/jobs/run`).
- **Cloud Run Job (`okf-pipeline-job`):** Continues executing long-running `extract_and_sync` and `sync` batch jobs outside HTTP timeouts (`3600s` timeout).
- **ADK Reasoning Layer (`extracter_agent` + `query_agent`):** Tool wrappers record exact monotonic start/end timestamps (`time.perf_counter()`) around every ADK tool execution and emit structured `step` and `tool_call` SSE frames.

### 2.2 WAF 6-Pillar Alignment Summary
| WAF Pillar | Design Enforcement in v2.1 |
| :--- | :--- |
| **Operational Excellence** | Shared `telemetry-card.js` exposes real-time tool latency (`ms`), guardrail verdicts, and total duration directly in both chat windows; structured Cloud Logging / Cloud Monitoring / Cloud Trace telemetry with SLI/SLO error budgets, Terraform Infrastructure Manager IaC, and Cloud Build / Cloud Run revision rollback inherited from v2. |
| **Security, Privacy & Compliance** | Zero Trust Pattern 1B Direct Cloud Run Native IAP + PyJWT ES256 JWK Set + `IAP_JWT_AUDIENCE` enforced on all new endpoints (`/api/gcs/sync`, `/api/extractor/chat/stream`), with VPC-SC, CMEK/KMS, Shift-Left CodeMender SAST, and SLSA/Binary Authorization governance inherited from v2; 4-point SAIF 2.0 callbacks (`before_agent_callback`, `after_tool_callback`, `after_model_callback`) and deterministic HITL `PURGE SPANNER` modal preserved unchanged. |
| **Reliability** | Interactive `Extract + Sync` bounds sync errors via graceful degradation: if Spanner sync encounters an upstream error after extraction succeeds, extraction output is still saved to GCS and a typed `UPSTREAM_UNAVAILABLE_DEGRADED` step badge is surfaced in the timeline card (Rule 13 WAF harmonization). |
| **Cost Optimization** | Scale-to-zero (`min_instances=0`), single-document interactive sync uses `INCREMENTAL` mode (MD5 hash skip — only upserts touched concepts, avoiding full bundle re-embedding), and `Sync GCS` uses `_manifest.json` rebuild without invoking Vertex AI. |
| **Performance Optimization** | True SSE streaming (`Cache-Control: no-cache`, `X-Accel-Buffering: no`) eliminates blocking wait in Extractor Assistant; in-place DOM updates prevent layout thrashing on large traces. |
| **Sustainability** | Co-located in `asia-southeast1` with incremental MD5-deduplicated Spanner syncs avoiding redundant compute and embedding calls. |

### 2.3 New & Updated API Contracts
1. **`POST /api/gcs/sync`** (Rate-limited, IAP-authenticated):
   - Action: Calls `sync_bundle_from_gcs(force=True)` (when `USE_GCS_STORAGE=true`), rebuilds `_manifest.json` (`force_gcs=True`), invalidates `manifest_store` cache, and returns:
     ```json
     {
       "status": "success",
       "gcs_bucket": "gs://engineering-kg-demo-okf-knowledge",
       "raw_pdf_count": 11,
       "okf_file_count": 42,
       "conflict_count": 3,
       "sync_version": "a264ffa9730dce63",
       "raw_subfolders": {"pid": 8, "standards": 2, "operating_manuals": 1},
       "duration_ms": 412.5
     }
     ```
2. **`POST /api/extractor/chat/stream`** (alias `POST /api/chat/extract/stream`, Rate-limited, IAP-authenticated):
   - Request (`UnifiedExtractRequest` extended with `sync_to_spanner: bool = False`, `sync_mode: str = "INCREMENTAL"`):
     - Validates `model` against Gemini 4 allowlist (`gemini-4-carbon`, `gemini-4-hydrogen`, `gemini-4-argon`, `gemini-4-neon`).
     - Runs `before_agent_callback` (Model Armor / prompt injection check) and emits `STEP 0 // GUARDRAIL` with exact `duration_ms`.
     - Streams SSE events:
       - `event: start` — `{job_id, model, target_pdf, sync_to_spanner}`
       - `event: step` — `{step_id, step_index, phase, title, status, duration_ms, detail}` (`RUNNING` -> `COMPLETED` / `BLOCKED` / `DEGRADED` / `ERROR`)
       - `event: tool_call` — `{call_index, tool_name, args, status, duration_ms, summary}` (`RUNNING` -> `COMPLETED` / `ERROR`)
       - `event: token` — `{text}`
       - `event: done` — `{status, model, reply_markdown, touched_concepts, sync_version, spanner_counts, steps, tool_calls, steps_sum_ms, total_duration_ms}`
       - `event: error` — `{error, job_id}`
   - When `sync_to_spanner=true` and extraction succeeds:
     1. Emits `STEP N // GCS PUBLISH` (`RUNNING` -> `COMPLETED` with `duration_ms`), exporting updated `.md` files to GCS + rebuilding `_manifest.json`.
     2. Emits `STEP N+1 // SPANNER SYNC` (`RUNNING` -> `COMPLETED` or `DEGRADED` with `duration_ms`), running incremental `sync_markdown_bundle_to_spanner` and invalidating workbench Spanner caches so Tab 2 immediately reflects new concepts!
3. **`POST /api/query/chat/stream`** (Enhanced telemetry consistency):
   - Preserves existing payload schema and adds `step_id` correlation so `telemetry-card.js` updates each `RUNNING` tool call row in place when `COMPLETED` arrives without duplicating `step` + `tool_call` lines.

### 2.4 Shared Frontend Module Contract (`unified_web/static/js/telemetry-card.js`)
- Exports `createTelemetryCard({ model, modeLabel })` returning a controller `{ element, onStep(payload), onToolCall(payload), onDone(payload), onError(msg), destroy() }`:
  - Renders `<details class="wb-telemetry" open>` with live elapsed timer (`setInterval` every `100 ms`, cleared on `done`/`error`).
  - Tracks rows by stable key (`tool:<call_index>` or `step:<step_id|step_index>`) so `RUNNING` -> `COMPLETED` updates the exact same row with its final `duration_ms` badge.
  - Prevents duplicate rows when `query/chat/stream` emits both `tool_call` (COMPLETED) and an accompanying `step` for the same ADK tool call.

---

## 3. Security, Privacy, Rules 1–13 & SAIF 2.0 Compliance Matrix

| Control / Risk | Enforcement in v2.1 |
| :--- | :--- |
| **Rule 10 (Pattern 1B IAP)** | All new endpoints sit behind `security_and_cache_middleware` (PyJWT ES256 JWK Set + `IAP_JWT_AUDIENCE`). Zero `allUsers`. |
| **SAIF `PIJ` (Prompt Injection)** | `before_agent_callback` (Extractor) & `check_query_prompt_security` (Query) run as `STEP 0 // GUARDRAIL` on every SSE turn before any LLM/tool call; blocked turns stream a visible `BLOCKED` guardrail row. |
| **SAIF `DLP` (Sensitive Data)** | Tool args and summaries rendered in `telemetry-card.js` are HTML-escaped via `escapeHtml()` (zero raw innerHTML injection) and truncated safely (`<= 240 chars`) after `after_tool_callback` redaction. |
| **SAIF `RAC` (Rogue Actions / HITL & Anti-Confused-Deputy)** | End-user identity propagation (`User Auth` via verified IAP JWT principal email) tags every job and audit log; Read-Only Query Agent remains strictly isolated from mutating Extractor/Sync actions; destructive `Purge & Reload` stays gated behind the externalized deterministic HITL `PURGE SPANNER` modal + `X-Confirm-Purge: CONFIRMED` + `X-Idempotency-Key` headers inside the Batch Job modal's Advanced panel. |
| **SAIF `DMS` (Denial of ML Service)** | `POST /api/extractor/chat/stream` and `POST /api/gcs/sync` are protected by per-principal `SlidingWindowRateLimiter`, strict model allowlist, and `MAX_AGENT_TOOL_CALLS` execution budgets. |

---

## 4. Resiliency, Timeouts, Idempotency & Graceful Degradation
- **Batch vs. Interactive Separation:** Large multi-document extraction runs on Cloud Run Job `okf-pipeline-job` (`3600s` timeout); single-document interactive `Extract + Sync` streams over SSE with `900s` Cloud Run request timeout and live heartbeats.
- **Graceful Degradation (Rule 13 + WAF Reliability):** If GCS upload or Spanner sync fails during interactive `Extract + Sync`, the backend emits a typed `status: "DEGRADED"` step with actionable error detail rather than discarding extracted Markdown or fabricating fake counts.
- **Client Cleanup:** `telemetry-card.js` clears all active elapsed timers in `finally` blocks so aborted streams never leak browser timers.

---

## 5. Observability & AgentOps
- **In-Chat Live Telemetry (Both Tabs):** Every turn in both Extractor Assistant and Query Workbench displays step-by-step phase, tool name, arguments snippet, status badge, exact per-step latency (`ms`), and total turn latency (`total_duration_ms`).
- **Server-Side Telemetry:** Structured latency fields (`duration_ms`, `steps_sum_ms`, `total_duration_ms`, `tool_calls`) preserved in JSON responses and Cloud Logging.

---

## 6. Performance, FinOps & Sustainability
- **Incremental Interactive Sync:** Interactive `Extract + Sync` defaults to `INCREMENTAL` Spanner sync with MD5 skip, keeping per-document sync latency low and avoiding redundant `ML.PREDICT` embedding costs.
- **Manifest-First GCS Sync:** `Sync GCS` refreshes `_manifest.json` in a single GCS sync + directory scan without touching Spanner or Vertex AI.

---

## 7. Architectural Decision Records (ADRs)
- **ADR-21-01 (Identical Persistent Toolbar + Interactive Batch Modal):** Keeping `[Batch Extract + Sync (Job)]`, `[Extract + Sync (Interactive)]`, and `[Sync GCS]` consistent across both Raw Docs and OKF Bundle views (with scope selection, Sync Mode, and Advanced Purge/Sync-Only inside the Batch Launcher Modal) eliminates toolbar churn and visual clutter while preserving 100% of v2 pipeline capabilities.
- **ADR-21-02 (Shared `telemetry-card.js` + SSE for Extractor Chat):** Reusing one canonical SSE event schema (`start`, `step`, `tool_call`, `token`, `done`, `error`) and one Vanilla ESM component (`telemetry-card.js`) across both tabs ensures identical latency UX and eliminates code duplication.

---

## 8. Failure Mode & Effects Analysis (FMEA)
| Failure Mode | Impact | Mitigation |
| :--- | :--- | :--- |
| User clicks `Extract + Sync (Interactive)` without selecting a raw document (e.g., on initial load or in OKF Bundle view) | Ambiguous extraction target | If a raw doc was selected, extract it immediately; if an OKF concept is selected and has a resolved primary PDF, extract that source PDF; otherwise show a clear inline toast guiding the user to click any raw PDF first (zero silent failures). |
| SSE connection drops mid-extraction | Spinner stuck in UI | `try/catch/finally` stops elapsed timer, marks active step `ERROR`, and surfaces reconnect/refresh guidance. |
| Duplicate rows when both `tool_call` and `step` fire for the same tool | Cluttered timeline | `telemetry-card.js` deduplicates by `tool:<call_index>` and skips redundant `ADK TOOL` mirror `step` events once the corresponding `tool_call` row exists. |

---

## 9. Step-by-Step Implementation Plan & Testing Strategy

| Step | Files Touched | Deliverables | Mandatory Unit & Property-Based Tests |
| :--- | :--- | :--- | :--- |
| **Step 1: Backend SSE Extractor Stream & GCS Sync API** | `unified_web/server.py`, `unified_web/models.py` | Extend `UnifiedExtractRequest` (`sync_to_spanner`, `sync_mode`), implement `POST /api/extractor/chat/stream` with live per-tool timing (`RUNNING` -> `COMPLETED` + `duration_ms`) + optional GCS export & incremental Spanner sync steps, and implement `POST /api/gcs/sync`. | **Unit:** `POST /api/gcs/sync` returns counts/version; `POST /api/extractor/chat/stream` emits `start`, `step`, `tool_call` with `duration_ms >= 0`, `done` (including blocked guardrail & sync step). **PBT (Hypothesis):** Across arbitrary prompt/model inputs, `total_duration_ms >= 0` and disallowed models always return `400`. |
| **Step 2: Shared Live Telemetry Card Module (`telemetry-card.js`) & Query Chat Upgrade** | `unified_web/static/js/telemetry-card.js`, `unified_web/static/js/query-tab.js`, `unified_web/static/css/workbench.css` | Build `telemetry-card.js` (auto-expanded while running, live elapsed timer, in-place `RUNNING` -> `COMPLETED` row updates, exact `ms` latency badges, collapsible when done) and wire into `query-tab.js` so Query Chat renders clean live tool calls, steps, and per-step latency. | **Unit:** Verify JS syntax (`node --check`), ESM import integrity, and DOM contract assertions in `tests/test_v2_ui_contracts.py`. |
| **Step 3: Streamlined 2-Button Extractor Toolbar, Popups, Zero-Enter Interactive Extract + Sync & GCS Sync** | `unified_web/static/index.html`, `unified_web/static/js/extractor-tab.js`, `unified_web/static/js/jobs-drawer.js`, `unified_web/static/js/main.js`, `unified_web/static/css/workbench.css` | Replace cluttered 5-button toolbar with persistent `[Batch Extract + Sync (Job)]`, `[Extract + Sync (Interactive)]` + `?` info popover, and `[Sync GCS]`; add interactive Batch Launcher Modal (explaining what it does, All Docs vs Particular Doc Types picker, Sync Mode, Advanced Sync-Only & Purge HITL); wire zero-Enter streaming execution in Extractor Assistant via `telemetry-card.js`. | **Unit & PBT:** Verify HTML/JS contracts (exact 2 extract buttons + Sync GCS + popups + modal controls + zero-Enter handler + `telemetry-card.js` wired in both tabs) in `tests/test_v2_ui_contracts.py` and full `pytest tests/` regression. |
| **Step 4: Living Spec Sync & Live Cloud Run Rollout** | `specs/plan/PROGRESS_REPORT_20261120.md`, `specs/README.md` | Sync living specs, commit & push to `upgrade-v2`, redeploy `okf-engineering-workbench` to `engineering-kg-demo`, and verify live endpoints. | Live `/healthz`, `/api/gcs/sync`, `/api/extractor/chat/stream`, and `/api/query/chat/stream` verification. |

---

## 10. Plan Progress Tracking
Tracked in [`specs/plan/PROGRESS_REPORT_20261120.md`](../plan/PROGRESS_REPORT_20261120.md).
