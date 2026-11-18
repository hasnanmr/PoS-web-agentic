"""Shared helpers for integration tests that create tenants through the API."""

from __future__ import annotations

import os
from typing import Any
from uuid import UUID

import psycopg

ADMIN_URL = os.environ.get("TEST_DATABASE_URL")
APP_URL = os.environ.get("TEST_APP_DATABASE_URL")


def admin_sql(sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    assert ADMIN_URL
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall() if cur.description else []


def cleanup_domain(domain: str) -> None:
    """Delete every tenant whose users or owner invitations use `@domain`, with all its rows."""
    assert ADMIN_URL
    pattern = f"%@{domain}"
    with psycopg.connect(ADMIN_URL) as conn:
        conn.execute("set local session_replication_role = replica")  # skip append-only triggers
        conn.execute(
            "create temp table gone on commit drop as"
            " select tenant_id as id from app.users where email like %s"
            " union select tenant_id from app.owner_invitations"
            " where email like %s and tenant_id is not null",
            (pattern, pattern),
        )
        conn.execute(
            """
            do $$ declare t text;
            begin
              for t in select table_name from information_schema.columns
                       where table_schema = 'app' and column_name = 'tenant_id'
                         and table_name not in ('users', 'owner_invitations', 'tenants')
              loop
                execute format('delete from app.%I where tenant_id in (select id from gone)', t);
              end loop;
            end $$
            """
        )
        conn.execute("delete from app.owner_invitations where email like %s", (pattern,))
        conn.execute("delete from app.users where tenant_id in (select id from gone)")
        conn.execute("delete from app.tenants where id in (select id from gone)")
        conn.execute("delete from auth.users where email like %s", (pattern,))


def invite_owner(user_id: UUID, email: str) -> None:
    admin_sql("insert into auth.users (id, email) values (%s, %s)", (user_id, email))
    admin_sql("select app.record_owner_invitation(%s, %s, 'platform@test', null)", (email, user_id))
