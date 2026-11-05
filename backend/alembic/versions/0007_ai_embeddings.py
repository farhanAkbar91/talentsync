"""AI embeddings: cv_embeddings & job_embeddings (pgvector 384 dimensi)

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-06

Satu baris embedding per (dokumen, model, text_kind); re-embed menimpa baris
lama lewat unique constraint. Pencarian similarity di MVP memakai sequential
scan yang disengaja — tanpa index vektor (HNSW/IVFFlat ditambahkan belakangan
bila skala data menuntut).
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cv_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cv_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("text_kind", sa.String(length=30), nullable=False),
        # Tanpa index vektor: sequential scan disengaja untuk skala MVP.
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["cv_id"], ["cvs.id"], ondelete="CASCADE", name=op.f("fk_cv_embeddings_cv_id_cvs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cv_embeddings")),
        sa.UniqueConstraint("cv_id", "model", "text_kind", name=op.f("uq_cv_embeddings_cv_id")),
    )

    op.create_table(
        "job_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("text_kind", sa.String(length=30), nullable=False),
        # Tanpa index vektor: sequential scan disengaja untuk skala MVP.
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], ondelete="CASCADE", name=op.f("fk_job_embeddings_job_id_jobs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_embeddings")),
        sa.UniqueConstraint("job_id", "model", "text_kind", name=op.f("uq_job_embeddings_job_id")),
    )


def downgrade() -> None:
    op.drop_table("job_embeddings")
    op.drop_table("cv_embeddings")
