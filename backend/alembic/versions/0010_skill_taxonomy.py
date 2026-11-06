"""skill taxonomy: canonical_skills, skill_aliases, candidate_skills, job_skills

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-06

Fondasi taksonomi skill (M2): definisi kanon + alias hasil seed skills_v1.json,
lalu skill kandidat & skill lowongan hasil normalisasi ekstraksi (M3). Alias
UNIK GLOBAL — satu string alias hanya menunjuk satu skill kanon (anti false
positive); skill kanon yang sudah terpakai diproteksi ON DELETE RESTRICT.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canonical_skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("skill_type", sa.String(length=10), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("related", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("taxonomy_version", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_canonical_skills")),
        sa.UniqueConstraint("slug", name=op.f("uq_canonical_skills_slug")),
        sa.CheckConstraint("skill_type IN ('hard','soft')", name="ck_canonical_skills_skill_type"),
    )
    op.create_table(
        "skill_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_skill_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=160), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False, server_default="seed"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["canonical_skill_id"],
            ["canonical_skills.id"],
            ondelete="CASCADE",
            name=op.f("fk_skill_aliases_canonical_skill_id_canonical_skills"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_aliases")),
        sa.UniqueConstraint("alias", name=op.f("uq_skill_aliases_alias")),
        sa.CheckConstraint("source IN ('seed','manual')", name="ck_skill_aliases_source"),
    )
    op.create_index(op.f("ix_skill_aliases_alias"), "skill_aliases", ["alias"], unique=False)
    op.create_table(
        "candidate_skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_user_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_skill_id", sa.Uuid(), nullable=False),
        sa.Column("source_cv_id", sa.Uuid(), nullable=True),
        sa.Column("raw_name", sa.String(length=160), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("source_section", sa.String(length=30), nullable=True),
        sa.Column("extraction_method", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="suggested"),
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
            name=op.f("fk_candidate_skills_candidate_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["canonical_skill_id"],
            ["canonical_skills.id"],
            ondelete="RESTRICT",
            name=op.f("fk_candidate_skills_canonical_skill_id_canonical_skills"),
        ),
        sa.ForeignKeyConstraint(
            ["source_cv_id"],
            ["cvs.id"],
            ondelete="SET NULL",
            name=op.f("fk_candidate_skills_source_cv_id_cvs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_skills")),
        sa.UniqueConstraint(
            "candidate_user_id",
            "canonical_skill_id",
            name=op.f("uq_candidate_skills_candidate_user_id"),
        ),
        sa.CheckConstraint(
            "extraction_method IN ('explicit','inferred','manual')",
            name="ck_candidate_skills_extraction_method",
        ),
        sa.CheckConstraint(
            "status IN ('suggested','accepted','rejected')",
            name="ck_candidate_skills_status",
        ),
    )
    op.create_index(
        op.f("ix_candidate_skills_candidate_user_id"),
        "candidate_skills",
        ["candidate_user_id"],
        unique=False,
    )
    op.create_table(
        "job_skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("canonical_skill_id", sa.Uuid(), nullable=False),
        sa.Column("raw_name", sa.String(length=160), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            ondelete="CASCADE",
            name=op.f("fk_job_skills_job_id_jobs"),
        ),
        sa.ForeignKeyConstraint(
            ["canonical_skill_id"],
            ["canonical_skills.id"],
            ondelete="RESTRICT",
            name=op.f("fk_job_skills_canonical_skill_id_canonical_skills"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_skills")),
        sa.UniqueConstraint("job_id", "canonical_skill_id", name=op.f("uq_job_skills_job_id")),
    )
    op.create_index(op.f("ix_job_skills_job_id"), "job_skills", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_job_skills_job_id"), table_name="job_skills")
    op.drop_table("job_skills")
    op.drop_index(op.f("ix_candidate_skills_candidate_user_id"), table_name="candidate_skills")
    op.drop_table("candidate_skills")
    op.drop_index(op.f("ix_skill_aliases_alias"), table_name="skill_aliases")
    op.drop_table("skill_aliases")
    op.drop_table("canonical_skills")
