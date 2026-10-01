#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${SCRIPT_DIR}"

if [[ -f ".env" ]]; then
  set -a
  source ".env"
  set +a
fi

mkdir -p build/eval_reports

echo "Starting 120-Question Live OKF Spanner Query Agent Evaluation..."
PYTHONPATH=. .venv/bin/python evals/run_live_query_agent_eval.py \
  --dataset evals/datasets/query_agent_spanner_eval.jsonl \
  --checkpoint build/eval_reports/query_agent_spanner_eval_checkpoint.jsonl \
  --report-json build/eval_reports/query_agent_spanner_eval_report.json \
  --report-md specs/plan/QUERY_AGENT_EVAL_REPORT.md \
  --use-agent-runtime \
  --concurrency 3 \
  "$@"
