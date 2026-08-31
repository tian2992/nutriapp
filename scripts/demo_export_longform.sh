#!/usr/bin/env bash
# Demo: run the coverage report, then export the long-form growth dataset.
#
# Usage (from anywhere):
#   scripts/demo_export_longform.sh [csv|parquet]
#
# Defaults to parquet. Writes into nutriapp/exports/ (gitignored). See
# docs/longform_dataset.md for what the columns mean and
# scripts/demo_growth_splines.sh to fit a model against the result.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DJANGO_DIR="$REPO_ROOT/nutriapp"
FORMAT="${1:-parquet}"

for venv in "$REPO_ROOT/.venv" "$DJANGO_DIR/.venv"; do
  if [ -f "$venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$venv/bin/activate"
    break
  fi
done

cd "$DJANGO_DIR"

echo "== Coverage report (run this before trusting any model fit) =="
python manage.py growth_model_coverage_report

echo
echo "== Exporting long-form dataset (--format $FORMAT) =="
python manage.py export_longform --format "$FORMAT"

echo
echo "Done. Export written under $DJANGO_DIR/exports/."
