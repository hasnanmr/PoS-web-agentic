"""Meta WhatsApp webhook (T-045, T-046) — serves the worker flows W1-W12, not a screen.

- `GET /webhooks/whatsapp`: Meta's verification handshake when the URL is registered
  (`hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`).
- `POST /webhooks/whatsapp`: checks `X-Hub-Signature-256` (HMAC-SHA256 of the raw body with the
  app secret), finds each event's outlet from the receiving phone number id (FR2.10), and
  publishes it to `wa.inbound` with publisher confirms. It answers 200 straight away and never
  runs order logic or writes business tables (api-boundaries §1). Events for unknown numbers
  are dropped (logged). If the broker does not confirm, it answers 503 so Meta delivers again;
  duplicates are ignored by the worker (`processed_messages`).

Not part of the admin API contract, so it is left out of the OpenAPI schema.
"""

from __future__ import annotations

import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import PlainTextResponse

from app import db
from app.api.errors import ApiError
from app.config import Settings, whatsapp_webhook_ready
from app.core import conversations
from app.core.actor import ActorContext
from app.messaging.broker import Publisher, PublishError
from app.messaging.envelope import Envelope
from app.messaging.topology import WA_INBOUND
from app.whatsapp.webhook import parse_events, valid_signature

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

PATH = "/webhooks/whatsapp"


def _not_ready() -> ApiError:
    return ApiError(503, "whatsapp_not_configured", "WhatsApp webhook is not configured")


@router.get(PATH)
async def verify(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    if settings.whatsapp_verify_token is None:
        raise _not_ready()
    q = request.query_params
    token = q.get("hub.verify_token") or ""
    expected = settings.whatsapp_verify_token.get_secret_value()
    if q.get("hub.mode") == "subscribe" and hmac.compare_digest(token, expected):
        return PlainTextResponse(q.get("hub.challenge") or "")
    raise ApiError(403, "forbidden", "verification token does not match")


@router.post(PATH)
async def receive(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    publisher: Publisher | None = request.app.state.publisher
    pool: Any = request.app.state.db_pool
    if not whatsapp_webhook_ready(settings) or publisher is None or pool is None:
        raise _not_ready()
    assert settings.whatsapp_app_secret is not None  # noqa: S101 - checked above

    body = await request.body()
    secret = settings.whatsapp_app_secret.get_secret_value()
    if not valid_signature(secret, body, request.headers.get("X-Hub-Signature-256")):
        logger.warning("whatsapp webhook with an invalid signature rejected")
        raise ApiError(401, "invalid_signature", "signature does not match")
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise ApiError(400, "validation_failed", "body is not JSON") from exc

    events = parse_events(data)
    if not events:
        return Response(status_code=200)

    ctx = ActorContext.for_system(None)
    outlets: dict[str, Any] = {}
    async with db.transaction(pool, ctx) as conn:
        for number in {e.phone_number_id for e in events}:
            outlets[number] = await conversations.resolve_outlet_by_number(conn, number)

    published = 0
    try:
        for event in events:
            found = outlets.get(event.phone_number_id)
            if found is None:
                logger.warning(
                    "whatsapp event for an unknown phone number id dropped",
                    extra={"phone_number_id": event.phone_number_id, "kind": event.kind},
                )
                continue
            tenant_id, outlet_id = found
            await publisher.publish(
                WA_INBOUND.exchange,
                Envelope(
                    type=f"wa.inbound.{event.kind}",
                    tenant_id=tenant_id,
                    outlet_id=outlet_id,
                    idempotency_key=event.idempotency_key,
                    payload=event.payload,
                ),
                correlation_id=ctx.correlation_id,
            )
            published += 1
    except PublishError as exc:
        logger.error(
            "whatsapp webhook could not publish; Meta will retry",
            extra={"published": published, "error": str(exc)},
        )
        raise ApiError(503, "queue_unavailable", "message queue unavailable") from exc
    return Response(status_code=200)
