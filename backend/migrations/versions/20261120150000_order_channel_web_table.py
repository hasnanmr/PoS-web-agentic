"""Order channel web_table for the customer table web page (T-133).

Revision ID: 20261120150000
Revises: 20261120122524
"""

from migrations.sqlfile import run_sql

revision = "20261120150000"
down_revision = "20261120122524"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
