"""Stock item names are unique among active items only, so archived ingredients free the name.

Revision ID: 20261120000200
Revises: 20261119171439
"""

from migrations.sqlfile import run_sql

revision = "20261120000200"
down_revision = "20261119171439"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
