"""Broker-independent consumer step (T-111; Appendix A.5).

`run_handler` turns one delivery into an `Outcome`; the AMQP adapter carries it out
(republish to a retry tier or the dead-letter exchange, then ack). Keeping the decision here
lets tests drive retries and dead-lettering without a broker.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

from app.messaging.envelope import (
    HEADER_ATTEMPT,
    HEADER_CORRELATION,
    HEADER_FAILURE,
    Envelope,
    InvalidEnvelopeError,
)
from app.messaging.policy import decide
from app.messaging.topology import DEAD_LETTER_EXCHANGE, WorkQueue

logger = logging.getLogger(__name__)

Handler = Callable[[Envelope, str], Awaitable[None]]
"""A message handler: (envelope, correlation id). Raise to retry or dead-letter."""


@dataclass(frozen=True, slots=True)
class Outcome:
    action: Literal["ack", "retry", "dead"]
    exchange: str | None = None  # where to republish (retry tier or dead-letter exchange)
    headers: dict[str, Any] = field(default_factory=dict)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def attempt_of(headers: Mapping[str, Any]) -> int:
    try:
        return max(int(_text(headers.get(HEADER_ATTEMPT)) or 1), 1)
    except ValueError:
        return 1


async def run_handler(
    body: bytes, headers: Mapping[str, Any], wq: WorkQueue, handler: Handler
) -> Outcome:
    attempt = attempt_of(headers)
    correlation = _text(headers.get(HEADER_CORRELATION)) or uuid4().hex
    base = {HEADER_CORRELATION: correlation, HEADER_ATTEMPT: attempt}
    try:
        envelope = Envelope.from_json(body)
    except InvalidEnvelopeError as exc:
        logger.error(
            "invalid envelope dead-lettered",
            extra={"queue": wq.queue, "error": str(exc), "correlation_id": correlation},
        )
        return Outcome(
            "dead", DEAD_LETTER_EXCHANGE, {**base, HEADER_FAILURE: f"invalid_envelope: {exc}"}
        )
    try:
        await handler(envelope, correlation)
    except Exception as exc:
        decision = decide(exc, attempt, wq)
        log = {
            "queue": wq.queue,
            "type": envelope.type,
            "envelope_id": str(envelope.id),
            "attempt": attempt,
            "reason": decision.reason,
            "correlation_id": correlation,
        }
        if decision.action == "retry" and decision.tier is not None:
            logger.warning("message retry scheduled", extra={**log, "tier": decision.tier.queue})
            return Outcome("retry", decision.tier.exchange, {**base, HEADER_ATTEMPT: attempt + 1})
        logger.error("message dead-lettered", extra=log, exc_info=exc)
        return Outcome("dead", DEAD_LETTER_EXCHANGE, {**base, HEADER_FAILURE: decision.reason})
    return Outcome("ack")
