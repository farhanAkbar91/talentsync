"""Model lowongan pekerjaan (P2) — internal (HR-posted).

Struktur skills: [{"name": str, "required": bool}] — pembobotan 60% required /
40% preferred (desain Figma "Buat Lowongan Baru") diterapkan oleh matching engine
di fase AI; flag `required` sudah membedakan kedua kelompok sejak sekarang.
Kolom eksternal ingestion (source_name, external_id, dst.) ditambahkan pada fase
pipeline; `source_type` sudah disiapkan agar migrasi belakangan kecil.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.profile import JSONVariant

JOB_STATUSES = ("draft", "active", "paused", "closed", "expired", "archived")
EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "internship", "freelance")
WORK_MODES = ("onsite", "hybrid", "remote")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','active','paused','closed','expired','archived')",
            name="ck_jobs_status",
        ),
        CheckConstraint(
            "employment_type IN ('full_time','part_time','contract','internship','freelance')",
            name="ck_jobs_employment_type",
        ),
        CheckConstraint("work_mode IN ('onsite','hybrid','remote')", name="ck_jobs_work_mode"),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="ck_jobs_salary_range",
        ),
        # Katalog publik selalu memfilter status aktif → index parsial di PostgreSQL.
        Index(
            "ix_jobs_status_closing_active",
            "status",
            "closing_at",
            postgresql_where=text("status = 'active' AND deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), index=True)
    posted_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    source_type: Mapped[str] = mapped_column(String(10), default="hr")

    title: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[Any]] = mapped_column(JSONVariant, default=list)

    category: Mapped[str | None] = mapped_column(String(100))
    employment_type: Mapped[str] = mapped_column(String(20))
    work_mode: Mapped[str] = mapped_column(String(10))
    seniority: Mapped[str | None] = mapped_column(String(50))
    location_text: Mapped[str | None] = mapped_column(String(255), index=True)

    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    salary_currency: Mapped[str] = mapped_column(String(8), default="IDR")

    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    closed_reason: Mapped[str | None] = mapped_column(String(20))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    closing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(lazy="joined")  # noqa: F821
