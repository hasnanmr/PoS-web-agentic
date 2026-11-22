"""A table QR order may be takeaway and keeps its table (C8 "Bawa pulang").

Revision ID: 20261122120000
Revises: 20261121200000
"""

from migrations.sqlfile import run_sql

revision = "20261122120000"
down_revision = "20261121200000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
