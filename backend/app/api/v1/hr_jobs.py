"""Endpoint HR: kelola lowongan milik perusahaannya (RBAC: role 'hr').

M9: ranking pelamar & perbandingan dua pelamar (skor dibangun dari blok yang
sama dengan match_service, dipersist ke match_results)."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.exceptions import BadRequestError
from app.db.session import get_db
from app.models.skill import CanonicalSkill, JobSkill
from app.models.user import User
from app.schemas.common import Page
from app.schemas.job import (
    ApplicantCompareOut,
    ApplicantRankingItemOut,
    JobHrOut,
    JobIn,
    JobRankingOut,
    NormalizedJobSkill,
    NormalizedJobSkillCanonical,
)
from app.services import application_service, job_service, match_service, skill_service

router = APIRouter(prefix="/hr/jobs", tags=["hr-jobs"])
hr_dependency = require_roles("hr")


def _to_hr_out(job) -> JobHrOut:
    return JobHrOut(
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
        status=job.status,
        closed_reason=job.closed_reason,
        created_at=job.created_at,
        updated_at=job.updated_at,
        deleted_at=job.deleted_at,
    )


@router.get("/stats")
def job_stats(user: User = Depends(hr_dependency), db: Session = Depends(get_db)) -> dict:
    return job_service.company_job_stats(db, user)


@router.get("", response_model=Page[JobHrOut])
def list_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=50),
    user: User = Depends(hr_dependency),
    db: Session = Depends(get_db),
) -> Page[JobHrOut]:
    rows, total = job_service.list_company_jobs(
        db, user, status=status_filter, page=page, size=size
    )
    return Page[JobHrOut](
        items=[_to_hr_out(job) for job in rows],
        total=total,
        page=page,
        size=size,
        pages=max(1, -(-total // size)),
    )


@router.post("", response_model=JobHrOut, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobIn, user: User = Depends(hr_dependency), db: Session = Depends(get_db)
) -> JobHrOut:
    return _to_hr_out(job_service.create_job(db, user, payload))


def _load_skills_normalized(db: Session, job) -> list[NormalizedJobSkill]:
    """Baris job_skills lowongan + nama kanonnya (None-safe saat belum ada baris).
    Nama mentah tanpa padanan kanon tidak pernah menjadi baris — ia tetap tampil
    di `skills` (JSONB). needs_review diangkat untuk baris ber-confidence rendah
    (fuzzy 0.8) atau tanpa confidence."""
    rows = db.execute(
        select(JobSkill, CanonicalSkill)
        .join(CanonicalSkill, JobSkill.canonical_skill_id == CanonicalSkill.id)
        .where(JobSkill.job_id == job.id)
        .order_by(JobSkill.created_at)
    ).all()
    items: list[NormalizedJobSkill] = []
    for job_skill, canon in rows:
        confidence = float(job_skill.confidence) if job_skill.confidence is not None else None
        items.append(
            NormalizedJobSkill(
                canonical=NormalizedJobSkillCanonical(
                    slug=canon.slug, name=canon.name, category=canon.category
                ),
                raw_name=job_skill.raw_name,
                required=job_skill.required,
                confidence=confidence,
                needs_review=(
                    confidence is None or confidence < skill_service.REVIEW_REDERIVE_BELOW
                ),
            )
        )
    return items


@router.get("/{job_id}", response_model=JobHrOut)
def get_job(
    job_id: uuid.UUID, user: User = Depends(hr_dependency), db: Session = Depends(get_db)
) -> JobHrOut:
    job = job_service.get_job_for_company(db, user, job_id)
    out = _to_hr_out(job)
    out.skills_normalized = _load_skills_normalized(db, job)
    return out


@router.put("/{job_id}", response_model=JobHrOut)
def update_job(
    job_id: uuid.UUID,
    payload: JobIn,
    request: Request,
    user: User = Depends(hr_dependency),
    db: Session = Depends(get_db),
) -> JobHrOut:
    return _to_hr_out(
        job_service.update_job(db, user, job_id, payload, settings=request.app.state.settings)
    )


@router.post("/{job_id}/publish", response_model=JobHrOut)
def publish_job(
    job_id: uuid.UUID,
    request: Request,
    user: User = Depends(hr_dependency),
    db: Session = Depends(get_db),
) -> JobHrOut:
    return _to_hr_out(
        job_service.transition_job(db, user, job_id, "publish", settings=request.app.state.settings)
    )


@router.post("/{job_id}/pause", response_model=JobHrOut)
def pause_job(
    job_id: uuid.UUID, user: User = Depends(hr_dependency), db: Session = Depends(get_db)
) -> JobHrOut:
    return _to_hr_out(job_service.transition_job(db, user, job_id, "pause"))


@router.post("/{job_id}/resume", response_model=JobHrOut)
def resume_job(
    job_id: uuid.UUID, user: User = Depends(hr_dependency), db: Session = Depends(get_db)
) -> JobHrOut:
    return _to_hr_out(job_service.transition_job(db, user, job_id, "resume"))


@router.post("/{job_id}/close", response_model=JobHrOut)
def close_job(
    job_id: uuid.UUID, user: User = Depends(hr_dependency), db: Session = Depends(get_db)
) -> JobHrOut:
    return _to_hr_out(job_service.transition_job(db, user, job_id, "close"))


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_job(
    job_id: uuid.UUID, user: User = Depends(hr_dependency), db: Session = Depends(get_db)
) -> None:
    job_service.archive_job(db, user, job_id)


# --- Ranking & perbandingan pelamar (M9) ---


@router.get("/{job_id}/ranking", response_model=JobRankingOut)
def job_ranking(
    job_id: uuid.UUID,
    request: Request,
    user: User = Depends(hr_dependency),
    db: Session = Depends(get_db),
) -> JobRankingOut:
    """Ranking pelamar lowongan milik perusahaan HR (404 bila bukan).

    Item urut overall DESC; pelamar dengan CV lamaran belum terkonfirmasi
    (overall None + reason) selalu paling akhir. Skor dipersist ke match_results
    per (cv_id, job_id, model_version) — konsumen M9 dari match_results."""
    settings = request.app.state.settings
    items = application_service.rank_job_applicants(db, user, job_id, settings)
    return JobRankingOut(
        job_id=job_id,
        model_version=match_service.build_model_version(settings),
        computed_at=datetime.now(UTC),
        total=len(items),
        items=[ApplicantRankingItemOut(**item) for item in items],
    )


@router.get("/{job_id}/compare", response_model=ApplicantCompareOut)
def compare_job_applicants(
    job_id: uuid.UUID,
    request: Request,
    ids: str = Query(..., description="Dua id lamaran dipisah koma: ids=<a>,<b>"),
    user: User = Depends(hr_dependency),
    db: Session = Depends(get_db),
) -> ApplicantCompareOut:
    """Bandingkan dua pelamar lowongan milik perusahaan HR (side-by-side).

    `ids` wajib tepat 2 UUID berbeda yang keduanya lamaran lowongan ini —
    selain itu 400; lamaran tak ada / bukan milik lowongan ini → 404."""
    parts = [part.strip() for part in ids.split(",") if part.strip()]
    if len(parts) != 2:
        raise BadRequestError("Sertakan tepat dua id lamaran: ids=<a>,<b>.")
    try:
        id_a, id_b = (uuid.UUID(part) for part in parts)
    except ValueError as exc:
        raise BadRequestError("Parameter ids harus berisi dua UUID valid.") from exc

    result = application_service.compare_applicants(
        db, user, job_id, id_a, id_b, request.app.state.settings
    )
    return ApplicantCompareOut(**result)
