"""Platform-admin command line (T-006).

Every new owner is invited by a platform admin (product-owner decision
2026-11-17). There is no platform-admin screen in the wireframes, so this is a
CLI, not an API endpoint. It needs SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and
DATABASE_URL, and should be run from the operator's machine or a one-off Railway
command, never from the public API.

    uv run python -m app.cli invite-owner --email owner@cafe.id --invited-by you@platform
    uv run python -m app.cli revoke-owner-invite --id <uuid> \
        --invited-by you@platform --reason "..."

Flow: Supabase sends the invite email → the owner sets a password → their token
carries app_role "owner_pending" → O1 "Buat profil bisnis" creates the tenant (T-010).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

from app import db
from app.auth.supabase_admin import SupabaseAdmin, SupabaseAdminError
from app.config import ConfigError, Settings, load_settings


def _require(settings: Settings, *, admin_api: bool) -> tuple[str, SupabaseAdmin | None]:
    missing = []
    if settings.database_url is None:
        missing.append("DATABASE_URL")
    if admin_api and settings.supabase_url is None:
        missing.append("SUPABASE_URL")
    if admin_api and settings.supabase_service_role_key is None:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise ConfigError("Missing configuration: " + ", ".join(missing))
    admin = None
    if admin_api:
        assert settings.supabase_url is not None  # noqa: S101
        assert settings.supabase_service_role_key is not None  # noqa: S101
        admin = SupabaseAdmin(
            str(settings.supabase_url), settings.supabase_service_role_key.get_secret_value()
        )
    return str(settings.database_url), admin


async def invite_owner(
    settings: Settings, email: str, invited_by: str, note: str | None, redirect_to: str | None
) -> UUID:
    database_url, admin = _require(settings, admin_api=True)
    assert admin is not None  # noqa: S101
    invited = admin.invite_user(email, data={"invited_as": "owner"}, redirect_to=redirect_to)
    async with db.connect(database_url) as conn:
        cur = await conn.execute(
            "select app.record_owner_invitation(%s, %s, %s, %s)",
            (invited.email, invited.user_id, invited_by, note),
        )
        row = await cur.fetchone()
    assert row is not None  # noqa: S101
    return row[0]


async def revoke_owner_invite(
    settings: Settings, invitation_id: UUID, invited_by: str, reason: str
) -> None:
    database_url, _ = _require(settings, admin_api=False)
    async with db.connect(database_url) as conn:
        await conn.execute(
            "select app.revoke_owner_invitation(%s, %s, %s)", (invitation_id, invited_by, reason)
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="SME POS platform-admin tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p_inv = sub.add_parser("invite-owner", help="invite a new business owner by email")
    p_inv.add_argument("--email", required=True)
    p_inv.add_argument("--invited-by", required=True, help="platform admin identifier")
    p_inv.add_argument("--note")
    p_inv.add_argument("--redirect-to", help="admin app URL that sets the password")

    p_rev = sub.add_parser("revoke-owner-invite", help="revoke an unused owner invitation")
    p_rev.add_argument("--id", required=True, type=UUID)
    p_rev.add_argument("--invited-by", required=True)
    p_rev.add_argument("--reason", required=True)

    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        if args.command == "invite-owner":
            inv_id = asyncio.run(
                invite_owner(settings, args.email, args.invited_by, args.note, args.redirect_to)
            )
            print(f"Invitation {inv_id} sent to {args.email}")
        else:
            asyncio.run(revoke_owner_invite(settings, args.id, args.invited_by, args.reason))
            print(f"Invitation {args.id} revoked")
    except (ConfigError, SupabaseAdminError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
