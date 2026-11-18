#!/usr/bin/env bash
# Create a migration: backend/migrations/sql/<timestamp>_<name>.sql (write the SQL here) and
# the Alembic revision backend/migrations/versions/<timestamp>_<name>.py that runs it.
set -euo pipefail
name="${1:?usage: scripts/new-migration.sh snake_case_name}"
[[ "$name" =~ ^[a-z0-9_]+$ ]] || { echo "name must be snake_case"; exit 1; }
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/backend"
rev="$(date -u +%Y%m%d%H%M%S)"
head="$(uv run --quiet alembic heads | awk '{print $1}')"
printf -- '-- %s\n' "$name" > "migrations/sql/${rev}_${name}.sql"
uv run --quiet alembic revision --rev-id "$rev" -m "$name" --head "$head" >/dev/null
echo "created migrations/sql/${rev}_${name}.sql and migrations/versions/${rev}_${name}.py (revises ${head})"
