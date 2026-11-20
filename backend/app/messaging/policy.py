"""Error classification and retry decisions (T-111; Appendix A.3).

- Retryable: network timeout, HTTP 429, HTTP 5xx, DB deadlock or serialization failure,
  lock timeout, lost DB/broker connection.
- Permanent (dead-letter at once): HTTP 4xx other than 429, invalid payload, unknown message
  type, and any unexpected exception (a bug is parked in the dead-letter queue for replay
  instead of looping).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import psycopg
import psycopg.errors
from psycopg_pool import PoolTimeout

from app.messaging.envelope import InvalidEnvelopeError
from app.messaging.topology import RetryTier, WorkQueue, retry_tier_for


class RetryableError(Exception):
    """A temporary failure: try the message again later."""


class PermanentError(Exception):
    """The message can never succeed as it is: dead-letter it with this reason."""


_RETRYABLE = (
    psycopg.errors.DeadlockDetected,
    psycopg.errors.SerializationFailure,
    psycopg.errors.LockNotAvailable,
    psycopg.errors.QueryCanceled,  # statement / lock timeout
    psycopg.OperationalError,  # connection lost or refused
    PoolTimeout,
    TimeoutError,
    ConnectionError,
)


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, RetryableError):
        return True
    if isinstance(exc, PermanentError | InvalidEnvelopeError):
        return False
    return isinstance(exc, _RETRYABLE)


@dataclass(frozen=True, slots=True)
class Decision:
    action: Literal["retry", "dead"]
    reason: str
    tier: RetryTier | None = None


def failure_reason(exc: BaseException) -> str:
    text = str(exc).strip() or type(exc).__name__
    return f"{type(exc).__name__}: {text}"[:500]


def decide(exc: BaseException, attempt: int, wq: WorkQueue) -> Decision:
    """What to do with a message whose `attempt`-th try raised `exc`."""
    reason = failure_reason(exc)
    if not is_retryable(exc):
        return Decision("dead", reason)
    if attempt >= wq.max_attempts:
        return Decision("dead", f"max attempts ({wq.max_attempts}) reached; last error {reason}")
    return Decision("retry", reason, retry_tier_for(attempt))
