"""Actor context for every write (T-008).

Each request, worker message, or scheduled job runs with one `ActorContext`. It is
used to set the database session (`app.tenant_id`, `app.user_id`, `app.actor`,
`app.device_outlet_id`, `app.device_id`, see `app.db.transaction`) and is recorded on every
ledger, stock, order, reservation, attendance, and audit write (NFR3).

Actor types match the database enum `app.actor_type`:

- ``user``   — a named owner or staff member (from a verified Supabase token)
- ``system`` — workers, the scheduler, automatic timeouts
- ``agent``  — the AI agent (MVP: read-only recommendations)
- ``device`` — a paired outlet attendance tablet (T-121)
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"
    DEVICE = "device"


class ReasonRequiredError(ValueError):
    """Raised when an action that needs a reason (reversal, rejection, correction) has none."""


@dataclass(frozen=True, slots=True)
class ActorContext:
    actor_type: ActorType
    tenant_id: UUID | None
    user_id: UUID | None = None
    device_id: UUID | None = None
    device_outlet_id: UUID | None = None
    reason: str | None = None
    correlation_id: str = field(default_factory=lambda: uuid4().hex)
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.actor_type is ActorType.USER and (self.user_id is None or self.tenant_id is None):
            raise ValueError("a user actor needs user_id and tenant_id")
        if self.actor_type is ActorType.DEVICE and (
            self.device_id is None or self.device_outlet_id is None or self.tenant_id is None
        ):
            raise ValueError("a device actor needs device_id, device_outlet_id and tenant_id")
        if self.actor_type in (ActorType.SYSTEM, ActorType.AGENT) and self.user_id is not None:
            raise ValueError("system and agent actors have no user_id")

    # Factories -------------------------------------------------------------------
    @classmethod
    def for_user(
        cls, tenant_id: UUID, user_id: UUID, *, correlation_id: str | None = None
    ) -> ActorContext:
        return cls(
            ActorType.USER,
            tenant_id,
            user_id=user_id,
            correlation_id=correlation_id or uuid4().hex,
        )

    @classmethod
    def for_system(
        cls, tenant_id: UUID | None, *, correlation_id: str | None = None
    ) -> ActorContext:
        return cls(ActorType.SYSTEM, tenant_id, correlation_id=correlation_id or uuid4().hex)

    @classmethod
    def for_agent(cls, tenant_id: UUID, *, correlation_id: str | None = None) -> ActorContext:
        return cls(ActorType.AGENT, tenant_id, correlation_id=correlation_id or uuid4().hex)

    @classmethod
    def for_device(
        cls,
        tenant_id: UUID,
        device_id: UUID,
        outlet_id: UUID,
        *,
        correlation_id: str | None = None,
    ) -> ActorContext:
        return cls(
            ActorType.DEVICE,
            tenant_id,
            device_id=device_id,
            device_outlet_id=outlet_id,
            correlation_id=correlation_id or uuid4().hex,
        )

    # Helpers ---------------------------------------------------------------------
    @property
    def actor_id(self) -> UUID | None:
        """The id stored in `actor_id` columns: the user or the device; None otherwise."""
        if self.actor_type is ActorType.USER:
            return self.user_id
        if self.actor_type is ActorType.DEVICE:
            return self.device_id
        return None

    def with_reason(self, reason: str | None) -> ActorContext:
        """Return a copy carrying a reason; blank reasons raise `ReasonRequiredError`."""
        cleaned = (reason or "").strip()
        if not cleaned:
            raise ReasonRequiredError("a reason is required for this action")
        return replace(self, reason=cleaned)

    def session_settings(self) -> dict[str, str]:
        """Values for the transaction-local `set_config` calls (Appendix B.4)."""
        return {
            "app.tenant_id": str(self.tenant_id) if self.tenant_id else "",
            "app.user_id": str(self.user_id) if self.user_id else "",
            "app.actor": self.actor_type.value,
            "app.device_outlet_id": str(self.device_outlet_id) if self.device_outlet_id else "",
            "app.device_id": str(self.device_id) if self.device_id else "",
            "app.correlation_id": self.correlation_id,
        }
