"""T-004: tenants, outlets, users, staff assignments, drawers, tables, devices, audit.

Revision ID: 20261117000200
Revises: 20261117000100
"""

from migrations.sqlfile import run_sql

revision = "20261117000200"
down_revision = "20261117000100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
