"""One active attendance tablet per outlet; forget it before pairing a new one (O3, K0).

Revision ID: 20261120104500
Revises: 20261120000200
"""

from migrations.sqlfile import run_sql

revision = "20261120104500"
down_revision = "20261120000200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
