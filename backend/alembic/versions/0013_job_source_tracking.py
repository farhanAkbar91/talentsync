"""job_source_tracking: provenance lowongan eksternal (pipeline ingestion)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-07

Dua kolom nullable di `jobs`:
- `external_id` — ID/slug asli dari sumber (RemoteOK slug, Remotive id,
  Arbeitnow slug); kunci dedupe bersama `source_type`.
- `source_url` — tautan sumber asli; ATRIBUSI WAJIB untuk lowongan eksternal
  (docs/03 §3: RemoteOK mensyaratkan follow-link balik ke remoteok.com).

Unique index PARSIAL `uq_jobs_source_external (source_type, external_id)` hanya
berlaku untuk baris ingestion (external_id terisi dan belum soft-delete) —
lowongan HR (external_id NULL) dan riwayat arsip tidak terjangkut. Gaya sama
dengan ix_jobs_status_closing_active (0003): postgresql_where + sa.text.
"""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("external_id", sa.String(length=160), nullable=True))
    op.add_column("jobs", sa.Column("source_url", sa.String(length=500), nullable=True))
    op.create_index(
        "uq_jobs_source_external",
        "jobs",
        ["source_type", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_jobs_source_external", table_name="jobs")
    op.drop_column("jobs", "source_url")
    op.drop_column("jobs", "external_id")
