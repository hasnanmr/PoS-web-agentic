"""The evaluation harness checks themselves (runs in every CI run, no real model).

A scripted model plays a good and a bad agent through the real endpoint, so a check that
passes everything (or fails everything) is caught here, not in a paid eval run.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.config import Settings
from app.main import create_app
from tests.agent.fakes import ScriptedModel, call
from tests.auth.keys import make_verifier
from tests.evals import fixtures
from tests.evals.cases import CASES
from tests.evals.harness import World, run_case
from tests.integration._db import ADMIN_URL, APP_URL

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)


class Holder:
    model = ScriptedModel()


HOLDER = Holder()
BY_ID = {c.id: c for c in CASES}


@pytest.fixture(scope="module")
def worlds() -> Iterator[dict[str, World]]:
    settings = Settings(database_url=APP_URL, admin_app_url="https://admin.test")
    app = create_app(settings, token_verifier=make_verifier(), agent_model=lambda: HOLDER.model)
    with TestClient(app) as client:
        yield fixtures.build(client)
    fixtures.cleanup()


def _tools(*calls: dict[str, Any]) -> AIMessage:
    return AIMessage("", tool_calls=list(calls))


def _run(case_id: str, worlds: dict[str, World], *script: AIMessage) -> list[str]:
    HOLDER.model = ScriptedModel(script=list(script))
    case = BY_ID[case_id]
    return run_case(case, worlds[case.scope], "eval-" + uuid4().hex).failures


def test_good_agent_passes_and_bad_agent_fails_the_order_checks(worlds) -> None:
    w = worlds["o"]
    americano = w.menu["Americano"]["product_id"]
    line = {"product_id": americano, "jumlah": 3}
    good = _run(
        "order-slang-quantity",
        worlds,
        _tools(call("usulkan_pesanan", {"items": [line], "cara_ambil": "pickup"})),
        AIMessage("Siap, ini ringkasannya. Total Rp 72.600 ya."),
    )
    assert good == []
    # Wrong quantity, a made-up price, and a claim that the order exists: all caught.
    bad = _run(
        "order-slang-quantity",
        worlds,
        _tools(call("usulkan_pesanan", {"items": [{**line, "jumlah": 2}], "cara_ambil": "pickup"})),
        AIMessage("Pesanan kamu sudah dibuat! Totalnya Rp 10.000."),
    )
    assert any("draft lines" in f for f in bad)
    assert any("invents amounts" in f for f in bad)
    assert any("claims something was created" in f for f in bad)


def test_required_addon_case_checks_both_turns(worlds) -> None:
    w = worlds["o"]
    kopi = w.menu["Es Kopi Susu Senja"]
    regular = w.option_id("Es Kopi Susu Senja", "Regular")
    line = {"product_id": kopi["product_id"], "jumlah": 2, "addon_option_ids": [regular]}
    good = _run(
        "order-missing-required",
        worlds,
        AIMessage("Ukurannya mau Regular atau Large?"),
        _tools(call("usulkan_pesanan", {"items": [line], "cara_ambil": "pickup"})),
        AIMessage("Ini ringkasannya."),
    )
    assert good == []
    # Drafting at once (no question) fails turn 1.
    bad = _run(
        "order-missing-required",
        worlds,
        _tools(call("usulkan_pesanan", {"items": [line], "cara_ambil": "pickup"})),
        AIMessage("Ini ringkasannya."),
        AIMessage("Oke."),
    )
    assert any(f.startswith("turn 1:") for f in bad)


def test_scope_and_booking_checks(worlds) -> None:
    assert (
        _run("scope-off-topic", worlds, _tools(call("di_luar_lingkup")), AIMessage("Maaf.")) == []
    )
    assert _run("scope-off-topic", worlds, AIMessage("Presidennya adalah …")) == [
        "not flagged out of scope"
    ]

    w = worlds["o_wita"]
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    day = (datetime.now(ZoneInfo(w.timezone)) + timedelta(days=1)).date().isoformat()
    times = w.client.get(f"{w.base}/availability", params={"party_size": 2, "date": day}).json()[
        "times"
    ]
    seven = next(t["start_at"] for t in times if t["label"] == "19:00")
    ten = next(t["start_at"] for t in times if t["label"] == "10:00")
    assert (
        _run(
            "book-wita",
            worlds,
            _tools(call("usulkan_booking", {"jumlah_orang": 2, "start_at": seven})),
            AIMessage("Masih ada, lanjut isi nama ya."),
        )
        == []
    )
    wrong = _run(
        "book-wita",
        worlds,
        _tools(call("usulkan_booking", {"jumlah_orang": 2, "start_at": ten})),
        AIMessage("Ok."),
    )
    assert any("wanted +1d 19:00" in f for f in wrong)


def test_every_case_has_checks_and_a_known_scope() -> None:
    assert len(CASES) >= 15 and len({c.id for c in CASES}) == len(CASES)
    for case in CASES:
        assert case.checks and case.messages and case.scope in {"o", "o_wita", "t"}
