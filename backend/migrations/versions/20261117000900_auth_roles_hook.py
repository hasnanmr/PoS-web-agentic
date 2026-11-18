"""T-113: JWT claim contract, custom access token hook, backend DB role,

Revision ID: 20261117000900
Revises: 20261117000800
"""

from migrations.sqlfile import run_sql

revision = "20261117000900"
down_revision = "20261117000800"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
