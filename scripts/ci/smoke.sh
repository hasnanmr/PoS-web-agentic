#!/usr/bin/env bash
# Post-deploy smoke test: both services are up AND serve the expected commit.
#   backend  GET /readyz        -> 200, status "ok" (database reachable), version == expected
#            GET /api/v1/me     -> 401 without a token (API routes mounted, auth enforced)
#   admin    GET /version.txt   -> the expected commit (written by CI into the build)
#            GET /              -> 200 with the SPA root element
# Retries until SMOKE_TIMEOUT seconds (default 300): Railway switches traffic once the new
# deployment is healthy, so the old version can answer for a short while.
# Env: BACKEND_URL, ADMIN_URL, BACKEND_EXPECTED, ADMIN_EXPECTED (commit SHAs; "any" skips the
#      version check), ALLOW_UNSTAMPED=1 also accepts images built before version stamps
#      (backend "unknown", admin without version.txt), used when verifying a rollback.
set -uo pipefail
: "${BACKEND_URL:?}" "${ADMIN_URL:?}" "${BACKEND_EXPECTED:?}" "${ADMIN_EXPECTED:?}"
timeout="${SMOKE_TIMEOUT:-300}"
allow_unstamped="${ALLOW_UNSTAMPED:-0}"
deadline=$(( $(date +%s) + timeout ))

version_ok() { # actual expected
  [ "$2" = "any" ] || [ "$1" = "$2" ] || { [ "$allow_unstamped" = 1 ] && [ "$1" = "unknown" ]; }
}

check() {
  local body code version
  body="$(curl -fsS --max-time 10 "$BACKEND_URL/readyz?ts=$(date +%s)")" || { echo "backend /readyz not healthy"; return 1; }
  [ "$(jq -r .status <<<"$body")" = "ok" ] || { echo "backend /readyz: $body"; return 1; }
  version="$(jq -r '.version // "unknown"' <<<"$body")"
  version_ok "$version" "$BACKEND_EXPECTED" || { echo "backend serves $version, expected $BACKEND_EXPECTED"; return 1; }
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$BACKEND_URL/api/v1/me")"
  [ "$code" = "401" ] || { echo "backend /api/v1/me without token returned $code, expected 401"; return 1; }

  curl -fsS --max-time 10 "$ADMIN_URL/?ts=$(date +%s)" | grep -q 'id="root"' || { echo "admin / has no SPA root"; return 1; }
  version="$(curl -fsS --max-time 10 "$ADMIN_URL/version.txt?ts=$(date +%s)" | head -c 100 | tr -d '[:space:]')"
  # A missing file falls back to index.html (SPA), so compare the content, not the status.
  case "$version" in *"<"*|"") version="unknown" ;; esac
  version_ok "$version" "$ADMIN_EXPECTED" || { echo "admin serves $version, expected $ADMIN_EXPECTED"; return 1; }
  echo "backend $BACKEND_URL and admin $ADMIN_URL healthy"
  return 0
}

attempt=1
while true; do
  if check; then exit 0; fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "::error::smoke test failed after ${timeout}s"; exit 1
  fi
  echo "attempt $attempt failed; retrying in 10s"; attempt=$((attempt + 1)); sleep 10
done
