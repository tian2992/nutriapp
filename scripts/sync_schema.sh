#!/usr/bin/env bash
# sync_schema.sh - bring the database schema in line with the models, in the
# same local / compose / container modes as nutri_data.sh.
#
#   sync_schema.sh [--mode MODE] [--data-dir DIR] [--repair] [--no-makemigrations]
#
# Without --repair it only reports: makemigrations, migrate --run-syncdb, then
# a table-and-column comparison against the database (exit 4 on drift).
# With --repair it also adds the missing tables and columns.
#
# Typical use on a server whose database predates a model change:
#   scripts/sync_schema.sh            # see what is missing
#   scripts/sync_schema.sh --repair   # add it
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

global=() rest=()
while (($#)); do
  case "$1" in
    --mode|--data-dir)
      [ $# -ge 2 ] || { echo "[nutri-data] error: $1 needs a value" >&2; exit 1; }
      global+=("$1" "$2"); shift 2 ;;
    *) rest+=("$1"); shift ;;
  esac
done

exec "$SCRIPT_DIR/nutri_data.sh" ${global[@]+"${global[@]}"} sync-schema ${rest[@]+"${rest[@]}"}
