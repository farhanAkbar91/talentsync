"""Katalog publik lowongan (kandidat / tanpa auth untuk pencarian)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import Page
from app.schemas.job import JobPublicOut
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


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
