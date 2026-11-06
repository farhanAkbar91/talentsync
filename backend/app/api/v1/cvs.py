"""Endpoint CV kandidat: upload aman, daftar, primary, unduh, soft delete,
serta baca & konfirmasi hasil ekstraksi (M1)."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, sessionmaker

from app.core.deps import require_roles
from app.db.session import get_db, get_session_factory
from app.models.cv import CvExtraction
from app.models.user import User
from app.schemas.cv import CVOut, DiagnosisOut, ExtractionConfirmIn, ExtractionOut
from app.schemas.skill import (
    CandidateSkillItemOut,
    CandidateSkillListOut,
    SkillApplyIn,
    SkillApplyOut,
)
from app.services import cv_service, diagnosis_service, extraction_service, skill_service

router = APIRouter(prefix="/cvs", tags=["cvs"])
candidate_dependency = require_roles("candidate")


@router.post("", response_model=CVOut, status_code=status.HTTP_201_CREATED)
def upload_cv(
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> CVOut:
    settings = request.app.state.settings
    cv = cv_service.upload_cv(db, user, file, settings)
    # Ekstraksi dasar berjalan di luar siklus request (session baru, tugas terpisah).
    background_tasks.add_task(cv_service.run_extraction, session_factory, cv.id, settings)
    return _to_out(cv)


def _to_out(cv) -> CVOut:
    return CVOut(
        id=cv.id,
        status=cv.status,
        original_filename=cv.original_filename,
        file_size_bytes=cv.file_size_bytes,
        content_sha256=cv.content_sha256,
        is_primary=cv.is_primary,
        version=cv.version,
        page_count=cv.extraction.page_count if cv.extraction else None,
        extraction_status=cv.extraction.status if cv.extraction else None,
        extraction_confirmed=cv.extraction.is_confirmed if cv.extraction else None,
        created_at=cv.created_at,
        updated_at=cv.updated_at,
    )


@router.get("", response_model=list[CVOut])
def list_cvs(
    user: User = Depends(candidate_dependency), db: Session = Depends(get_db)
) -> list[CVOut]:
    return [_to_out(cv) for cv in cv_service.list_cvs(db, user)]


@router.get("/{cv_id}/extraction", response_model=ExtractionOut)
def get_cv_extraction(
    cv_id: uuid.UUID,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> ExtractionOut:
    extraction = extraction_service.get_extraction(db, user, cv_id)
    return _extraction_to_out(cv_id, extraction)


@router.put("/{cv_id}/extraction/confirm", response_model=ExtractionOut)
def confirm_cv_extraction(
    cv_id: uuid.UUID,
    request: Request,
    body: ExtractionConfirmIn | None = None,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> ExtractionOut:
    payload = body.payload if body is not None else None
    extraction = extraction_service.confirm_extraction(
        db, user, cv_id, payload, settings=request.app.state.settings
    )
    return _extraction_to_out(cv_id, extraction)


def _extraction_to_out(cv_id: uuid.UUID, extraction: CvExtraction) -> ExtractionOut:
    return ExtractionOut(
        cv_id=cv_id,
        status=extraction.status,
        parser_version=extraction.parser_version,
        payload=extraction.payload,
        confirmed_at=extraction.confirmed_at,
        confirmed_by=extraction.confirmed_by,
    )


@router.patch("/{cv_id}/primary", response_model=CVOut)
def set_primary(
    cv_id: uuid.UUID,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> CVOut:
    return _to_out(cv_service.set_primary(db, user, cv_id))


# --- Skill kandidat per CV (M2 Wave 2B) ---


@router.get("/{cv_id}/skills", response_model=CandidateSkillListOut)
def list_cv_skills(
    cv_id: uuid.UUID,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> CandidateSkillListOut:
    """Skill hasil ekstraksi CV ini + skill accepted dari CV lain yang belum
    terwakili (status accepted pada item = "Sudah diterapkan" di UI)."""
    rows = skill_service.get_cv_skills(db, user, cv_id)
    raw_items = skill_service.build_skill_items(db, rows)
    items = [CandidateSkillItemOut.model_validate(i) for i in raw_items]
    return CandidateSkillListOut(items=items, total=len(items))


@router.post("/{cv_id}/skills/apply", response_model=SkillApplyOut)
def apply_cv_skills(
    cv_id: uuid.UUID,
    body: SkillApplyIn,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> SkillApplyOut:
    """Terima saran skill: suggested -> accepted + merge ke profil kandidat."""
    applied = skill_service.apply_skills_to_profile(db, user, cv_id, body.skill_ids)
    return SkillApplyOut(applied=applied)


@router.get("/{cv_id}/file")
def download_cv(
    cv_id: uuid.UUID,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> FileResponse:
    path, original_name = cv_service.get_cv_file(db, user, cv_id)
    return FileResponse(path, media_type="application/pdf", filename=original_name)


@router.delete("/{cv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cv(
    cv_id: uuid.UUID,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> None:
    cv_service.soft_delete_cv(db, user, cv_id)


# --- Diagnosis CV (M7 Wave 4, deterministik tanpa LLM) ---


@router.get("/{cv_id}/diagnosis", response_model=DiagnosisOut)
def get_cv_diagnosis(
    cv_id: uuid.UUID,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> DiagnosisOut:
    """Panduan kualitas CV (skor, label, kekuatan, perbaikan) dari aturan beku —
    informatif pra-konfirmasi di halaman review; 409 bila ekstraksi belum done."""
    return DiagnosisOut.model_validate(diagnosis_service.get_diagnosis(db, user, cv_id))
