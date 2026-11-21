"""Encrypt values written before field encryption (migration 20261121140000).

Usage (owner role, like `app.tools.migrate`; needs the production DATA_ENCRYPTION_KEY):

    MIGRATION_DATABASE_URL=postgresql://postgres...@.../postgres \\
    DATA_ENCRYPTION_KEY=... uv run python -m app.tools.encrypt_existing [--dry-run]

Only rows whose value is still plaintext (no `enc:v1:` prefix) are rewritten, so running it
again does nothing. Guest phones also get their blind index. Table QR tokens keep their
SHA-256 (computed from the plaintext by the migration), so printed QR codes keep working.
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg

from app.core import crypto
from app.core.reservations import phone_index

# (table, primary key, column, crypto context)
COLUMNS: tuple[tuple[str, str, str, str], ...] = (
    ("orders", "id", "customer_name", "orders.customer_name"),
    ("orders", "id", "delivery_address", "orders.delivery_address"),
    ("reservations", "id", "guest_name", "reservations.guest_name"),
    ("reservations", "id", "guest_phone", "reservations.guest_phone"),
    ("tables", "id", "qr_token", "tables.qr_token"),
)


def run(url: str, *, dry_run: bool = False) -> dict[str, int]:
    counts: dict[str, int] = {}
    with psycopg.connect(url) as conn:
        # Append-only and touch triggers must not fire for a pure re-encoding of a value.
        conn.execute("set local session_replication_role = replica")
        for table, pk, column, context in COLUMNS:
            rows = conn.execute(
                f"select {pk}, {column} from app.{table}"  # noqa: S608 - constant identifiers
                f" where {column} is not null and {column} not like 'enc:v1:%%'"
            ).fetchall()
            counts[f"{table}.{column}"] = len(rows)
            if dry_run:
                continue
            for key, value in rows:
                conn.execute(
                    f"update app.{table} set {column} = %s where {pk} = %s",  # noqa: S608
                    (crypto.encrypt(value, context), key),
                )
                if (table, column) == ("reservations", "guest_phone"):
                    conn.execute(
                        "update app.reservations set guest_phone_index = %s where id = %s",
                        (phone_index(value), key),
                    )
        if dry_run:
            conn.rollback()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.tools.encrypt_existing", description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="count only, change nothing")
    args = parser.parse_args(argv)
    url = os.environ.get("MIGRATION_DATABASE_URL", "").strip()
    key = os.environ.get("DATA_ENCRYPTION_KEY", "").strip()
    if not url or not key:
        print("set MIGRATION_DATABASE_URL and DATA_ENCRYPTION_KEY", file=sys.stderr)
        return 1
    crypto.configure(key)
    for name, n in run(url, dry_run=args.dry_run).items():
        print(f"{name}: {n} {'to encrypt' if args.dry_run else 'encrypted'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
