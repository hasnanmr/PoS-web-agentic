"""RabbitMQ adapter (aio-pika): topology declaration, confirmed publishing, consuming.

Appendix A.5: manual ack only after the handler's transaction committed, publisher confirms
on every publish, heartbeat 30 s, automatic reconnect (robust connection), correlation id in
headers. Retries and dead letters are republished by the consumer, then the original is
acked; if that republish fails the original is requeued instead.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aio_pika
import yarl
from aio_pika.abc import (
    AbstractIncomingMessage,
    AbstractRobustChannel,
    AbstractRobustConnection,
)

from app.messaging.broker import PublishError
from app.messaging.consumer import Handler, run_handler
from app.messaging.envelope import HEADER_ATTEMPT, HEADER_CORRELATION, Envelope
from app.messaging.topology import (
    DEAD_LETTER_EXCHANGE,
    RETRY_RETURN_EXCHANGE,
    RETRY_TIERS,
    WORK_QUEUES,
    WorkQueue,
)

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 30
PUBLISH_TIMEOUT_SECONDS = 10


def _with_heartbeat(url: str) -> str:
    parsed = yarl.URL(url)
    if "heartbeat" in parsed.query:
        return url
    return str(parsed.update_query(heartbeat=HEARTBEAT_SECONDS))


async def declare_topology(channel: AbstractRobustChannel) -> None:
    """Declare every exchange, queue, and binding (idempotent; safe on every start)."""
    dlx = await channel.declare_exchange(
        DEAD_LETTER_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
    )
    ret = await channel.declare_exchange(
        RETRY_RETURN_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True
    )
    for tier in RETRY_TIERS:
        ex = await channel.declare_exchange(
            tier.exchange, aio_pika.ExchangeType.TOPIC, durable=True
        )
        q = await channel.declare_queue(
            tier.queue,
            durable=True,
            arguments={"x-message-ttl": tier.ttl_ms, "x-dead-letter-exchange": ret.name},
        )
        await q.bind(ex, "#")
    for wq in WORK_QUEUES:
        ex = await channel.declare_exchange(wq.exchange, aio_pika.ExchangeType.DIRECT, durable=True)
        q = await channel.declare_queue(wq.queue, durable=True)
        await q.bind(ex, wq.exchange)
        await q.bind(ret, wq.exchange)
        dead = await channel.declare_queue(wq.dead_queue, durable=True)
        await dead.bind(dlx, wq.exchange)


class AmqpBroker:
    """One robust connection; a confirm channel for publishing, one channel per consumer."""

    def __init__(self, url: str) -> None:
        self._url = _with_heartbeat(url)
        self._conn: AbstractRobustConnection | None = None
        self._pub: AbstractRobustChannel | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        async with self._lock:
            if self._pub is not None and not self._pub.is_closed:
                return
            if self._conn is None or self._conn.is_closed:
                self._conn = await aio_pika.connect_robust(self._url)
            self._pub = await self._conn.channel(publisher_confirms=True, on_return_raises=True)
            await declare_topology(self._pub)

    async def close(self) -> None:
        if self._conn is not None and not self._conn.is_closed:
            await self._conn.close()
        self._conn = None
        self._pub = None

    async def _publish_raw(
        self, exchange: str, routing_key: str, body: bytes, headers: dict[str, Any]
    ) -> None:
        try:
            await self.connect()
            assert self._pub is not None  # noqa: S101
            ex = await self._pub.get_exchange(exchange, ensure=False)
            message = aio_pika.Message(
                body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers=headers,
            )
            await ex.publish(message, routing_key, timeout=PUBLISH_TIMEOUT_SECONDS)
        except PublishError:
            raise
        except Exception as exc:  # connection, confirm timeout, unroutable (returned) message
            raise PublishError(f"publish to {exchange} failed: {exc}") from exc

    async def publish(
        self, exchange: str, envelope: Envelope, *, correlation_id: str | None = None
    ) -> None:
        headers: dict[str, Any] = {HEADER_ATTEMPT: 1}
        if correlation_id:
            headers[HEADER_CORRELATION] = correlation_id
        await self._publish_raw(exchange, exchange, envelope.to_json(), headers)

    async def consume(self, wq: WorkQueue, handler: Handler) -> None:
        """Start consuming `wq` (returns once the consumer is registered)."""
        await self.connect()
        assert self._conn is not None  # noqa: S101
        channel = await self._conn.channel()
        await channel.set_qos(prefetch_count=wq.prefetch)
        queue = await channel.get_queue(wq.queue, ensure=False)

        async def on_message(message: AbstractIncomingMessage) -> None:
            outcome = await run_handler(message.body, dict(message.headers or {}), wq, handler)
            if outcome.action != "ack" and outcome.exchange is not None:
                try:
                    await self._publish_raw(
                        outcome.exchange, wq.exchange, message.body, outcome.headers
                    )
                except PublishError:
                    logger.exception("republish failed; requeueing", extra={"queue": wq.queue})
                    await message.nack(requeue=True)
                    return
            await message.ack()

        await queue.consume(on_message)
        logger.info("consuming", extra={"queue": wq.queue, "prefetch": wq.prefetch})
