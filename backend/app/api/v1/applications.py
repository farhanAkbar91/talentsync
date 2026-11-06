"""Endpoint lamaran (M9): daftar milik kandidat, daftar pelamar & transisi
status milik HR.

Router terpisah dari /jobs & /me agar tidak menabrak route {job_id} — kontrak
jalur FROZEN wave ini: /applications/mine (kandidat),
/applications/job/{job_id} (HR pemilik), /applications/{id}/status (HR pemilik).
"""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.db.session import get_db
from app.models.user import User
from app.schemas.application import (
    ApplicationHrItemOut,
    ApplicationMineItemOut,
    ApplicationStatusIn,
    ApplicationStatusOut,
)
from app.services import application_service

router = APIRouter(prefix="/applications", tags=["applications"])
candidate_dependency = require_roles("candidate")
hr_dependency = require_roles("hr")


@router.get("/mine", response_model=list[ApplicationMineItemOut])
def list_my_applications(
    user: User = Depends(candidate_dependency), db: Session = Depends(get_db)
) -> list[ApplicationMineItemOut]:
    """Semua lamaran kandidat, terbaru dulu, + info lowongan untuk tampilan."""
    rows = application_service.list_my_applications(db, user)
    return [
        ApplicationMineItemOut(
            id=application.id,
            job_id=job.id,
            status=application.status,
            cover_letter=application.cover_letter,
            cv_id=application.cv_id,
            job_title=job.title,
            company=job.company.name if job.company is not None else None,
            job_status=job.status,
            location=job.location_text,
            created_at=application.created_at,
        )
        for application, job in rows
    ]


@router.get("/job/{job_id}", response_model=list[ApplicationHrItemOut])
def list_job_applications(
    job_id: uuid.UUID,
    user: User = Depends(hr_dependency),
    db: Session = Depends(get_db),
) -> list[ApplicationHrItemOut]:
    """Pelamar satu lowongan milik perusahaan HR (404 bila milik perusahaan
    lain), terbaru dulu — termasuk info CV yang dipakai saat melamar."""
    rows = application_service.list_job_applications(db, user, job_id)
    return [
        ApplicationHrItemOut(
            id=application.id,
            job_id=application.job_id,
            status=application.status,
            cover_letter=application.cover_letter,
            candidate_user_id=candidate.id,
            cv_id=application.cv_id,
            updated_at=application.updated_at,
            candidate_name=candidate.full_name,
            cv_filename=cv.original_filename if cv is not None else None,
            cv_confirmed=(
                cv is not None
                and cv.extraction is not None
                and cv.extraction.confirmed_at is not None
            ),
            created_at=application.created_at,
        )
        for application, cv, candidate in rows
    ]


@router.patch("/{application_id}/status", response_model=ApplicationStatusOut)
def update_application_status(
    application_id: uuid.UUID,
    payload: ApplicationStatusIn,
    user: User = Depends(hr_dependency),
    db: Session = Depends(get_db),
) -> ApplicationStatusOut:
    """HR mengubah status lamaran milik perusahaannya. hired/rejected terminal
    (409 bila diubah lagi); 404 bila lamaran bukan milik perusahaannya."""
    application = application_service.update_status(db, user, application_id, payload.status)
    return ApplicationStatusOut(
        id=application.id,
        job_id=application.job_id,
        status=application.status,
        cover_letter=application.cover_letter,
        candidate_user_id=application.candidate_user_id,
        cv_id=application.cv_id,
        updated_at=application.updated_at,
    )


@router.get("/{application_id}/cv")
def download_applicant_cv(
    application_id: uuid.UUID,
    user: User = Depends(hr_dependency),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Unduh CV pelamar — khusus HR pemilik lowongan (alur rekrutmen)."""
    path, original_name = application_service.get_applicant_cv_file(db, user, application_id)
    return FileResponse(path, media_type="application/pdf", filename=original_name)
