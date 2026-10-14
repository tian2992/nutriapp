#!/usr/bin/env bash
# nutri_data.sh - bulk-load a field workbook, export and import fixtures.
#
#   nutri_data.sh [--mode MODE] [--data-dir DIR] COMMAND [options]
#
# Commands
#   load-xlsx FILE [--profile P] [--sheet S] [--batch-id B] [--dry-run] [--quiet-warnings]
#       Runs `manage.py load_xlsx_patients`. FILE and a --profile JSON path are
#       taken from the machine you run this on, whatever the mode.
#   export-fixtures [--output FILE] [--models "app.Model ..."] [--indent N]
#       Runs `manage.py dumpdata` into FILE (default DATA_DIR/fixtures/
#       nutriapp_<timestamp>.json). A .gz/.bz2/.xz extension compresses it.
#       Default models: anthrocalc and auth.user (visits point at their user).
#   import-fixtures FILE [--force]
#       Runs `manage.py loaddata`. Refuses a database that already holds
#       patients or visits unless --force: fixtures carry primary keys and
#       overwrite whatever row has the same one.
#   sync-schema [--repair] [--no-makemigrations]
#       Runs `makemigrations`, then `migrate --run-syncdb`, then compares every
#       model's table and columns with the database. --run-syncdb only creates
#       tables for apps WITHOUT migrations, so it cannot add a column such as
#       visit.entered_by to a table that already exists; the comparison finds
#       those, and --repair adds them (create_model / add_field, as a
#       migration would). Exit 4 if drift remains. See scripts/sync_schema.sh.
#
# Modes (--mode, or NUTRI_MODE; default auto)
#   local      python manage.py in this checkout, using its .venv if present.
#              Honors DATABASE_URL / .env; SQLite when neither is set.
#   compose    `docker compose run --rm web python manage.py ...`: a throwaway
#              container on the compose network. Input and output files are
#              bind-mounted for the run, so nothing needs to be baked into the
#              image.
#   container  we are already inside the app container (the image ships this
#              script as `nutri-data`); run manage.py in place. Paths are
#              container paths.
#   auto       container when inside one, else compose when docker and the
#              compose file are usable (ADR 0001), else local.
#
# Environment
#   NUTRI_MODE          same as --mode
#   NUTRI_DATA_DIR      where default fixture output goes (default <repo>/data,
#                       or /data inside a container)
#   NUTRI_SERVICE       compose service to run in (default web)
#   NUTRI_COMPOSE_FILE  compose file (default <repo>/docker-compose.yaml)
#   NUTRI_RUN_USER      uid:gid for compose runs (default: the caller's, so
#                       files written to bind mounts belong to you). Set it to
#                       the empty string to keep the image's user.
#   NUTRI_MANAGE_DIR    directory holding manage.py (local/container modes)
#   NUTRI_SKIP_MIGRATE  set to 1 to skip the `migrate` local mode runs first
#                       (compose/container runs migrate through entrypoint.sh)
#
# Fixtures hold names of children and password hashes. Output files are made
# 0600 and ./data is gitignored; keep it that way.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
TAG="[nutri-data]"

die() { echo "$TAG error: $*" >&2; exit 1; }
log() { echo "$TAG $*" >&2; }
usage() { sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "${BASH_SOURCE[0]}"; }

in_container() { [ -f /.dockerenv ] || [ -f /run/.containerenv ]; }

# ---- global options ---------------------------------------------------------
MODE="${NUTRI_MODE:-auto}"
DATA_DIR="${NUTRI_DATA_DIR:-}"
while (($#)); do
  case "$1" in
    --mode)     [ $# -ge 2 ] || die "--mode needs a value"; MODE="$2"; shift 2 ;;
    --data-dir) [ $# -ge 2 ] || die "--data-dir needs a value"; DATA_DIR="$2"; shift 2 ;;
    -h|--help)  usage; exit 0 ;;
    --)         shift; break ;;
    -*)         die "unknown option '$1' before the command (see --help)" ;;
    *)          break ;;
  esac
done
[ $# -ge 1 ] || { usage >&2; exit 2; }
COMMAND="$1"; shift

# ---- mode and paths ---------------------------------------------------------
COMPOSE_FILE="${NUTRI_COMPOSE_FILE:-$REPO_ROOT/docker-compose.yaml}"
SERVICE="${NUTRI_SERVICE:-web}"

compose_usable() {
  command -v docker >/dev/null 2>&1 \
    && docker compose version >/dev/null 2>&1 \
    && [ -f "$COMPOSE_FILE" ] \
    && docker info >/dev/null 2>&1
}

if [ "$MODE" = auto ]; then
  if in_container; then MODE=container
  elif compose_usable; then MODE=compose
  else MODE=local
  fi
fi
case "$MODE" in
  local|compose|container) ;;
  *) die "unknown mode '$MODE' (local, compose, container or auto)" ;;
esac

if [ -z "$DATA_DIR" ]; then
  if [ "$MODE" = container ]; then DATA_DIR=/data; else DATA_DIR="$REPO_ROOT/data"; fi
fi

MANAGE_DIR=""
if [ "$MODE" != compose ]; then
  for candidate in "${NUTRI_MANAGE_DIR:-}" "$REPO_ROOT/nutriapp" /app "$PWD"; do
    if [ -n "$candidate" ] && [ -f "$candidate/manage.py" ]; then MANAGE_DIR="$candidate"; break; fi
  done
  [ -n "$MANAGE_DIR" ] || die "manage.py not found; set NUTRI_MANAGE_DIR"
fi

if [ "$MODE" = local ] && [ -z "${VIRTUAL_ENV:-}" ]; then
  # Not `source activate`: its VIRTUAL_ENV path is baked in at creation time
  # and goes stale when the checkout is moved.
  for venv in "$REPO_ROOT/.venv" "$MANAGE_DIR/.venv"; do
    if [ -x "$venv/bin/python" ]; then
      export VIRTUAL_ENV="$venv" PATH="$venv/bin:$PATH"
      break
    fi
  done
fi

if [ "$MODE" = compose ]; then
  compose_usable || die "compose mode needs a running docker daemon and $COMPOSE_FILE"
  [ -f "$REPO_ROOT/.env" ] || die "$REPO_ROOT/.env is missing; docker-compose.yaml requires it (see .env.example)"
fi

# ---- running manage.py ------------------------------------------------------
# Bind mounts for compose runs. Files outside the container are staged here so
# the caller always passes paths from their own machine.
MOUNTS=()
STAGE_N=0
STAGED=""

# stage_input HOST_FILE -> STAGED = the path manage.py must be given
stage_input() {
  local host="$1" dir base
  [ -f "$host" ] || die "file not found: $host"
  dir="$(cd "$(dirname "$host")" && pwd -P)"
  base="$(basename "$host")"
  if [ "$MODE" = compose ]; then
    STAGE_N=$((STAGE_N + 1))
    MOUNTS+=(-v "$dir/$base:/input/$STAGE_N/$base:ro")
    STAGED="/input/$STAGE_N/$base"
  else
    STAGED="$dir/$base"
  fi
}

# stage_output HOST_FILE -> STAGED = the path manage.py must write to
stage_output() {
  local host="$1" dir base
  dir="$(dirname "$host")"
  (umask 077; mkdir -p "$dir")
  dir="$(cd "$dir" && pwd -P)"
  base="$(basename "$host")"
  if [ "$MODE" = compose ]; then
    MOUNTS+=(-v "$dir:/output")
    STAGED="/output/$base"
  else
    STAGED="$dir/$base"
  fi
}

run_manage() {
  if [ "$MODE" = compose ]; then
    local opts=(--rm -T -e SKIP_COLLECTSTATIC=1)
    local run_user
    if [ "${NUTRI_RUN_USER+set}" = set ]; then run_user="$NUTRI_RUN_USER"; else run_user="$(id -u):$(id -g)"; fi
    if [ -n "$run_user" ]; then
      # An arbitrary uid has no home directory; give it somewhere writable.
      opts+=(-u "$run_user" -e HOME=/tmp -e MPLCONFIGDIR=/tmp/matplotlib)
    fi
    docker compose --project-directory "$REPO_ROOT" -f "$COMPOSE_FILE" run \
      "${opts[@]}" ${MOUNTS[@]+"${MOUNTS[@]}"} "$SERVICE" python manage.py "$@"
  else
    (cd "$MANAGE_DIR" && python manage.py "$@")
  fi
}

# compose and container runs apply migrations in entrypoint.sh; a bare local
# checkout may be on a fresh SQLite file with no tables.
ensure_schema() {
  # Migrations are not committed; without them `migrate` only warns that the
  # models have unmigrated changes and creates no anthrocalc tables.
  local migrations_dir="$MANAGE_DIR/anthrocalc/migrations"
  [ "$MODE" != compose ] || migrations_dir="$REPO_ROOT/nutriapp/anthrocalc/migrations"
  compgen -G "$migrations_dir/0*.py" >/dev/null \
    || die "no migrations in $migrations_dir. Generate them first: python manage.py makemigrations (server: ansible-playbook server_deploy.yml --tags django_setup)"

  if [ "$MODE" = local ] && [ "${NUTRI_SKIP_MIGRATE:-0}" != 1 ]; then
    log "applying migrations (NUTRI_SKIP_MIGRATE=1 to skip)"
    run_manage migrate --noinput >&2
  fi
}

need_value() { [ "$2" -ge 2 ] || die "$1 needs a value"; }

# ---- commands ---------------------------------------------------------------
cmd_load_xlsx() {
  local file="" profile="" sheet="" batch="" flags=()
  while (($#)); do
    case "$1" in
      --file)      need_value "$1" $#; file="$2"; shift 2 ;;
      --profile)   need_value "$1" $#; profile="$2"; shift 2 ;;
      --sheet)     need_value "$1" $#; sheet="$2"; shift 2 ;;
      --batch-id)  need_value "$1" $#; batch="$2"; shift 2 ;;
      --dry-run|--quiet-warnings) flags+=("$1"); shift ;;
      -h|--help)   usage; exit 0 ;;
      -*)          die "load-xlsx: unknown option '$1'" ;;
      *)           [ -z "$file" ] || die "load-xlsx: more than one file given"; file="$1"; shift ;;
    esac
  done
  [ -n "$file" ] || die "load-xlsx: no workbook given"

  stage_input "$file"
  local args=(load_xlsx_patients --file "$STAGED")
  if [ -n "$profile" ]; then
    # A built-in profile is a name; a custom one is a JSON file to ship along.
    if [ -f "$profile" ]; then stage_input "$profile"; profile="$STAGED"; fi
    args+=(--profile "$profile")
  fi
  [ -z "$sheet" ] || args+=(--sheet "$sheet")
  [ -z "$batch" ] || args+=(--batch-id "$batch")
  args+=(${flags[@]+"${flags[@]}"})

  ensure_schema
  run_manage "${args[@]}"
}

cmd_export_fixtures() {
  local output="" models="anthrocalc auth.user" indent=2
  while (($#)); do
    case "$1" in
      --output) need_value "$1" $#; output="$2"; shift 2 ;;
      --models) need_value "$1" $#; models="$2"; shift 2 ;;
      --indent) need_value "$1" $#; indent="$2"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) die "export-fixtures: unexpected argument '$1'" ;;
    esac
  done
  [ -n "$output" ] || output="$DATA_DIR/fixtures/nutriapp_$(date -u +%Y%m%dT%H%M%SZ).json"
  [[ "$indent" =~ ^[0-9]+$ ]] || die "export-fixtures: --indent must be a number"

  stage_output "$output"
  local runtime_path="$STAGED" model_list
  read -r -a model_list <<<"$models"

  ensure_schema
  # --natural-foreign: permissions and content types are referenced by name,
  # not by primary keys that differ between databases.
  run_manage dumpdata "${model_list[@]}" --natural-foreign --indent "$indent" \
    --output "$runtime_path" >&2

  local host_file
  host_file="$(cd "$(dirname "$output")" && pwd -P)/$(basename "$output")"
  [ -s "$host_file" ] || die "export-fixtures: $host_file was not written"
  chmod 600 "$host_file"
  log "wrote $host_file ($(wc -c <"$host_file") bytes)"
  echo "$host_file"
}

cmd_import_fixtures() {
  local file="" force=0
  while (($#)); do
    case "$1" in
      --force) force=1; shift ;;
      -h|--help) usage; exit 0 ;;
      -*) die "import-fixtures: unknown option '$1'" ;;
      *) [ -z "$file" ] || die "import-fixtures: more than one file given"; file="$1"; shift ;;
    esac
  done
  [ -n "$file" ] || die "import-fixtures: no fixture file given"

  stage_input "$file"
  local runtime_path="$STAGED"

  ensure_schema
  if [ "$force" != 1 ]; then
    # Exit 3 = data present; any other failure is a real error.
    local rc=0
    run_manage shell -c \
      'import sys; from anthrocalc.models import Patient, Visit; sys.exit(3 if Patient.objects.exists() or Visit.objects.exists() else 0)' \
      >/dev/null || rc=$?
    case "$rc" in
      0) ;;
      3) die "import-fixtures: the database already has patients or visits; loading would overwrite rows that share a primary key. Pass --force to load anyway." ;;
      *) die "import-fixtures: could not inspect the database (exit $rc)" ;;
    esac
  fi
  run_manage loaddata "$runtime_path"
}

# Compares the live schema with the models, table by table and column by
# column. Passed to `manage.py shell -c`, so it needs no image rebuild.
read -r -d '' SYNC_SCHEMA_PY <<'PY' || true
import sys
from django.apps import apps
from django.db import connection


def find_drift():
    missing_tables, missing_columns = [], []
    with connection.cursor() as cursor:
        tables = set(connection.introspection.table_names(cursor))
        # include_auto_created: the hidden tables behind ManyToManyFields.
        for model in apps.get_models(include_auto_created=True):
            meta = model._meta
            if meta.proxy or not meta.managed or meta.swapped:
                continue
            if meta.db_table not in tables:
                missing_tables.append(model)
                continue
            have = {c.name for c in connection.introspection.get_table_description(cursor, meta.db_table)}
            for field in meta.local_concrete_fields:
                if field.column not in have:
                    missing_columns.append((model, field))
    return missing_tables, missing_columns


def show(tables, columns):
    for m in tables:
        print(f"  missing table   {m._meta.db_table}  ({m._meta.label})")
    for m, f in columns:
        print(f"  missing column  {m._meta.db_table}.{f.column}  ({m._meta.label}.{f.name})")


tables, columns = find_drift()
if not tables and not columns:
    print("Schema matches the models: every table and column exists.")
    sys.exit(0)

print("Schema drift (models expect these, the database lacks them):")
show(tables, columns)
if not REPAIR:
    print("Re-run with --repair to add them.")
    sys.exit(4)

# Same operations a migration would run, without relying on django_migrations
# (whose history may not match the database).
if tables:
    # create_model also creates the M2M tables of the model it is given, so a
    # hidden through table is skipped when its owning model is created here.
    to_create = [
        m for m in tables
        if not (m._meta.auto_created and m._meta.auto_created in tables)
    ]
    try:
        # One editor for the batch: foreign keys between new tables are added
        # as deferred SQL once every table exists, so order does not matter.
        with connection.schema_editor() as editor:
            for m in to_create:
                editor.create_model(m)
        print("  created: " + ", ".join(m._meta.db_table for m in tables))
    except Exception as exc:
        print(f"  could not create tables: {exc}")
for m, f in columns:
    try:
        with connection.schema_editor() as editor:
            editor.add_field(m, f)
        print(f"  added column {m._meta.db_table}.{f.column}")
    except Exception as exc:
        print(f"  could not add {m._meta.db_table}.{f.column}: {exc}")

tables, columns = find_drift()
if tables or columns:
    print("Still out of sync:")
    show(tables, columns)
    sys.exit(4)
print("Schema now matches the models.")
PY

cmd_sync_schema() {
  local repair=0 makemig=1
  while (($#)); do
    case "$1" in
      --repair) repair=1; shift ;;
      --no-makemigrations) makemig=0; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die "sync-schema: unexpected argument '$1'" ;;
    esac
  done

  if [ "$makemig" = 1 ]; then
    log "makemigrations (written to the mounted migrations directory)"
    run_manage makemigrations --noinput
  fi
  log "migrate --run-syncdb"
  run_manage migrate --noinput --run-syncdb

  local py_repair=False rc=0
  [ "$repair" = 1 ] && py_repair=True
  run_manage shell -c "REPAIR = $py_repair"$'\n'"$SYNC_SCHEMA_PY" || rc=$?
  case "$rc" in
    0) ;;
    4) die "sync-schema: the database is still out of sync with the models (see above)." ;;
    *) die "sync-schema: could not inspect the database (exit $rc)" ;;
  esac
}

log "mode=$MODE"
case "$COMMAND" in
  sync-schema|sync_schema)           cmd_sync_schema "$@" ;;
  load-xlsx|load_xlsx)               cmd_load_xlsx "$@" ;;
  export-fixtures|export_fixtures)   cmd_export_fixtures "$@" ;;
  import-fixtures|import_fixtures)   cmd_import_fixtures "$@" ;;
  help)                              usage ;;
  *) die "unknown command '$COMMAND' (load-xlsx, export-fixtures, import-fixtures, sync-schema)" ;;
esac
