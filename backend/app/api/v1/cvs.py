"""Endpoint CV kandidat: upload aman, daftar, primary, unduh, soft delete."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, sessionmaker

from app.core.deps import require_roles
from app.db.session import get_db, get_session_factory
from app.models.user import User
from app.schemas.cv import CVOut
from app.services import cv_service

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
        created_at=cv.created_at,
        updated_at=cv.updated_at,
    )


@router.get("", response_model=list[CVOut])
def list_cvs(
    user: User = Depends(candidate_dependency), db: Session = Depends(get_db)
) -> list[CVOut]:
    return [_to_out(cv) for cv in cv_service.list_cvs(db, user)]


@router.patch("/{cv_id}/primary", response_model=CVOut)
def set_primary(
    cv_id: uuid.UUID,
    user: User = Depends(candidate_dependency),
    db: Session = Depends(get_db),
) -> CVOut:
    return _to_out(cv_service.set_primary(db, user, cv_id))


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
