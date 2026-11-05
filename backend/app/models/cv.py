"""Model CV (dokumen) & hasil ekstraksi dasar.

- File disimpan di luar root statis dengan nama acak; akses hanya via endpoint
  berotorisasi (blueprint §5.1).
- `cv_extractions` menyimpan hasil ekstraksi; P2 mengisi raw_text (PyMuPDF dasar),
  fase AI berikutnya mengisi `payload` terstruktur (kolom ditambahkan belakangan).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

CV_STATUSES = ("pending", "processing", "ready", "failed")


class CV(Base):
    __tablename__ = "cvs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','ready','failed')", name="ck_cvs_status"
        ),
        # Guard race dedupe: satu CV aktif (belum dihapus) per isi identik per pemilik.
        Index(
            "uq_cvs_owner_sha_active",
            "candidate_user_id",
            "content_sha256",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    file_path: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    is_primary: Mapped[bool] = mapped_column(default=False)
    # Rantai versi untuk hasil optimasi CV (fase AI); upload manual selalu v1 tanpa parent.
    version: Mapped[int] = mapped_column(default=1)
    parent_cv_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cvs.id", use_alter=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    extraction: Mapped["CvExtraction | None"] = relationship(
        back_populates="cv", uselist=False, lazy="joined"
    )


class CvExtraction(Base):
    __tablename__ = "cv_extractions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cv_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cvs.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|done|failed
    raw_text: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    parser_version: Mapped[str] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cv: Mapped[CV] = relationship(back_populates="extraction")
