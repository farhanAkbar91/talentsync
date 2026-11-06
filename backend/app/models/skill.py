"""Model taksonomi skill (M2): kanon, alias, skill kandidat & skill lowongan.

- `canonical_skills` menyimpan definisi kanon hasil seed skills_v1.json;
  satu baris per slug, `related` berupa daftar slug (JSONB).
- `skill_aliases` memetakan alias → skill kanon; alias UNIK GLOBAL sehingga
  satu string alias selalu menunjuk tepat satu skill kanon (anti false positive).
- `candidate_skills` / `job_skills` menyimpan skill hasil ekstraksi (M3) yang
  sudah dinormalisasi ke skill kanon, lengkap dengan raw_name + confidence
  untuk jejak audit dan review HR.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.profile import JSONVariant

SKILL_TYPES = ("hard", "soft")
ALIAS_SOURCES = ("seed", "manual")
EXTRACTION_METHODS = ("explicit", "inferred", "manual")
CANDIDATE_SKILL_STATUSES = ("suggested", "accepted", "rejected")


class CanonicalSkill(Base):
    __tablename__ = "canonical_skills"
    __table_args__ = (
        CheckConstraint("skill_type IN ('hard','soft')", name="ck_canonical_skills_skill_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    skill_type: Mapped[str] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(Text)
    # Daftar slug skill terkait (harus ada di tabel ini — divalidasi di data seed).
    related: Mapped[list[Any] | None] = mapped_column(JSONVariant)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    taxonomy_version: Mapped[str] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SkillAlias(Base):
    __tablename__ = "skill_aliases"
    __table_args__ = (
        CheckConstraint("source IN ('seed','manual')", name="ck_skill_aliases_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    canonical_skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE")
    )
    # Unik global: satu alias hanya boleh menunjuk satu skill kanon.
    alias: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(10), default="seed")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CandidateSkill(Base):
    __tablename__ = "candidate_skills"
    __table_args__ = (
        # Satu baris per (kandidat, skill kanon) — update status/confidence menimpa.
        UniqueConstraint("candidate_user_id", "canonical_skill_id"),
        CheckConstraint(
            "extraction_method IN ('explicit','inferred','manual')",
            name="ck_candidate_skills_extraction_method",
        ),
        CheckConstraint(
            "status IN ('suggested','accepted','rejected')",
            name="ck_candidate_skills_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # RESTRICT: skill kanon yang sudah terpakai tidak boleh terhapus diam-diam.
    canonical_skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="RESTRICT")
    )
    # Traceability: CV sumber bisa terhapus (SET NULL) tanpa menghapus skill.
    source_cv_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cvs.id", ondelete="SET NULL")
    )
    raw_name: Mapped[str] = mapped_column(String(160))
    confidence: Mapped[float] = mapped_column(Float)
    evidence: Mapped[str | None] = mapped_column(Text)
    source_section: Mapped[str | None] = mapped_column(String(30))
    extraction_method: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="suggested")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class JobSkill(Base):
    __tablename__ = "job_skills"
    __table_args__ = (
        # Satu baris per (lowongan, skill kanon).
        UniqueConstraint("job_id", "canonical_skill_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    canonical_skill_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="RESTRICT")
    )
    raw_name: Mapped[str] = mapped_column(String(160))
    required: Mapped[bool] = mapped_column(default=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
