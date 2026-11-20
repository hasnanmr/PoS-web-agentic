"""Webhook signature and payload parsing, incoming messages, outgoing limits, Graph errors."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import urllib.error
from typing import Any

import pytest

from app.whatsapp import outgoing
from app.whatsapp.graph import GraphError, HttpGraphClient
from app.whatsapp.incoming import parse_message
from app.whatsapp.webhook import parse_events, valid_signature

SECRET = "app-secret"


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def meta_body(**value: Any) -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "1555", "phone_number_id": "111"},
                            **value,
                        },
                    }
                ],
            }
        ],
    }


def test_signature_must_match_the_raw_body() -> None:
    body = b'{"a": 1}'
    assert valid_signature(SECRET, body, sign(body))
    assert not valid_signature(SECRET, body + b" ", sign(body))
    assert not valid_signature(SECRET, body, sign(body, "other"))
    assert not valid_signature(SECRET, body, None)
    assert not valid_signature(SECRET, body, hashlib.sha256(body).hexdigest())


def test_messages_and_statuses_become_separate_events() -> None:
    data = meta_body(
        contacts=[{"profile": {"name": "Rina"}, "wa_id": "6281234567890"}],
        messages=[
            {
                "from": "6281234567890",
                "id": "wamid.1",
                "timestamp": "1763600000",
                "type": "text",
                "text": {"body": "Halo"},
            }
        ],
        statuses=[{"id": "wamid.out", "status": "delivered", "recipient_id": "6281234567890"}],
    )
    msg, status = parse_events(data)
    assert msg.kind == "message" and msg.idempotency_key == "wamid.1"
    assert msg.phone_number_id == "111"
    assert msg.payload["contact"] == {"wa_id": "6281234567890", "name": "Rina"}
    assert status.kind == "status" and status.idempotency_key == "wamid.out:delivered"


@pytest.mark.parametrize(
    "data",
    [
        {"object": "page", "entry": []},
        meta_body(messages=[{"type": "text"}]),  # no id or sender
        {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "x"}]}]},
        [],
        None,
    ],
)
def test_other_payloads_produce_no_events(data: Any) -> None:
    assert parse_events(data) == []


def test_incoming_text_list_reply_and_template_button() -> None:
    text = parse_message({"type": "text", "text": {"body": "  MENU \n"}})
    assert text.keyword == "menu"
    row = parse_message(
        {
            "type": "interactive",
            "interactive": {"list_reply": {"id": "menu:pesan", "title": "Pesan"}},
        }
    )
    assert row.reply_id == "menu:pesan" and row.keyword == ""
    btn = parse_message({"type": "button", "button": {"payload": "p1", "text": "Ya"}})
    assert btn.reply_id == "p1"
    assert parse_message({"type": "sticker"}).type == "sticker"


def test_outgoing_builders_enforce_meta_limits() -> None:
    msg = outgoing.list_message(
        "Body", "Lihat pilihan", [outgoing.Section("Pilih layanan", [outgoing.Row("a", "A")])]
    )
    assert msg["interactive"]["action"]["sections"][0]["rows"] == [{"id": "a", "title": "A"}]
    with pytest.raises(ValueError, match="list button"):
        outgoing.list_message("B", "x" * 21, [outgoing.Section("S", [outgoing.Row("a", "A")])])
    with pytest.raises(ValueError, match="row title"):
        outgoing.list_message("B", "b", [outgoing.Section("S", [outgoing.Row("a", "x" * 25)])])
    rows = [outgoing.Row(str(i), str(i)) for i in range(11)]
    with pytest.raises(ValueError, match="1-10 rows"):
        outgoing.list_message("B", "b", [outgoing.Section("S", rows)])
    with pytest.raises(ValueError, match="buttons"):
        outgoing.reply_buttons("B", [("1", "a"), ("2", "b"), ("3", "c"), ("4", "d")])
    assert outgoing.text("Halo")["text"]["body"] == "Halo"


class _Resp(io.BytesIO):
    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _http_error(status: int, error: dict[str, Any]) -> urllib.error.HTTPError:
    body = io.BytesIO(json.dumps({"error": error}).encode())
    return urllib.error.HTTPError("https://graph", status, "err", {}, body)  # type: ignore[arg-type]


async def test_graph_client_sends_and_returns_the_message_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, Any] = {}

    def fake_urlopen(req: Any, timeout: float) -> _Resp:
        sent.update(url=req.full_url, auth=req.headers["Authorization"], body=json.loads(req.data))
        return _Resp(b'{"messages": [{"id": "wamid.OUT"}]}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = HttpGraphClient("https://graph.facebook.com", "v23.0", "tok")
    assert await client.send_message("111", "6281", outgoing.text("Halo")) == "wamid.OUT"
    assert sent["url"] == "https://graph.facebook.com/v23.0/111/messages"
    assert sent["auth"] == "Bearer tok"
    assert sent["body"]["to"] == "6281" and sent["body"]["messaging_product"] == "whatsapp"


@pytest.mark.parametrize(
    ("status", "code", "retryable", "outside_window"),
    [
        (500, 1, True, False),
        (429, None, True, False),
        (400, 130429, True, False),  # Meta throughput limit
        (400, 131047, False, True),  # outside the 24-hour window
        (400, 100, False, False),  # invalid parameter
    ],
)
async def test_graph_errors_are_classified(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    code: int | None,
    retryable: bool,
    outside_window: bool,
) -> None:
    def fake_urlopen(req: Any, timeout: float) -> _Resp:
        raise _http_error(status, {"code": code, "message": "nope"} if code else {})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = HttpGraphClient("https://graph.facebook.com", "v23.0", "tok")
    with pytest.raises(GraphError) as info:
        await client.send_message("111", "6281", outgoing.text("Halo"))
    assert info.value.retryable is retryable
    assert info.value.outside_window is outside_window


async def test_graph_network_failure_is_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req: Any, timeout: float) -> _Resp:
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = HttpGraphClient("https://graph.facebook.com", "v23.0", "tok")
    with pytest.raises(GraphError) as info:
        await client.send_message("111", "6281", outgoing.text("Halo"))
    assert info.value.status == 0 and info.value.retryable
