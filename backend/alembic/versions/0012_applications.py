"""applications: lamaran kandidat per lowongan (M9 HR candidate ranking)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-07

Satu lamaran per (lowongan, kandidat) — UNIQUE(job_id, candidate_user_id).
`cv_id` merekam CV yang dipakai saat melamar (snapshot, bukan CV primer saat
ini): hard delete CV → SET NULL agar riwayat lamaran tetap ada. Tanpa RLS —
tabel operasional seperti tabel lain (keputusan konsisten Wave sebelumnya).
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_user_id", sa.Uuid(), nullable=False),
        sa.Column("cv_id", sa.Uuid(), nullable=True),
        sa.Column("cover_letter", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="submitted"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], ondelete="CASCADE", name=op.f("fk_applications_job_id_jobs")
        ),
        sa.ForeignKeyConstraint(
            ["candidate_user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_applications_candidate_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["cv_id"], ["cvs.id"], ondelete="SET NULL", name=op.f("fk_applications_cv_id_cvs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.CheckConstraint(
            "status IN ('submitted','reviewed','shortlisted','rejected','hired')",
            name="ck_applications_status",
        ),
        sa.UniqueConstraint("job_id", "candidate_user_id", name=op.f("uq_applications_job_id")),
    )
    op.create_index(op.f("ix_applications_job_id"), "applications", ["job_id"], unique=False)
    op.create_index(
        op.f("ix_applications_candidate_user_id"),
        "applications",
        ["candidate_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_applications_candidate_user_id"), table_name="applications")
    op.drop_index(op.f("ix_applications_job_id"), table_name="applications")
    op.drop_table("applications")
