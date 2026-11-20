"""Inbound worker: `wa.inbound.q` → conversation flows → replies on `wa.outbound` (T-046 to T-049).

One message = one transaction (system actor, the message's tenant):
  lock the (outlet, customer) pair → claim the Meta message id (duplicate → stop) → contact
  and conversation → log the message → run the flow → save state → log replies as `queued`.
Replies are published after the commit (api-boundaries §5). If that publish fails the
message is retried; the retry finds it already claimed and republishes the replies that are
still queued, so no reply is lost and nothing is processed twice.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

from psycopg_pool import AsyncConnectionPool

from app import db
from app.core import conversations as conv
from app.core.actor import ActorContext
from app.messaging.broker import Publisher, PublishError
from app.messaging.envelope import Envelope
from app.messaging.policy import PermanentError, RetryableError
from app.messaging.topology import WA_OUTBOUND
from app.whatsapp.incoming import parse_message
from app.worker import flows

logger = logging.getLogger(__name__)

_WA_ID = re.compile(r"^\d{6,15}$")


def _timestamp(message: dict[str, Any]) -> datetime:
    try:
        return datetime.fromtimestamp(int(message["timestamp"]), UTC)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return datetime.now(UTC)


class InboundHandler:
    def __init__(self, pool: AsyncConnectionPool, publisher: Publisher) -> None:
        self._pool = pool
        self._publisher = publisher

    async def __call__(self, envelope: Envelope, correlation_id: str) -> None:
        if envelope.type == "wa.inbound.message":
            await self._message(envelope, correlation_id)
        elif envelope.type == "wa.inbound.status":
            await self._status(envelope, correlation_id)
        else:
            raise PermanentError(f"unknown message type {envelope.type!r}")

    async def _message(self, envelope: Envelope, correlation_id: str) -> None:
        payload = envelope.payload
        message = payload.get("message")
        contact = payload.get("contact") or {}
        wa_id = str(contact.get("wa_id") or "")
        if not isinstance(message, dict) or not _WA_ID.match(wa_id):
            raise PermanentError("invalid inbound payload (message or wa_id)")
        ctx = ActorContext.for_system(envelope.tenant_id, correlation_id=correlation_id)
        outlet_id = envelope.outlet_id
        replies: list[tuple[int, dict[str, Any]]] = []

        async with db.transaction(self._pool, ctx) as conn:
            await conv.lock_customer(conn, outlet_id, wa_id)
            profile = await conv.outlet_profile(conn, outlet_id)
            if profile is None:
                raise PermanentError(f"outlet {outlet_id} not found or inactive")
            if not await conv.claim_message(conn, ctx, outlet_id, envelope.idempotency_key):
                replies = await conv.unsent_replies(conn, envelope.idempotency_key)
                logger.info(
                    "duplicate inbound message ignored",
                    extra={
                        "meta_message_id": envelope.idempotency_key,
                        "republish": len(replies),
                        "correlation_id": correlation_id,
                    },
                )
            else:
                contact_id = await conv.upsert_contact(
                    conn, ctx, wa_id, contact.get("name"), _timestamp(message)
                )
                c = await conv.open_conversation(conn, ctx, outlet_id, contact_id)
                incoming = parse_message(message)
                await conv.record_inbound(
                    conn, ctx, outlet_id, c.id, envelope.idempotency_key, incoming.type, message
                )
                result = flows.handle(c.flow, c.state, incoming, profile)
                await conv.save_conversation(conn, c.id, result.flow, result.state)
                for body in result.replies:
                    mid = await conv.queue_outbound(conn, ctx, outlet_id, c.id, body["type"], body)
                    replies.append((mid, body))

        await self._publish(envelope, profile.phone_number_id, wa_id, replies, correlation_id)

    async def _publish(
        self,
        envelope: Envelope,
        phone_number_id: str | None,
        wa_id: str,
        replies: list[tuple[int, dict[str, Any]]],
        correlation_id: str,
    ) -> None:
        if not replies:
            return
        if not phone_number_id:  # number disconnected after the webhook accepted the message
            raise PermanentError(f"outlet {envelope.outlet_id} has no WhatsApp phone number id")
        try:
            for message_id, body in replies:
                await self._publisher.publish(
                    WA_OUTBOUND.exchange,
                    Envelope(
                        type=f"wa.outbound.{body['type']}",
                        tenant_id=envelope.tenant_id,
                        outlet_id=envelope.outlet_id,
                        idempotency_key=f"msg:{message_id}",
                        payload={
                            "message_id": message_id,
                            "phone_number_id": phone_number_id,
                            "to": wa_id,
                            "body": body,
                        },
                    ),
                    correlation_id=correlation_id,
                )
        except PublishError as exc:
            raise RetryableError(f"replies not published: {exc}") from exc
        ctx = ActorContext.for_system(envelope.tenant_id, correlation_id=correlation_id)
        async with db.transaction(self._pool, ctx) as conn:
            await conv.mark_enqueued(conn, [message_id for message_id, _ in replies])

    async def _status(self, envelope: Envelope, correlation_id: str) -> None:
        status = envelope.payload.get("status")
        if not isinstance(status, dict) or not status.get("id") or not status.get("status"):
            raise PermanentError("invalid status payload")
        ctx = ActorContext.for_system(envelope.tenant_id, correlation_id=correlation_id)
        async with db.transaction(self._pool, ctx) as conn:
            changed = await conv.apply_status(conn, str(status["id"]), str(status["status"]))
        if status["status"] == "failed":
            logger.warning(
                "whatsapp message delivery failed",
                extra={
                    "meta_message_id": status["id"],
                    "errors": status.get("errors"),
                    "correlation_id": correlation_id,
                },
            )
        logger.debug("delivery status", extra={"changed": changed, "status": status["status"]})
