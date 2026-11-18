#!/usr/bin/env bash
# Migration hygiene (T-009), Alembic layout (backend/migrations):
#  1. SQL files are named <14-digit timestamp>_<snake_name>.sql with unique timestamps, and
#     each has exactly one revision file of the same name (and vice versa).
#  2. One migration head (no branches).
#  3. Migrations already on the base branch are never edited or deleted (add a new one).
#     Base branch defaults to origin/main.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
base="${MIGRATION_BASE_REF:-origin/main}"
sql_dir=backend/migrations/sql
ver_dir=backend/migrations/versions
status=0

for f in "$sql_dir"/*.sql; do
  name="$(basename "$f" .sql)"
  if ! [[ "$name" =~ ^[0-9]{14}_[a-z0-9_]+$ ]]; then
    echo "bad migration name: $name.sql (expected YYYYMMDDHHMMSS_snake_case.sql)"; status=1
  fi
  [ -f "$ver_dir/$name.py" ] || { echo "missing revision file: $ver_dir/$name.py"; status=1; }
done
for f in "$ver_dir"/*.py; do
  name="$(basename "$f" .py)"
  [ -f "$sql_dir/$name.sql" ] || { echo "revision without SQL file: $sql_dir/$name.sql"; status=1; }
done
dupes="$(ls "$sql_dir"/*.sql | xargs -n1 basename | cut -c1-14 | sort | uniq -d)"
if [ -n "$dupes" ]; then echo "duplicate migration timestamps: $dupes"; status=1; fi

heads="$(cd backend && uv run --quiet alembic heads | wc -l | tr -d ' ')"
if [ "$heads" != "1" ]; then echo "expected one migration head, found $heads"; status=1; fi

if git rev-parse --verify --quiet "$base" >/dev/null; then
  # --no-renames: files moved here from supabase/migrations count as added, not edited.
  changed="$(git diff --no-renames --name-status "$base"...HEAD -- "$sql_dir" "$ver_dir" \
    | awk '$1 ~ /^(M|D)/ {print $0}')"
  if [ -n "$changed" ]; then
    echo "migrations already on $base were modified or removed (add a new migration instead):"
    echo "$changed"; status=1
  fi
  # SQL that was on the base branch under supabase/migrations must move unchanged.
  for old in $(git ls-tree --name-only "$base" supabase/migrations/ 2>/dev/null | grep '\.sql$' || true); do
    new="$sql_dir/$(basename "$old")"
    if ! cmp -s <(git show "$base:$old") "$new"; then
      echo "migration changed while moving: $old -> $new"; status=1
    fi
  done
else
  echo "note: $base not found; skipping the 'no edits to merged migrations' check"
fi

[ "$status" = 0 ] && echo "migrations ok"
exit "$status"
