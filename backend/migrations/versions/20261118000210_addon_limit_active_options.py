"""PR #7 review fixes.

Revision ID: 20261118000210
Revises: 20261118000200
"""

from migrations.sqlfile import run_sql

revision = "20261118000210"
down_revision = "20261118000200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
