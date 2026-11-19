"""Private Supabase Storage bucket for menu photos (T-132).

Revision ID: 20261120000100
Revises: 20261119000200
"""

from migrations.sqlfile import run_sql

revision = "20261120000100"
down_revision = "20261119000200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
