"""attendance_tablets

Revision ID: 20261119170052
Revises: 20261120000100
"""

from migrations.sqlfile import run_sql

revision = "20261119170052"
down_revision = "20261120000100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
