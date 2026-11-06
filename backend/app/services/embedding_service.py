"""Service embedding (M3): vektor CV terkonfirmasi & lowongan → cv/job_embeddings.

Aturan main:
- Hanya CV dengan ekstraksi TERKONFIRMASI (confirmed_at terisi, payload ada)
  yang di-embed — hard gate, hasil review kandidat adalah sumber kebenaran.
- Upsert per (dokumen, model, text_kind): baris lama untuk kunci yang sama
  dihapus dulu, baris baru disisipkan. Baris model LAMA tidak pernah dihapus
  (retensi multi-versi — roll-back model bisa membandingkan skor antar versi).
- Upsert berjalan di dalam SAVEPOINT (`begin_nested`): bila gagal, hanya
  bagian embedding yang dibatalkan — transaksi luar (skills/confirm/publish)
  tetap sehat dan commit normal oleh pemanggil.
- Embedder di-inject lewat `embedder_factory` (default `get_embedder`,
  singleton malas per proses) agar test bisa memakai embedder palsu murah.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.matching.embedder import TextEmbedder, build_cv_text, build_job_text, get_embedder
from app.core.config import Settings
from app.models.ai import CvEmbedding, JobEmbedding
from app.models.cv import CV, CvExtraction
from app.models.job import Job

logger = logging.getLogger(__name__)

TEXT_KIND_CV = "profile"
TEXT_KIND_JOB = "job"

# Status lowongan yang layak di-embed oleh re-embed massal (draft/closed tidak).
REEMBED_JOB_STATUSES = ("active", "paused")


def _encode_text(text: str, settings: Settings, embedder_factory) -> list[float]:
    """Encode satu teks via embedder (factory injektable → singleton di prod)."""
    factory: Callable[[str], TextEmbedder] = embedder_factory or get_embedder
    embedder = factory(settings.embedding_model)
    vectors = embedder.encode([text])
    if not vectors:  # defensif: chunk_text tidak pernah kosong, tapi jaga kontrak
        raise ValueError("Embedder mengembalikan vektor kosong.")
    return vectors[0]


def _upsert_embedding(
    db: Session,
    model_cls: type[CvEmbedding] | type[JobEmbedding],
    doc_field: str,
    doc_id: uuid.UUID,
    model: str,
    text_kind: str,
    vector: list[float],
) -> bool:
    """Upsert satu baris embedding (delete-then-insert) di dalam SAVEPOINT.

    Mengembalikan True bila upsert berhasil (pemanggil lalu commit). Bila
    gagal: log warning + False — transaksi luar TIDAK tercemar.
    """
    try:
        with db.begin_nested():
            # Hapus baris kunci yang sama dulu, flush agar urutan DELETE
            # mendahului INSERT (UNIQUE constraint), baru sisipkan baris baru.
            existing = db.scalars(
                select(model_cls)
                .where(getattr(model_cls, doc_field) == doc_id)
                .where(model_cls.model == model)
                .where(model_cls.text_kind == text_kind)
            ).all()
            for row in existing:
                db.delete(row)
            db.flush()
            db.add(
                model_cls(
                    **{
                        doc_field: doc_id,
                        "model": model,
                        "text_kind": text_kind,
                        "embedding": vector,
                    }
                )
            )
    except Exception:
        logger.warning(
            "Upsert embedding %s (%s) gagal — dilewati, transaksi utama tetap lanjut.",
            model_cls.__tablename__,
            doc_id,
            exc_info=True,
        )
        return False
    return True


def embed_cv(
    db: Session,
    cv_id: uuid.UUID,
    settings: Settings,
    *,
    embedder_factory: Callable[[str], TextEmbedder] | None = None,
) -> None:
    """Embed CV terkonfirmasi → CvEmbedding (model & text_kind 'profile').

    Skip senyap bila: embeddings_enabled mati, CV dihapus/tidak ada, atau
    ekstraksi belum dikonfirmasi / payload kosong (hard gate M3).
    """
    if not settings.embeddings_enabled:
        return
    cv = db.get(CV, cv_id)
    if cv is None or cv.deleted_at is not None:
        return
    extraction = cv.extraction
    if extraction is None or extraction.payload is None or extraction.confirmed_at is None:
        return

    text = build_cv_text(extraction.payload)
    vector = _encode_text(text, settings, embedder_factory)
    if _upsert_embedding(
        db, CvEmbedding, "cv_id", cv_id, settings.embedding_model, TEXT_KIND_CV, vector
    ):
        # Commit di sini = commit transaksi yang sama dengan hook pemanggil
        # (skills + konfirmasi + embedding ter-commit atomik sekali).
        db.commit()


def embed_job(
    db: Session,
    job_id: uuid.UUID,
    settings: Settings,
    *,
    embedder_factory: Callable[[str], TextEmbedder] | None = None,
) -> None:
    """Embed lowongan → JobEmbedding (model & text_kind 'job').

    Dipanggil hook publish & update lowongan; skip senyap bila fitur mati
    atau lowongan tidak ada / sudah dihapus (soft delete).
    """
    if not settings.embeddings_enabled:
        return
    job = db.get(Job, job_id)
    if job is None or job.deleted_at is not None:
        return

    text = build_job_text(
        title=job.title,
        skill_names=[s["name"] for s in job.skills],
        description=job.description,
        requirements=job.requirements,
        responsibilities=job.responsibilities,
    )
    vector = _encode_text(text, settings, embedder_factory)
    if _upsert_embedding(
        db, JobEmbedding, "job_id", job_id, settings.embedding_model, TEXT_KIND_JOB, vector
    ):
        db.commit()


def reembed_all(
    db_factory: Callable[[], Session],
    settings: Settings,
    *,
    force: bool = False,
) -> dict[str, int]:
    """Re-embed SELURUH CV terkonfirmasi + lowongan aktif/paused non-deleted
    terhadap `settings.embedding_model` (untuk swap model / refresh vektor).

    - `force=True`: bypass guard `embeddings_enabled` (mis. batch offline saat
      fitur realtime dimatikan). Default: mengikuti guard standar.
    - Mengembalikan rekap hitungan; baris model lain tidak pernah disentuh.
    """
    effective = settings
    if force and not settings.embeddings_enabled:
        effective = settings.model_copy(update={"embeddings_enabled": True})

    summary = {
        "cvs_eligible": 0,
        "cvs_embedded": 0,
        "jobs_eligible": 0,
        "jobs_embedded": 0,
        "errors": 0,
    }
    with db_factory() as db:
        # CV layak: tidak dihapus + ekstraksi terkonfirmasi dengan payload ada.
        cv_ids = db.scalars(
            select(CV.id)
            .join(CvExtraction, CvExtraction.cv_id == CV.id)
            .where(CV.deleted_at.is_(None))
            .where(CvExtraction.confirmed_at.is_not(None))
            .where(CvExtraction.payload.is_not(None))
        ).all()
        summary["cvs_eligible"] = len(cv_ids)
        for cv_id in cv_ids:
            try:
                embed_cv(db, cv_id, effective)
            except Exception:
                db.rollback()
                summary["errors"] += 1
                logger.warning("Re-embed CV %s gagal.", cv_id, exc_info=True)

        # Lowongan layak: aktif/paused dan tidak dihapus.
        job_ids = db.scalars(
            select(Job.id)
            .where(Job.deleted_at.is_(None))
            .where(Job.status.in_(REEMBED_JOB_STATUSES))
        ).all()
        summary["jobs_eligible"] = len(job_ids)
        for job_id in job_ids:
            try:
                embed_job(db, job_id, effective)
            except Exception:
                db.rollback()
                summary["errors"] += 1
                logger.warning("Re-embed lowongan %s gagal.", job_id, exc_info=True)

        # Hitung baris yang benar-benar membawa vektor model aktif (embed_cv/
        # embed_job boleh saja skip senyap — hitungan "embedded" harus jujur).
        summary["cvs_embedded"] = (
            db.scalar(
                select(func.count())
                .select_from(CvEmbedding)
                .where(
                    # in_([]) aman: SQLAlchemy 2.0 menghasilkan kondisi selalu-false.
                    CvEmbedding.cv_id.in_(cv_ids),
                    CvEmbedding.model == effective.embedding_model,
                    CvEmbedding.text_kind == TEXT_KIND_CV,
                )
            )
            or 0
        )
        summary["jobs_embedded"] = (
            db.scalar(
                select(func.count())
                .select_from(JobEmbedding)
                .where(
                    JobEmbedding.job_id.in_(job_ids),
                    JobEmbedding.model == effective.embedding_model,
                    JobEmbedding.text_kind == TEXT_KIND_JOB,
                )
            )
            or 0
        )
    return summary
