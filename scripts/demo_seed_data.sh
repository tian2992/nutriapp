#!/usr/bin/env bash
# Demo: seed the database with synthetic patients/visits/measurements for
# exercising export_longform, growth_model_coverage_report, and
# analysis/growth_splines.R without real patient data. Run this first, then
# scripts/demo_export_longform.sh and scripts/demo_growth_splines.sh.
#
# Usage (from anywhere):
#   scripts/demo_seed_data.sh
#   scripts/demo_seed_data.sh --patients 30 --min-visits 10 --max-visits 14
#
# All arguments are passed straight through to `generate_demo_data`; see
# `python manage.py generate_demo_data --help` for the full option list.
# Refuses to run against a database that already has Patient rows unless you
# pass --force yourself - never do that against real clinic data.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DJANGO_DIR="$REPO_ROOT/nutriapp"

for venv in "$REPO_ROOT/.venv" "$DJANGO_DIR/.venv"; do
  if [ -f "$venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$venv/bin/activate"
    break
  fi
done

cd "$DJANGO_DIR"

echo "== Seeding synthetic demo data =="
python manage.py generate_demo_data "$@"

echo
echo "Done. Try scripts/demo_export_longform.sh next, then scripts/demo_growth_splines.sh."
