"""Drop the table QR target setting (T-147): the QR always opens the web chat.

Revision ID: 20261121160000
Revises: 20261121140000
"""

from migrations.sqlfile import run_sql

revision = "20261121160000"
down_revision = "20261121140000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
