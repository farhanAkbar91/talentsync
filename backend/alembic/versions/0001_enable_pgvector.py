"""enable pgvector extension

Revision ID: 0001
Revises:
Create Date: 2026-11-04

Aktifkan extension pgvector di database sebelum tabel apa pun dibuat.
Dijalankan otomatis oleh container api saat start (alembic upgrade head).
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
