"""Skema lowongan — versi publik (kandidat) & versi HR."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EMPLOYMENT_TYPES = ("full_time", "part_time", "contract", "internship", "freelance")
WORK_MODES = ("onsite", "hybrid", "remote")
JOB_STATUSES = ("draft", "active", "paused", "closed", "expired", "archived")


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    required: bool


class JobIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=20, max_length=20000)
    responsibilities: str | None = Field(default=None, max_length=20000)
    requirements: str | None = Field(default=None, max_length=20000)
    skills: list[SkillIn] = Field(min_length=1, max_length=30)
    category: str | None = Field(default=None, max_length=100)
    employment_type: Literal["full_time", "part_time", "contract", "internship", "freelance"]
    work_mode: Literal["onsite", "hybrid", "remote"]
    seniority: str | None = Field(default=None, max_length=50)
    location_text: str | None = Field(default=None, max_length=255)
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    salary_currency: str = Field(default="IDR", max_length=8)
    # Batas akhir lamaran divalidasi service-side (harus di masa depan saat publish).
    closing_at: datetime | None = None

    @field_validator("title", "category", "seniority", "location_text")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("skills")
    @classmethod
    def _normalize_skills(cls, v: list[SkillIn]) -> list[SkillIn]:
        # Dedupe case-insensitive; jika nama sama muncul sebagai required & preferred,
        # prioritas pada required. Minimal 1 skill required (desain form 60/40).
        seen: dict[str, SkillIn] = {}
        for s in v:
            name = s.name.strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                seen[key] = SkillIn(name=seen[key].name, required=seen[key].required or s.required)
            else:
                seen[key] = SkillIn(name=name, required=s.required)
        if not any(s.required for s in seen.values()):
            raise ValueError("Minimal satu skill wajib (required) harus diisi.")
        return list(seen.values())

    @model_validator(mode="after")
    def _check_salary(self) -> "JobIn":
        if self.salary_min is not None and self.salary_max is not None:
            if self.salary_min > self.salary_max:
                raise ValueError("Gaji minimum tidak boleh melebihi gaji maksimum.")
        return self


class CompanyBriefOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    industry: str | None
    location: str | None
    website: str | None


class JobPublicOut(BaseModel):
    """Versi kandidat/publik — tanpa field internal (posted_by, dsb.)."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    title: str
    company: CompanyBriefOut
    description: str
    responsibilities: str | None
    requirements: str | None
    skills: list[SkillIn]
    category: str | None
    employment_type: str
    work_mode: str
    seniority: str | None
    location_text: str | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str
    posted_at: datetime | None
    closing_at: datetime | None


class JobHrOut(JobPublicOut):
    """Versi HR — tambah status & metadata internal."""

    status: str
    closed_reason: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
