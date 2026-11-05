"""jobs: lowongan internal (HR-posted) dengan lifecycle & weighted skills

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("posted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=10), nullable=False, server_default="hr"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("responsibilities", sa.Text(), nullable=True),
        sa.Column("requirements", sa.Text(), nullable=True),
        sa.Column("skills", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("employment_type", sa.String(length=20), nullable=False),
        sa.Column("work_mode", sa.String(length=10), nullable=False),
        sa.Column("seniority", sa.String(length=50), nullable=True),
        sa.Column("location_text", sa.String(length=255), nullable=True),
        sa.Column("salary_min", sa.Numeric(14, 2), nullable=True),
        sa.Column("salary_max", sa.Numeric(14, 2), nullable=True),
        sa.Column("salary_currency", sa.String(length=8), nullable=False, server_default="IDR"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("closed_reason", sa.String(length=20), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_jobs_company_id_companies")
        ),
        sa.ForeignKeyConstraint(
            ["posted_by_user_id"], ["users.id"], name=op.f("fk_jobs_posted_by_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.CheckConstraint(
            "status IN ('draft','active','paused','closed','expired','archived')",
            name="ck_jobs_status",
        ),
        sa.CheckConstraint(
            "employment_type IN ('full_time','part_time','contract','internship','freelance')",
            name="ck_jobs_employment_type",
        ),
        sa.CheckConstraint("work_mode IN ('onsite','hybrid','remote')", name="ck_jobs_work_mode"),
        sa.CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="ck_jobs_salary_range",
        ),
    )
    op.create_index(op.f("ix_jobs_title"), "jobs", ["title"], unique=False)
    op.create_index(op.f("ix_jobs_company_id"), "jobs", ["company_id"], unique=False)
    op.create_index(op.f("ix_jobs_location_text"), "jobs", ["location_text"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_index(op.f("ix_jobs_posted_at"), "jobs", ["posted_at"], unique=False)
    op.create_index(
        "ix_jobs_status_closing_active",
        "jobs",
        ["status", "closing_at"],
        unique=False,
        postgresql_where=sa.text("status = 'active' AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_status_closing_active", table_name="jobs")
    op.drop_index(op.f("ix_jobs_posted_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_location_text"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_company_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_title"), table_name="jobs")
    op.drop_table("jobs")
