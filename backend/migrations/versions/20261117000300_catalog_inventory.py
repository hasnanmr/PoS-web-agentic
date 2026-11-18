"""T-004: menu, add-ons, per-outlet prices, tags, ingredients, recipes, stock movements.

Revision ID: 20261117000300
Revises: 20261117000200
"""

from migrations.sqlfile import run_sql

revision = "20261117000300"
down_revision = "20261117000200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
