"""Order channel web_online and reservation source web_chat (T-140).

Revision ID: 20261121100000
Revises: 20261120150100
"""

from migrations.sqlfile import run_sql

revision = "20261121100000"
down_revision = "20261120150100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
