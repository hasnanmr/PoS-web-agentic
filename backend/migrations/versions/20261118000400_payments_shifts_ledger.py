"""Wave 4: QRIS proof review (S4), blind-count shift close (S8), expenses and reports (O9, O10).

Revision ID: 20261118000400
Revises: 20261118000310
"""

from migrations.sqlfile import run_sql

revision = "20261118000400"
down_revision = "20261118000310"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
