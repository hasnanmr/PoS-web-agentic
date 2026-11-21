#!/usr/bin/env bash
# Run the web chat agent evaluation set (T-092) against a real model. Costs model tokens:
# roughly 18 cases x 1-3 model calls each.
#
# Needs:
#   OPENAI_BASE_URL, MODEL_NAME (+ OPENAI_API_KEY)   the model to evaluate (same names as the API)
#   TEST_DATABASE_URL, TEST_APP_DATABASE_URL          a migrated test database (scripts/db-test.sh)
# Optional:
#   LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST   trace every case and score it
#
# Usage:
#   OPENAI_BASE_URL=https://api.anthropic.com/v1/ OPENAI_API_KEY=… MODEL_NAME=claude-opus-5-5 \
#   TEST_DATABASE_URL=postgresql://postgres@localhost:5432/sme_test \
#   TEST_APP_DATABASE_URL=postgresql://app_backend@localhost:5432/sme_test \
#   scripts/agent-eval.sh
#
# Writes backend/eval-reports/agent-eval-<time>.json. Exit code 1 when a critical case fails or
# fewer than 90 % of the other cases pass.
set -euo pipefail
: "${OPENAI_BASE_URL:?set OPENAI_BASE_URL (the model to evaluate)}"
: "${MODEL_NAME:?set MODEL_NAME}"
: "${TEST_DATABASE_URL:?set TEST_DATABASE_URL (migrated test database)}"
: "${TEST_APP_DATABASE_URL:?set TEST_APP_DATABASE_URL (role app_backend)}"
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root/backend"
AGENT_EVAL=1 uv run pytest tests/evals/test_agent_eval.py -q -s -p no:cacheprovider "$@"
