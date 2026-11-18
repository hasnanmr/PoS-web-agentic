"""T-004: reservations and reservation events.

Revision ID: 20261117000600
Revises: 20261117000500
"""

from migrations.sqlfile import run_sql

revision = "20261117000600"
down_revision = "20261117000500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
