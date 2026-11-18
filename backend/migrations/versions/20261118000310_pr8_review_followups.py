"""PR #8 review follow-ups.

Revision ID: 20261118000310
Revises: 20261118000300
"""

from migrations.sqlfile import run_sql

revision = "20261118000310"
down_revision = "20261118000300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
