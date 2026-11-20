"""WhatsApp customers, conversations, and the message log (T-046, T-048, T-049).

Used by the webhook (outlet lookup only) and the WhatsApp worker. Message bodies are stored as
opaque JSON: this module knows nothing about WhatsApp formats. Everything except
`resolve_outlet_by_number` runs inside `app.db.transaction` with a `system` actor and the
message's tenant, so RLS keeps each tenant's customers apart.

Personal data (phone, name) lives only in `whatsapp_contacts` (FR12.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.core.actor import ActorContext

# Outbound delivery status: only moves forward (queued → enqueued → sent → delivered → read).
# `queued` = logged, not yet confirmed by RabbitMQ; `enqueued` = on `wa.outbound`.
# `failed` replaces queued/enqueued/sent but never a message already delivered or read.
_STATUS_RANK = {"queued": 0, "enqueued": 0, "sent": 1, "delivered": 2, "read": 3}


async def resolve_outlet_by_number(
    conn: AsyncConnection, phone_number_id: str
) -> tuple[UUID, UUID] | None:
    """(tenant_id, outlet_id) of the active outlet that owns this Meta phone number id (FR2.10).

    Runs before any tenant is known, through the definer function (Appendix B.6)."""
    cur = await conn.execute(
        "select tenant_id, outlet_id from app.resolve_outlet_by_phone_number_id(%s)",
        (phone_number_id,),
    )
    row = await cur.fetchone()
    return (row[0], row[1]) if row else None


@dataclass(frozen=True, slots=True)
class OutletProfile:
    outlet_id: UUID
    tenant_name: str
    outlet_name: str
    phone_number_id: str | None
    reservations_enabled: bool

    @property
    def display_name(self) -> str:
        """How the bot names the outlet, e.g. "Kopi Senja \u2013 Dago" (wireframe W1)."""
        return f"{self.tenant_name} \u2013 {self.outlet_name}"


async def outlet_profile(conn: AsyncConnection, outlet_id: UUID) -> OutletProfile | None:
    cur = await conn.execute(
        """
        select t.name, o.name, o.whatsapp_phone_number_id, coalesce(rs.is_enabled, false)
          from app.outlets o
          join app.tenants t on t.id = o.tenant_id
          left join app.reservation_settings rs on rs.outlet_id = o.id
         where o.id = %s and o.is_active
        """,
        (outlet_id,),
    )
    row = await cur.fetchone()
    if row is None:
        return None
    return OutletProfile(outlet_id, row[0], row[1], row[2], bool(row[3]))


async def lock_customer(conn: AsyncConnection, outlet_id: UUID, wa_id: str) -> None:
    """Process one conversation at a time (T-046): a transaction-scoped advisory lock on the
    (outlet, customer) pair, which is unique per conversation and exists before the
    conversation row does."""
    await conn.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"wa:{outlet_id}:{wa_id}",)
    )


async def claim_message(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, meta_message_id: str
) -> bool:
    """Record that an inbound message is being processed (NFR8, T-048). False = already done.

    Written in the same transaction as everything the message changes, so a rollback frees
    it for the retry and a commit makes every redelivery a no-op."""
    cur = await conn.execute(
        """
        insert into app.processed_messages (meta_message_id, tenant_id, outlet_id)
        values (%s, %s, %s) on conflict (meta_message_id) do nothing
        returning meta_message_id
        """,
        (meta_message_id, ctx.tenant_id, outlet_id),
    )
    return await cur.fetchone() is not None


def phone_of(wa_id: str) -> str:
    """Stored phone format: E.164 with a plus ("6281234567890" → "+6281234567890")."""
    return f"+{wa_id.lstrip('+')}"


async def upsert_contact(
    conn: AsyncConnection, ctx: ActorContext, wa_id: str, name: str | None, at: datetime
) -> UUID:
    """The tenant's contact for this phone, created on first contact. `last_inbound_at`
    tracks the 24-hour customer service window (FR6.2)."""
    cur = await conn.execute(
        """
        insert into app.whatsapp_contacts (tenant_id, phone, display_name, last_inbound_at)
        values (%s, %s, %s, %s)
        on conflict (tenant_id, phone) where phone is not null do update
           set display_name = coalesce(excluded.display_name, app.whatsapp_contacts.display_name),
               last_inbound_at = greatest(app.whatsapp_contacts.last_inbound_at,
                                          excluded.last_inbound_at)
        returning id
        """,
        (ctx.tenant_id, phone_of(wa_id), (name or "").strip()[:120] or None, at),
    )
    row = await cur.fetchone()
    assert row is not None  # noqa: S101
    return row[0]


@dataclass(frozen=True, slots=True)
class Conversation:
    id: UUID
    flow: str | None
    state: dict[str, Any]
    updated_at: datetime


async def open_conversation(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, contact_id: UUID
) -> Conversation:
    """The (outlet, contact) conversation, created on first contact, locked for update."""
    await conn.execute(
        """
        insert into app.conversations (tenant_id, outlet_id, contact_id) values (%s, %s, %s)
        on conflict (outlet_id, contact_id) do nothing
        """,
        (ctx.tenant_id, outlet_id, contact_id),
    )
    cur = await conn.cursor(row_factory=dict_row).execute(
        """
        select id, flow, state, updated_at from app.conversations
         where outlet_id = %s and contact_id = %s for update
        """,
        (outlet_id, contact_id),
    )
    row = await cur.fetchone()
    assert row is not None  # noqa: S101
    state = row["state"] if isinstance(row["state"], dict) else {}
    return Conversation(row["id"], row["flow"], state, row["updated_at"])


async def save_conversation(
    conn: AsyncConnection, conversation_id: UUID, flow: str | None, state: dict[str, Any]
) -> None:
    await conn.execute(
        "update app.conversations set flow = %s, state = %s where id = %s",
        (flow, Jsonb(state), conversation_id),
    )


async def record_inbound(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    conversation_id: UUID,
    meta_message_id: str,
    message_type: str,
    body: dict[str, Any],
) -> None:
    await conn.execute(
        """
        insert into app.messages
          (tenant_id, outlet_id, conversation_id, direction, meta_message_id, message_type, body)
        values (%s, %s, %s, 'inbound', %s, %s, %s)
        """,
        (ctx.tenant_id, outlet_id, conversation_id, meta_message_id, message_type, Jsonb(body)),
    )


async def queue_outbound(
    conn: AsyncConnection,
    ctx: ActorContext,
    outlet_id: UUID,
    conversation_id: UUID,
    message_type: str,
    body: dict[str, Any],
) -> int:
    """Log an outgoing message as `queued`; the outbound worker sends it and marks it."""
    cur = await conn.execute(
        """
        insert into app.messages
          (tenant_id, outlet_id, conversation_id, direction, message_type, body, status)
        values (%s, %s, %s, 'outbound', %s, %s, 'queued')
        returning id
        """,
        (ctx.tenant_id, outlet_id, conversation_id, message_type, Jsonb(body)),
    )
    row = await cur.fetchone()
    assert row is not None  # noqa: S101
    return int(row[0])


async def unsent_replies(
    conn: AsyncConnection, meta_message_id: str
) -> list[tuple[int, dict[str, Any]]]:
    """Replies to an inbound message that are still `queued` (their publish may have been lost).

    A reply is written in the same transaction as the inbound row, so it shares its
    `created_at` (transaction time) and conversation."""
    cur = await conn.execute(
        """
        select r.id, r.body from app.messages i
          join app.messages r on r.conversation_id = i.conversation_id
                             and r.direction = 'outbound' and r.status = 'queued'
                             and r.created_at = i.created_at
         where i.meta_message_id = %s and i.direction = 'inbound'
         order by r.id
        """,
        (meta_message_id,),
    )
    return [(int(r[0]), r[1]) for r in await cur.fetchall()]


async def mark_enqueued(conn: AsyncConnection, message_ids: list[int]) -> None:
    """RabbitMQ confirmed these replies; a redelivered inbound message no longer republishes
    them."""
    await conn.execute(
        "update app.messages set status = 'enqueued' where id = any(%s) and status = 'queued'",
        (message_ids,),
    )


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    id: int
    status: str | None
    meta_message_id: str | None


async def lock_outbound(
    conn: AsyncConnection, message_id: int
) -> OutboundMessage | Literal["busy", "missing"]:
    """Lock an outbound message for sending, held until the transaction ends.

    "busy" = another copy of the same queue message is sending it right now (duplicates
    happen: a redelivered inbound message republishes replies that are still queued); that
    copy skips instead of sending twice."""
    cur = await conn.execute(
        "select id, status, meta_message_id from app.messages"
        " where id = %s and direction = 'outbound' for update skip locked",
        (message_id,),
    )
    row = await cur.fetchone()
    if row is not None:
        return OutboundMessage(int(row[0]), row[1], row[2])
    cur = await conn.execute(
        "select 1 from app.messages where id = %s and direction = 'outbound'", (message_id,)
    )
    return "busy" if await cur.fetchone() else "missing"


async def mark_sent(conn: AsyncConnection, message_id: int, meta_message_id: str) -> None:
    """Store Meta's id; a delivery status that already arrived is not moved back."""
    await conn.execute(
        """
        update app.messages set meta_message_id = %s,
               status = case when status in ('delivered', 'read') then status else 'sent' end
         where id = %s
        """,
        (meta_message_id, message_id),
    )


async def mark_failed(conn: AsyncConnection, message_id: int, reason: str) -> None:
    await conn.execute(
        "update app.messages set status = 'failed',"
        " body = body || jsonb_build_object('error', %s::text)"
        " where id = %s and meta_message_id is null",
        (reason[:500], message_id),
    )


async def apply_status(conn: AsyncConnection, meta_message_id: str, status: str) -> bool:
    """Apply a Meta delivery status to an outbound message. False if unknown or not newer."""
    if status != "failed" and status not in _STATUS_RANK:
        return False
    cur = await conn.execute(
        "select id, status from app.messages where meta_message_id = %s and direction = 'outbound'",
        (meta_message_id,),
    )
    row = await cur.fetchone()
    if row is None:
        return False
    current = _STATUS_RANK.get(row[1] or "queued", -1)
    if status == "failed":
        if row[1] in ("delivered", "read", "failed"):
            return False
    elif _STATUS_RANK[status] <= current:
        return False
    await conn.execute("update app.messages set status = %s where id = %s", (status, row[0]))
    return True
