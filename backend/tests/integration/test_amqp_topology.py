"""RabbitMQ topology, retry tier round trip, and dead-lettering against a real broker
(T-110, T-111; Appendix A.2/A.3). Runs when TEST_RABBITMQ_URL is set (CI service)."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import aio_pika
import pytest

from app.messaging.amqp import AmqpBroker
from app.messaging.envelope import HEADER_ATTEMPT, HEADER_FAILURE, Envelope
from app.messaging.policy import PermanentError, RetryableError
from app.messaging.topology import RETRY_TIERS, WA_INBOUND, WORK_QUEUES

RABBIT = os.environ.get("TEST_RABBITMQ_URL")

pytestmark = pytest.mark.skipif(not RABBIT, reason="TEST_RABBITMQ_URL not set")


def _env(key: str) -> Envelope:
    return Envelope(
        type="wa.inbound.message",
        tenant_id=uuid4(),
        outlet_id=uuid4(),
        idempotency_key=key,
        payload={"n": 1},
    )


async def test_retry_returns_to_the_working_queue_and_failures_are_dead_lettered() -> None:
    assert RABBIT
    broker = AmqpBroker(RABBIT)
    await broker.connect()
    await broker.close()
    await broker.connect()  # declaring the topology twice is a no-op

    conn = await aio_pika.connect_robust(RABBIT)
    try:
        ch = await conn.channel()
        names = [q for wq in WORK_QUEUES for q in (wq.queue, wq.dead_queue)]
        names += [t.queue for t in RETRY_TIERS]
        for name in dict.fromkeys(names):
            await (await ch.declare_queue(name, passive=True)).purge()

        seen: list[tuple[str, int]] = []
        done = asyncio.Event()

        async def handler(env: Envelope, correlation: str) -> None:
            seen.append((env.idempotency_key, len(seen)))
            if env.idempotency_key == "permanent":
                raise PermanentError("template rejected")
            if [k for k, _ in seen].count("retry-once") == 1:
                raise RetryableError("meta 503")
            done.set()

        await broker.consume(WA_INBOUND, handler)
        await broker.publish(WA_INBOUND.exchange, _env("permanent"), correlation_id="c-1")
        await broker.publish(WA_INBOUND.exchange, _env("retry-once"), correlation_id="c-2")
        await asyncio.wait_for(done.wait(), timeout=30)  # first retry tier is 5 s

        assert [k for k, _ in seen].count("retry-once") == 2
        assert [k for k, _ in seen].count("permanent") == 1

        dead = await ch.declare_queue(WA_INBOUND.dead_queue, passive=True)
        msg = await dead.get(timeout=5)
        assert msg is not None
        assert Envelope.from_json(msg.body).idempotency_key == "permanent"
        headers = msg.headers or {}
        assert "template rejected" in str(headers[HEADER_FAILURE])
        assert int(str(headers[HEADER_ATTEMPT])) == 1
        await msg.ack()

        await asyncio.sleep(0.5)
        working = await ch.declare_queue(WA_INBOUND.queue, passive=True)
        assert working.declaration_result.message_count == 0
    finally:
        await broker.close()
        await conn.close()
