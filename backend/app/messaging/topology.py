"""Exchanges, queues, and retry tiers, declared by code (T-110; Task Breakdown Appendix A.2/A.3).

Every working exchange is `direct` and its routing key equals the exchange name, so a retry
republished with the original routing key comes back to the right working queue through
`retry.return`.
"""

from __future__ import annotations

from dataclasses import dataclass

DEAD_LETTER_EXCHANGE = "wa.dlx"
RETRY_RETURN_EXCHANGE = "retry.return"


@dataclass(frozen=True, slots=True)
class WorkQueue:
    exchange: str  # also the routing key
    queue: str
    dead_queue: str
    max_attempts: int
    prefetch: int


WA_INBOUND = WorkQueue("wa.inbound", "wa.inbound.q", "wa.dead.q", max_attempts=4, prefetch=10)
WA_OUTBOUND = WorkQueue("wa.outbound", "wa.outbound.q", "wa.dead.q", max_attempts=6, prefetch=5)
CATALOG_SYNC = WorkQueue(
    "catalog.sync", "catalog.sync.q", "catalog.dead.q", max_attempts=8, prefetch=5
)
JOBS = WorkQueue("jobs", "jobs.due.q", "jobs.dead.q", max_attempts=4, prefetch=10)

WORK_QUEUES: tuple[WorkQueue, ...] = (WA_INBOUND, WA_OUTBOUND, CATALOG_SYNC, JOBS)


@dataclass(frozen=True, slots=True)
class RetryTier:
    exchange: str
    queue: str
    ttl_ms: int


RETRY_TIERS: tuple[RetryTier, ...] = (
    RetryTier("retry.5s", "retry.5s.q", 5_000),
    RetryTier("retry.30s", "retry.30s.q", 30_000),
    RetryTier("retry.2m", "retry.2m.q", 120_000),
)


def retry_tier_for(attempt: int) -> RetryTier:
    """Attempt 1 failed → 5 s, attempt 2 → 30 s, attempt 3 and later → 2 min (A.3)."""
    return RETRY_TIERS[min(max(attempt, 1), len(RETRY_TIERS)) - 1]


def work_queue_for(exchange: str) -> WorkQueue:
    for wq in WORK_QUEUES:
        if wq.exchange == exchange:
            return wq
    raise KeyError(exchange)
