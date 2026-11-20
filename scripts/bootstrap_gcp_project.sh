#!/usr/bin/env bash
# ==============================================================================
# Idempotent GCP Project Bootstrap Script (SPEC-20261120-UNIFIED-WORKBENCH-V2)
# Prepares a brand-new GCP project (e.g., `engineering-kg-demo`) with:
#   1. Enabling all required Google Cloud APIs (Cloud Run, Build, Artifact Registry,
#      Vertex AI, Spanner, GCS, Dataplex, Lineage, IAP, Model Armor, DLP, etc.)
#   2. Creating service identities (Spanner, IAP) & granting Spanner SA
#      `roles/aiplatform.user` for native Spanner `ML.PREDICT` embeddings
#   3. Granting least-privilege runtime SA roles (Run Job developer, Spanner, GCS, Vertex, Dataplex)
#   4. Provisioning Artifact Registry repo, GCS bucket (+ reference/raw upload),
#      Cloud Spanner Enterprise instance/DB + DDL v2 (OkfTextEmbeddingModel + ANN Vector Index)
#
# Usage:
#   ./scripts/bootstrap_gcp_project.sh [--env nonprod|prod] [--dry-run]
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${SCRIPT_DIR}"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

DRY_RUN=0
DEPLOY_ENV="NONPROD"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --env|-e)
      DEPLOY_ENV="$(echo "$2" | tr '[:lower:]' '[:upper:]')"
      shift 2
      ;;
    --help|-h)
      sed -n '2,18p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-engineering-kg-demo}"
REGION="${GOOGLE_CLOUD_LOCATION:-asia-southeast1}"
AR_REPO="${ARTIFACT_REGISTRY_REPO:-okf-workbench}"
GCS_BUCKET="${DESTINATION_GCS_BUCKET:-${PROJECT_ID}-okf-knowledge}"
RAW_PREFIX="${SOURCE_GCS_RAW_PREFIX:-reference/raw}"
SPANNER_INST="${SPANNER_INSTANCE_ID:-okf-knowledge-spanner}"
SPANNER_DB="${SPANNER_DATABASE_ID:-okf_knowledge_graph}"
SPANNER_PU="${SPANNER_PROCESSING_UNITS:-100}"

REQUIRED_APIS=(
  "run.googleapis.com"
  "cloudbuild.googleapis.com"
  "artifactregistry.googleapis.com"
  "aiplatform.googleapis.com"
  "spanner.googleapis.com"
  "storage.googleapis.com"
  "dataplex.googleapis.com"
  "datalineage.googleapis.com"
  "iap.googleapis.com"
  "compute.googleapis.com"
  "iam.googleapis.com"
  "serviceusage.googleapis.com"
  "cloudresourcemanager.googleapis.com"
  "modelarmor.googleapis.com"
  "dlp.googleapis.com"
  "logging.googleapis.com"
  "monitoring.googleapis.com"
  "cloudtrace.googleapis.com"
  "secretmanager.googleapis.com"
  "config.googleapis.com"
)

run_cmd() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] $*"
  else
    "$@"
  fi
}

echo "=============================================================================="
echo "[Bootstrap] Preparing GCP Project for OKF Engineering Workbench v2"
echo "  Project ID:       ${PROJECT_ID}"
echo "  Region:           ${REGION}"
echo "  Environment:      ${DEPLOY_ENV}"
echo "  Artifact Repo:    ${AR_REPO}"
echo "  GCS Bucket:       gs://${GCS_BUCKET}"
echo "  Spanner:          ${SPANNER_INST} / ${SPANNER_DB} (${SPANNER_PU} PU, ENTERPRISE)"
echo "  Dry Run:          ${DRY_RUN}"
echo "=============================================================================="

echo "[1/5] Enabling ${#REQUIRED_APIS[@]} required Google Cloud APIs..."
run_cmd gcloud services enable "${REQUIRED_APIS[@]}" --project="${PROJECT_ID}" --quiet

PROJECT_NUMBER="${GOOGLE_CLOUD_PROJECT_NUMBER:-}"
if [[ "${DRY_RUN}" -eq 0 && ( -z "${PROJECT_NUMBER}" || "${PROJECT_NUMBER}" == "000000000000" ) ]]; then
  PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
fi
PROJECT_NUMBER="${PROJECT_NUMBER:-000000000000}"

echo "[2/5] Ensuring GCP Service Identities (Spanner & IAP) and IAM bindings..."
run_cmd gcloud beta services identity create --service=spanner.googleapis.com --project="${PROJECT_ID}" --quiet || true
run_cmd gcloud beta services identity create --service=iap.googleapis.com --project="${PROJECT_ID}" --quiet || true

SPANNER_SA="service-${PROJECT_NUMBER}@gcp-sa-spanner.iam.gserviceaccount.com"
RUNTIME_SA="${CLOUD_RUN_SERVICE_ACCOUNT:-${PROJECT_NUMBER}-compute@developer.gserviceaccount.com}"

echo "  -> Granting roles/aiplatform.user to Spanner Service Agent (${SPANNER_SA}) for native ML.PREDICT..."
run_cmd gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SPANNER_SA}" \
  --role="roles/aiplatform.user" \
  --quiet >/dev/null

RUNTIME_ROLES=(
  "roles/aiplatform.user"
  "roles/spanner.databaseUser"
  "roles/storage.objectAdmin"
  "roles/run.developer"
  "roles/dataplex.editor"
  "roles/datalineage.editor"
  "roles/logging.logWriter"
  "roles/cloudtrace.agent"
  "roles/artifactregistry.writer"
)
echo "  -> Granting runtime SA (${RUNTIME_SA}) required platform roles..."
for role in "${RUNTIME_ROLES[@]}"; do
  run_cmd gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${RUNTIME_SA}" \
    --role="${role}" \
    --quiet >/dev/null
done

echo "[3/5] Ensuring VPC Network/Subnet (Private Google Access + Cloud NAT) & Artifact Registry (${AR_REPO}) exist..."
VPC_NET="${CLOUD_RUN_VPC_NETWORK:-default}"
VPC_SUB="${CLOUD_RUN_VPC_SUBNET:-default}"
if [[ "${CLOUD_RUN_VPC_MODE:-direct}" == "direct" ]]; then
  if [[ "${DRY_RUN}" -eq 1 ]] || ! gcloud compute networks describe "${VPC_NET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    run_cmd gcloud compute networks create "${VPC_NET}" --project="${PROJECT_ID}" --subnet-mode=custom --quiet
  fi
  if [[ "${DRY_RUN}" -eq 1 ]] || ! gcloud compute networks subnets describe "${VPC_SUB}" --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    run_cmd gcloud compute networks subnets create "${VPC_SUB}" --project="${PROJECT_ID}" --network="${VPC_NET}" --region="${REGION}" --range=10.10.0.0/24 --enable-private-ip-google-access --quiet
  fi
  if [[ "${DRY_RUN}" -eq 1 ]] || ! gcloud compute routers describe okf-nat-router --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    run_cmd gcloud compute routers create okf-nat-router --project="${PROJECT_ID}" --network="${VPC_NET}" --region="${REGION}" --quiet
    run_cmd gcloud compute routers nats create okf-nat-gw --project="${PROJECT_ID}" --router=okf-nat-router --region="${REGION}" --auto-allocate-nat-external-ips --nat-all-subnet-ip-ranges --quiet
  fi
fi

if [[ "${DRY_RUN}" -eq 1 ]] || ! gcloud artifacts repositories describe "${AR_REPO}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  run_cmd gcloud artifacts repositories create "${AR_REPO}" \
    --repository-format=docker \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --description="OKF Engineering Workbench v2 container images (Cloud Run Service & Pipeline Job)" \
    --quiet
else
  echo "  -> Artifact Registry repository ${AR_REPO} already exists."
fi

echo "[4/5] Ensuring GCS Bucket & syncing local reference/raw/ documents..."
if [[ "${DRY_RUN}" -eq 1 ]] || ! gcloud storage buckets describe "gs://${GCS_BUCKET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  run_cmd gcloud storage buckets create "gs://${GCS_BUCKET}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --uniform-bucket-level-access \
    --quiet
else
  echo "  -> GCS bucket gs://${GCS_BUCKET} already exists."
fi

if [[ -d "reference/raw" ]]; then
  run_cmd gcloud storage rsync "reference/raw" "gs://${GCS_BUCKET}/${RAW_PREFIX}" \
    --project="${PROJECT_ID}" \
    --recursive \
    --exclude='(^|.*/)README\.md$' \
    --quiet
fi

echo "[5/5] Ensuring Cloud Spanner Enterprise instance, database & DDL v2 (ML.PREDICT + ANN Vector Index)..."
if [[ "${DRY_RUN}" -eq 1 ]] || ! gcloud spanner instances describe "${SPANNER_INST}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  run_cmd gcloud spanner instances create "${SPANNER_INST}" \
    --project="${PROJECT_ID}" \
    --config="regional-${REGION}" \
    --description="OKF Knowledge Graph v2" \
    --processing-units="${SPANNER_PU}" \
    --edition=ENTERPRISE \
    --quiet
else
  echo "  -> Cloud Spanner instance ${SPANNER_INST} already exists."
fi

if [[ "${DRY_RUN}" -eq 1 ]] || ! gcloud spanner databases describe "${SPANNER_DB}" --instance="${SPANNER_INST}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  run_cmd gcloud spanner databases create "${SPANNER_DB}" \
    --instance="${SPANNER_INST}" \
    --project="${PROJECT_ID}" \
    --ddl-file="query_agent/spanner/schema.sql" \
    --quiet
else
  echo "  -> Cloud Spanner database ${SPANNER_DB} already exists."
fi

if [[ "${DRY_RUN}" -eq 0 ]]; then
  PY_BIN=".venv/bin/python"
  [[ -x "${PY_BIN}" ]] || PY_BIN="$(command -v python3)"
  echo "  -> Applying idempotent Spanner DDL v2 (OkfTextEmbeddingModel + ANN Vector & Graph Secondary Indexes)..."
  PYTHONPATH=. "${PY_BIN}" -c '
from query_agent.spanner.repository import SpannerGraphRepository
repo = SpannerGraphRepository(use_in_memory=False)
print("DDL v2 result:", repo.ensure_schema_v2())
'
else
  echo "[DRY-RUN] PYTHONPATH=. .venv/bin/python -c 'from query_agent.spanner.repository import SpannerGraphRepository; SpannerGraphRepository(use_in_memory=False).ensure_schema_v2()'"
fi

echo "=============================================================================="
echo "[Bootstrap] Completed successfully for project ${PROJECT_ID}!"
echo "=============================================================================="
