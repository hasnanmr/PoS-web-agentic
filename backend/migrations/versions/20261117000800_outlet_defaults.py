"""T-004: defaults for every new outlet.

Revision ID: 20261117000800
Revises: 20261117000700
"""

from migrations.sqlfile import run_sql

revision = "20261117000800"
down_revision = "20261117000700"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
