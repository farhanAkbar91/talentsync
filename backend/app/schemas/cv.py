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


class DiagnosisStrengthOut(BaseModel):
    """Satu aturan diagnosis yang LOLOS (M7) — teks positif tampilan."""

    rule_id: str
    text: str


class DiagnosisImprovementOut(BaseModel):
    """Satu aturan diagnosis yang GAGAL (M7) — teks perbaikan + severity."""

    rule_id: str
    text: str
    severity: str  # "penting" (−12) | "saran" (−6)


class DiagnosisOut(BaseModel):
    """Hasil diagnosis deterministik CV (M7, tanpa LLM) — panel review kandidat."""

    cv_id: uuid.UUID
    quality_score: int
    label: str  # "Baik" (≥80) | "Cukup" (≥60) | "Perlu Perbaikan" (<60)
    strengths: list[DiagnosisStrengthOut]
    improvements: list[DiagnosisImprovementOut]
    computed_at: datetime
