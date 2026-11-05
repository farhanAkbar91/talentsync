"""cvs: dokumen CV kandidat + hasil ekstraksi dasar

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-04
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cvs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("parent_cv_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["candidate_user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_cvs_candidate_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_cv_id"], ["cvs.id"], name=op.f("fk_cvs_parent_cv_id_cvs"), use_alter=True
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cvs")),
        sa.CheckConstraint(
            "status IN ('pending','processing','ready','failed')", name="ck_cvs_status"
        ),
    )
    op.create_index(op.f("ix_cvs_candidate_user_id"), "cvs", ["candidate_user_id"], unique=False)
    op.create_index(op.f("ix_cvs_content_sha256"), "cvs", ["content_sha256"], unique=False)

    op.create_table(
        "cv_extractions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cv_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("parser_version", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["cv_id"], ["cvs.id"], ondelete="CASCADE", name=op.f("fk_cv_extractions_cv_id_cvs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cv_extractions")),
        sa.UniqueConstraint("cv_id", name=op.f("uq_cv_extractions_cv_id")),
    )
    op.create_index(op.f("ix_cv_extractions_cv_id"), "cv_extractions", ["cv_id"], unique=False)


def downgrade() -> None:
    op.drop_table("cv_extractions")
    op.drop_index(op.f("ix_cvs_content_sha256"), table_name="cvs")
    op.drop_index(op.f("ix_cvs_candidate_user_id"), table_name="cvs")
    op.drop_table("cvs")
