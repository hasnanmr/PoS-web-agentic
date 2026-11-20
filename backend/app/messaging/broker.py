"""Publisher interface plus an in-memory implementation for tests and local shells."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.messaging.envelope import Envelope


class PublishError(RuntimeError):
    """The broker did not confirm the message (callers may answer 503 or retry)."""


class Publisher(Protocol):
    async def publish(
        self, exchange: str, envelope: Envelope, *, correlation_id: str | None = None
    ) -> None:
        """Publish persistently and wait for the broker's confirm; raise `PublishError`."""
        ...


@dataclass
class InMemoryPublisher:
    """Collects published envelopes. Set `fail = True` to simulate a broker outage."""

    published: list[tuple[str, Envelope, str | None]] = field(default_factory=list)
    fail: bool = False

    async def publish(
        self, exchange: str, envelope: Envelope, *, correlation_id: str | None = None
    ) -> None:
        if self.fail:
            raise PublishError("broker unavailable (simulated)")
        self.published.append((exchange, envelope, correlation_id))

    def take(self, exchange: str | None = None) -> list[Envelope]:
        """Return and forget what was published (optionally only to `exchange`)."""
        picked = [e for x, e, _ in self.published if exchange is None or x == exchange]
        self.published = [p for p in self.published if exchange is not None and p[0] != exchange]
        return picked
