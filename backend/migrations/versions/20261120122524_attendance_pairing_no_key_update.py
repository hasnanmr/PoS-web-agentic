"""attendance_pairing_no_key_update

Revision ID: 20261120122524
Revises: 20261120104500
"""

from migrations.sqlfile import run_sql

revision = "20261120122524"
down_revision = "20261120104500"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
