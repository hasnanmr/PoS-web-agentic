"""Security Advisor: fix mutable search paths on app functions. All relations in

Revision ID: 20261118000250
Revises: 20261118000210
"""

from migrations.sqlfile import run_sql

revision = "20261118000250"
down_revision = "20261118000210"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
