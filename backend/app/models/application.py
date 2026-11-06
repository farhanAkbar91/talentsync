"""Model lamaran (M9): kandidat melamar lowongan aktif dengan CV primer.

- `cv_id` merekam CV yang DIPAKAI saat melamar (snapshot identitas lamaran) —
  bukan FK dinamis ke CV primer saat ini; bila CV itu dihapus (hard delete),
  SET NULL menyimpan riwayat lamaran tanpa menggantung.
- UNIQUE(job_id, candidate_user_id): satu kali melamar per lowongan per
  kandidat — melamar ulang ditolak di service (409).
- Status bergerak `submitted → reviewed → shortlisted → hired/rejected`;
  `hired` & `rejected` terminal (transisi dijaga service, bukan DB).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

APPLICATION_STATUSES = ("submitted", "reviewed", "shortlisted", "rejected", "hired")
# Status akhir: sekali hired/rejected, lamaran tidak boleh berubah lagi.
TERMINAL_APPLICATION_STATUSES = ("hired", "rejected")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("job_id", "candidate_user_id"),
        CheckConstraint(
            "status IN ('submitted','reviewed','shortlisted','rejected','hired')",
            name="ck_applications_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    candidate_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # CV saat melamar; SET NULL agar lamaran bertahan saat CV dihapus permanen.
    cv_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cvs.id", ondelete="SET NULL"))
    cover_letter: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="submitted")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped["Job"] = relationship(lazy="joined")  # noqa: F821
    cv: Mapped["CV | None"] = relationship(lazy="joined")  # noqa: F821
