"""Service diagnosis CV (M7): panduan kualitas deterministik tanpa LLM.

Diagnosis bersifat informatif — bekerja pada payload ekstraksi apa pun
terlepas dari status konfirmasi (panduan pra-konfirmasi di halaman review).
Kepemilikan memakai aturan yang sama dengan cv_service._owned_cv — akses oleh
non-pemilik → 404 (jangan bocorkan keberadaan resource).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ai.diagnosis.diagnosis import diagnose_payload
from app.core.exceptions import ConflictError, NotFoundError
from app.models.user import User
from app.services import cv_service

_CONFLICT_MESSAGE = "Ekstraksi belum selesai — diagnosis butuh payload."


def get_diagnosis(db: Session, user: User, cv_id: uuid.UUID) -> dict:
    """Diagnosis CV milik kandidat peminta — dict siap divalidasi DiagnosisOut.

    - CV tidak ada / bukan milik peminta / baris ekstraksi hilang → 404.
    - Ekstraksi belum `done` atau payload kosong → 409 (tidak ada yang dinilai).
    """
    cv = cv_service._owned_cv(db, user, cv_id)
    extraction = cv.extraction
    if extraction is None:
        raise NotFoundError("Hasil ekstraksi tidak ditemukan.")
    # Status bukan done ATAU payload None (mis. payload gagal dibangun saat
    # ekstraksi) → tidak ada payload untuk dinilai.
    if extraction.status != "done" or extraction.payload is None:
        raise ConflictError(_CONFLICT_MESSAGE)

    result = diagnose_payload(extraction.payload)
    result["cv_id"] = cv.id
    result["computed_at"] = _now_iso()
    return result


def _now_iso() -> str:
    """Waktu perhitungan diagnosis dalam ISO UTC."""
    return datetime.now(UTC).isoformat()
