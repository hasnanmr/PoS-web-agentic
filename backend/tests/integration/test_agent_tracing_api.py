"""Langfuse traces of one agent turn, audited without a network (in-memory span exporter).

Follows the Langfuse best-practices checklist: one trace per turn in a session, a readable root
(customer message in, reply out), correct observation types (agent / generation / tool),
stable names, model and token usage on generations, an outcome score, no framework noise,
and no phone number or email in any exported attribute.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import SecretStr

from app.config import Settings
from app.core.agent import tracing
from app.main import create_app

from ..agent.fakes import ScriptedModel, call
from ..auth.keys import make_verifier
from ..evals import fixtures
from ._db import ADMIN_URL, APP_URL

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

USAGE = {"input_tokens": 1200, "output_tokens": 40, "total_tokens": 1240}


class Holder:
    model = ScriptedModel()


HOLDER = Holder()


@pytest.fixture(scope="module")
def traced() -> Iterator[dict[str, Any]]:
    exporter = InMemorySpanExporter()
    settings = SimpleNamespace(
        langfuse_configured=True,
        langfuse_public_key="pk-lf-test",
        langfuse_secret_key=SecretStr("sk-lf-test"),
        langfuse_host="http://127.0.0.1:9",
        app_env="local",
    )
    scores: list[dict[str, Any]] = []
    app = create_app(
        Settings(database_url=APP_URL, admin_app_url="https://admin.test"),
        token_verifier=make_verifier(),
        agent_model=lambda: HOLDER.model,
    )
    # After create_app: it configures tracing from its own (key-less) settings.
    assert tracing.configure(settings, span_exporter=exporter)
    from langfuse import get_client

    with (
        mock.patch.object(
            type(get_client()), "create_score", lambda _self, **kw: scores.append(kw)
        ),
        TestClient(app) as client,
    ):
        yield {
            "client": client,
            "worlds": fixtures.build(client),
            "exporter": exporter,
            "scores": scores,
        }
        fixtures.cleanup()
    tracing._ENABLED = False  # other tests run untraced


def _turn(traced: dict[str, Any], text: str, *script: AIMessage, event: str = "final") -> list[Any]:
    HOLDER.model = ScriptedModel(name="generate-reply", script=list(script))
    traced["exporter"].clear()
    world = traced["worlds"]["o"]
    res = traced["client"].post(
        f"{world.base}/agent/messages",
        headers={"X-Chat-Session": "s-" + "t" * 30},
        json={"text": text, "context": "order"},
    )
    assert res.status_code == 200 and f"event: {event}" in res.text, res.text
    tracing.flush()
    return list(traced["exporter"].get_finished_spans())


def test_one_turn_is_a_clean_masked_trace(traced) -> None:
    americano = traced["worlds"]["o"].menu["Americano"]["product_id"]
    spans = _turn(
        traced,
        "americano 1 ambil sendiri, a.n. Rina 0812-3456-7221 rina@mail.com",
        AIMessage("", tool_calls=[call("lihat_menu", {"cari": "americano"})], usage_metadata=USAGE),
        AIMessage(
            "",
            tool_calls=[
                call(
                    "usulkan_pesanan",
                    {"items": [{"product_id": americano, "jumlah": 1}], "cara_ambil": "pickup"},
                    1,
                )
            ],
            usage_metadata=USAGE,
        ),
        AIMessage("Siap kak, ini ringkasannya.", usage_metadata=USAGE),
    )
    by_name: dict[str, list[Any]] = {}
    for s in spans:
        by_name.setdefault(s.name, []).append(s)
    kind = {s.name: dict(s.attributes).get("langfuse.observation.type") for s in spans}

    # Root: the turn, customer message in, reply out, trace attributes set.
    (root,) = by_name["web-chat-reply"]
    attrs = dict(root.attributes)
    assert attrs["langfuse.observation.type"] == "span"
    assert json.loads(attrs["langfuse.observation.input"]) == [
        {"role": "user", "content": "americano 1 ambil sendiri, a.n. Rina [no HP] [email]"}
    ]
    assert json.loads(attrs["langfuse.observation.output"]) == {
        "role": "assistant",
        "content": "Siap kak, ini ringkasannya.",
    }
    assert attrs["session.id"].startswith("chat-") and len(attrs["session.id"]) == 21
    assert attrs["langfuse.trace.name"] == "web-chat-reply"
    assert list(attrs["langfuse.trace.tags"]) == ["context:order"]
    assert attrs["langfuse.environment"] == "local" and attrs["langfuse.version"]
    meta = json.loads(attrs["langfuse.observation.metadata.order_draft"])
    assert meta["total"] == 24200

    # Tree: the deep agent under the root; one generation per model call; tools as tools.
    (agent,) = by_name["deep-agent"]
    assert kind["deep-agent"] == "agent" and agent.parent.span_id == root.context.span_id
    assert len(by_name["generate-reply"]) == 3 and kind["generate-reply"] == "generation"
    assert kind["lihat_menu"] == kind["usulkan_pesanan"] == "tool"
    gen = dict(by_name["generate-reply"][0].attributes)
    assert gen["langfuse.observation.model.name"] == "scripted"
    usage = json.loads(gen["langfuse.observation.usage_details"])
    assert usage["input"] == 1200 and usage["output"] == 40

    # No middleware noise, and no personal data in any exported attribute.
    assert not [s.name for s in spans if s.name.endswith(("before_agent", "after_agent"))]
    exported = json.dumps([dict(s.attributes) for s in spans], ensure_ascii=False)
    assert "3456" not in exported and "rina@mail.com" not in exported

    # Outcome score on the trace.
    assert traced["scores"][-1] == {
        "trace_id": format(root.context.trace_id, "032x"),
        "name": "turn_outcome",
        "value": "order_draft",
        "data_type": "CATEGORICAL",
    }


def test_a_failed_turn_is_marked_and_scored(traced) -> None:
    spans = _turn(
        traced,
        "semua menu",
        *[AIMessage("", tool_calls=[call("lihat_menu", {"cari": f"x{i}"}, i)]) for i in range(6)],
        event="error",
    )
    (root,) = [s for s in spans if s.name == "web-chat-reply"]
    attrs = dict(root.attributes)
    assert attrs["langfuse.observation.level"] == "WARNING"
    assert attrs["langfuse.observation.status_message"] == "agent_limit"
    assert traced["scores"][-1]["value"] == "agent_limit"
