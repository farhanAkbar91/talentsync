"""cv_optimizations: riwayat generasi saran perbaikan CV per lowongan

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-06

Menyimpan saran LLM (suggestions) beserta keputusan HR per saran (decisions)
dan laporan grounding; applied_cv_id menunjuk CV versi hasil terapkan (SET
NULL agar riwayat tetap ada meski CV turunannya dihapus).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cv_optimizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cv_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="generating"),
        sa.Column("suggestions", postgresql.JSONB(), nullable=True),
        sa.Column("decisions", postgresql.JSONB(), nullable=True),
        sa.Column("grounding_report", postgresql.JSONB(), nullable=True),
        sa.Column("llm_provider", sa.String(length=40), nullable=True),
        sa.Column("llm_model", sa.String(length=80), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("applied_cv_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["applied_cv_id"],
            ["cvs.id"],
            ondelete="SET NULL",
            name=op.f("fk_cv_optimizations_applied_cv_id_cvs"),
        ),
        sa.ForeignKeyConstraint(
            ["cv_id"], ["cvs.id"], ondelete="CASCADE", name=op.f("fk_cv_optimizations_cv_id_cvs")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            ondelete="CASCADE",
            name=op.f("fk_cv_optimizations_job_id_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cv_optimizations")),
        sa.CheckConstraint(
            "status IN ('generating','completed','failed','applied')",
            name="ck_cv_optimizations_status",
        ),
    )


def downgrade() -> None:
    op.drop_table("cv_optimizations")
