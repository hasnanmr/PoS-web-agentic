#!/usr/bin/env bash
# Apply every migration to an empty database, then run the schema smoke tests.
# Usage: DATABASE_URL=postgresql://postgres@localhost:5432/sme_test scripts/db-test.sh
# The database must be empty (it is not dropped or reset by this script).
set -euo pipefail
: "${DATABASE_URL:?set DATABASE_URL to an empty test database}"
root="$(cd "$(dirname "$0")/.." && pwd)"
for f in "$root"/supabase/migrations/*.sql; do
  echo "migrate: $(basename "$f")"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$f"
done
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$root/supabase/seed.sql"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f "$root/supabase/tests/schema_smoke.sql" 2>&1 \
  | sed 's/^psql:[^ ]* NOTICE:  //'
