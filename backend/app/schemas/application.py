"""Skema lamaran (M9): kandidat melamar, daftar milik kandidat, daftar pelamar
& transisi status milik HR."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Kontrak status lamaran (mirror CHECK di model/migrasi).
ApplicationStatusLiteral = Literal["submitted", "reviewed", "shortlisted", "rejected", "hired"]


class ApplicationCreateIn(BaseModel):
    """Body POST /jobs/{job_id}/apply — cover letter opsional."""

    cover_letter: str | None = Field(default=None, max_length=5000)


class ApplicationStatusIn(BaseModel):
    """Body PATCH /applications/{application_id}/status."""

    status: ApplicationStatusLiteral


class ApplicationOut(BaseModel):
    """Inti lamaran — respons POST /jobs/{job_id}/apply."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    job_id: uuid.UUID
    status: str
    cover_letter: str | None


class ApplicationMineItemOut(ApplicationOut):
    """Item GET /applications/mine — + info lowongan untuk tampilan."""

    cv_id: uuid.UUID | None
    job_title: str
    company: str | None
    job_status: str
    location: str | None
    created_at: datetime


class ApplicationStatusOut(ApplicationOut):
    """Respons PATCH /applications/{application_id}/status."""

    candidate_user_id: uuid.UUID
    cv_id: uuid.UUID | None
    updated_at: datetime


class ApplicationHrItemOut(ApplicationStatusOut):
    """Item daftar pelamar milik HR (GET /applications/job/{job_id}) — + nama
    kandidat & info CV yang dipakai saat melamar."""

    candidate_name: str
    cv_filename: str | None
    cv_confirmed: bool
    created_at: datetime
