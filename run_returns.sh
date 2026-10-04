#!/usr/bin/env bash
set -euo pipefail

# Script to run calculate_justetf_returns.py
# Usage:
#   ./run_returns.sh [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--output-dir DIR]
# or:
#   bash run_returns.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"
PY_SCRIPT="calculate_justetf_returns.py"
REQUIREMENTS_FILE="requirements.txt"
MONTHLY_INSTRUMENTS_FILE="input/instruments.csv"
BENCHMARK_INSTRUMENTS_FILE="input/benchmark_instruments.csv"
WEIGHTS_FILE="input/weights.csv"
START_DATE="2024-09-01"
END_DATE=""
OUTPUT_DIR="output"
RETRIES=3

usage() {
  echo "Usage: $0 [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--output-dir DIR] [--retries N]"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --start)
      [ "$#" -ge 2 ] || { echo "[ERROR] --start requires a date."; exit 1; }
      START_DATE="$2"
      shift 2
      ;;
    --end)
      [ "$#" -ge 2 ] || { echo "[ERROR] --end requires a date."; exit 1; }
      END_DATE="$2"
      shift 2
      ;;
    --output-dir)
      [ "$#" -ge 2 ] || { echo "[ERROR] --output-dir requires a directory."; exit 1; }
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --retries)
      [ "$#" -ge 2 ] || { echo "[ERROR] --retries requires a number."; exit 1; }
      RETRIES="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

MONTHLY_OUTPUT_FILE="$OUTPUT_DIR/db_HistoryMonthly.csv"
BENCHMARK_OUTPUT_FILE="$OUTPUT_DIR/db_HistoryBenchmark.csv"

# Last complete available month: the final day of the previous month.
if [ -z "$END_DATE" ]; then
  END_DATE="$(date -v1d -v-1m -v+1m -v-1d '+%Y-%m-%d')"
fi

mkdir -p "$OUTPUT_DIR"

on_error() {
  echo "[ERROR] Run stopped at line $1. Check the message above and your input files."
}
trap 'on_error $LINENO' ERR

if [ ! -x "$VENV_PYTHON" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] Python 3 is required to create $VENV_DIR, but python3 was not found."
    exit 1
  fi

  echo "[INFO] Creating local Python environment in $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
  if [ ! -f "$REQUIREMENTS_FILE" ]; then
    echo "[ERROR] Missing $REQUIREMENTS_FILE in $SCRIPT_DIR."
    exit 1
  fi
  echo "[INFO] Installing dependencies from $REQUIREMENTS_FILE..."
  "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_FILE"
else
  echo "[INFO] Reusing local Python environment: $VENV_DIR"
fi

# Use the virtual environment interpreter directly instead of depending on
# activation to update PATH (which may not provide a `python` command). To
# update dependencies later, run: "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS_FILE" --upgrade

if [ ! -f "$PY_SCRIPT" ]; then
  echo "[ERROR] Missing $PY_SCRIPT in current folder: $SCRIPT_DIR"
  exit 1
fi

if [ ! -f "$MONTHLY_INSTRUMENTS_FILE" ]; then
  echo "[ERROR] Missing $MONTHLY_INSTRUMENTS_FILE in current folder: $SCRIPT_DIR"
  exit 1
fi

if [ ! -f "$BENCHMARK_INSTRUMENTS_FILE" ]; then
  echo "[ERROR] Missing $BENCHMARK_INSTRUMENTS_FILE in current folder: $SCRIPT_DIR"
  exit 1
fi

if [ ! -f "$WEIGHTS_FILE" ]; then
  echo "[WARNING] Missing $WEIGHTS_FILE. Proceeding without weights for the portfolio file."
  echo "[INFO] Generating portfolio returns..."
  "$VENV_PYTHON" "$PY_SCRIPT" \
    --instruments "$MONTHLY_INSTRUMENTS_FILE" \
    --output "$MONTHLY_OUTPUT_FILE" \
    --start "$START_DATE" \
    --end "$END_DATE" \
    --retries "$RETRIES"
else
  echo "[INFO] Generating portfolio returns..."
  "$VENV_PYTHON" "$PY_SCRIPT" \
    --instruments "$MONTHLY_INSTRUMENTS_FILE" \
    --weights "$WEIGHTS_FILE" \
    --output "$MONTHLY_OUTPUT_FILE" \
    --start "$START_DATE" \
    --end "$END_DATE" \
    --retries "$RETRIES"
fi

echo "[INFO] Generating benchmark returns..."
"$VENV_PYTHON" "$PY_SCRIPT" \
  --instruments "$BENCHMARK_INSTRUMENTS_FILE" \
  --output "$BENCHMARK_OUTPUT_FILE" \
  --start "$START_DATE" \
  --end "$END_DATE" \
  --benchmark-mode \
  --retries "$RETRIES"

echo "[SUCCESS] Run complete. Generated files:"
echo "  - $MONTHLY_OUTPUT_FILE"
echo "  - $BENCHMARK_OUTPUT_FILE"
