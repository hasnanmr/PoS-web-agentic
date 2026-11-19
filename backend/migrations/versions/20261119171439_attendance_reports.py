"""attendance_reports

Revision ID: 20261119171439
Revises: 20261119170052
"""

from migrations.sqlfile import run_sql

revision = "20261119171439"
down_revision = "20261119170052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
