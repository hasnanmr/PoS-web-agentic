"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

from migrations.sqlfile import run_sql

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
