"""T-004: scheduled jobs (Appendix A.4) and staff attendance (FR5.1-FR5.7).

Revision ID: 20261117000700
Revises: 20261117000600
"""

from migrations.sqlfile import run_sql

revision = "20261117000700"
down_revision = "20261117000600"
branch_labels = None
depends_on = None


def upgrade() -> None:
    run_sql(revision)


def downgrade() -> None:
    raise NotImplementedError("forward-only: add a new migration instead")
