#!/usr/bin/env bash
set -euo pipefail

# Script to run calculate_justetf_returns.py
# Usage:
#   ./run_returns.sh
# or:
#   bash run_returns.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"
PY_SCRIPT="calculate_justetf_returns.py"
MONTHLY_INSTRUMENTS_FILE="input/instruments.csv"
BENCHMARK_INSTRUMENTS_FILE="input/benchmark_instruments.csv"
WEIGHTS_FILE="input/weights.csv"
MONTHLY_OUTPUT_FILE="output/db_HistoryMonthly.csv"
BENCHMARK_OUTPUT_FILE="output/db_HistoryBenchmark.csv"
START_DATE="2024-09-01"
# Last complete available month: the final day of the previous month.
END_DATE="$(date -v1d -v-1m -v+1m -v-1d '+%Y-%m-%d')"

mkdir -p output

if [ ! -x "$VENV_PYTHON" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: Python 3 is required to create $VENV_DIR, but python3 was not found."
    exit 1
  fi

  echo "Virtual environment missing or incomplete: $VENV_DIR"
  echo "Creating virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

# Use the virtual environment interpreter directly instead of depending on
# activation to update PATH (which may not provide a `python` command).
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install pandas git+https://github.com/druzsan/justetf-scraping.git

if [ ! -f "$PY_SCRIPT" ]; then
  echo "Error: missing $PY_SCRIPT in current folder: $SCRIPT_DIR"
  exit 1
fi

if [ ! -f "$MONTHLY_INSTRUMENTS_FILE" ]; then
  echo "Error: missing $MONTHLY_INSTRUMENTS_FILE in current folder: $SCRIPT_DIR"
  exit 1
fi

if [ ! -f "$BENCHMARK_INSTRUMENTS_FILE" ]; then
  echo "Error: missing $BENCHMARK_INSTRUMENTS_FILE in current folder: $SCRIPT_DIR"
  exit 1
fi

if [ ! -f "$WEIGHTS_FILE" ]; then
  echo "Warning: missing $WEIGHTS_FILE. Proceeding without weights for the monthly file."
  "$VENV_PYTHON" "$PY_SCRIPT" \
    --instruments "$MONTHLY_INSTRUMENTS_FILE" \
    --output "$MONTHLY_OUTPUT_FILE" \
    --start "$START_DATE" \
    --end "$END_DATE"
else
  "$VENV_PYTHON" "$PY_SCRIPT" \
    --instruments "$MONTHLY_INSTRUMENTS_FILE" \
    --weights "$WEIGHTS_FILE" \
    --output "$MONTHLY_OUTPUT_FILE" \
    --start "$START_DATE" \
    --end "$END_DATE"
fi

"$VENV_PYTHON" "$PY_SCRIPT" \
  --instruments "$BENCHMARK_INSTRUMENTS_FILE" \
  --output "$BENCHMARK_OUTPUT_FILE" \
  --start "$START_DATE" \
  --end "$END_DATE" \
  --benchmark-mode

echo "Done. Generated files: $MONTHLY_OUTPUT_FILE, $BENCHMARK_OUTPUT_FILE"
