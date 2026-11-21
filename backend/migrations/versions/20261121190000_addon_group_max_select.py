"""Optional add-on groups can cap how many options are chosen ("Tambahan · opsional, maks 2").

Revision ID: 20261121190000
Revises: 20261121180000
"""

from migrations.sqlfile import run_sql

revision = "20261121190000"
down_revision = "20261121180000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
