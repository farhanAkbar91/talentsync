"""Orkestrator pipeline ekstraksi CV — deterministik, tanpa LLM (M1).

Alur: preprocess_text → segment_sections → entities (per section) →
payload_schema (validasi Pydantic) → dict. Setiap tahap entitas dibungkus
try/except per section: bila satu heuristik gagal, section itu menjadi kosong
dengan confidence 0.0 dan masuk needs_review — payload tetap dihasilkan.
Fungsi build_payload TOTAL terhadap teks biasa (tidak pernah melempar).
"""

import logging

from app.ai.extraction.entities import (
    extract_awards,
    extract_certifications,
    extract_contact,
    extract_education,
    extract_experiences,
    extract_languages,
    extract_projects,
    extract_skills,
)
from app.ai.extraction.payload_schema import (
    ContactPayload,
    ExtractionPayload,
)
from app.ai.extraction.preprocess import preprocess_text
from app.ai.extraction.segmenter import segment_sections

logger = logging.getLogger(__name__)

# Contact kosong — bentuk sama dengan hasil extract_contact.
_EMPTY_CONTACT: dict = {
    "name": None,
    "email": None,
    "phone": None,
    "location": None,
    "links": [],
    "confidence": {"name": 0.0, "email": 0.0, "phone": 0.0, "location": 0.0},
    "evidence": {"name": "", "email": "", "phone": "", "location": ""},
}

# Kunci section kanonik → extractor-nya (dict stabil untuk orkestrasi).
_EXTRACTORS = {
    "experience": extract_experiences,
    "education": extract_education,
    "skills": extract_skills,
    "certifications": extract_certifications,
    "languages": extract_languages,
    "projects": extract_projects,
    "awards": extract_awards,
}


def build_payload(raw_text: str) -> dict:
    """Bangun payload terstruktur dari teks CV mentah. Deterministik: teks
    sama → payload sama (tanpa LLM, tanpa keacakan selain timestamp)."""
    lines = preprocess_text(raw_text or "")
    sections = segment_sections(lines)

    contact = _safe(lambda: extract_contact(sections["contact"]), _EMPTY_CONTACT)
    summary = _safe(lambda: _join_summary(sections["summary"]), None)

    items: dict[str, list[dict]] = {}
    for key, extractor in _EXTRACTORS.items():
        items[key] = _safe(lambda ex=extractor, ls=sections[key]: ex(ls), [])

    field_confidence = {
        "name": contact["confidence"]["name"],
        "email": contact["confidence"]["email"],
        "phone": contact["confidence"]["phone"],
        "location": contact["confidence"]["location"],
        "summary": 0.8 if summary else 0.0,
        "experiences": _mean_confidence(items["experience"]),
        "education": _mean_confidence(items["education"]),
        "skills": _mean_confidence(items["skills"]),
        "certifications": _mean_confidence(items["certifications"]),
        "languages": _mean_confidence(items["languages"]),
    }

    payload = ExtractionPayload(
        contact=ContactPayload(
            name=contact["name"],
            email=contact["email"],
            phone=contact["phone"],
            location=contact["location"],
            links=contact["links"],
        ),
        summary=summary,
        experiences=items["experience"],
        education=items["education"],
        skills=items["skills"],
        certifications=items["certifications"],
        languages=items["languages"],
        projects=items["projects"],
        awards=items["awards"],
        field_confidence=field_confidence,
        # needs_review & sections_found dihitung ulang validator payload_schema
        # (berbasis konten) agar konsisten saat payload diedit lalu divalidasi lagi.
    )
    return payload.to_dict()


def _safe(fn, default):
    """Jalankan extractor per-section; kegagalan tak terduga → nilai default
    (section kosong, confidence 0.0 → otomatis masuk needs_review)."""
    try:
        return fn()
    except Exception:  # noqa: BLE001 - heuristik tidak boleh meruntuhkan payload
        logger.warning("Ekstraksi section gagal (abaikan section ini)", exc_info=True)
        return default


def _join_summary(lines: list[str]) -> str | None:
    """Gabungkan baris ringkasan menjadi satu paragraf (None bila kosong)."""
    text = " ".join(line.strip() for line in lines if line.strip())
    return text or None


def _mean_confidence(items: list[dict]) -> float:
    """Confidence tingkat section = rata-rata confidence item (0.0 bila kosong)."""
    if not items:
        return 0.0
    return round(sum(float(item.get("confidence", 0.0)) for item in items) / len(items), 4)
