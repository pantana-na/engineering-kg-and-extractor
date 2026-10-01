#!/usr/bin/env bash
# ==============================================================================
# Detached Dual-Mode Live Vertex AI Evaluation Runner (V5)
#
# Strictly preserves all V1, V2, V3, and V4 bundles and reports intact for
# historical comparison, and executes both V5 modes concurrently in isolated
# local & GCS targets:
#   1. By-Equipment / By-Product (--dataset wiki):
#      - Bundle:  build/okf_bundle_by_equipment_v5/
#      - GCS:     gs://.../okf-bundles/phenol-plant-by-equipment-v5
#      - Report:  evals/reports/live_vertex_eval_by_equipment_v5.json
#      - Log:     evals/reports/by_equipment_eval_v5.log
#   2. By-PDF (--dataset file-by-file):
#      - Bundle:  build/okf_bundle_by_pdf_v5/
#      - GCS:     gs://.../okf-bundles/phenol-plant-by-pdf-v5
#      - Report:  evals/reports/live_vertex_eval_by_pdf_v5.json
#      - Log:     evals/reports/by_pdf_eval_v5.log
# ==============================================================================

set -uo pipefail
trap '' HUP

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

echo "=============================================================================="
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] VERIFYING V4 BUNDLES & REPORTS ARE PRESERVED"
echo "=============================================================================="
ls -ld build/okf_bundle_by_pdf_v4 build/okf_bundle_by_equipment_v4 \
       evals/reports/live_vertex_eval_by_pdf_v4.json \
       evals/reports/live_vertex_eval_by_equipment_v4.json

run_by_equipment_v5() {
  echo "=============================================================================="
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] STARTING V5 BY-EQUIPMENT (--dataset wiki)"
  echo "=============================================================================="
  rm -rf build/okf_bundle_by_equipment_v5 evals/reports/live_vertex_eval_by_equipment_v5.json
  mkdir -p build/okf_bundle_by_equipment_v5

  OUTPUT_BUNDLE_DIR="build/okf_bundle_by_equipment_v5" \
  DESTINATION_GCS_PREFIX="okf-bundles/phenol-plant-by-equipment-v5" \
  .venv/bin/python evals/run_live_vertex_eval.py \
    --dataset wiki \
    --limit 200 \
    --use-agent-runtime \
    --concurrency 3 \
    --resume \
    --output evals/reports/live_vertex_eval_by_equipment_v5.json \
    > evals/reports/by_equipment_eval_v5.log 2>&1

  .venv/bin/python -c '
from pathlib import Path
from extracter_agent.okf.indexer import generate_bundle_indexes
from extracter_agent.gcs.exporter import GCSExporter
from extracter_agent.config import get_config

cfg = get_config()
b_eq = Path("build/okf_bundle_by_equipment_v5")
generate_bundle_indexes(b_eq)
exp = GCSExporter(bucket_name=cfg.destination_gcs_bucket)
exp.export_bundle(b_eq, prefix="okf-bundles/phenol-plant-by-equipment-v5")
' >> evals/reports/by_equipment_eval_v5.log 2>&1

  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] COMPLETED V5 BY-EQUIPMENT"
}

run_by_pdf_v5() {
  echo "=============================================================================="
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] STARTING V5 BY-PDF (--dataset file-by-file)"
  echo "=============================================================================="
  rm -rf build/okf_bundle_by_pdf_v5 evals/reports/live_vertex_eval_by_pdf_v5.json
  mkdir -p build/okf_bundle_by_pdf_v5

  OUTPUT_BUNDLE_DIR="build/okf_bundle_by_pdf_v5" \
  DESTINATION_GCS_PREFIX="okf-bundles/phenol-plant-by-pdf-v5" \
  .venv/bin/python evals/run_live_vertex_eval.py \
    --dataset file-by-file \
    --skip-baseline \
    --limit 200 \
    --use-agent-runtime \
    --concurrency 3 \
    --resume \
    --output evals/reports/live_vertex_eval_by_pdf_v5.json \
    > evals/reports/by_pdf_eval_v5.log 2>&1

  .venv/bin/python -c '
from pathlib import Path
from extracter_agent.okf.indexer import generate_bundle_indexes
from extracter_agent.gcs.exporter import GCSExporter
from extracter_agent.config import get_config

cfg = get_config()
b_pdf = Path("build/okf_bundle_by_pdf_v5")
generate_bundle_indexes(b_pdf)
exp = GCSExporter(bucket_name=cfg.destination_gcs_bucket)
exp.export_bundle(b_pdf, prefix="okf-bundles/phenol-plant-by-pdf-v5")
' >> evals/reports/by_pdf_eval_v5.log 2>&1

  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] COMPLETED V5 BY-PDF"
}

run_by_equipment_v5 &
PID_EQ=$!

run_by_pdf_v5 &
PID_PDF=$!

echo "Launched V5 By-Equipment (PID=${PID_EQ}) and V5 By-PDF (PID=${PID_PDF})"
wait "${PID_EQ}" "${PID_PDF}"

echo "=============================================================================="
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ALL V5 EVALUATIONS COMPLETED"
echo "=============================================================================="
