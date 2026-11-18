"""T-019, T-022, T-024: stock thresholds through a definer function, and the editable

Revision ID: 20261118000200
Revises: 20261118000100
"""

from migrations.sqlfile import run_sql

revision = "20261118000200"
down_revision = "20261118000100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
