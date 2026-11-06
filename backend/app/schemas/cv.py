"""Skema CV."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class CVOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    status: str
    original_filename: str
    file_size_bytes: int
    content_sha256: str
    is_primary: bool
    version: int
    page_count: int | None = None
    extraction_status: str | None = None
    extraction_confirmed: bool | None = None
    created_at: datetime
    updated_at: datetime


class ExtractionOut(BaseModel):
    """Hasil ekstraksi CV: payload terstruktur + jejak konfirmasi review."""

    model_config = {"from_attributes": True}

    cv_id: uuid.UUID
    status: str
    parser_version: str
    payload: dict | None = None
    confirmed_at: datetime | None = None
    confirmed_by: uuid.UUID | None = None


class ExtractionConfirmIn(BaseModel):
    """Body opsional PUT /cvs/{id}/extraction/confirm — payload hasil koreksi
    kandidat saat review (tanpa body → konfirmasi apa adanya)."""

    payload: dict | None = None
