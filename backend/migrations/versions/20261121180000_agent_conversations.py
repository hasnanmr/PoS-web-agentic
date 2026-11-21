"""Web chat agent: encrypted conversation history and the tool-call log (T-086, T-091).

Revision ID: 20261121180000
Revises: 20261121160000
"""

from migrations.sqlfile import run_sql

revision = "20261121180000"
down_revision = "20261121160000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
