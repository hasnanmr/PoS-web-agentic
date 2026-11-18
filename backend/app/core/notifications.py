"""Customer notification hook for order changes (S2 note, S4 rejection, glossary §5).

Called inside the transaction that changes the order. WhatsApp delivery (outbox + worker,
T-049 onward) is not part of the POS-core demo, so for now the hook only logs what would
be sent; counter orders have no WhatsApp contact and are skipped. When the worker exists,
this function writes the outbox row in the same transaction, and callers stay unchanged.
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from psycopg import AsyncConnection

from app.core.actor import ActorContext

logger = logging.getLogger(__name__)

OrderNotice = Literal["payment_confirmed", "proof_rejected"]


async def order_customer(
    conn: AsyncConnection, ctx: ActorContext, order_id: UUID, notice: OrderNotice
) -> bool:
    """Queue a customer message about `order_id`. Returns False when the order has no
    WhatsApp contact (nothing to send)."""
    cur = await conn.execute("select contact_id from app.orders where id = %s", (order_id,))
    row = await cur.fetchone()
    if row is None or row[0] is None:
        return False
    logger.info(
        "customer notification pending (WhatsApp worker not configured)",
        extra={"order_id": str(order_id), "notice": notice, "correlation_id": ctx.correlation_id},
    )
    return True
