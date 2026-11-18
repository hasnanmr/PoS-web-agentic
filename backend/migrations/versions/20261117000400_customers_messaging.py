"""T-004: WhatsApp customers, consent, conversations, messages, duplicate check.

Revision ID: 20261117000400
Revises: 20261117000300
"""

from migrations.sqlfile import run_sql

revision = "20261117000400"
down_revision = "20261117000300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
