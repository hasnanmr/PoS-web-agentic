"""A table in use is occupied automatically; "Kosongkan meja" releases it (FR9.11, T-149).

Revision ID: 20261121200000
Revises: 20261121190000
"""

from migrations.sqlfile import run_sql

revision = "20261121200000"
down_revision = "20261121190000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
