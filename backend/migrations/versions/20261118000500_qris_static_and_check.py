"""PoC demo: static QRIS per outlet (O3 "QRIS statis outlet") and the staff cross-check of

Revision ID: 20261118000500
Revises: 20261118000400
"""

from migrations.sqlfile import run_sql

revision = "20261118000500"
down_revision = "20261118000400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
