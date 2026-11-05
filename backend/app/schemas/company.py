"""Skema perusahaan (HR)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    industry: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    contact_email: EmailStr | None = None

    @field_validator("name", "industry", "location")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class CompanyOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    description: str | None
    industry: str | None
    location: str | None
    website: str | None
    contact_email: str | None
    created_at: datetime
