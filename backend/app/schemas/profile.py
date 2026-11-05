"""Skema profil kandidat.

Item pendidikan/pengalaman/sertifikasi disimpan sebagai list JSONB dengan struktur
kunci tetap agar mudah dipakai matching engine (fase AI) tanpa migrasi tambahan.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class EducationItem(BaseModel):
    school: str = Field(min_length=1, max_length=255)
    degree: str | None = Field(default=None, max_length=100)
    field_of_study: str | None = Field(default=None, max_length=100)
    start_year: int | None = Field(default=None, ge=1950, le=2100)
    end_year: int | None = Field(default=None, ge=1950, le=2100)


class ExperienceItem(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    start_period: str | None = Field(default=None, max_length=50)
    end_period: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=3000)


class CertificationItem(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    issuer: str | None = Field(default=None, max_length=255)
    year: int | None = Field(default=None, ge=1950, le=2100)


class LinkItem(BaseModel):
    linkedin: str | None = Field(default=None, max_length=255)
    github: str | None = Field(default=None, max_length=255)
    portfolio: str | None = Field(default=None, max_length=255)


class CandidateProfileIn(BaseModel):
    # Nama lengkap milik akun (users.full_name) — diperbarui lewat profil demi
    # satu form yang utuh di frontend.
    full_name: str = Field(min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    location: str | None = Field(default=None, max_length=255)
    headline: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=5000)
    skills: list[str] = Field(default_factory=list, max_length=30)
    education: list[EducationItem] = Field(default_factory=list, max_length=10)
    experience: list[ExperienceItem] = Field(default_factory=list, max_length=15)
    certifications: list[CertificationItem] = Field(default_factory=list, max_length=15)
    links: LinkItem = Field(default_factory=LinkItem)

    @field_validator("skills")
    @classmethod
    def _clean_skills(cls, v: list[str]) -> list[str]:
        cleaned: list[str] = []
        for s in v:
            s = s.strip()
            if s and s.lower() not in [x.lower() for x in cleaned]:
                cleaned.append(s[:50])
        return cleaned

    @field_validator("phone")
    @classmethod
    def _clean_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class CandidateProfileOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str
    phone: str | None
    location: str | None
    headline: str | None
    summary: str | None
    skills: list[str]
    education: list[dict[str, Any]]
    experience: list[dict[str, Any]]
    certifications: list[dict[str, Any]]
    links: dict[str, Any]
    updated_at: datetime
