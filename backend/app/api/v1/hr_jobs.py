"""Endpoint HR: kelola lowongan milik perusahaannya (RBAC: role 'hr')."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import Page
from app.schemas.job import JobHrOut, JobIn
from app.services import job_service

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


@router.get("/{job_id}", response_model=JobHrOut)
def get_job(
    job_id: uuid.UUID, user: User = Depends(hr_dependency), db: Session = Depends(get_db)
) -> JobHrOut:
    return _to_hr_out(job_service.get_job_for_company(db, user, job_id))


@router.put("/{job_id}", response_model=JobHrOut)
def update_job(
    job_id: uuid.UUID,
    payload: JobIn,
    user: User = Depends(hr_dependency),
    db: Session = Depends(get_db),
) -> JobHrOut:
    return _to_hr_out(job_service.update_job(db, user, job_id, payload))


@router.post("/{job_id}/publish", response_model=JobHrOut)
def publish_job(
    job_id: uuid.UUID, user: User = Depends(hr_dependency), db: Session = Depends(get_db)
) -> JobHrOut:
    return _to_hr_out(job_service.transition_job(db, user, job_id, "publish"))


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
