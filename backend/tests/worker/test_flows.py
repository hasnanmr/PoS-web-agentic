"""W1 main menu and conversation state rules (T-049, T-050; FR2.0, AC2.1, AC2.14)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.core.conversations import OutletProfile
from app.whatsapp.incoming import Incoming
from app.worker import flows
from app.worker.flows import FlowResult, main_menu


def profile(reservations: bool) -> OutletProfile:
    return OutletProfile(uuid4(), "Kopi Senja", "Dago", "111", reservations)


def rows(result: FlowResult) -> list[tuple[str, str, str | None]]:
    (msg,) = result.replies
    (section,) = msg["interactive"]["action"]["sections"]
    assert section["title"] == "Pilih layanan"
    return [(r["id"], r["title"], r.get("description")) for r in section["rows"]]


def text(body: str) -> Incoming:
    return Incoming("text", text=body)


def test_greeting_shows_the_w1_list_with_reservations() -> None:
    result = flows.handle(None, {}, text("Halo"), profile(reservations=True))
    (msg,) = result.replies
    assert msg["interactive"]["body"]["text"] == (
        "Selamat datang di Kopi Senja \N{EN DASH} Dago ☕\nMau ngapain hari ini?"
    )
    assert msg["interactive"]["action"]["button"] == "Lihat pilihan"
    assert rows(result) == [
        ("menu:pesan", "Pesan", "Lihat katalog & pesan"),
        ("menu:rekomendasi", "Rekomendasi", "Owner's picks & best seller"),
        ("menu:reservasi", "Reservasi", "Booking meja"),
        ("menu:reservasi_saya", "Reservasi Saya", "Lihat, batal, reschedule"),
        ("menu:data_saya", "Data Saya", "Membership & data pribadi"),
    ]
    assert result.flow is None and result.state == {}


def test_reservation_rows_are_hidden_when_reservations_are_off() -> None:
    result = flows.handle(None, {}, text("Halo"), profile(reservations=False))
    assert [r[1] for r in rows(result)] == ["Pesan", "Rekomendasi", "Data Saya"]


@pytest.mark.parametrize("word", ["menu", "MENU", "  Menu  "])
def test_menu_keyword_drops_the_unfinished_flow(word: str, monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def order_flow(state: dict[str, Any], incoming: Incoming, p: OutletProfile) -> FlowResult:
        nonlocal called
        called = True
        return FlowResult([], "order", state)

    monkeypatch.setitem(flows.FLOWS, "order", order_flow)
    result = flows.handle("order", {"cart": [1]}, text(word), profile(True))
    assert not called
    assert result.flow is None and result.state == {} and len(result.replies) == 1


def test_unknown_saved_flow_restarts_at_the_main_menu() -> None:
    result = flows.handle("removed_flow", {"step": 9}, text("2"), profile(True))
    assert result.flow is None and result.state == {} and rows(result)


def test_a_menu_choice_starts_its_registered_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    def order_flow(state: dict[str, Any], incoming: Incoming, p: OutletProfile) -> FlowResult:
        return FlowResult([{"type": "text", "text": {"body": "katalog"}}], "pesan", {"step": 1})

    monkeypatch.setitem(flows.FLOWS, main_menu.PESAN, order_flow)
    tap = Incoming("interactive", text="Pesan", reply_id="menu:pesan")
    result = flows.handle(None, {}, tap, profile(True))
    assert result.flow == "pesan" and result.state == {"step": 1}


def test_a_hidden_or_unbuilt_choice_shows_the_menu_again() -> None:
    hidden = Incoming("interactive", reply_id="menu:reservasi")
    result = flows.handle(None, {}, hidden, profile(reservations=False))
    assert result.flow is None and rows(result)[0][1] == "Pesan"
    unbuilt = Incoming("interactive", reply_id="menu:data_saya")
    assert flows.handle(None, {}, unbuilt, profile(True)).flow is None
