"""T-004: bills, orders, items, events, payments, proofs, shifts, ledger.

Revision ID: 20261117000500
Revises: 20261117000400
"""

from migrations.sqlfile import run_sql

revision = "20261117000500"
down_revision = "20261117000400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
