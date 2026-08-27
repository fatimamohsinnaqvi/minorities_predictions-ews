#!/usr/bin/env bash
# Reproduce the headline forecasting analysis (rolling-origin validation +
# calibration). Creates a local venv, installs deps, runs the eval.
# Usage:  bash run.sh
set -e

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "==> Creating virtual environment (.venv) ..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Installing analysis dependencies ..."
pip install --quiet --upgrade pip
pip install --quiet pandas numpy scikit-learn matplotlib scipy joblib

echo "==> Running temporal validation ..."
python src/models/psweek_temporal_eval.py

echo ""
echo "==> Done. See:"
echo "    outputs/reports/psweek_temporal_eval.json"
echo "    outputs/figures/model/psweek_rolling_origin.png"
echo "    outputs/figures/model/psweek_calibration.png"
echo ""
echo "To run the dashboard instead:  cd dashboard && pip install -r requirements.txt && streamlit run app.py"
