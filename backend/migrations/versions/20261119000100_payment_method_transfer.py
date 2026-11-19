"""Payment method transfer for supplier payments (T-125).

Revision ID: 20261119000100
Revises: 20261118000500
"""

from migrations.sqlfile import run_sql

revision = "20261119000100"
down_revision = "20261118000500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
