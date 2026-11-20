"""Table QR web page schema: access key, customer claim, QR target (T-133).

Revision ID: 20261120150100
Revises: 20261120150000
"""

from migrations.sqlfile import run_sql

revision = "20261120150100"
down_revision = "20261120150000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
