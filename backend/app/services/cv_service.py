"""Service CV: upload aman, metadata, primary, soft delete, ekstraksi dasar.

Keamanan file (blueprint §5.1–5.2):
- Validasi ekstensi + magic bytes %PDF + batas ukuran (streaming, bukan read all).
- Nama file acak (uuid) di dalam uploads_dir/cvs/{user_id}/ — di luar root statis.
- Akses file HANYA via endpoint berotorisasi; sha256 untuk dedupe per pemilik.
"""

import hashlib
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.ai.extraction.basic_pdf import PARSER_VERSION, PdfExtractionError, extract_text_from_pdf
from app.core.config import Settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
)
from app.models.cv import CV, CvExtraction
from app.models.user import User

CHUNK_SIZE = 1024 * 1024  # 1 MB
MAX_TEXT_CHARS = 200_000

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Buang karakter kontrol/pembatas header Content-Disposition (anti header
    injection) dan batasi panjang. Nama asli hanya metadata tampilan."""
    cleaned = "".join(ch for ch in name if ch.isprintable() and ch not in '"\\\r\n\t;')
    cleaned = cleaned.strip().strip("'")
    return cleaned[:120] or "cv.pdf"


def upload_cv(db: Session, user: User, file: UploadFile, settings: Settings) -> CV:
    filename = _sanitize_filename((file.filename or "").strip()) or "cv.pdf"
    if not filename.lower().endswith(".pdf"):
        raise BadRequestError("Hanya berkas PDF yang didukung.")
    if file.content_type and not file.content_type.lower().startswith("application/pdf"):
        raise BadRequestError("Tipe konten harus application/pdf.")

    # Baca streaming dengan batas keras (jangan memuat file raksasa ke memori).
    size = 0
    chunks: list[bytes] = []
    while True:
        chunk = file.file.read(CHUNK_SIZE)
        if not chunk:
            break
        size += len(chunk)
        if size > settings.max_cv_size_bytes:
            raise PayloadTooLargeError(
                f"Ukuran berkas melebihi batas {settings.max_cv_size_bytes // (1024 * 1024)} MB."
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise BadRequestError("Berkas kosong.")
    if not data.startswith(b"%PDF-"):
        raise BadRequestError("Berkas bukan PDF yang valid.")

    sha = hashlib.sha256(data).hexdigest()
    duplicate = db.scalar(
        select(CV).where(
            CV.candidate_user_id == user.id,
            CV.content_sha256 == sha,
            CV.deleted_at.is_(None),
        )
    )
    if duplicate is not None:
        raise ConflictError("CV dengan isi identik sudah pernah diunggah.")

    target_dir = Path(settings.uploads_dir) / "cvs" / str(user.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.pdf"
    file_path = target_dir / stored_name
    file_path.write_bytes(data)

    has_primary = (
        db.scalar(
            select(func.count())
            .select_from(CV)
            .where(
                CV.candidate_user_id == user.id,
                CV.deleted_at.is_(None),
                CV.is_primary.is_(True),
            )
        )
        or 0
    ) > 0

    cv = CV(
        candidate_user_id=user.id,
        status="pending",
        file_path=str(file_path),
        original_filename=filename,
        mime_type="application/pdf",
        file_size_bytes=len(data),
        content_sha256=sha,
        is_primary=not has_primary,
    )
    db.add(cv)
    db.flush()
    db.add(CvExtraction(cv_id=cv.id, status="pending", parser_version=PARSER_VERSION))
    try:
        db.commit()
    except IntegrityError as exc:
        # Race dedupe: partial unique index (owner + sha256, CV aktif) yang menolak.
        db.rollback()
        file_path.unlink(missing_ok=True)  # jangan tinggalkan file yatim
        raise ConflictError("CV dengan isi identik sudah pernah diunggah.") from exc
    db.refresh(cv)
    return cv


def run_extraction(
    session_factory: sessionmaker[Session], cv_id: uuid.UUID, settings: Settings
) -> None:
    """Background task: ekstraksi teks dasar. Tidak pernah melempar — status gagal
    terekam di database (blueprint: pipeline tidak boleh diam-diam gagal)."""
    with session_factory() as db:
        cv = db.get(CV, cv_id)
        if cv is None or cv.deleted_at is not None:
            return
        extraction = cv.extraction
        if extraction is None:
            extraction = CvExtraction(cv_id=cv.id, status="pending", parser_version=PARSER_VERSION)
            db.add(extraction)
            db.flush()

        cv.status = "processing"
        db.commit()
        try:
            pages, text = extract_text_from_pdf(cv.file_path, max_pages=settings.max_cv_pages)
            cv.status = "ready"
            extraction.status = "done"
            extraction.page_count = pages
            extraction.raw_text = text[:MAX_TEXT_CHARS]
            extraction.error_message = None
        except PdfExtractionError as exc:
            cv.status = "failed"
            extraction.status = "failed"
            extraction.error_message = str(exc)
            db.commit()
            return
        except Exception as exc:  # kegagalan tak terduga tetap terekam, tanpa crash worker
            cv.status = "failed"
            extraction.status = "failed"
            extraction.error_message = "Kegagalan ekstraksi tak terduga."
            db.commit()
            logger.warning("CV extraction unexpected failure cv=%s: %s", cv_id, exc)
            return
        db.commit()


def list_cvs(db: Session, user: User) -> list[CV]:
    return list(
        db.scalars(
            select(CV)
            .where(CV.candidate_user_id == user.id, CV.deleted_at.is_(None))
            .order_by(CV.created_at.desc())
        )
        .unique()
        .all()
    )


def _owned_cv(db: Session, user: User, cv_id: uuid.UUID) -> CV:
    cv = db.get(CV, cv_id)
    if cv is None or cv.deleted_at is not None or cv.candidate_user_id != user.id:
        raise NotFoundError("Dokumen CV tidak ditemukan.")
    return cv


def set_primary(db: Session, user: User, cv_id: uuid.UUID) -> CV:
    cv = _owned_cv(db, user, cv_id)
    if cv.status == "failed":
        raise ConflictError("CV yang gagal diproses tidak dapat dijadikan CV utama.")
    for other in list_cvs(db, user):
        if other.id != cv.id and other.is_primary:
            other.is_primary = False
    cv.is_primary = True
    db.commit()
    db.refresh(cv)
    return cv


def soft_delete_cv(db: Session, user: User, cv_id: uuid.UUID) -> None:
    cv = _owned_cv(db, user, cv_id)
    was_primary = cv.is_primary
    cv.deleted_at = datetime.now(UTC)
    cv.is_primary = False
    db.commit()
    if was_primary:
        remaining = list_cvs(db, user)
        if remaining:
            remaining[0].is_primary = True
            db.commit()


def get_cv_file(db: Session, user: User, cv_id: uuid.UUID) -> tuple[Path, str]:
    """Kembalikan (path, nama asli) — pemanggil mengirim sebagai FileResponse.
    Akses oleh non-pemilik → 404 (jangan bocorkan keberadaan)."""
    cv = _owned_cv(db, user, cv_id)
    return Path(cv.file_path), cv.original_filename
