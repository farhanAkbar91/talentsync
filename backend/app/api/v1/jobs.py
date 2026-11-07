"""Katalog publik lowongan (kandidat / tanpa auth untuk pencarian).

M4/M5: endpoint kecocokan (compatibility) & skill gap untuk kandidat — RBAC
peran candidate (pola sama dengan cvs.py); HR/roles lain → 403.
M9: POST /jobs/{id}/apply — kandidat melamar lowongan aktif (daftar lamaran
dan endpoint HR ada di router applications.py).
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.db.session import get_db
from app.models.user import User
from app.schemas.application import ApplicationCreateIn, ApplicationOut
from app.schemas.common import Page
from app.schemas.job import JobCompatibilityOut, JobGapOut, JobPublicOut
from app.services import application_service, job_service, match_service

router = APIRouter(prefix="/jobs", tags=["jobs"])
candidate_dependency = require_roles("candidate")


def _to_public(job) -> JobPublicOut:
    return JobPublicOut(
        id=job.id,
        title=job.title,
        company=job.company,
        description=job.description,
        responsibilities=job.responsibilities,
        requirements=job.requirements,
        skills=job.skills or [],
        category=job.category,
        employment_type=job.employment_type,
        work_mode=job.work_mode,
        seniority=job.seniority,
        location_text=job.location_text,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        posted_at=job.posted_at,
        closing_at=job.closing_at,
        source_type=job.source_type,
        source_url=job.source_url,
    )


@router.get("", response_model=Page[JobPublicOut])
def list_jobs(
    q: str | None = Query(default=None, max_length=100, description="Cari berdasarkan judul"),
    location: str | None = Query(default=None, max_length=100),
    employment_type: str | None = Query(default=None),
    work_mode: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> Page[JobPublicOut]:
    rows, total = job_service.list_public_jobs(
        db,
        q=q,
        location=location,
        employment_type=employment_type,
        work_mode=work_mode,
        page=page,
        size=size,
    )
    return Page[JobPublicOut](
        items=[_to_public(job) for job in rows],
        total=total,
        page=page,
        size=size,
        pages=max(1, -(-total // size)),
    )


@router.get("/{job_id}", response_model=JobPublicOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)) -> JobPublicOut:
    return _to_public(job_service.get_public_job(db, job_id))


# --- Kompatibilitas & skill gap (M4/M5, kandidat) ---


@router.get("/{job_id}/compatibility", response_model=JobCompatibilityOut)
def get_job_compatibility(
    job_id: uuid.UUID,
    request: Request,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> JobCompatibilityOut:
    """Skor kecocokan CV primer kandidat vs lowongan aktif (400 MATCH_UNAVAILABLE
    bila CV utama belum terkonfirmasi; 404 bila lowongan nonaktif)."""
    result = match_service.compute_match(db, user, job_id, request.app.state.settings)
    return JobCompatibilityOut(**match_service.compatibility_payload(result))


@router.get("/{job_id}/gap", response_model=JobGapOut)
def get_job_gap(
    job_id: uuid.UUID,
    request: Request,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> JobGapOut:
    """Matriks gap skill + item + saran belajar (reuse compute_match — persist)."""
    return JobGapOut(**match_service.get_gap(db, user, job_id, request.app.state.settings))


# --- Lamar lowongan (M9, kandidat) ---


@router.post("/{job_id}/apply", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
def apply_to_job(
    job_id: uuid.UUID,
    payload: ApplicationCreateIn,
    request: Request,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> ApplicationOut:
    """Lamar lowongan aktif dengan CV primer terkonfirmasi.

    404 bila lowongan tidak aktif; 400 kode APPLICATION_UNAVAILABLE bila belum
    ada CV primer terkonfirmasi; 409 bila sudah pernah melamar lowongan ini."""
    application = application_service.apply_to_job(
        db, user, job_id, payload.cover_letter, request.app.state.settings
    )
    return ApplicationOut(
        id=application.id,
        job_id=application.job_id,
        status=application.status,
        cover_letter=application.cover_letter,
    )
