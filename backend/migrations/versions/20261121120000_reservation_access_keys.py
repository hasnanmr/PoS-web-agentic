"""Extra booking access keys for "Cari dengan kode + HP" (T-061, C12).

Revision ID: 20261121120000
Revises: 20261121100100
"""

from migrations.sqlfile import run_sql

revision = "20261121120000"
down_revision = "20261121100100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
