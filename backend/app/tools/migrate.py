"""Apply pending schema migrations (Alembic) to the database at MIGRATION_DATABASE_URL.

    uv run python -m app.tools.migrate            # upgrade to head; no-op when up to date
    uv run python -m app.tools.migrate --dry-run  # only list what would run
    uv run python -m app.tools.migrate --check    # exit 1 if migrations are pending

Use an owner role (e.g. `postgres`) in session mode (Supabase pooler port 5432, not the
6543 transaction pooler); never the app_backend URL the API uses.

Adoption: databases migrated before Alembic (with the Supabase CLI, history in
`supabase_migrations.schema_migrations`) are stamped at the newest revision recorded
there, so only later revisions run. Revision ids are the 14-digit SQL file prefixes.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, pool

VERSION_SCHEMA = "alembic"
BACKEND_DIR = Path(__file__).resolve().parents[2]


def database_url() -> str:
    url = os.environ.get("MIGRATION_DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("MIGRATION_DATABASE_URL is not set (owner role, session mode)")
    return url


def sqlalchemy_url() -> str:
    url = database_url()
    for prefix in ("postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    raise SystemExit("MIGRATION_DATABASE_URL must be a postgresql:// URL")


def _libpq_url() -> str:
    return sqlalchemy_url().replace("postgresql+psycopg://", "postgresql://", 1)


def alembic_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


def _current(script: ScriptDirectory) -> str | None:
    engine = create_engine(sqlalchemy_url(), poolclass=pool.NullPool)
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"version_table_schema": VERSION_SCHEMA})
        return ctx.get_current_revision()


def _supabase_cli_revision(script: ScriptDirectory) -> str | None:
    """Newest revision applied by the Supabase CLI, when Alembic has not run here yet."""
    with psycopg.connect(_libpq_url()) as conn:
        has_alembic, has_cli = conn.execute(
            "select to_regclass(%s) is not null, to_regclass(%s) is not null",
            (f"{VERSION_SCHEMA}.alembic_version", "supabase_migrations.schema_migrations"),
        ).fetchone()  # type: ignore[misc]
        if has_alembic or not has_cli:
            return None
        applied = [
            r[0]
            for r in conn.execute(
                "select version from supabase_migrations.schema_migrations order by version"
            ).fetchall()
        ]
    if not applied:
        return None
    known = {rev.revision for rev in script.walk_revisions()}
    unknown = [v for v in applied if v not in known]
    if unknown:
        raise SystemExit(f"Supabase CLI history has versions without a revision: {unknown}")
    return applied[-1]


def _pending(script: ScriptDirectory, current: str | None) -> list[str]:
    head = script.get_current_head()
    if current == head:
        return []
    revs = list(script.iterate_revisions(head, current or "base"))
    return [r.revision for r in reversed(revs)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="list pending revisions only")
    parser.add_argument("--check", action="store_true", help="exit 1 if revisions are pending")
    args = parser.parse_args(argv)

    cfg = alembic_config()
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        raise SystemExit(f"expected one migration head, found {heads}")

    baseline = _supabase_cli_revision(script)
    if baseline and not (args.dry_run or args.check):
        print(f"adopting Supabase CLI history: stamping {baseline}")
        command.stamp(cfg, baseline)
    current = _current(script) or baseline
    pending = _pending(script, current)
    print(f"current: {current or 'empty'} · head: {heads[0]}")
    if not pending:
        print("up to date, nothing to apply")
        return 0
    print("pending: " + ", ".join(pending))
    if args.check:
        return 1
    if args.dry_run:
        return 0
    command.upgrade(cfg, "head")
    print(f"applied {len(pending)} migration(s); now at {_current(script)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
