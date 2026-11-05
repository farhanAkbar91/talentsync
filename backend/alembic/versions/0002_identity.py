"""identity: users, refresh_tokens, candidate_profiles, companies, company_members

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.CheckConstraint("role IN ('candidate', 'hr')", name="ck_users_role"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_refresh_tokens_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_tokens_token_hash")),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)

    op.create_table(
        "candidate_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("headline", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("skills", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("education", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("experience", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("certifications", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("links", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_candidate_profiles_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_candidate_profiles")),
    )

    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("website", sa.String(length=255), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], name=op.f("fk_companies_created_by_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )

    op.create_table(
        "company_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_in_company", sa.String(length=20), nullable=False, server_default="owner"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            ondelete="CASCADE",
            name=op.f("fk_company_members_company_id_companies"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_company_members_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_company_members")),
        sa.UniqueConstraint("user_id", name=op.f("uq_company_members_user_id")),
    )
    op.create_index(
        op.f("ix_company_members_company_id"), "company_members", ["company_id"], unique=False
    )


def downgrade() -> None:
    op.drop_table("company_members")
    op.drop_table("companies")
    op.drop_table("candidate_profiles")
    op.drop_table("refresh_tokens")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
