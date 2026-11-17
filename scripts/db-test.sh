#!/usr/bin/env bash
# Apply every migration to an empty database, then run the SQL test suites.
# Usage: DATABASE_URL=postgresql://postgres@localhost:5432/sme_test scripts/db-test.sh
# Run as a superuser on an EMPTY database (it is not dropped or reset by this script).
# On plain PostgreSQL the Supabase shim (roles anon/authenticated/supabase_auth_admin
# and auth.users) is created first; on a Supabase database it is skipped.
set -euo pipefail
: "${DATABASE_URL:?set DATABASE_URL to an empty test database}"
root="$(cd "$(dirname "$0")/.." && pwd)"
run() { psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q "$@"; }
notices() { sed 's/^psql:[^ ]* NOTICE:  //'; }

if [ "$(run -tAc "select to_regclass('auth.users') is null")" = "t" ]; then
  echo "shim: supabase_shim.sql (plain PostgreSQL)"
  run -f "$root/supabase/tests/supabase_shim.sql"
fi
for f in "$root"/supabase/migrations/*.sql; do
  echo "migrate: $(basename "$f")"
  run -f "$f"
done
run -f "$root/supabase/seed.sql"
echo "--- schema_smoke.sql"
run -f "$root/supabase/tests/schema_smoke.sql" 2>&1 | notices
echo "--- rls.sql"
run -f "$root/supabase/tests/rls.sql" 2>&1 | notices
