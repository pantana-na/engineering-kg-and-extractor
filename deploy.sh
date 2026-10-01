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
# Usage:
#   ./deploy.sh --target all            # Provision infra + deploy all agents & UIs
#   ./deploy.sh --target infra          # Provision GCS bucket, raw PDFs & Spanner DB
#   ./deploy.sh --target agent_runtime  # Deploy Agent 1 (Extracter Agent)
#   ./deploy.sh --target query_agent    # Deploy Agent 2 (Spanner Query Agent)
#   ./deploy.sh --target cloud_run      # Deploy Workbench 1 (extracter-agent-web)
#   ./deploy.sh --target query_web      # Deploy Workbench 2 (okf-query-agent-web)
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Load unified .env configuration if present (Rule 8)
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-your-gcp-project-id}"
REGION="${NONPROD_REGION:-asia-southeast1}"
MODEL_LOCATION="${GEMINI_LOCATION:-global}"
AGENT_DIR="extracter_agent"
AGENT_DISPLAY_NAME="${SERVICE_NAME:-extracter-agent}"
QUERY_AGENT_DISPLAY_NAME="${QUERY_SERVICE_NAME:-okf-query-agent}"
WEB_SERVICE_NAME="${CLOUD_RUN_WEB_SERVICE:-extracter-agent-web}"
GCS_BUCKET="${DESTINATION_GCS_BUCKET:-${PROJECT_ID}-okf-knowledge}"
GCS_PREFIX="${DESTINATION_GCS_PREFIX:-okf-bundles/chemical-plant}"
RAW_PREFIX="${SOURCE_GCS_RAW_PREFIX:-reference/raw}"
MODEL_NAME="${GEMINI_MODEL:-gemini-3.8-flash}"
SPANNER_INST="${SPANNER_INSTANCE_ID:-okf-knowledge-spanner}"
SPANNER_DB="${SPANNER_DATABASE_ID:-okf_knowledge_graph}"
SPANNER_PU="${SPANNER_PROCESSING_UNITS:-100}"

# Ensure gcloud uses fresh Application Default Credentials token when available
if command -v gcloud >/dev/null 2>&1; then
  ADC_TOKEN="$(gcloud auth application-default print-access-token 2>/dev/null || true)"
  if [[ -n "${ADC_TOKEN}" ]]; then
    export CLOUDSDK_AUTH_ACCESS_TOKEN="${ADC_TOKEN}"
  fi
fi

TARGET="cloud_run"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target|-t)
      TARGET="$2"
      shift 2
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
    all)
      TARGET="all"
      shift
      ;;
    --help|-h)
      sed -n '2,19p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

provision_infra() {
  echo "=============================================================================="
  echo "[Infra] Ensuring GCS Bucket, Raw PDFs & Cloud Spanner Graph DB Exist"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  GCS Bucket:       gs://${GCS_BUCKET}"
  echo "  Spanner Instance: ${SPANNER_INST} (${SPANNER_PU} PU)"
  echo "  Spanner Database: ${SPANNER_DB}"
  echo "=============================================================================="

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
    echo "Uploading synthetic raw engineering PDFs from reference/raw/ to gs://${GCS_BUCKET}/${RAW_PREFIX}/..."
    gcloud storage rsync "reference/raw" "gs://${GCS_BUCKET}/${RAW_PREFIX}" \
      --project="${PROJECT_ID}" \
      --recursive \
      --quiet
  fi

  if ! gcloud spanner instances describe "${SPANNER_INST}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "Creating Cloud Spanner instance ${SPANNER_INST} (${SPANNER_PU} PU) in regional-${REGION}..."
    gcloud spanner instances create "${SPANNER_INST}" \
      --project="${PROJECT_ID}" \
      --config="regional-${REGION}" \
      --description="OKF Graph-RAG Knowledge Base (${SPANNER_INST})" \
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
  local raw_engine_id="${NONPROD_AGENT_RUNTIME_ID:-}"
  local agent_engine_id="${raw_engine_id##*/}"
  local adk_bin=".venv/bin/adk"
  if [[ ! -x "${adk_bin}" ]]; then
    adk_bin="$(command -v adk || true)"
  fi

  echo "=============================================================================="
  echo "[1/2] Deploying ADK Agent to Gemini Enterprise Agent Platform (agent_runtime)"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  Model Location:   ${MODEL_LOCATION}"
  echo "  Display Name:     ${AGENT_DISPLAY_NAME}"
  echo "=============================================================================="

  if [[ -n "${agent_engine_id}" && "${agent_engine_id}" =~ ^[0-9]+$ ]]; then
    "${adk_bin}" deploy agent_engine \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --agent_engine_id="${agent_engine_id}" \
      --display_name="${AGENT_DISPLAY_NAME}" \
      "${AGENT_DIR}"
  else
    "${adk_bin}" deploy agent_engine \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --display_name="${AGENT_DISPLAY_NAME}" \
      "${AGENT_DIR}"
  fi
}

deploy_query_agent_runtime() {
  local raw_engine_id="${NONPROD_QUERY_AGENT_RUNTIME_ID:-}"
  local agent_engine_id="${raw_engine_id##*/}"
  local adk_bin=".venv/bin/adk"
  if [[ ! -x "${adk_bin}" ]]; then
    adk_bin="$(command -v adk || true)"
  fi

  echo "=============================================================================="
  echo "[Query Agent] Deploying Separate OKF Spanner Query Agent to agent_runtime"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  Model Location:   ${MODEL_LOCATION}"
  echo "  Display Name:     ${QUERY_AGENT_DISPLAY_NAME}"
  echo "=============================================================================="

  if [[ -n "${agent_engine_id}" && "${agent_engine_id}" =~ ^[0-9]+$ ]]; then
    "${adk_bin}" deploy agent_engine \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --agent_engine_id="${agent_engine_id}" \
      --display_name="${QUERY_AGENT_DISPLAY_NAME}" \
      "query_agent"
  else
    "${adk_bin}" deploy agent_engine \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --display_name="${QUERY_AGENT_DISPLAY_NAME}" \
      "query_agent"
  fi
}

deploy_adk_web_cloud_run() {
  echo "=============================================================================="
  echo "[Cloud Run] Deploying OKF v0.2 Engineering Extraction Workbench"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  Model Location:   ${MODEL_LOCATION}"
  echo "  Model Name:       ${MODEL_NAME}"
  echo "  Service Name:     ${WEB_SERVICE_NAME}"
  echo "  GCS Bucket:       gs://${GCS_BUCKET}/${GCS_PREFIX}"
  echo "=============================================================================="

  gcloud run deploy "${WEB_SERVICE_NAME}" \
    --source="." \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --no-invoker-iam-check \
    --no-cpu-throttling \
    --memory=2Gi \
    --cpu=2 \
    --timeout=600 \
    --min-instances="${NONPROD_MIN_INSTANCES:-0}" \
    --max-instances="${NONPROD_MAX_INSTANCES:-3}" \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},NONPROD_REGION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=true,GEMINI_LOCATION=${MODEL_LOCATION},GEMINI_MODEL=${MODEL_NAME},USE_GCS_STORAGE=true,SOURCE_GCS_RAW_PREFIX=${RAW_PREFIX},DESTINATION_GCS_BUCKET=${GCS_BUCKET},DESTINATION_GCS_PREFIX=${GCS_PREFIX},SPANNER_INSTANCE_ID=${SPANNER_INST},SPANNER_DATABASE_ID=${SPANNER_DB},OUTPUT_BUNDLE_DIR=/tmp/okf_bundle,APP_MODULE=extracter_agent.web_server:app" \
    --quiet

  local web_url
  web_url="$(gcloud run services describe "${WEB_SERVICE_NAME}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --format='value(status.url)' 2>/dev/null || true)"
  if [[ -n "${web_url}" ]]; then
    echo ""
    echo "=============================================================================="
    echo "OKF Extraction Workbench Live:          ${web_url}"
    echo "Architecture Diagram Live:              ${web_url}/architecture-diagram"
    echo "Google ADK Developer UI Live:           ${web_url}/dev-ui/?app=extracter_agent"
    echo "Live Telemetry Status API:              ${web_url}/api/demo/status"
    echo "=============================================================================="
  fi
}

deploy_query_web_cloud_run() {
  local query_web_service="${QUERY_WEB_SERVICE_NAME:-okf-query-agent-web}"
  local query_runtime_id="${NONPROD_QUERY_AGENT_RUNTIME_ID:-}"

  echo "=============================================================================="
  echo "[Cloud Run] Deploying Separate OKF Spanner Graph & Retrieval Workbench UI"
  echo "  Project:          ${PROJECT_ID}"
  echo "  Region:           ${REGION}"
  echo "  Model Location:   ${MODEL_LOCATION}"
  echo "  Model Name:       ${MODEL_NAME}"
  echo "  Service Name:     ${query_web_service}"
  echo "  Spanner DB:       ${SPANNER_INST} / ${SPANNER_DB}"
  echo "=============================================================================="

  gcloud run deploy "${query_web_service}" \
    --source="." \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --no-invoker-iam-check \
    --no-cpu-throttling \
    --memory=2Gi \
    --cpu=2 \
    --timeout=600 \
    --min-instances="${NONPROD_MIN_INSTANCES:-0}" \
    --max-instances="${NONPROD_MAX_INSTANCES:-3}" \
    --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},NONPROD_REGION=${REGION},GOOGLE_GENAI_USE_VERTEXAI=true,GEMINI_LOCATION=${MODEL_LOCATION},GEMINI_MODEL=${MODEL_NAME},SPANNER_INSTANCE_ID=${SPANNER_INST},SPANNER_DATABASE_ID=${SPANNER_DB},QUERY_AGENT_RUNTIME_ID=${query_runtime_id##*/},DESTINATION_GCS_BUCKET=${GCS_BUCKET},DESTINATION_GCS_PREFIX=${GCS_PREFIX},APP_MODULE=query_agent.web_server:app" \
    --quiet

  local query_web_url
  query_web_url="$(gcloud run services describe "${query_web_service}" \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --format='value(status.url)' 2>/dev/null || true)"
  if [[ -n "${query_web_url}" ]]; then
    echo ""
    echo "=============================================================================="
    echo "OKF Spanner Retrieval Workbench Live:   ${query_web_url}"
    echo "Liveness Health Probe (/healthz):       ${query_web_url}/healthz"
    echo "Spanner Hierarchy API:                  ${query_web_url}/api/spanner/hierarchy"
    echo "Spanner Interactive Graph API:          ${query_web_url}/api/spanner/graph?center_tag=D-2304"
    echo "Dataplex Universal Catalog API:         ${query_web_url}/api/catalog"
    echo "=============================================================================="
  fi
}

case "${TARGET}" in
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
  all)
    provision_infra
    deploy_agent_runtime
    deploy_query_agent_runtime
    deploy_adk_web_cloud_run
    deploy_query_web_cloud_run
    ;;
  *)
    echo "Invalid target '${TARGET}'. Expected: all | infra | agent_runtime | query_agent | cloud_run | query_web" >&2
    exit 1
    ;;
esac
