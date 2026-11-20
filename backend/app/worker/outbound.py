"""Outbound worker: `wa.outbound.q` → WhatsApp Cloud API (T-047).

Each send runs inside one short transaction that locks the message row (`FOR UPDATE SKIP
LOCKED`): a duplicate copy of the queue message that arrives while the first is sending skips
it, and one that arrives later sees Meta's id and skips too. A crash during the send rolls the
lock back and RabbitMQ redelivers, so delivery is at least once.

Errors follow Appendix A.3: 429, 5xx, network, and Meta throttling codes retry; other 4xx
mark the message `failed` and dead-letter it. Meta's outside-the-24-hour-window error is
dead-lettered too for now; the switch to an approved template arrives with T-055 (Wave 5c).
"""

from __future__ import annotations

import logging

from psycopg_pool import AsyncConnectionPool

from app import db
from app.core import conversations as conv
from app.core.actor import ActorContext
from app.messaging.envelope import Envelope
from app.messaging.policy import PermanentError, RetryableError
from app.whatsapp.graph import GraphClient, GraphError

logger = logging.getLogger(__name__)


class OutboundHandler:
    def __init__(self, pool: AsyncConnectionPool, graph: GraphClient) -> None:
        self._pool = pool
        self._graph = graph

    async def __call__(self, envelope: Envelope, correlation_id: str) -> None:
        if not envelope.type.startswith("wa.outbound."):
            raise PermanentError(f"unknown message type {envelope.type!r}")
        p = envelope.payload
        try:
            message_id = int(p["message_id"])
            phone_number_id, to, body = str(p["phone_number_id"]), str(p["to"]), p["body"]
        except (KeyError, TypeError, ValueError) as exc:
            raise PermanentError(f"invalid outbound payload: {exc}") from exc
        if not isinstance(body, dict):
            raise PermanentError("invalid outbound payload: body")
        ctx = ActorContext.for_system(envelope.tenant_id, correlation_id=correlation_id)
        log = {"message_id": message_id, "type": envelope.type, "correlation_id": correlation_id}

        error: Exception | None = None
        async with db.transaction(self._pool, ctx) as conn:
            row = await conv.lock_outbound(conn, message_id)
            if row == "missing":
                raise PermanentError(f"outbound message {message_id} not found")
            if row == "busy":
                logger.info("outbound message is being sent by another copy", extra=log)
                return
            if row.meta_message_id is not None or row.status == "failed":
                logger.info("outbound message already handled", extra={**log, "status": row.status})
                return
            try:
                meta_id = await self._graph.send_message(phone_number_id, to, body)
            except GraphError as exc:
                if exc.retryable:
                    error = RetryableError(str(exc))
                else:
                    await conv.mark_failed(conn, message_id, str(exc))
                    reason = "outside_24h_window" if exc.outside_window else "rejected"
                    error = PermanentError(f"{reason}: {exc}")
                error.__cause__ = exc
            else:
                await conv.mark_sent(conn, message_id, meta_id)
        if error is not None:
            raise error
        logger.info("whatsapp message sent", extra=log)
