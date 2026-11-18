"""Run the plain-SQL file of a revision: migrations/sql/<revision>_<name>.sql.

Executed on the raw psycopg connection without parameters (no bind parsing, so `:` and `%`
in the SQL are left alone), inside the revision's transaction.
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

SQL_DIR = Path(__file__).parent / "sql"


def sql_path(revision: str) -> Path:
    matches = sorted(SQL_DIR.glob(f"{revision}_*.sql"))
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected one migrations/sql/{revision}_*.sql, found {len(matches)}"
        )
    return matches[0]


def run_sql(revision: str) -> None:
    # The raw psycopg connection, with no parameters: `%` and `:` stay literal and the file
    # may hold many statements. Same connection, so it runs in the revision's transaction.
    driver = op.get_bind().connection.driver_connection
    driver.execute(sql_path(revision).read_text(encoding="utf-8"))  # type: ignore[union-attr]
