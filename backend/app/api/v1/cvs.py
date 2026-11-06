"""Endpoint CV kandidat: upload aman, daftar, primary, unduh, soft delete,
baca & konfirmasi hasil ekstraksi (M1), diagnosis (M7), dan optimasi CV by LLM
(M8: generasi saran ter-grounding + penerapan versi baru)."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, sessionmaker

from app.core.deps import require_roles
from app.db.session import get_db, get_session_factory
from app.models.ai import CvOptimization
from app.models.cv import CvExtraction
from app.models.user import User
from app.schemas.cv import (
    CVOut,
    DiagnosisOut,
    ExtractionConfirmIn,
    ExtractionOut,
    OptimizationApplyIn,
    OptimizationApplyOut,
    OptimizationListOut,
    OptimizationOut,
    OptimizationStartIn,
    OptimizationStartOut,
)
from app.schemas.skill import (
    CandidateSkillItemOut,
    CandidateSkillListOut,
    SkillApplyIn,
    SkillApplyOut,
)
from app.services import (
    cv_service,
    diagnosis_service,
    extraction_service,
    optimization_service,
    skill_service,
)

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


# --- Optimasi CV by LLM (M8 Wave 5) ---


@router.post(
    "/{cv_id}/optimizations",
    response_model=OptimizationStartOut,
    status_code=status.HTTP_201_CREATED,
)
def start_cv_optimization(
    cv_id: uuid.UUID,
    body: OptimizationStartIn,
    background_tasks: BackgroundTasks,
    request: Request,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
) -> OptimizationStartOut:
    """Mulai generasi saran optimasi CV untuk satu lowongan aktif (M8).

    Baris 'generating' dibuat lalu panggilan Groq dijalankan sebagai background
    task (session baru, pola upload CV). Bila sudah ada hasil completed dengan
    prompt_version aktif, baris itu dikembalikan apa adanya (cached=true,
    tanpa panggilan LLM).
    """
    settings = request.app.state.settings
    opt = optimization_service.start_generation(
        db, user, cv_id, body.job_id, settings, regenerate=body.regenerate
    )
    # Cache kuota = satu-satunya jalur yang mengembalikan baris completed.
    cached = opt.status == "completed"
    if not cached:
        background_tasks.add_task(
            optimization_service.run_generation,
            session_factory,
            opt.id,
            cv_id,
            body.job_id,
            settings,
        )
    return OptimizationStartOut(
        id=opt.id,
        cv_id=opt.cv_id,
        job_id=opt.job_id,
        status=opt.status,
        cached=cached,
        model_version=opt.llm_model if cached else None,
        created_at=opt.created_at,
    )


@router.get("/{cv_id}/optimizations", response_model=OptimizationListOut)
def list_cv_optimizations(
    cv_id: uuid.UUID,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> OptimizationListOut:
    """Riwayat generasi saran optimasi CV ini, terbaru lebih dulu."""
    rows = optimization_service.list_optimizations(db, user, cv_id)
    items = [OptimizationOut.model_validate(row) for row in rows]
    return OptimizationListOut(items=items, total=len(items))


@router.get("/{cv_id}/optimizations/{opt_id}", response_model=OptimizationOut)
def get_cv_optimization(
    cv_id: uuid.UUID,
    opt_id: uuid.UUID,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> OptimizationOut:
    """Detail satu hasil optimasi: saran per edit + laporan grounding + status."""
    opt = optimization_service.get_optimization(db, user, cv_id, opt_id)
    return OptimizationOut.model_validate(opt)


@router.post(
    "/{cv_id}/optimizations/{opt_id}/apply",
    response_model=OptimizationApplyOut,
)
def apply_cv_optimization(
    cv_id: uuid.UUID,
    opt_id: uuid.UUID,
    body: OptimizationApplyIn,
    request: Request,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> OptimizationApplyOut:
    """Terapkan saran yang diterima → CV versi baru (parent turun sebagai primer).

    Body `decisions` memetakan suggestion_id → bool (True = diterima). Gerbang
    grounding dijalankan ulang di service (defense in depth) sebelum CV baru
    (PDF ReportLab + ekstraksi auto-confirm) dibuat.
    """
    new_cv = optimization_service.apply_optimization(
        db, user, cv_id, opt_id, body.decisions, request.app.state.settings
    )
    # Hitung exact dari keputusan yang tersimpan (bukan isi body mentah —
    # key tak dikenal pada body tidak dihitung).
    opt = db.get(CvOptimization, opt_id)
    applied = sum(
        1 for decision in (opt.decisions or {}).values() if decision.get("accepted") is True
    )
    return OptimizationApplyOut(new_cv_id=new_cv.id, applied=applied)
