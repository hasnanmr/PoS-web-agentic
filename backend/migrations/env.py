"""Alembic environment: one transaction per revision, version table in schema `alembic`.

The schema is not exposed by the Supabase Data API (unlike `public`), and app_backend has no
access to it. The URL comes from MIGRATION_DATABASE_URL (see app/tools/migrate.py).
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool, text

from app.tools.migrate import VERSION_SCHEMA, sqlalchemy_url

config = context.config


def run_migrations_offline() -> None:
    context.configure(
        url=sqlalchemy_url(),
        literal_binds=True,
        version_table_schema=VERSION_SCHEMA,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(sqlalchemy_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        connection.execute(text(f"create schema if not exists {VERSION_SCHEMA}"))
        connection.execute(text(f"revoke all on schema {VERSION_SCHEMA} from public"))
        connection.commit()
        context.configure(
            connection=connection,
            version_table_schema=VERSION_SCHEMA,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
