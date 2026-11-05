"""Model AI engine (P3.0): embedding, hasil matching, dan optimasi CV.

- `cv_embeddings` / `job_embeddings` menyimpan vektor 384 dimensi (pgvector)
  untuk pencarian similarity; satu baris per (dokumen, model, text_kind) dan
  re-embed menimpa baris lama. Pencarian di MVP memakai sequential scan yang
  disengaja — index vektor (HNSW/IVFFlat) ditambahkan bila skala menuntut.
- `match_results` menyimpan skor matching + evidence sebagai dasar transparansi
  skor di UI ("mengapa CV ini cocok").
- `cv_optimizations` menyimpan riwayat generasi saran perbaikan CV per lowongan
  beserta keputusan HR atas tiap saran.
"""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
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

# pgvector 384 dimensi di PostgreSQL; varian JSON untuk test suite di SQLite.
EmbeddingVector: Any = Vector(384).with_variant(JSON(), "sqlite")

CV_OPTIMIZATION_STATUSES = ("generating", "completed", "failed", "applied")


class CvEmbedding(Base):
    __tablename__ = "cv_embeddings"
    __table_args__ = (
        # Satu embedding per (cv, model, text_kind) — re-embed menimpa baris lama.
        UniqueConstraint("cv_id", "model", "text_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cv_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cvs.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(120))
    text_kind: Mapped[str] = mapped_column(String(30))
    embedding: Mapped[list[float]] = mapped_column(EmbeddingVector)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class JobEmbedding(Base):
    __tablename__ = "job_embeddings"
    __table_args__ = (
        # Satu embedding per (job, model, text_kind) — re-embed menimpa baris lama.
        UniqueConstraint("job_id", "model", "text_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(120))
    text_kind: Mapped[str] = mapped_column(String(30))
    embedding: Mapped[list[float]] = mapped_column(EmbeddingVector)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MatchResult(Base):
    __tablename__ = "match_results"
    __table_args__ = (
        # Satu hasil match per (cv, job, model_version) — versi baru menimpa skor lama.
        UniqueConstraint("cv_id", "job_id", "model_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cv_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cvs.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    overall: Mapped[float] = mapped_column(Float)
    # factors: {"skills": 0.83, "experience": 0.71, ...}; matched/missing: daftar skill.
    factors: Mapped[dict[str, Any]] = mapped_column(JSONVariant)
    matched_skills: Mapped[list[Any]] = mapped_column(JSONVariant)
    missing_skills: Mapped[list[Any]] = mapped_column(JSONVariant)
    evidence: Mapped[list[Any] | None] = mapped_column(JSONVariant)
    top_experiences: Mapped[list[Any] | None] = mapped_column(JSONVariant)
    explanation: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(60))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CvOptimization(Base):
    __tablename__ = "cv_optimizations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('generating','completed','failed','applied')",
            name="ck_cv_optimizations_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    cv_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cvs.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="generating")
    suggestions: Mapped[list[Any] | None] = mapped_column(JSONVariant)
    # Keputusan HR per saran: {"<suggestion_id>": {"accepted": bool, "note": str}}.
    decisions: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant)
    grounding_report: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant)
    llm_provider: Mapped[str | None] = mapped_column(String(40))
    llm_model: Mapped[str | None] = mapped_column(String(80))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(Text)
    # CV hasil terapkan (versi baru); SET NULL agar riwayat optimasi tetap ada
    # meski CV turunannya dihapus.
    applied_cv_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cvs.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
