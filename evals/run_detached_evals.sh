#!/usr/bin/env bash
# ==============================================================================
# SIGHUP-Immune Detached Deploy + Dual Evaluation Runner (Option A v2)
#
# Phase 0: Deploys the updated ADK Agent to Vertex AI Agent Runtime
#          (agent_runtime) and Cloud Run ADK Web UI (cloud_run) via ./deploy.sh.
# Phase 1: Executes the 139-case By-Equipment (wiki) evaluation into isolated
#          bundle directory build/okf_bundle_by_equipment (and syncs to
#          build/okf_bundle) with report evals/reports/live_vertex_eval_by_equipment.json
#          (also mirrored to evals/reports/live_vertex_eval_full.json).
# Phase 2: Executes the 136-case Individual PDF (file-by-file) evaluation into
#          isolated bundle directory build/okf_bundle_by_pdf and isolated GCS
#          prefix okf-bundles/phenol-plant-by-pdf with report
#          evals/reports/live_vertex_eval_by_pdf.json.
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

mkdir -p evals/reports build

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] === PHASE 0: Deploying Updated Agent Runtime & Cloud Run Web UI ===" > evals/reports/deploy_v2_live.log
rm -rf extracter_agent_tmp*
./deploy.sh --target all >> evals/reports/deploy_v2_live.log 2>&1
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] === PHASE 0 COMPLETE: Deployment Finished ===" >> evals/reports/deploy_v2_live.log

if [[ ! -d "build/okf_bundle_by_equipment" ]]; then
  cp -a build/okf_bundle build/okf_bundle_by_equipment
fi

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] === PHASE 1: Starting By-Equipment (wiki) Evaluation (139 Cases) ===" > evals/reports/by_equipment_eval_live.log

OUTPUT_BUNDLE_DIR="build/okf_bundle_by_equipment" \
DESTINATION_GCS_PREFIX="okf-bundles/phenol-plant-by-equipment" \
PYTHONPATH=. .venv/bin/python -u evals/run_live_vertex_eval.py \
  --use-agent-runtime \
  --dataset wiki \
  --limit 130 \
  --concurrency 4 \
  --resume \
  --output evals/reports/live_vertex_eval_by_equipment.json >> evals/reports/by_equipment_eval_live.log 2>&1

cp -f evals/reports/live_vertex_eval_by_equipment.json evals/reports/live_vertex_eval_full.json
cp -f evals/reports/by_equipment_eval_live.log evals/reports/full_eval_live.log

# Rebuild indexes for By-Equipment bundle and sync to main bundle + GCS
.venv/bin/python -c '
from pathlib import Path
from extracter_agent.okf.indexer import generate_bundle_indexes
from extracter_agent.gcs.exporter import GCSExporter
from extracter_agent.config import get_config

cfg = get_config()
b_eq = Path("build/okf_bundle_by_equipment")
generate_bundle_indexes(b_eq)
exp = GCSExporter(project_id=cfg.google_cloud_project)
exp.export_bundle(b_eq, cfg.destination_gcs_bucket, "okf-bundles/phenol-plant-by-equipment")
exp.export_bundle(b_eq, cfg.destination_gcs_bucket, cfg.destination_gcs_prefix)
' >> evals/reports/by_equipment_eval_live.log 2>&1

cp -a build/okf_bundle_by_equipment/. build/okf_bundle/
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] === PHASE 1 COMPLETE: Saved to build/okf_bundle_by_equipment ===" >> evals/reports/by_equipment_eval_live.log

# Prepare clean, isolated directory for Phase 2 (Individual PDF / file-by-file evaluation)
mkdir -p build/okf_bundle_by_pdf
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] === PHASE 2: Starting Clean Individual PDF (file-by-file) Evaluation (136 Raw PDFs) ===" > evals/reports/by_pdf_eval_live.log

OUTPUT_BUNDLE_DIR="build/okf_bundle_by_pdf" \
DESTINATION_GCS_PREFIX="okf-bundles/phenol-plant-by-pdf" \
PYTHONPATH=. .venv/bin/python -u evals/run_live_vertex_eval.py \
  --use-agent-runtime \
  --dataset file-by-file \
  --skip-baseline \
  --limit 136 \
  --concurrency 4 \
  --resume \
  --output evals/reports/live_vertex_eval_by_pdf.json >> evals/reports/by_pdf_eval_live.log 2>&1

# Rebuild indexes for By-PDF bundle and sync to GCS
.venv/bin/python -c '
from pathlib import Path
from extracter_agent.okf.indexer import generate_bundle_indexes
from extracter_agent.gcs.exporter import GCSExporter
from extracter_agent.config import get_config

cfg = get_config()
b_pdf = Path("build/okf_bundle_by_pdf")
generate_bundle_indexes(b_pdf)
exp = GCSExporter(project_id=cfg.google_cloud_project)
exp.export_bundle(b_pdf, cfg.destination_gcs_bucket, "okf-bundles/phenol-plant-by-pdf")
' >> evals/reports/by_pdf_eval_live.log 2>&1

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] === PHASE 2 COMPLETE: Individual PDF Evaluation Finished ===" >> evals/reports/by_pdf_eval_live.log
