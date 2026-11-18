#!/usr/bin/env bash
# Roll BOTH services back to the deployments that served before this run (snapshot), then
# verify with the smoke test. The database is not rolled back: migrations are additive and
# forward-only, so the previous code keeps working on the migrated schema.
# Env: RAILWAY_TOKEN, BACKEND_PREV_ID/SHA, ADMIN_PREV_ID/SHA (empty when there was none),
#      BACKEND_URL, ADMIN_URL
set -euo pipefail
rolled=0
for svc in BACKEND ADMIN; do
  id_var="${svc}_PREV_ID"; id="${!id_var:-}"; name="$(tr '[:upper:]' '[:lower:]' <<<"$svc")"
  if [ -z "$id" ]; then echo "::warning::no previous $name deployment to roll back to"; continue; fi
  echo "rolling back $name to deployment $id"
  railway api --compact --raw-var id="$id" 'mutation($id: String!) { deploymentRollback(id: $id) }' \
    | jq -e '.data.deploymentRollback == true' >/dev/null \
    || { echo "::error::rollback of $name to $id was refused"; exit 1; }
  rolled=1
done
[ "$rolled" = 1 ] || exit 0
BACKEND_EXPECTED="${BACKEND_PREV_SHA:-any}" ADMIN_EXPECTED="${ADMIN_PREV_SHA:-any}" ALLOW_UNSTAMPED=1 \
  SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-420}" "$(dirname "$0")/smoke.sh"
