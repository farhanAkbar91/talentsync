"""Service hasil ekstraksi CV: baca & konfirmasi (review kandidat, M1).

Kepemilikan memakai aturan yang sama dengan cv_service._owned_cv — akses oleh
non-pemilik / CV milik orang lain → 404 (jangan bocorkan keberadaan resource).
"""

import logging
import uuid
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.extraction.payload_schema import PAYLOAD_PARSER_VERSION, ExtractionPayload
from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.cv import CvExtraction
from app.models.user import User
from app.services import cv_service, embedding_service

logger = logging.getLogger(__name__)


def get_extraction(db: Session, user: User, cv_id: uuid.UUID) -> CvExtraction:
    """Ambil baris ekstraksi milik CV kandidat peminta; CV bukan miliknya,
    tidak ada, atau baris ekstraksi hilang → NotFoundError (404)."""
    cv = cv_service._owned_cv(db, user, cv_id)
    extraction = cv.extraction
    if extraction is None:
        raise NotFoundError("Hasil ekstraksi tidak ditemukan.")
    return extraction


def confirm_extraction(
    db: Session,
    user: User,
    cv_id: uuid.UUID,
    payload: dict | None = None,
    *,
    settings: Settings | None = None,
) -> CvExtraction:
    """Konfirmasi hasil ekstraksi (boleh berulang — timestamp & payload ikut
    diperbarui). Bila `payload` disertakan, kandidat menyunting hasil review:
    simpan setelah validasi skema; parser_version dipaksa kembali ke versi
    parser heuristik agar jejak asal data tidak tertukar.

    `settings` (opsional, dari endpoint) mengaktifkan hook embedding M3."""
    extraction = get_extraction(db, user, cv_id)
    if extraction.status != "done":
        raise ConflictError("Ekstraksi belum siap dikonfirmasi.")

    if payload is not None:
        try:
            validated = ExtractionPayload.model_validate(payload)
        except ValidationError as exc:
            raise BadRequestError("Payload ekstraksi tidak valid.") from exc
        extraction.payload = validated.to_dict()
        extraction.parser_version = PAYLOAD_PARSER_VERSION

    # M2 (Wave 2B): normalisasi + persist skill kandidat dari payload — berjalan
    # untuk kedua jalur (payload dikoreksi maupun konfirmasi apa adanya) dan ikut
    # commit tunggal di bawah (atomisitas M1 terjaga). Import lokal untuk memutus
    # siklus impor antar service (skill_service memakai cv_service).
    from app.services import skill_service  # noqa: PLC0415 — patah siklus impor

    skill_service.persist_cv_skills(db, user, extraction.cv_id, extraction)

    extraction.confirmed_at = datetime.now(UTC)
    extraction.confirmed_by = user.id

    # M4: payload/skill CV berubah — hasil match lama tidak valid lagi. Import
    # lokal memutus siklus impor (match_service tidak mengimpor service ini).
    from app.services import match_service  # noqa: PLC0415 — patah siklus impor

    match_service.invalidate_cv(db, extraction.cv_id)

    # M3: CV terkonfirmasi langsung di-embedding (vektor profil). Guard ganda:
    # hanya bila settings tersedia & fitur aktif; kegagalan embedding tidak
    # boleh membatalkan konfirmasi — log warning, konfirmasi tetap commit.
    if settings is not None:
        try:
            embedding_service.embed_cv(db, extraction.cv_id, settings)
        except Exception:
            logger.warning("Embedding CV %s gagal — dilewati.", cv_id, exc_info=True)

    db.commit()
    db.refresh(extraction)
    return extraction
