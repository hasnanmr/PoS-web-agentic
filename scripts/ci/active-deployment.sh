#!/usr/bin/env bash
# Print "<deployment id> <commit sha>" of the deployment that is serving now (latest SUCCESS)
# for a Railway service, or nothing if there is none. Used to snapshot what to roll back to.
# Usage: scripts/ci/active-deployment.sh <service id>
# Env: RAILWAY_TOKEN, RAILWAY_PROJECT_ID, RAILWAY_ENVIRONMENT_ID
set -euo pipefail
service="${1:?usage: active-deployment.sh <service id>}"
: "${RAILWAY_PROJECT_ID:?}" "${RAILWAY_ENVIRONMENT_ID:?}"
railway api --compact \
  --raw-var project="$RAILWAY_PROJECT_ID" --raw-var env="$RAILWAY_ENVIRONMENT_ID" --raw-var service="$service" \
  'query($project: String!, $env: String!, $service: String!) {
     deployments(first: 20, input: {projectId: $project, environmentId: $env, serviceId: $service}) {
       edges { node { id status meta } } } }' \
  | jq -r '[.data.deployments.edges[].node | select(.status == "SUCCESS")][0]
           | select(. != null) | "\(.id) \(.meta.cliMessage // "unknown")"'
