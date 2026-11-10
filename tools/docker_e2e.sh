#!/usr/bin/env bash
# End to end with Docker Compose: PostgreSQL and the sqlshow image, a small dataset, every command, and the result files
# are checked (read-only root and no capabilities for sqlshow, no published port for the database).
# Usage: bash tools/docker_e2e.sh
set -euo pipefail

export COMPOSE_PROJECT_NAME="sqlshow-e2e-$$"
cleanup() { docker compose down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

run() { docker compose run --rm sqlshow "$@"; }
read_out() { docker compose run --rm --entrypoint cat sqlshow "$1"; }
expect() { grep -q -- "$2" <<<"$1" || { echo "expected '$2' in: $1" >&2; exit 1; }; }

docker compose build sqlshow
docker compose up -d --wait db

expect "$(run init --scale 0.02 --seed 3)" "loaded into schema 'sqlshow' (scale 0.02, seed 3)"
expect "$(run queries)" "q13"
expect "$(run run --repeat 1 --only q01,q07)" "q07"
expect "$(run bench --repeat 1 --only e01,e07)" "e07"
expect "$(run evaluate --repeat 1 --out /out)" "written: /out/report.json"

json="$(read_out /out/report.json)"
expect "$json" '"id": "q13"'
expect "$json" '"id": "e10"'
expect "$json" '"scale": 0.02'
md="$(read_out /out/evaluation.md)"
expect "$md" "# Evaluation"
expect "$md" "PostgreSQL 18"

run render /out/report.json -o /out/again.md >/dev/null
[ "$(read_out /out/again.md)" = "$md" ] || { echo "the report rebuilt from the JSON is not identical" >&2; exit 1; }

# a wrong password is a clean error with exit code 2, not a traceback
set +e
docker compose run --rm -e SQLSHOW_DSN="postgresql://sqlshow:wrong@db:5432/sqlshow" sqlshow run >/dev/null 2>/tmp/e2e-err
code=$?
set -e
[ "$code" = 2 ] && grep -q "cannot connect" /tmp/e2e-err || { echo "expected exit 2 and 'cannot connect'" >&2; exit 1; }

echo "docker end-to-end: OK"
