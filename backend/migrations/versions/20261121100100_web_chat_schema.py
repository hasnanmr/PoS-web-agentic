"""Web chat schema: outlet slug, chat sessions, customers, booking codes (T-140).

Revision ID: 20261121100100
Revises: 20261121100000
"""

from migrations.sqlfile import run_sql

revision = "20261121100100"
down_revision = "20261121100000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
