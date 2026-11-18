"""T-004: schema, extensions, and enums.

Revision ID: 20261117000100
Revises:
"""

from migrations.sqlfile import run_sql

revision = "20261117000100"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
