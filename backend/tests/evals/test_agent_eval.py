"""Agent evaluation set (T-092) against the real model — run before each prompt or model change.

    AGENT_EVAL=1 OPENAI_BASE_URL=… OPENAI_API_KEY=… MODEL_NAME=… scripts/agent-eval.sh

Skipped unless AGENT_EVAL=1, a model is configured, and the test database is set. Every case
goes through the real endpoint, gateway, tools, and guard; only the model is external. The
run writes `backend/eval-reports/agent-eval-<time>.json` and fails when a critical case fails
or fewer than 90 % of the other cases pass. With LANGFUSE_* set, each case is also scored in
Langfuse (score `agent_eval` on the case's chat session).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core import web_chat
from app.core.agent import tracing
from app.core.agent.prompt import PROMPT_VERSION
from app.main import create_app
from tests.auth.keys import make_verifier
from tests.evals import fixtures
from tests.evals.cases import CASES
from tests.evals.harness import Result, run_case
from tests.integration._db import ADMIN_URL, APP_URL

# Read at import: the autouse `clean_env` fixture removes these from the environment per test.
EVAL_ENV = {
    k: os.environ.get(k)
    for k in (
        "AGENT_EVAL",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "MODEL_NAME",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "LANGFUSE_HOST",
    )
}
NON_CRITICAL_PASS_RATE = 0.9
REPORTS = Path(__file__).resolve().parents[2] / "eval-reports"

pytestmark = pytest.mark.skipif(
    not (
        EVAL_ENV["AGENT_EVAL"] == "1"
        and EVAL_ENV["OPENAI_BASE_URL"]
        and EVAL_ENV["MODEL_NAME"]
        and ADMIN_URL
        and APP_URL
    ),
    reason="agent eval: set AGENT_EVAL=1, OPENAI_BASE_URL, MODEL_NAME, and the test database",
)


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    settings = Settings(
        database_url=APP_URL,
        admin_app_url="https://admin.test",
        openai_base_url=EVAL_ENV["OPENAI_BASE_URL"],
        openai_api_key=EVAL_ENV["OPENAI_API_KEY"],
        model_name=EVAL_ENV["MODEL_NAME"],
        langfuse_public_key=EVAL_ENV["LANGFUSE_PUBLIC_KEY"],
        langfuse_secret_key=EVAL_ENV["LANGFUSE_SECRET_KEY"],
        **({"langfuse_host": EVAL_ENV["LANGFUSE_HOST"]} if EVAL_ENV["LANGFUSE_HOST"] else {}),
    )
    with TestClient(create_app(settings, token_verifier=make_verifier())) as c:
        yield c
    fixtures.cleanup()


def test_agent_eval(client: TestClient) -> None:
    from app.api.v1 import public_chat

    worlds = fixtures.build(client)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    results: list[Result] = []
    for case in CASES:
        public_chat._hits.clear()  # the per-session agent limit is for customers, not the eval
        session = "eval-" + uuid4().hex
        result = run_case(case, worlds[case.scope], session)
        results.append(result)
        tracing.score_session(
            f"chat-{web_chat.hash_key(session)[:16]}",
            "agent_eval",
            1.0 if result.passed else 0.0,
            comment=f"{run_id} {case.id}: " + ("; ".join(result.failures) or "ok"),
        )
    tracing.flush()

    critical_failed = [r for r in results if r.case.critical and not r.passed]
    others = [r for r in results if not r.case.critical]
    rate = sum(r.passed for r in others) / len(others) if others else 1.0
    report = {
        "run": run_id,
        "model": EVAL_ENV["MODEL_NAME"],
        "prompt_version": PROMPT_VERSION,
        "passed": sum(r.passed for r in results),
        "total": len(results),
        "non_critical_pass_rate": round(rate, 3),
        "cases": [
            {
                "id": r.case.id,
                "title": r.case.title,
                "critical": r.case.critical,
                "passed": r.passed,
                "failures": r.failures,
                "conversation": [
                    {
                        "customer": t.text,
                        "agent": (t.final or {}).get("reply_text"),
                        "draft": (t.final or {}).get("order_draft")
                        or (t.final or {}).get("booking_draft"),
                        "out_of_scope": (t.final or {}).get("out_of_scope"),
                        "error": t.error,
                    }
                    for t in r.turns
                ],
            }
            for r in results
        ],
    }
    REPORTS.mkdir(exist_ok=True)
    path = REPORTS / f"agent-eval-{run_id}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(f"\nAgent eval {run_id} · {EVAL_ENV['MODEL_NAME']} · prompt {PROMPT_VERSION} → {path}")
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(
            f"  {mark} {'[critical] ' if r.case.critical else ''}{r.case.id}"
            + ("" if r.passed else f" — {'; '.join(r.failures)}")
        )
    print(f"  {report['passed']}/{report['total']} passed · non-critical {rate:.0%}")

    assert not critical_failed, f"critical cases failed: {[r.case.id for r in critical_failed]}"
    assert rate >= NON_CRITICAL_PASS_RATE, f"non-critical pass rate {rate:.0%} < 90%"
