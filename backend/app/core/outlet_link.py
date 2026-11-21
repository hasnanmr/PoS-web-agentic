"""Outlet link `/o/<slug>` — O8 "Link outlet & QR" on page 07 (T-147).

The owner sets or changes the outlet's public slug. Slugs are unique across Thinker (every
tenant), so a taken slug is caught by the unique index, which RLS does not hide. Changing it
makes the old link and outlet QR stop working at once: the public lookup only knows the current
slug (C13 "Link ini sudah tidak berlaku"). Owner only; the API checks the role.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection, errors

from app.core.actor import ActorContext
from app.core.audit import record_audit
from app.core.errors import ConflictError, DomainError, NotFoundError

# Same rule as the `outlets.public_slug` check: 3-40 lower-case letters, digits, and single
# hyphens, starting and ending with a letter or digit.
SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")


class SlugInvalidError(DomainError):
    status_code = 422

    def __init__(self) -> None:
        super().__init__(
            "slug_invalid",
            "slug must be 3-40 lower-case letters, digits, and single hyphens",
            {"field": "slug"},
        )


def normalize(slug: str) -> str:
    return slug.strip().lower()


def valid(slug: str) -> bool:
    return bool(SLUG_PATTERN.match(slug)) and "--" not in slug


def outlet_url(app_url: str, slug: str) -> str:
    return f"{app_url.rstrip('/')}/o/{slug}"


async def get_link(conn: AsyncConnection, outlet_id: UUID) -> dict[str, Any]:
    cur = await conn.execute(
        "select public_slug, name from app.outlets where id = %s", (outlet_id,)
    )
    row = await cur.fetchone()
    if row is None:
        raise NotFoundError("outlet")
    return {"slug": row[0], "outlet_name": row[1]}


async def set_slug(
    conn: AsyncConnection, ctx: ActorContext, outlet_id: UUID, slug: str
) -> dict[str, Any]:
    slug = normalize(slug)
    if not valid(slug):
        raise SlugInvalidError
    before = await get_link(conn, outlet_id)
    if before["slug"] == slug:
        return before
    try:
        await conn.execute(
            "update app.outlets set public_slug = %s where id = %s", (slug, outlet_id)
        )
    except errors.UniqueViolation as exc:
        raise ConflictError("slug_taken", "this link is already used by another outlet") from exc
    await record_audit(
        conn,
        ctx,
        action="outlet.slug_changed",
        entity_type="outlet",
        entity_id=outlet_id,
        outlet_id=outlet_id,
        data={"from": before["slug"], "to": slug},
    )
    return {**before, "slug": slug}
