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


# --- Optimasi CV by LLM (M8 Wave 5) ---


class OptimizationStartIn(BaseModel):
    """Body POST /cvs/{id}/optimizations — lowongan tujuan + opsi regenerate."""

    job_id: uuid.UUID
    regenerate: bool = False


class OptimizationStartOut(BaseModel):
    """Respons mulai generasi: baris 'generating' baru atau hasil cache kuota.

    `cached=True` berarti baris hasil completed lama dikembalikan apa adanya
    (tanpa panggilan LLM)."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    cv_id: uuid.UUID
    job_id: uuid.UUID
    status: str
    cached: bool
    model_version: str | None = None
    created_at: datetime


class OptimizationOut(BaseModel):
    """Detail satu baris optimasi: saran + laporan grounding + keputusan."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    cv_id: uuid.UUID
    job_id: uuid.UUID
    status: str  # generating | completed | failed | applied
    suggestions: list[dict] | None = None
    grounding_report: dict | None = None
    decisions: dict | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    prompt_version: str | None = None
    error_message: str | None = None
    applied_cv_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class OptimizationListOut(BaseModel):
    """Respons daftar riwayat optimasi CV (terbaru lebih dulu)."""

    items: list[OptimizationOut]
    total: int


class OptimizationApplyIn(BaseModel):
    """Body POST .../apply — keputusan per suggestion_id (True = diterima)."""

    decisions: dict[str, bool]


class OptimizationApplyOut(BaseModel):
    """Respons penerapan: CV versi baru + jumlah saran yang diterapkan."""

    new_cv_id: uuid.UUID
    applied: int
