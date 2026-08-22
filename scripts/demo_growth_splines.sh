#!/usr/bin/env bash
# Demo: fit analysis/growth_splines.R against the most recent CSV export.
#
# Usage (from anywhere):
#   scripts/demo_growth_splines.sh                 # uses the latest CSV export, generating one if none exists
#   scripts/demo_growth_splines.sh path/to/export.csv
#
# Uses CSV (not parquet) by default so the demo needs no extra R packages
# beyond base R + nlme - see analysis/growth_splines.R for the parquet option.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DJANGO_DIR="$REPO_ROOT/nutriapp"
EXPORTS_DIR="$DJANGO_DIR/exports"
R_SCRIPT="$REPO_ROOT/analysis/growth_splines.R"

if ! command -v Rscript >/dev/null 2>&1; then
  echo "Rscript not found on PATH. Install R first (e.g. 'sudo apt install r-base' on Debian)." >&2
  exit 1
fi

EXPORT_PATH="${1:-}"
if [ -z "$EXPORT_PATH" ]; then
  EXPORT_PATH="$(ls -t "$EXPORTS_DIR"/longform_*.csv 2>/dev/null | head -n1 || true)"
fi

if [ -z "$EXPORT_PATH" ]; then
  echo "No CSV export found under $EXPORTS_DIR - generating one now."
  "$SCRIPT_DIR/demo_export_longform.sh" csv
  EXPORT_PATH="$(ls -t "$EXPORTS_DIR"/longform_*.csv | head -n1)"
fi

echo "== Fitting growth_splines.R against $EXPORT_PATH =="
Rscript "$R_SCRIPT" "$EXPORT_PATH"
