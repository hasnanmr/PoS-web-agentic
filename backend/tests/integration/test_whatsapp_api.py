"""WhatsApp webhook and worker against Postgres through RLS (T-045 to T-050).

Meta → `POST /webhooks/whatsapp` → envelope on `wa.inbound` (in-memory publisher) → inbound
worker → W1 main menu reply on `wa.outbound` → outbound worker → fake Graph API. Covers the
signature check, outlet mapping by phone number id (FR2.10), duplicate messages (NFR8),
delivery statuses, the "menu" keyword (AC2.14), reservation rows (AC2.1), retries, and
dead-letter decisions.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app import cli, db
from app.config import Settings
from app.main import create_app
from app.messaging.broker import InMemoryPublisher
from app.messaging.envelope import Envelope
from app.messaging.policy import PermanentError, RetryableError
from app.whatsapp.graph import GraphError
from app.worker.inbound import InboundHandler
from app.worker.outbound import OutboundHandler

from ..auth.keys import make_token, make_verifier
from ._db import ADMIN_URL, APP_URL, admin_sql, cleanup_domain, invite_owner

pytestmark = pytest.mark.skipif(
    not (ADMIN_URL and APP_URL), reason="TEST_DATABASE_URL / TEST_APP_DATABASE_URL not set"
)

DOMAIN = "whatsapp.test"
OWNER = UUID("71000000-0000-0000-0000-0000000000a0")
SECRET = "test-app-secret"
VERIFY = "test-verify-token"
NUMBER = "990000000000501"
CUSTOMER = "6281234500501"


def _settings(**extra: Any) -> Settings:
    return Settings(
        database_url=APP_URL,
        rabbitmq_url="amqp://guest:guest@localhost:5672/",
        whatsapp_app_secret=SECRET,
        whatsapp_verify_token=VERIFY,
        **extra,
    )


@pytest.fixture(scope="module")
def inbox() -> InMemoryPublisher:
    return InMemoryPublisher()


@pytest.fixture(scope="module")
def client(inbox: InMemoryPublisher) -> Iterator[TestClient]:
    cleanup_domain(DOMAIN)
    invite_owner(OWNER, f"owner@{DOMAIN}")
    app = create_app(_settings(), token_verifier=make_verifier(), publisher=inbox)
    with TestClient(app) as c:
        yield c
    cleanup_domain(DOMAIN)


@pytest.fixture(scope="module")
def outlet(client: TestClient) -> dict[str, Any]:
    res = client.post(
        "/api/v1/owner/onboarding",
        headers={
            "Authorization": "Bearer "
            + make_token(sub=str(OWNER), tenant_id=None, app_role="owner_pending")
        },
        json={"business": {"name": "Kopi Senja", "type": "cafe"}, "outlet": {"name": "Dago"}},
    )
    assert res.status_code == 201, res.text
    tenant, outlet_id = res.json()["tenant_id"], res.json()["outlet_id"]
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", APP_URL or "")
        assert (
            cli.main(["whatsapp-connect", "--outlet", outlet_id, "--phone-number-id", NUMBER]) == 0
        )
    return {"tenant": tenant, "id": outlet_id}


def _post(client: TestClient, data: dict[str, Any], secret: str = SECRET) -> Any:
    body = json.dumps(data).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/whatsapp",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )


def _meta(number: str = NUMBER, **value: Any) -> dict[str, Any]:
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
                            "metadata": {"display_phone_number": "1555", "phone_number_id": number},
                            **value,
                        },
                    }
                ],
            }
        ],
    }


def _text(msg_id: str, body: str) -> dict[str, Any]:
    return _meta(
        contacts=[{"profile": {"name": "Rina"}, "wa_id": CUSTOMER}],
        messages=[
            {
                "from": CUSTOMER,
                "id": msg_id,
                "timestamp": "1763600000",
                "type": "text",
                "text": {"body": body},
            }
        ],
    )


def _receive(client: TestClient, inbox: InMemoryPublisher, data: dict[str, Any]) -> Envelope:
    res = _post(client, data)
    assert res.status_code == 200, res.text
    (env,) = inbox.take("wa.inbound")
    return env


class FakeGraph:
    def __init__(self, error: GraphError | None = None, prefix: str = "wamid.out") -> None:
        self.sent: list[tuple[str, str, dict[str, Any]]] = []
        self.error = error
        self.prefix = prefix

    async def send_message(self, phone_number_id: str, to: str, body: dict[str, Any]) -> str:
        if self.error is not None:
            raise self.error
        self.sent.append((phone_number_id, to, body))
        return f"{self.prefix}.{len(self.sent)}"


def _messages(outlet_id: str) -> list[tuple[Any, ...]]:
    return admin_sql(
        "select id, direction, message_type, status, meta_message_id from app.messages"
        " where outlet_id = %s order by id",
        (outlet_id,),
    )


def _row_titles(env: Envelope) -> list[str]:
    sections = env.payload["body"]["interactive"]["action"]["sections"]
    return [r["title"] for r in sections[0]["rows"]]


# Webhook ------------------------------------------------------------------------------


def test_meta_verification_handshake(client: TestClient) -> None:
    ok = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY, "hub.challenge": "1158201444"},
    )
    assert ok.status_code == 200 and ok.text == "1158201444"
    bad = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "x"},
    )
    assert bad.status_code == 403


def test_invalid_signature_is_rejected_and_nothing_is_published(
    client: TestClient, inbox: InMemoryPublisher, outlet: dict[str, Any]
) -> None:
    res = _post(client, _text("wamid.badsig", "Halo"), secret="not-the-secret")
    assert res.status_code == 401 and res.json()["error"]["code"] == "invalid_signature"
    assert inbox.take() == []


def test_unknown_number_is_acknowledged_and_dropped(
    client: TestClient, inbox: InMemoryPublisher, outlet: dict[str, Any]
) -> None:
    assert _post(client, _meta("990000000000999", messages=[])).status_code == 200
    data = _text("wamid.unknown", "Halo")
    data["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "990000000000999"
    assert _post(client, data).status_code == 200
    assert inbox.take() == []


def test_broker_outage_answers_503_so_meta_retries(
    client: TestClient, inbox: InMemoryPublisher, outlet: dict[str, Any]
) -> None:
    inbox.fail = True
    try:
        res = _post(client, _text("wamid.outage", "Halo"))
    finally:
        inbox.fail = False
    assert res.status_code == 503 and res.json()["error"]["code"] == "queue_unavailable"


def test_webhook_answers_503_when_whatsapp_is_not_configured() -> None:
    app = create_app(Settings(database_url=APP_URL), publisher=InMemoryPublisher())
    with TestClient(app) as c:
        assert c.post("/webhooks/whatsapp", content=b"{}").status_code == 503
        assert c.get("/webhooks/whatsapp").status_code == 503


def test_webhook_is_not_in_the_admin_api_contract(client: TestClient) -> None:
    assert "/webhooks/whatsapp" not in client.app.openapi()["paths"]  # type: ignore[attr-defined]


# Worker -------------------------------------------------------------------------------


async def test_first_message_gets_the_w1_main_menu_and_is_sent(
    client: TestClient, inbox: InMemoryPublisher, outlet: dict[str, Any]
) -> None:
    env = _receive(client, inbox, _text("wamid.hello", "Halo"))
    assert env.type == "wa.inbound.message" and str(env.outlet_id) == outlet["id"]
    assert str(env.tenant_id) == outlet["tenant"] and env.idempotency_key == "wamid.hello"

    pool = db.create_pool(APP_URL or "", min_size=1, max_size=2)
    await pool.open(wait=True)
    try:
        out = InMemoryPublisher()
        await InboundHandler(pool, out)(env, "corr-1")
        (reply,) = out.take("wa.outbound")
        assert reply.type == "wa.outbound.interactive"
        assert reply.payload["to"] == CUSTOMER and reply.payload["phone_number_id"] == NUMBER
        assert _row_titles(reply) == ["Pesan", "Rekomendasi", "Data Saya"]
        body = reply.payload["body"]["interactive"]["body"]["text"]
        assert body.startswith("Selamat datang di Kopi Senja \N{EN DASH} Dago")

        contact = admin_sql(
            "select phone, display_name, last_inbound_at is not null from app.whatsapp_contacts"
            " where tenant_id = %s",
            (outlet["tenant"],),
        )
        assert contact == [("+" + CUSTOMER, "Rina", True)]
        rows = _messages(outlet["id"])
        assert [(r[1], r[2], r[3]) for r in rows] == [
            ("inbound", "text", None),
            ("outbound", "interactive", "enqueued"),
        ]

        # The same message again (Meta retry or RabbitMQ redelivery): nothing new happens.
        await InboundHandler(pool, out)(env, "corr-2")
        assert out.take() == [] and len(_messages(outlet["id"])) == 2

        graph = FakeGraph()
        await OutboundHandler(pool, graph)(reply, "corr-1")
        assert graph.sent == [(NUMBER, CUSTOMER, reply.payload["body"])]
        assert _messages(outlet["id"])[-1][3:] == ("sent", "wamid.out.1")
        await OutboundHandler(pool, graph)(reply, "corr-1")  # redelivery: not sent twice
        assert len(graph.sent) == 1

        # Delivery statuses move forward only.
        for state in ("delivered", "sent"):
            status_env = _receive(
                client,
                inbox,
                _meta(statuses=[{"id": "wamid.out.1", "status": state, "recipient_id": CUSTOMER}]),
            )
            assert status_env.type == "wa.inbound.status"
            await InboundHandler(pool, out)(status_env, "corr-3")
        assert _messages(outlet["id"])[-1][3] == "delivered"
    finally:
        await pool.close()


async def test_menu_keyword_and_reservation_rows(
    client: TestClient, inbox: InMemoryPublisher, outlet: dict[str, Any]
) -> None:
    admin_sql(
        "update app.conversations set flow = 'order', state = '{\"cart\": [1]}'"
        " where outlet_id = %s",
        (outlet["id"],),
    )
    admin_sql(
        "insert into app.reservation_settings (outlet_id, tenant_id, is_enabled)"
        " values (%s, %s, true) on conflict (outlet_id) do update set is_enabled = true",
        (outlet["id"], outlet["tenant"]),
    )
    env = _receive(client, inbox, _text("wamid.menu", " Menu "))
    pool = db.create_pool(APP_URL or "", min_size=1, max_size=2)
    await pool.open(wait=True)
    try:
        out = InMemoryPublisher()
        await InboundHandler(pool, out)(env, "corr-4")
        (reply,) = out.take("wa.outbound")
        assert _row_titles(reply) == [
            "Pesan",
            "Rekomendasi",
            "Reservasi",
            "Reservasi Saya",
            "Data Saya",
        ]
        assert admin_sql(
            "select flow, state from app.conversations where outlet_id = %s", (outlet["id"],)
        ) == [(None, {})]
    finally:
        await pool.close()
        admin_sql(
            "update app.reservation_settings set is_enabled = false where outlet_id = %s",
            (outlet["id"],),
        )


async def test_lost_publish_is_retried_and_the_reply_is_not_lost(
    client: TestClient, inbox: InMemoryPublisher, outlet: dict[str, Any]
) -> None:
    env = _receive(client, inbox, _text("wamid.lost", "Halo lagi"))
    pool = db.create_pool(APP_URL or "", min_size=1, max_size=2)
    await pool.open(wait=True)
    try:
        broken = InMemoryPublisher(fail=True)
        with pytest.raises(RetryableError):
            await InboundHandler(pool, broken)(env, "corr-5")
        assert _messages(outlet["id"])[-1][3] == "queued"
        before = len(_messages(outlet["id"]))

        out = InMemoryPublisher()
        await InboundHandler(pool, out)(env, "corr-5")  # redelivery after the retry delay
        (reply,) = out.take("wa.outbound")
        assert reply.payload["message_id"] == _messages(outlet["id"])[-1][0]
        assert len(_messages(outlet["id"])) == before  # processed once, reply republished
        assert _messages(outlet["id"])[-1][3] == "enqueued"
    finally:
        await pool.close()


async def test_graph_errors_retry_or_fail_the_message(
    client: TestClient, inbox: InMemoryPublisher, outlet: dict[str, Any]
) -> None:
    env = _receive(client, inbox, _text("wamid.errors", "Halo"))
    pool = db.create_pool(APP_URL or "", min_size=1, max_size=2)
    await pool.open(wait=True)
    try:
        out = InMemoryPublisher()
        await InboundHandler(pool, out)(env, "corr-6")
        (reply,) = out.take("wa.outbound")
        with pytest.raises(RetryableError):
            await OutboundHandler(pool, FakeGraph(GraphError(503, None, "busy")))(reply, "c")
        assert _messages(outlet["id"])[-1][3] == "enqueued"
        with pytest.raises(PermanentError, match="outside_24h_window"):
            await OutboundHandler(pool, FakeGraph(GraphError(400, 131047, "re-engage")))(reply, "c")
        assert _messages(outlet["id"])[-1][3] == "failed"
        graph = FakeGraph()
        await OutboundHandler(pool, graph)(reply, "c")  # a failed message is not resent
        assert graph.sent == []
    finally:
        await pool.close()


class SlowGraph(FakeGraph):
    async def send_message(self, phone_number_id: str, to: str, body: dict[str, Any]) -> str:
        await asyncio.sleep(0.3)
        return await super().send_message(phone_number_id, to, body)


async def test_duplicate_copies_sent_at_the_same_time_reach_the_customer_once(
    client: TestClient, inbox: InMemoryPublisher, outlet: dict[str, Any]
) -> None:
    # Found in the end-to-end smoke run: Meta delivered one message twice, the duplicate
    # republished the still-queued reply, and both copies were sent at the same moment.
    env = _receive(client, inbox, _text("wamid.twice", "Halo"))
    pool = db.create_pool(APP_URL or "", min_size=2, max_size=3)
    await pool.open(wait=True)
    try:
        out = InMemoryPublisher()
        await InboundHandler(pool, out)(env, "corr-7")
        (reply,) = out.take("wa.outbound")
        graph = SlowGraph(prefix="wamid.slow")
        handler = OutboundHandler(pool, graph)
        await asyncio.gather(handler(reply, "a"), handler(reply, "b"))
        assert len(graph.sent) == 1
        assert _messages(outlet["id"])[-1][3] == "sent"
    finally:
        await pool.close()


async def test_unknown_envelope_type_is_permanent(outlet: dict[str, Any]) -> None:
    pool = db.create_pool(APP_URL or "", min_size=1, max_size=2)
    await pool.open(wait=True)
    try:
        env = Envelope(
            type="wa.inbound.reaction",
            tenant_id=UUID(outlet["tenant"]),
            outlet_id=UUID(outlet["id"]),
            idempotency_key="x",
            payload={},
        )
        with pytest.raises(PermanentError):
            await InboundHandler(pool, InMemoryPublisher())(env, "c")
    finally:
        await pool.close()


def test_cli_disconnects_the_number(
    client: TestClient, inbox: InMemoryPublisher, outlet: dict[str, Any]
) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("DATABASE_URL", APP_URL or "")
        assert cli.main(["whatsapp-connect", "--outlet", outlet["id"], "--disconnect"]) == 0
        try:
            row = admin_sql(
                "select whatsapp_phone_number_id, whatsapp_status from app.outlets where id = %s",
                (outlet["id"],),
            )
            assert row == [(None, "not_started")]
            assert _post(client, _text("wamid.after", "Halo")).status_code == 200
            assert inbox.take() == []  # the number no longer maps to the outlet
            audit = admin_sql(
                "select action from app.audit_events where outlet_id = %s"
                " and entity_type = 'outlet' and action like 'outlet.whatsapp%%' order by id",
                (outlet["id"],),
            )
            assert [a[0] for a in audit] == [
                "outlet.whatsapp_connected",
                "outlet.whatsapp_disconnected",
            ]
        finally:
            argv = ["whatsapp-connect", "--outlet", outlet["id"], "--phone-number-id", NUMBER]
            assert cli.main(argv) == 0
