"""T-005: row-level security and table privileges for app_backend.

Revision ID: 20261117001000
Revises: 20261117000900
"""

from migrations.sqlfile import run_sql

revision = "20261117001000"
down_revision = "20261117000900"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
