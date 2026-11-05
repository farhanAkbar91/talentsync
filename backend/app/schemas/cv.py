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
    created_at: datetime
    updated_at: datetime
