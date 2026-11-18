#!/usr/bin/env bash
# Migration hygiene (T-009):
#  1. File names follow <14-digit timestamp>_<snake_name>.sql and timestamps are unique.
#  2. Migrations that already exist on the base branch are never edited or deleted
#     (add a new migration instead). Base branch defaults to origin/main.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
base="${MIGRATION_BASE_REF:-origin/main}"
status=0

for f in supabase/migrations/*.sql; do
  name="$(basename "$f")"
  if ! [[ "$name" =~ ^[0-9]{14}_[a-z0-9_]+\.sql$ ]]; then
    echo "bad migration name: $name (expected YYYYMMDDHHMMSS_snake_case.sql)"; status=1
  fi
done
dupes="$(ls supabase/migrations/*.sql | xargs -n1 basename | cut -c1-14 | sort | uniq -d)"
if [ -n "$dupes" ]; then echo "duplicate migration timestamps: $dupes"; status=1; fi

if git rev-parse --verify --quiet "$base" >/dev/null; then
  changed="$(git diff --name-status "$base"...HEAD -- supabase/migrations | awk '$1 ~ /^(M|D|R)/ {print $0}')"
  if [ -n "$changed" ]; then
    echo "migrations already on $base were modified or removed (add a new migration instead):"
    echo "$changed"; status=1
  fi
else
  echo "note: $base not found; skipping the 'no edits to merged migrations' check"
fi

[ "$status" -eq 0 ] && echo "migrations ok"
exit "$status"
