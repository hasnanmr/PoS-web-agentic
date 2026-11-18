"""T-029: request idempotency for writes that must not run twice (order creation,

Revision ID: 20261118000300
Revises: 20261118000250
"""

from migrations.sqlfile import run_sql

revision = "20261118000300"
down_revision = "20261118000250"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
