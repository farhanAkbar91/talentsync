"""match_results: hasil matching CV vs lowongan + evidence

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-06

Satu hasil per (cv, job, model_version) — versi model baru menimpa skor lama.
Evidence & top_experiences menjadi dasar transparansi skor di UI.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "match_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cv_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("overall", sa.Float(), nullable=False),
        sa.Column("factors", postgresql.JSONB(), nullable=False),
        sa.Column("matched_skills", postgresql.JSONB(), nullable=False),
        sa.Column("missing_skills", postgresql.JSONB(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=True),
        sa.Column("top_experiences", postgresql.JSONB(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(length=60), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["cv_id"], ["cvs.id"], ondelete="CASCADE", name=op.f("fk_match_results_cv_id_cvs")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], ondelete="CASCADE", name=op.f("fk_match_results_job_id_jobs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_results")),
        sa.UniqueConstraint(
            "cv_id", "job_id", "model_version", name=op.f("uq_match_results_cv_id")
        ),
    )
    op.create_index(op.f("ix_match_results_job_id"), "match_results", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_match_results_job_id"), table_name="match_results")
    op.drop_table("match_results")
