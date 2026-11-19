"""Purchase orders: suppliers, POs, lines, goods receipts, supplier payments (T-125).

Revision ID: 20261119000200
Revises: 20261119000100
"""

from migrations.sqlfile import run_sql

revision = "20261119000200"
down_revision = "20261119000100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
