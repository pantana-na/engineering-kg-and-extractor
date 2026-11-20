#!/usr/bin/env bash
# ==============================================================================
# Unified Deployment Script for Extracter Agent & Spanner Query Agent
#
# Targets:
#   - all:           Provisions infra + deploys both Agent Runtimes + both Cloud Run UIs
#   - infra:         Provisions GCS bucket, uploads raw PDFs & creates Spanner DB
#   - agent_runtime: Deploys Agent 1 (extracter_orchestrator) to Agent Platform
#   - query_agent:   Deploys Agent 2 (okf_spanner_query_orchestrator) to Agent Platform
#   - cloud_run:     Deploys Workbench 1 (extracter-agent-web) to Cloud Run
#   - query_web:     Deploys Workbench 2 (okf-query-agent-web) to Cloud Run
#
# Options:
#   --target, -t <target>   Deployment target (default: cloud_run)
#   --env, -e <env>         Environment block from .env: nonprod | prod (default: nonprod)
#   --dry-run               Print resolved Cloud Build / Cloud Run flags without executing
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Load unified .env configuration if present without clobbering caller/CI overrides (Rule 8)
if [[ -f ".env" ]]; then
  while IFS= read -r _raw_line || [[ -n "${_raw_line}" ]]; do
    _line="${_raw_line#"${_raw_line%%[![:space:]]*}"}"
    [[ -z "${_line}" || "${_line}" == \#* ]] && continue
    _line="${_line#export }"
    if [[ "${_line}" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      _key="${BASH_REMATCH[1]}"
      _val="${BASH_REMATCH[2]}"
      _val="${_val%"${_val##*[![:space:]]}"}"
      if [[ "${_val}" =~ ^\"(.*)\"$ ]]; then
        _val="${BASH_REMATCH[1]}"
      elif [[ "${_val}" =~ ^\'(.*)\'$ ]]; then
        _val="${BASH_REMATCH[1]}"
      fi
      if [[ -z "${!_key:-}" ]]; then
        export "${_key}=${_val}"
      fi
    fi
  done < ".env"
  unset _raw_line _line _key _val
fi

TARGET="cloud_run"
DEPLOY_ENV="NONPROD"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target|-t)
      TARGET="$2"
      shift 2
      ;;
    --env|-e)
      DEPLOY_ENV="$(echo "$2" | tr '[:lower:]' '[:upper:]')"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    infra|provision)
      TARGET="infra"
      shift
      ;;
    agent|agent_runtime|agent_engine)
      TARGET="agent_runtime"
      shift
      ;;
    web|cloud_run|adk_web)
      TARGET="cloud_run"
      shift
      ;;
    query_agent|query_agent_runtime)
      TARGET="query_agent"
      shift
      ;;
    query_web|query_ui)
      TARGET="query_web"
      shift
      ;;
    unified|unified_web|workbench)
      TARGET="unified_web"
      shift
      ;;
    job|pipeline_job)
      TARGET="pipeline_job"
      shift
      ;;
    bootstrap)
      TARGET="bootstrap"
      shift
      ;;
    all)
      TARGET="all"
      shift
      ;;
    --help|-h)
      sed -n '2,20p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "${DEPLOY_ENV}" == "DEV" || "${DEPLOY_ENV}" == "DEVELOPMENT" ]]; then
  DEPLOY_ENV="NONPROD"
elif [[ "${DEPLOY_ENV}" == "PRODUCTION" || "${DEPLOY_ENV}" == "RELEASE" ]]; then
  DEPLOY_ENV="PROD"
fi

if [[ "${DEPLOY_ENV}" == "PROD" ]]; then
  PROJECT_ID="${PROD_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-your-gcp-project-id}}"
  REGION="${PROD_REGION:-${GOOGLE_CLOUD_LOCATION:-asia-southeast1}}"
  MIN_INSTANCES="${PROD_MIN_INSTANCES:-0}"
  MAX_INSTANCES="${PROD_MAX_INSTANCES:-10}"
  EXTRACTER_RUNTIME_ID="${PROD_AGENT_RUNTIME_ID:-}"
  QUERY_RUNTIME_ID="${PROD_QUERY_AGENT_RUNTIME_ID:-}"
else
  PROJECT_ID="${NONPROD_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-your-gcp-project-id}}"
  REGION="${NONPROD_REGION:-${GOOGLE_CLOUD_LOCATION:-asia-southeast1}}"
  MIN_INSTANCES="${NONPROD_MIN_INSTANCES:-0}"
  MAX_INSTANCES="${NONPROD_MAX_INSTANCES:-3}"
  EXTRACTER_RUNTIME_ID="${NONPROD_AGENT_RUNTIME_ID:-}"
  QUERY_RUNTIME_ID="${NONPROD_QUERY_AGENT_RUNTIME_ID:-}"
fi

MODEL_LOCATION="${GEMINI_LOCATION:-global}"
AGENT_DIR="extracter_agent"
AGENT_DISPLAY_NAME="${SERVICE_NAME:-extracter-agent}"
QUERY_AGENT_DISPLAY_NAME="${QUERY_SERVICE_NAME:-okf-query-agent}"
GCS_BUCKET="${DESTINATION_GCS_BUCKET:-${PROJECT_ID}-okf-knowledge}"
GCS_PREFIX="${DESTINATION_GCS_PREFIX:-okf-bundles/chemical-plant}"
RAW_PREFIX="${SOURCE_GCS_RAW_PREFIX:-reference/raw}"
MODEL_NAME="${GEMINI_MODEL:-gemini-4-argon}"
SPANNER_INST="${SPANNER_INSTANCE_ID:-okf-knowledge-spanner}"
SPANNER_DB="${SPANNER_DATABASE_ID:-okf_knowledge_graph}"
SPANNER_PU="${SPANNER_PROCESSING_UNITS:-100}"

# Ensure gcloud uses fresh Application Default Credentials token at every stage
refresh_adc_token() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    return 0
  fi
  export CLOUDSDK_CORE_DISABLE_PROMPTS=1
  local adc_token=""
  if command -v gcloud >/dev/null 2>&1; then
    adc_token="$(timeout 3 gcloud auth application-default print-access-token 2>/dev/null || true)"
  fi
  if [[ -z "${adc_token}" ]]; then
    local py_bin=".venv/bin/python"
    if [[ ! -x "${py_bin}" ]]; then
      py_bin="$(command -v python3 || true)"
    fi
    if [[ -n "${py_bin}" ]]; then
      adc_token="$("${py_bin}" -c 'import google.auth, google.auth.transport.requests; c, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"]); c.refresh(google.auth.transport.requests.Request()); print(c.token or "")' 2>/dev/null || true)"
    fi
  fi
  if [[ -n "${adc_token}" ]]; then
    export CLOUDSDK_AUTH_ACCESS_TOKEN="${adc_token}"
  fi
}

refresh_adc_token

# Resolve per-web-app Cloud Build SA, Ingress, Native IAP Security & VPC Egress from .env
resolve_webapp_flags() {
  local app_key="$1"
  local py_bin=".venv/bin/python"
  if [[ ! -x "${py_bin}" ]]; then
    py_bin="$(command -v python3 || true)"
  fi

  if [[ -n "${py_bin}" ]]; then
    local shell_eval
    shell_eval="$(PYTHONPATH=. "${py_bin}" -m extracter_agent.deploy_config --app "${app_key}" --env "${DEPLOY_ENV}" --format shell)"
    eval "${shell_eval}"
    return 0
  fi

  echo "Error: Python 3 environment required to resolve deploy_config." >&2
  return 1
}

ensure_iap_service_agent_invoker() {
  local service_name="$1"
  local security_mode="$2"
  if [[ "${security_mode}" != "iap" || "${DRY_RUN}" -eq 1 ]]; then
    return 0
  fi

  local proj_num="${GOOGLE_CLOUD_PROJECT_NUMBER:-}"
  if [[ -z "${proj_num}" || "${proj_num}" == "000000000000" ]]; then
    proj_num="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)' 2>/dev/null || true)"
  fi
  if [[ -n "${proj_num}" ]]; then
    local iap_sa="service-${proj_num}@gcp-sa-iap.iam.gserviceaccount.com"
    echo "Ensuring Cloud Run Native IAP service agent (${iap_sa}) holds roles/run.invoker on ${service_name}..."
    gcloud run services add-iam-policy-binding "${service_name}" \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --member="serviceAccount:${iap_sa}" \
      --role="roles/run.invoker" \
      --quiet >/dev/null 2>&1 || true
  fi
}

provision_infra() {
  echo "=============================================================================="
  echo "[Infra] Ensuring GCS Bucket, Raw PDFs & Cloud Spanner Graph DB Exist"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  GCS Bucket:       gs://${GCS_BUCKET}"
  echo "  Spanner Instance: ${SPANNER_INST} (${SPANNER_PU} PU)"
  echo "  Spanner Database: ${SPANNER_DB}"
  echo "=============================================================================="

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] Skipping live GCS & Cloud Spanner provisioning."
    return 0
  fi

  if ! gcloud storage buckets describe "gs://${GCS_BUCKET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "Creating GCS bucket gs://${GCS_BUCKET} in ${REGION}..."
    gcloud storage buckets create "gs://${GCS_BUCKET}" \
      --project="${PROJECT_ID}" \
      --location="${REGION}" \
      --uniform-bucket-level-access
  else
    echo "GCS bucket gs://${GCS_BUCKET} already exists."
  fi

  if [[ -d "reference/raw" ]]; then
    echo "Syncing raw engineering PDFs from reference/raw/ to gs://${GCS_BUCKET}/${RAW_PREFIX}/..."
    gcloud storage rsync "reference/raw" "gs://${GCS_BUCKET}/${RAW_PREFIX}" \
      --project="${PROJECT_ID}" \
      --recursive \
      --exclude='(^|.*/)README\.md$' \
      --quiet
  fi

  if ! gcloud spanner instances describe "${SPANNER_INST}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "Creating Cloud Spanner instance ${SPANNER_INST} (${SPANNER_PU} PU) in regional-${REGION}..."
    gcloud spanner instances create "${SPANNER_INST}" \
      --project="${PROJECT_ID}" \
      --config="regional-${REGION}" \
      --description="${SPANNER_INST:0:30}" \
      --processing-units="${SPANNER_PU}" \
      --edition=ENTERPRISE
  else
    echo "Cloud Spanner instance ${SPANNER_INST} already exists."
  fi

  if ! gcloud spanner databases describe "${SPANNER_DB}" --instance="${SPANNER_INST}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "Creating Cloud Spanner database ${SPANNER_DB} with query_agent/spanner/schema.sql..."
    gcloud spanner databases create "${SPANNER_DB}" \
      --instance="${SPANNER_INST}" \
      --project="${PROJECT_ID}" \
      --ddl-file="query_agent/spanner/schema.sql"
  else
    echo "Cloud Spanner database ${SPANNER_DB} already exists."
  fi
}

deploy_agent_runtime() {
  local raw_engine_id="${EXTRACTER_RUNTIME_ID}"
  local agent_engine_id="${raw_engine_id##*/}"
  local adk_bin=".venv/bin/adk"
  if [[ ! -x "${adk_bin}" ]]; then
    adk_bin="$(command -v adk || true)"
  fi

  echo "=============================================================================="
  echo "[Agent 1] Deploying OKF Extracter Agent to Vertex AI Agent Runtime"
  echo "  Environment:      ${DEPLOY_ENV}"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  Model Location:   ${MODEL_LOCATION}"
  echo "  Model Name:       ${MODEL_NAME}"
  echo "  Display Name:     ${AGENT_DISPLAY_NAME}"
  echo "=============================================================================="

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] adk deploy agent_engine --project=${PROJECT_ID} --region=${REGION} --display_name=${AGENT_DISPLAY_NAME} ${AGENT_DIR}"
    return 0
  fi

  local staged_env="${AGENT_DIR}/.env"
  local py_bin=".venv/bin/python"
  if [[ ! -x "${py_bin}" ]]; then
    py_bin="$(command -v python3 || true)"
  fi
  local had_agent_env=0
  if [[ -f "${staged_env}" ]]; then
    had_agent_env=1
  elif [[ -f ".env" ]]; then
    PYTHONPATH=. "${py_bin}" -m extracter_agent.deploy_config \
      --env "${DEPLOY_ENV}" \
      --dotenv-file ".env" \
      --format agent-env > "${staged_env}"
  fi

  local rc=0
  if [[ -n "${agent_engine_id}" && "${agent_engine_id}" =~ ^[0-9]+$ ]]; then
    "${adk_bin}" deploy agent_engine \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --agent_engine_id="${agent_engine_id}" \
      --display_name="${AGENT_DISPLAY_NAME}" \
      --temp_folder="/tmp/adk_deploy_${AGENT_DIR}" \
      "${AGENT_DIR}" || rc=$?
  else
    "${adk_bin}" deploy agent_engine \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --display_name="${AGENT_DISPLAY_NAME}" \
      --temp_folder="/tmp/adk_deploy_${AGENT_DIR}" \
      "${AGENT_DIR}" || rc=$?
  fi

  if [[ "${had_agent_env}" -eq 0 && -f "${staged_env}" ]]; then
    rm -f "${staged_env}"
  fi
  return "${rc}"
}

deploy_query_agent_runtime() {
  local raw_engine_id="${QUERY_RUNTIME_ID}"
  local agent_engine_id="${raw_engine_id##*/}"
  local adk_bin=".venv/bin/adk"
  if [[ ! -x "${adk_bin}" ]]; then
    adk_bin="$(command -v adk || true)"
  fi

  echo "=============================================================================="
  echo "[Agent 2] Deploying OKF Spanner Query Agent to Vertex AI Agent Runtime"
  echo "  Environment:      ${DEPLOY_ENV}"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  Model Location:   ${MODEL_LOCATION}"
  echo "  Model Name:       ${MODEL_NAME}"
  echo "  Display Name:     ${QUERY_AGENT_DISPLAY_NAME}"
  echo "=============================================================================="

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] adk deploy agent_engine --project=${PROJECT_ID} --region=${REGION} --display_name=${QUERY_AGENT_DISPLAY_NAME} query_agent"
    return 0
  fi

  local staged_env="query_agent/.env"
  local py_bin=".venv/bin/python"
  if [[ ! -x "${py_bin}" ]]; then
    py_bin="$(command -v python3 || true)"
  fi
  local had_agent_env=0
  if [[ -f "${staged_env}" ]]; then
    had_agent_env=1
  elif [[ -f ".env" ]]; then
    PYTHONPATH=. "${py_bin}" -m extracter_agent.deploy_config \
      --env "${DEPLOY_ENV}" \
      --dotenv-file ".env" \
      --format agent-env > "${staged_env}"
  fi

  local rc=0
  if [[ -n "${agent_engine_id}" && "${agent_engine_id}" =~ ^[0-9]+$ ]]; then
    "${adk_bin}" deploy agent_engine \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --agent_engine_id="${agent_engine_id}" \
      --display_name="${QUERY_AGENT_DISPLAY_NAME}" \
      --temp_folder="/tmp/adk_deploy_query_agent" \
      "query_agent" || rc=$?
  else
    "${adk_bin}" deploy agent_engine \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --display_name="${QUERY_AGENT_DISPLAY_NAME}" \
      --temp_folder="/tmp/adk_deploy_query_agent" \
      "query_agent" || rc=$?
  fi

  if [[ "${had_agent_env}" -eq 0 && -f "${staged_env}" ]]; then
    rm -f "${staged_env}"
  fi
  return "${rc}"
}

deploy_adk_web_cloud_run() {
  RESOLVED_SERVICE_NAME=""
  RESOLVED_GEMINI_MODEL=""
  RESOLVED_CLOUDBUILD_SA=""
  RESOLVED_RUNTIME_SA=""
  RESOLVED_SECURITY_MODE=""
  RESOLVED_INGRESS=""
  RESOLVED_VPC_MODE=""
  RESOLVED_CPU=""
  RESOLVED_MEMORY=""
  RESOLVED_CONCURRENCY=""
  RESOLVED_TIMEOUT=""
  RESOLVED_MIN_INSTANCES=""
  RESOLVED_MAX_INSTANCES=""
  RESOLVED_GCLOUD_FLAGS=()
  resolve_webapp_flags "EXTRACTER_WEB"

  echo "=============================================================================="
  echo "[Cloud Run 1] Deploying OKF v0.2 Engineering Extraction Workbench"
  echo "  Environment:      ${DEPLOY_ENV}"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  Service Name:     ${RESOLVED_SERVICE_NAME}"
  echo "  Model Name:       ${RESOLVED_GEMINI_MODEL} (${MODEL_LOCATION})"
  echo "  Cloud Build SA:   ${RESOLVED_CLOUDBUILD_SA}"
  echo "  Cloud Run SA:     ${RESOLVED_RUNTIME_SA}"
  echo "  Ingress:          ${RESOLVED_INGRESS}"
  echo "  Security Mode:    ${RESOLVED_SECURITY_MODE}"
  echo "  VPC Mode:         ${RESOLVED_VPC_MODE}"
  echo "  Sizing:           ${RESOLVED_CPU} vCPU / ${RESOLVED_MEMORY} / conc=${RESOLVED_CONCURRENCY} / timeout=${RESOLVED_TIMEOUT}s (${RESOLVED_MIN_INSTANCES}..${RESOLVED_MAX_INSTANCES} instances)"
  echo "  GCS Bucket:       gs://${GCS_BUCKET}/${GCS_PREFIX}"
  echo "=============================================================================="

  local cmd=(
    gcloud run deploy "${RESOLVED_SERVICE_NAME}"
    --source="."
    --project="${PROJECT_ID}"
    --region="${REGION}"
    "${RESOLVED_GCLOUD_FLAGS[@]}"
    --no-cpu-throttling
    --set-env-vars="DEPLOYMENT_ENV=${DEPLOY_ENV},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},NONPROD_REGION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=true,GEMINI_LOCATION=${MODEL_LOCATION},GEMINI_MODEL=${RESOLVED_GEMINI_MODEL},CLOUD_RUN_INGRESS=${RESOLVED_INGRESS},CLOUD_RUN_SECURITY_MODE=${RESOLVED_SECURITY_MODE},CLOUD_RUN_VPC_MODE=${RESOLVED_VPC_MODE},EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-005},USE_GCS_STORAGE=true,SOURCE_GCS_RAW_PREFIX=${RAW_PREFIX},DESTINATION_GCS_BUCKET=${GCS_BUCKET},DESTINATION_GCS_PREFIX=${GCS_PREFIX},SPANNER_INSTANCE_ID=${SPANNER_INST},SPANNER_DATABASE_ID=${SPANNER_DB},NONPROD_AGENT_RUNTIME_ID=${EXTRACTER_RUNTIME_ID},OUTPUT_BUNDLE_DIR=/tmp/okf_bundle,APP_MODULE=extracter_agent.web_server:app"
    --quiet
  )

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] ${cmd[*]}"
    return 0
  fi

  "${cmd[@]}"
  ensure_iap_service_agent_invoker "${RESOLVED_SERVICE_NAME}" "${RESOLVED_SECURITY_MODE}"

  local web_url
  web_url="$(gcloud run services describe "${RESOLVED_SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --format='value(status.url)' 2>/dev/null || true)"
  if [[ -n "${web_url}" ]]; then
    echo ""
    echo "=============================================================================="
    echo "OKF Extraction Workbench Live:          ${web_url}"
    echo "Architecture Diagram Live:              ${web_url}/architecture-diagram"
    echo "Live Telemetry Status API:              ${web_url}/api/demo/status"
    echo "=============================================================================="
  fi
}

deploy_query_web_cloud_run() {
  RESOLVED_SERVICE_NAME=""
  RESOLVED_GEMINI_MODEL=""
  RESOLVED_CLOUDBUILD_SA=""
  RESOLVED_RUNTIME_SA=""
  RESOLVED_SECURITY_MODE=""
  RESOLVED_INGRESS=""
  RESOLVED_VPC_MODE=""
  RESOLVED_CPU=""
  RESOLVED_MEMORY=""
  RESOLVED_CONCURRENCY=""
  RESOLVED_TIMEOUT=""
  RESOLVED_MIN_INSTANCES=""
  RESOLVED_MAX_INSTANCES=""
  RESOLVED_GCLOUD_FLAGS=()
  resolve_webapp_flags "QUERY_WEB"

  echo "=============================================================================="
  echo "[Cloud Run 2] Deploying OKF Spanner Graph & Retrieval Workbench UI"
  echo "  Environment:      ${DEPLOY_ENV}"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  Service Name:     ${RESOLVED_SERVICE_NAME}"
  echo "  Model Name:       ${RESOLVED_GEMINI_MODEL} (${MODEL_LOCATION})"
  echo "  Cloud Build SA:   ${RESOLVED_CLOUDBUILD_SA}"
  echo "  Cloud Run SA:     ${RESOLVED_RUNTIME_SA}"
  echo "  Ingress:          ${RESOLVED_INGRESS}"
  echo "  Security Mode:    ${RESOLVED_SECURITY_MODE}"
  echo "  VPC Mode:         ${RESOLVED_VPC_MODE}"
  echo "  Sizing:           ${RESOLVED_CPU} vCPU / ${RESOLVED_MEMORY} / conc=${RESOLVED_CONCURRENCY} / timeout=${RESOLVED_TIMEOUT}s (${RESOLVED_MIN_INSTANCES}..${RESOLVED_MAX_INSTANCES} instances)"
  echo "  Spanner DB:       ${SPANNER_INST} / ${SPANNER_DB}"
  echo "=============================================================================="

  local cmd=(
    gcloud run deploy "${RESOLVED_SERVICE_NAME}"
    --source="."
    --project="${PROJECT_ID}"
    --region="${REGION}"
    "${RESOLVED_GCLOUD_FLAGS[@]}"
    --no-cpu-throttling
    --set-env-vars="DEPLOYMENT_ENV=${DEPLOY_ENV},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},NONPROD_REGION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=true,GEMINI_LOCATION=${MODEL_LOCATION},GEMINI_MODEL=${RESOLVED_GEMINI_MODEL},CLOUD_RUN_INGRESS=${RESOLVED_INGRESS},CLOUD_RUN_SECURITY_MODE=${RESOLVED_SECURITY_MODE},CLOUD_RUN_VPC_MODE=${RESOLVED_VPC_MODE},EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-005},SPANNER_INSTANCE_ID=${SPANNER_INST},SPANNER_DATABASE_ID=${SPANNER_DB},DATAPLEX_ENTRY_GROUP_ID=${DATAPLEX_ENTRY_GROUP_ID:-okf-knowledge-assets},DATAPLEX_TAG_TEMPLATE_ID=${DATAPLEX_TAG_TEMPLATE_ID:-okf-governance-template},NONPROD_QUERY_AGENT_RUNTIME_ID=${QUERY_RUNTIME_ID},QUERY_AGENT_RUNTIME_ID=${QUERY_RUNTIME_ID##*/},DESTINATION_GCS_BUCKET=${GCS_BUCKET},DESTINATION_GCS_PREFIX=${GCS_PREFIX},APP_MODULE=query_agent.web_server:app"
    --quiet
  )

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] ${cmd[*]}"
    return 0
  fi

  "${cmd[@]}"
  ensure_iap_service_agent_invoker "${RESOLVED_SERVICE_NAME}" "${RESOLVED_SECURITY_MODE}"

  local query_web_url
  query_web_url="$(gcloud run services describe "${RESOLVED_SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --format='value(status.url)' 2>/dev/null || true)"
  if [[ -n "${query_web_url}" ]]; then
    echo ""
    echo "=============================================================================="
    echo "OKF Spanner Retrieval Workbench Live:   ${query_web_url}"
    echo "Liveness Health Probe (/healthz):       ${query_web_url}/healthz"
    echo "Spanner Hierarchy API:                  ${query_web_url}/api/spanner/hierarchy"
    echo "Dataplex Universal Catalog API:         ${query_web_url}/api/catalog"
    echo "=============================================================================="
  fi
}

deploy_unified_workbench_cloud_run() {
  RESOLVED_SERVICE_NAME=""
  RESOLVED_GEMINI_MODEL=""
  RESOLVED_CLOUDBUILD_SA=""
  RESOLVED_RUNTIME_SA=""
  RESOLVED_SECURITY_MODE=""
  RESOLVED_INGRESS=""
  RESOLVED_VPC_MODE=""
  RESOLVED_CPU=""
  RESOLVED_MEMORY=""
  RESOLVED_CONCURRENCY=""
  RESOLVED_TIMEOUT=""
  RESOLVED_MIN_INSTANCES=""
  RESOLVED_MAX_INSTANCES=""
  RESOLVED_GCLOUD_FLAGS=()
  resolve_webapp_flags "EXTRACTER_WEB"

  local unified_svc
  if [[ "${DEPLOY_ENV}" == "PROD" ]]; then
    unified_svc="${PROD_UNIFIED_WEB_SERVICE_NAME:-${UNIFIED_WEB_SERVICE_NAME:-okf-engineering-workbench-prod}}"
    local pipe_job="${PROD_PIPELINE_JOB_NAME:-${PIPELINE_JOB_NAME:-okf-pipeline-job-prod}}"
  else
    unified_svc="${NONPROD_UNIFIED_WEB_SERVICE_NAME:-${UNIFIED_WEB_SERVICE_NAME:-okf-engineering-workbench}}"
    local pipe_job="${NONPROD_PIPELINE_JOB_NAME:-${PIPELINE_JOB_NAME:-okf-pipeline-job}}"
  fi

  local ext_model="${EXTRACTER_DEFAULT_MODEL:-gemini-4-carbon}"
  local qry_model="${QUERY_DEFAULT_MODEL:-gemini-4-hydrogen}"
  local allowed_models="${ALLOWED_GEMINI_MODELS:-gemini-4-carbon,gemini-4-hydrogen,gemini-4-argon,gemini-4-neon}"
  local embed_mode="${SPANNER_NATIVE_EMBEDDING_MODE:-native_ml_predict}"
  local embed_loc="${SPANNER_EMBEDDING_LOCATION:-${REGION}}"

  echo "=============================================================================="
  echo "[Cloud Run Unified] Deploying OKF Engineering Knowledge Workbench v2"
  echo "  Environment:      ${DEPLOY_ENV}"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  Service Name:     ${unified_svc}"
  echo "  Pipeline Job:     ${pipe_job}"
  echo "  Default Models:   Extractor=${ext_model} | Query=${qry_model}"
  echo "  Security/Ingress: ${RESOLVED_SECURITY_MODE} / ${RESOLVED_INGRESS} / VPC=${RESOLVED_VPC_MODE}"
  echo "  Sizing:           ${RESOLVED_CPU} vCPU / ${RESOLVED_MEMORY} / conc=${RESOLVED_CONCURRENCY} / timeout=${RESOLVED_TIMEOUT}s (${RESOLVED_MIN_INSTANCES}..${RESOLVED_MAX_INSTANCES})"
  echo "=============================================================================="

  # Use ^|^ custom delimiter so commas inside ALLOWED_GEMINI_MODELS are preserved verbatim by gcloud
  local env_str="^|^DEPLOYMENT_ENV=${DEPLOY_ENV}|GOOGLE_CLOUD_PROJECT=${PROJECT_ID}|GOOGLE_CLOUD_LOCATION=${REGION}|NONPROD_REGION=${REGION}|GOOGLE_GENAI_USE_VERTEXAI=true|GEMINI_LOCATION=${MODEL_LOCATION}|GEMINI_MODEL=${RESOLVED_GEMINI_MODEL}|EXTRACTER_DEFAULT_MODEL=${ext_model}|QUERY_DEFAULT_MODEL=${qry_model}|ALLOWED_GEMINI_MODELS=${allowed_models}|CLOUD_RUN_INGRESS=${RESOLVED_INGRESS}|CLOUD_RUN_SECURITY_MODE=${RESOLVED_SECURITY_MODE}|CLOUD_RUN_VPC_MODE=${RESOLVED_VPC_MODE}|EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-005}|SPANNER_NATIVE_EMBEDDING_MODE=${embed_mode}|SPANNER_EMBEDDING_LOCATION=${embed_loc}|USE_GCS_STORAGE=true|SOURCE_GCS_RAW_PREFIX=${RAW_PREFIX}|DESTINATION_GCS_BUCKET=${GCS_BUCKET}|DESTINATION_GCS_PREFIX=${GCS_PREFIX}|SPANNER_INSTANCE_ID=${SPANNER_INST}|SPANNER_DATABASE_ID=${SPANNER_DB}|DATAPLEX_ENTRY_GROUP_ID=${DATAPLEX_ENTRY_GROUP_ID:-okf-knowledge-assets}|DATAPLEX_TAG_TEMPLATE_ID=${DATAPLEX_TAG_TEMPLATE_ID:-okf-governance-template}|UNIFIED_WEB_SERVICE_NAME=${unified_svc}|PIPELINE_JOB_NAME=${pipe_job}|CLOUD_RUN_JOBS_EXECUTION_MODE=cloud_run_job|OUTPUT_BUNDLE_DIR=/tmp/okf_bundle|JOB_STATUS_DIR=/tmp/okf_job_status|APP_MODULE=unified_web.server:app"

  local cmd=(
    gcloud run deploy "${unified_svc}"
    --source="."
    --project="${PROJECT_ID}"
    --region="${REGION}"
    "${RESOLVED_GCLOUD_FLAGS[@]}"
    --no-cpu-throttling
    --cpu-boost
    --set-env-vars="${env_str}"
    --quiet
  )

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] ${cmd[*]}"
    return 0
  fi

  "${cmd[@]}"
  ensure_iap_service_agent_invoker "${unified_svc}" "${RESOLVED_SECURITY_MODE}"

  local unified_url
  unified_url="$(gcloud run services describe "${unified_svc}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --format='value(status.url)' 2>/dev/null || true)"
  if [[ -n "${unified_url}" ]]; then
    echo ""
    echo "=============================================================================="
    echo "OKF Engineering Workbench v2 Live:      ${unified_url}"
    echo "Liveness Health Probe (/healthz):       ${unified_url}/healthz"
    echo "Gemini Model Selector API:              ${unified_url}/api/models"
    echo "Unified Status API:                     ${unified_url}/api/status"
    echo "=============================================================================="
  fi
}

deploy_pipeline_job_cloud_run() {
  RESOLVED_SERVICE_NAME=""
  RESOLVED_GEMINI_MODEL=""
  RESOLVED_CLOUDBUILD_SA=""
  RESOLVED_RUNTIME_SA=""
  RESOLVED_SECURITY_MODE=""
  RESOLVED_INGRESS=""
  RESOLVED_VPC_MODE=""
  RESOLVED_CPU=""
  RESOLVED_MEMORY=""
  RESOLVED_CONCURRENCY=""
  RESOLVED_TIMEOUT=""
  RESOLVED_MIN_INSTANCES=""
  RESOLVED_MAX_INSTANCES=""
  RESOLVED_GCLOUD_FLAGS=()
  resolve_webapp_flags "EXTRACTER_WEB"

  local pipe_job
  if [[ "${DEPLOY_ENV}" == "PROD" ]]; then
    pipe_job="${PROD_PIPELINE_JOB_NAME:-${PIPELINE_JOB_NAME:-okf-pipeline-job-prod}}"
  else
    pipe_job="${NONPROD_PIPELINE_JOB_NAME:-${PIPELINE_JOB_NAME:-okf-pipeline-job}}"
  fi
  local job_timeout="${PIPELINE_JOB_TIMEOUT:-3600}"
  local ar_repo="${ARTIFACT_REGISTRY_REPO:-okf-workbench}"
  local image_uri="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ar_repo}/${pipe_job}:latest"
  local ext_model="${EXTRACTER_DEFAULT_MODEL:-gemini-4-carbon}"
  local embed_mode="${SPANNER_NATIVE_EMBEDDING_MODE:-native_ml_predict}"
  local embed_loc="${SPANNER_EMBEDDING_LOCATION:-${REGION}}"

  echo "=============================================================================="
  echo "[Cloud Run Job] Deploying Parameterized Pipeline Job (${pipe_job})"
  echo "  Environment:      ${DEPLOY_ENV}"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  Image:            ${image_uri}"
  echo "  Task Timeout:     ${job_timeout}s | CPU=${RESOLVED_CPU} | Memory=${RESOLVED_MEMORY}"
  echo "=============================================================================="

  local build_cmd=(
    gcloud builds submit "."
    --project="${PROJECT_ID}"
    --region="${REGION}"
    --tag="${image_uri}"
    --service-account="${RESOLVED_CLOUDBUILD_SA}"
    --quiet
  )

  local vpc_flags=()
  if [[ "${RESOLVED_VPC_MODE}" == "direct" ]]; then
    vpc_flags+=("--network=${CLOUD_RUN_VPC_NETWORK:-default}" "--subnet=${CLOUD_RUN_VPC_SUBNET:-default}" "--vpc-egress=${CLOUD_RUN_VPC_EGRESS:-all-traffic}")
  elif [[ "${RESOLVED_VPC_MODE}" == "connector" && -n "${CLOUD_RUN_VPC_CONNECTOR:-}" ]]; then
    vpc_flags+=("--vpc-connector=${CLOUD_RUN_VPC_CONNECTOR}" "--vpc-egress=${CLOUD_RUN_VPC_EGRESS:-all-traffic}")
  fi

  local job_env="DEPLOYMENT_ENV=${DEPLOY_ENV},GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=true,USE_GCS_STORAGE=true,GEMINI_LOCATION=${MODEL_LOCATION},GEMINI_MODEL=${ext_model},EXTRACTER_DEFAULT_MODEL=${ext_model},SPANNER_NATIVE_EMBEDDING_MODE=${embed_mode},SPANNER_EMBEDDING_LOCATION=${embed_loc},EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-005},SOURCE_GCS_RAW_PREFIX=${RAW_PREFIX},DESTINATION_GCS_BUCKET=${GCS_BUCKET},DESTINATION_GCS_PREFIX=${GCS_PREFIX},SPANNER_INSTANCE_ID=${SPANNER_INST},SPANNER_DATABASE_ID=${SPANNER_DB},DATAPLEX_ENTRY_GROUP_ID=${DATAPLEX_ENTRY_GROUP_ID:-okf-knowledge-assets},DATAPLEX_TAG_TEMPLATE_ID=${DATAPLEX_TAG_TEMPLATE_ID:-okf-governance-template},PIPELINE_JOB_NAME=${pipe_job},OUTPUT_BUNDLE_DIR=/tmp/okf_bundle,JOB_STATUS_DIR=/tmp/okf_job_status"

  local job_cmd=(
    gcloud run jobs deploy "${pipe_job}"
    --project="${PROJECT_ID}"
    --region="${REGION}"
    --image="${image_uri}"
    --command="python,-m,scripts.pipeline_job_runner"
    --service-account="${RESOLVED_RUNTIME_SA}"
    --cpu="${RESOLVED_CPU}"
    --memory="${RESOLVED_MEMORY}"
    --task-timeout="${job_timeout}s"
    --max-retries=1
    "${vpc_flags[@]}"
    --set-env-vars="${job_env}"
    --quiet
  )

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] ${build_cmd[*]}"
    echo "[DRY-RUN] ${job_cmd[*]}"
    return 0
  fi

  "${build_cmd[@]}"
  "${job_cmd[@]}"
  gcloud run jobs add-iam-policy-binding "${pipe_job}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --member="serviceAccount:${RESOLVED_RUNTIME_SA}" \
    --role="roles/run.developer" \
    --quiet >/dev/null 2>&1 || true
}

case "${TARGET}" in
  bootstrap)
    if [[ "${DRY_RUN}" -eq 1 ]]; then
      bash scripts/bootstrap_gcp_project.sh --env "${DEPLOY_ENV}" --dry-run
    else
      bash scripts/bootstrap_gcp_project.sh --env "${DEPLOY_ENV}"
    fi
    ;;
  infra)
    provision_infra
    ;;
  agent_runtime)
    deploy_agent_runtime
    ;;
  query_agent)
    deploy_query_agent_runtime
    ;;
  cloud_run)
    deploy_adk_web_cloud_run
    ;;
  query_web)
    deploy_query_web_cloud_run
    ;;
  unified_web)
    deploy_unified_workbench_cloud_run
    ;;
  pipeline_job)
    deploy_pipeline_job_cloud_run
    ;;
  all)
    refresh_adc_token
    provision_infra
    refresh_adc_token
    deploy_agent_runtime
    refresh_adc_token
    deploy_query_agent_runtime
    refresh_adc_token
    deploy_pipeline_job_cloud_run
    refresh_adc_token
    deploy_unified_workbench_cloud_run
    ;;
  *)
    echo "Invalid target '${TARGET}'. Expected: all | bootstrap | infra | agent_runtime | query_agent | unified_web | pipeline_job | cloud_run | query_web" >&2
    exit 1
    ;;
esac
