"""cv_extractions: kolom fase AI (payload, confirmed_at, confirmed_by)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06

Menyiapkan cv_extractions untuk pipeline AI (P3.0): payload terstruktur hasil
ekstraksi LLM serta jejak review HR (kapan dan oleh siapa dikonfirmasi).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cv_extractions", sa.Column("payload", postgresql.JSONB(), nullable=True))
    op.add_column(
        "cv_extractions", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("cv_extractions", sa.Column("confirmed_by", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_cv_extractions_confirmed_by_users"),
        "cv_extractions",
        "users",
        ["confirmed_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_cv_extractions_confirmed_by_users"), "cv_extractions", type_="foreignkey"
    )
    op.drop_column("cv_extractions", "confirmed_by")
    op.drop_column("cv_extractions", "confirmed_at")
    op.drop_column("cv_extractions", "payload")
