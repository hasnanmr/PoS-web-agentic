"""Envelope, retry tiers, and the consumer decision (T-110, T-111; Appendix A.3/A.5)."""

from __future__ import annotations

from uuid import uuid4

import psycopg.errors
import pytest

from app.messaging.consumer import run_handler
from app.messaging.envelope import (
    HEADER_ATTEMPT,
    HEADER_CORRELATION,
    HEADER_FAILURE,
    Envelope,
    InvalidEnvelopeError,
)
from app.messaging.policy import PermanentError, RetryableError, decide
from app.messaging.topology import (
    DEAD_LETTER_EXCHANGE,
    WA_INBOUND,
    WA_OUTBOUND,
    retry_tier_for,
    work_queue_for,
)


def _envelope() -> Envelope:
    return Envelope(
        type="wa.inbound.message",
        tenant_id=uuid4(),
        outlet_id=uuid4(),
        idempotency_key="wamid.ABC",
        payload={"message": {"text": {"body": "Halo ☕"}}},
    )


def test_envelope_round_trip() -> None:
    env = _envelope()
    back = Envelope.from_json(env.to_json())
    assert back == env
    assert b'"occurred_at":"' in env.to_json() and b'Z"' in env.to_json()


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"type": "x"}', b'{"version": 2, "payload": {}}'],
)
def test_invalid_envelopes_are_rejected(body: bytes) -> None:
    with pytest.raises(InvalidEnvelopeError):
        Envelope.from_json(body)


def test_retry_tiers_follow_the_attempt_number() -> None:
    assert retry_tier_for(1).queue == "retry.5s.q"
    assert retry_tier_for(2).queue == "retry.30s.q"
    assert retry_tier_for(3).queue == "retry.2m.q"
    assert retry_tier_for(7).queue == "retry.2m.q"
    assert work_queue_for("wa.outbound") is WA_OUTBOUND


@pytest.mark.parametrize(
    "exc",
    [
        RetryableError("429"),
        TimeoutError(),
        ConnectionError(),
        psycopg.errors.DeadlockDetected(),
        psycopg.errors.SerializationFailure(),
        psycopg.OperationalError("connection lost"),
    ],
)
def test_temporary_failures_are_retried(exc: Exception) -> None:
    decision = decide(exc, 1, WA_INBOUND)
    assert decision.action == "retry" and decision.tier is not None


@pytest.mark.parametrize("exc", [PermanentError("400"), KeyError("bug"), ValueError("bad")])
def test_permanent_failures_and_bugs_are_dead_lettered(exc: Exception) -> None:
    assert decide(exc, 1, WA_INBOUND).action == "dead"


def test_max_attempts_dead_letters_a_retryable_failure() -> None:
    assert decide(TimeoutError(), WA_INBOUND.max_attempts - 1, WA_INBOUND).action == "retry"
    last = decide(TimeoutError(), WA_INBOUND.max_attempts, WA_INBOUND)
    assert last.action == "dead" and "max attempts (4)" in last.reason


async def test_success_is_acked_with_the_correlation_id() -> None:
    seen: list[str] = []

    async def handler(env: Envelope, correlation: str) -> None:
        seen.append(correlation)

    out = await run_handler(
        _envelope().to_json(), {HEADER_CORRELATION: b"c-1"}, WA_INBOUND, handler
    )
    assert out.action == "ack" and seen == ["c-1"]


async def test_retry_republishes_to_the_tier_with_the_next_attempt() -> None:
    async def handler(env: Envelope, correlation: str) -> None:
        raise RetryableError("meta 503")

    out = await run_handler(_envelope().to_json(), {HEADER_ATTEMPT: 2}, WA_INBOUND, handler)
    assert out.action == "retry" and out.exchange == "retry.30s"
    assert out.headers[HEADER_ATTEMPT] == 3 and out.headers[HEADER_CORRELATION]


async def test_dead_letter_carries_the_failure_reason() -> None:
    async def handler(env: Envelope, correlation: str) -> None:
        raise PermanentError("template rejected")

    out = await run_handler(_envelope().to_json(), {}, WA_INBOUND, handler)
    assert out.action == "dead" and out.exchange == DEAD_LETTER_EXCHANGE
    assert "template rejected" in out.headers[HEADER_FAILURE]


async def test_invalid_body_is_dead_lettered_without_calling_the_handler() -> None:
    called = False

    async def handler(env: Envelope, correlation: str) -> None:
        nonlocal called
        called = True

    out = await run_handler(b"{}", {}, WA_INBOUND, handler)
    assert out.action == "dead" and not called
    assert out.headers[HEADER_FAILURE].startswith("invalid_envelope")
