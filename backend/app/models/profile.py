"""Profil kandidat.

Data profil (skills, pendidikan, pengalaman, sertifikasi) disimpan sebagai
JSONB terstruktur dengan skema item yang tervalidasi di layer Pydantic —
cukup untuk MVP dan langsung reusable oleh matching engine di fase AI.
Normalisasi penuh ke tabel relasional dapat dilakukan belakangan tanpa
mengubah API (lihat ADR 0002).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# JSONB di PostgreSQL; varian JSON untuk test suite di SQLite (ADR 0002).
JSONVariant: Any = JSONB().with_variant(JSON(), "sqlite")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    phone: Mapped[str | None] = mapped_column(String(32))
    location: Mapped[str | None] = mapped_column(String(255))
    headline: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[Any]] = mapped_column(JSONVariant, default=list)
    education: Mapped[list[Any]] = mapped_column(JSONVariant, default=list)
    experience: Mapped[list[Any]] = mapped_column(JSONVariant, default=list)
    certifications: Mapped[list[Any]] = mapped_column(JSONVariant, default=list)
    # {"linkedin": "...", "github": "...", "portfolio": "..."}
    links: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="candidate_profile")  # noqa: F821
