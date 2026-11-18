"""T-010, T-012: owner onboarding (O1) and staff invitations (O4).

Revision ID: 20261118000100
Revises: 20261117001000
"""

from migrations.sqlfile import run_sql

revision = "20261118000100"
down_revision = "20261117001000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
