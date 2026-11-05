"""cv dedupe guard: partial unique index (owner + sha256) untuk CV aktif

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-05

Menutup race condition dedupe upload CV (check-then-insert): dua upload identik
bersamaan kini ditolak oleh database, bukan hanya oleh pengecekan service.
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_cvs_owner_sha_active",
        "cvs",
        ["candidate_user_id", "content_sha256"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_cvs_owner_sha_active", table_name="cvs")
