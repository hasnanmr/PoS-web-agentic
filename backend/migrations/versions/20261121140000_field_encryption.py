"""Field encryption and blind indexes for personal data and stored credentials.

Revision ID: 20261121140000
Revises: 20261121120000
"""

from migrations.sqlfile import run_sql

revision = "20261121140000"
down_revision = "20261121120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
