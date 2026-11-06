"""cvs: tambah FK self-reference parent_cv_id (terlewat di 0004)

Revision ID: 0011
Revises: 0010
Create Date: 2027-11-07

Bug lama (P2): FK self-referential dengan `use_alter=True` di dalam
`op.create_table` TIDAK dipancarkan Alembic untuk PostgreSQL — tabel `cvs`
terlahir tanpa constraint `fk_cvs_parent_cv_id_cvs`. Di SQLite tak terdeteksi
karena test membuat skema via `Base.metadata.create_all` (constraint ada).
Dampak: `Base.metadata.drop_all` di CI gagal, dan rantai versi CV (M8) tidak
dijaga integritasnya oleh database. Migrasi ini menambahkan FK tersebut.

Revision ID: 0011
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Mirror persis model (app/models/cv.py): FK tanpa ondelete → NO ACTION
    # (soft-delete dipakai di seluruh alur; hard delete baris CV tidak ada di API).
    op.create_foreign_key(
        "fk_cvs_parent_cv_id_cvs",
        source_table="cvs",
        referent_table="cvs",
        local_cols=["parent_cv_id"],
        remote_cols=["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_cvs_parent_cv_id_cvs", "cvs", type_="foreignkey")
