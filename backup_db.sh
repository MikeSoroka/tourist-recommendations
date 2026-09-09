#!/usr/bin/env bash
# Dump the project database. Reads credentials from .env / the environment so
# no password is stored in this file (the old backup_db.bat hardcoded one).
set -euo pipefail

[ -f .env ] && set -a && . ./.env && set +a

: "${DB_PASSWORD:?DB_PASSWORD is not set; copy .env.example to .env}"
export PGPASSWORD="$DB_PASSWORD"

OUT="${1:-tourist_recommendations_backup_$(date +%Y%m%d_%H%M%S).dump}"

pg_dump -U "${DB_USER:-postgres}" -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" \
        -F c -b -v -f "$OUT" "${DB_NAME:-tourist_recommendations}"

echo "Backup written to $OUT"
