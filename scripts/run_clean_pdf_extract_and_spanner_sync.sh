#!/usr/bin/env bash
# ==============================================================================
# SIGHUP-Immune Detached Runner:
#   Step 1: Purge all extracted .md files (local build/okf_bundle & GCS prefix)
#   Step 2: Extract all 136 PDFs (PDF-by-PDF via Vertex AI Agent Runtime)
#           + Build OKF Indexes (with reciprocal topology & link normalization)
#           + Publish to GCS
#   Step 3: Purge and Re-ingest Cloud Spanner (okf-knowledge-spanner-gc /
#           okf_knowledge_graph-gc) & Dataplex Universal Catalog
# ==============================================================================

trap '' HUP
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${SCRIPT_DIR}"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

export PYTHONUNBUFFERED=1
export PYTHONPATH="${SCRIPT_DIR}"
export GOOGLE_GENAI_USE_VERTEXAI="true"
export GEMINI_LOCATION="${GEMINI_LOCATION:-global}"
export USE_GCS_STORAGE="true"
export OUTPUT_BUNDLE_DIR="${OUTPUT_BUNDLE_DIR:-build/okf_bundle}"
export DESTINATION_GCS_BUCKET="${DESTINATION_GCS_BUCKET:-${GOOGLE_CLOUD_PROJECT:-engineering-kg-demo}-okf-knowledge}"
export DESTINATION_GCS_PREFIX="${DESTINATION_GCS_PREFIX:-okf-bundles/engineering-kg-demo}"

mkdir -p evals/reports

echo "=============================================================================="
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [STEP 1/3] PURGING EXTRACTED MD FILES (LOCAL & GCS)"
echo "  Project:        ${GOOGLE_CLOUD_PROJECT}"
echo "  Local Bundle:   ${OUTPUT_BUNDLE_DIR}"
echo "  GCS Prefix:     gs://${DESTINATION_GCS_BUCKET}/${DESTINATION_GCS_PREFIX}"
echo "=============================================================================="

rm -rf "${OUTPUT_BUNDLE_DIR}"
mkdir -p "${OUTPUT_BUNDLE_DIR}"
rm -f evals/reports/live_vertex_eval_gc_by_pdf.json

gcloud storage rm --recursive "gs://${DESTINATION_GCS_BUCKET}/${DESTINATION_GCS_PREFIX}/**" \
  --project="${GOOGLE_CLOUD_PROJECT}" --quiet 2>/dev/null || true

LOCAL_MD_COUNT="$(find "${OUTPUT_BUNDLE_DIR}" -name '*.md' | wc -l)"
echo "  -> Local .md files remaining after purge: ${LOCAL_MD_COUNT}"

echo "=============================================================================="
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [STEP 2/3] EXTRACTING ALL 136 PDF FILES (PDF BY PDF)"
echo "  Agent Runtime:  ${NONPROD_AGENT_RUNTIME_ID}"
echo "  Model:          ${GEMINI_MODEL}"
echo "=============================================================================="

.venv/bin/python -u evals/run_live_vertex_eval.py \
  --dataset file-by-file \
  --skip-baseline \
  --limit 200 \
  --use-agent-runtime \
  --concurrency 3 \
  --resume \
  --output evals/reports/live_vertex_eval_gc_by_pdf.json

echo "=============================================================================="
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [STEP 2B/3] BUILDING OKF INDEXES, RETRO-ENRICHING & PUBLISHING TO GCS"
echo "=============================================================================="

.venv/bin/python -u -c '
from pathlib import Path
from extracter_agent.okf.indexer import generate_bundle_indexes
from extracter_agent.gcs.exporter import GCSExporter
from extracter_agent.config import get_config

cfg = get_config()
bundle_path = Path("build/okf_bundle")
generate_bundle_indexes(bundle_path)
exp = GCSExporter(bucket_name=cfg.destination_gcs_bucket)
res = exp.export_bundle(bundle_path, prefix=cfg.destination_gcs_prefix, dry_run=False)
print("GCS Export Complete:", res["files_count"], "files uploaded to", res["destination_root_uri"])
'

BUNDLE_VERSION="${BUNDLE_VERSION:-v3-gc-argon}"

echo "=============================================================================="
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] [STEP 3/3] PURGING & RE-INGESTING CLOUD SPANNER DATABASE"
echo "  Spanner Instance: ${SPANNER_INSTANCE_ID}"
echo "  Spanner Database: ${SPANNER_DATABASE_ID}"
echo "  Bundle Version:   ${BUNDLE_VERSION}"
echo "=============================================================================="

.venv/bin/python -u -m scripts.ingest_okf_bundle_to_spanner \
  --bundle-dir build/okf_bundle \
  --bundle-version "${BUNDLE_VERSION}" \
  --purge

.venv/bin/python -u -c '
from query_agent.spanner.repository import SpannerGraphRepository
repo = SpannerGraphRepository(use_in_memory=False)
print("Final Cloud Spanner Live Counts:", repo.get_live_counts(), flush=True)
'

echo "=============================================================================="
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ALL 3 STEPS COMPLETED SUCCESSFULLY!"
echo "=============================================================================="
