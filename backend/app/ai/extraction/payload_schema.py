"""Skema payload terstruktur hasil ekstraksi CV — kontrak JSONB
`cv_extractions.payload` (M1, parser heuristik deterministik).

Key JSON berbahasa Inggris agar konsisten dengan penamaan JSONB
`candidate_profiles`; label UI (bahasa Indonesia) diterjemahkan di lapisan
presentasi. Field turunan (field_confidence / needs_review / sections_found)
dihitung ulang oleh validator agar selalu konsisten dengan isi payload.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, model_validator

PAYLOAD_PARSER_VERSION = "pymupdf-heuristic-v1"

# Kunci field yang punya skor confidence tingkat-field (section tanpa item
# selalu 0.0 → otomatis masuk needs_review).
FIELD_CONFIDENCE_KEYS = (
    "name",
    "email",
    "phone",
    "location",
    "summary",
    "experiences",
    "education",
    "skills",
    "certifications",
    "languages",
)

NEEDS_REVIEW_THRESHOLD = 0.6


class ContactPayload(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    links: list[str] = Field(default_factory=list)


class ExperienceItem(BaseModel):
    title: str | None = None
    company: str | None = None
    period: str | None = None
    start: str | None = None
    end: str | None = None
    current: bool = False
    bullets: list[str] = Field(default_factory=list)
    evidence: str = ""
    confidence: float = 0.0


class EducationItem(BaseModel):
    degree: str | None = None
    institution: str | None = None
    field: str | None = None
    years: str | None = None
    gpa: float | None = None
    evidence: str = ""
    confidence: float = 0.0


class SkillItem(BaseModel):
    name: str
    evidence: str = ""
    confidence: float = 0.0


class CertificationItem(BaseModel):
    name: str
    issuer: str | None = None
    year: int | None = None
    evidence: str = ""
    confidence: float = 0.0


class LanguageItem(BaseModel):
    language: str
    level: str | None = None
    evidence: str = ""
    confidence: float = 0.0


class ProjectItem(BaseModel):
    name: str | None = None
    description: str | None = None
    evidence: str = ""
    confidence: float = 0.0


class AwardItem(BaseModel):
    text: str
    evidence: str = ""
    confidence: float = 0.0


class ExtractionPayload(BaseModel):
    parser_version: str = PAYLOAD_PARSER_VERSION
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    contact: ContactPayload = Field(default_factory=ContactPayload)
    summary: str | None = None
    experiences: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    skills: list[SkillItem] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    languages: list[LanguageItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    awards: list[AwardItem] = Field(default_factory=list)
    field_confidence: dict[str, float] = Field(default_factory=dict)
    needs_review: list[str] = Field(default_factory=list)
    sections_found: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _derive_review_metadata(self) -> "ExtractionPayload":
        """Hitung ulang metadata review agar payload selalu konsisten:
        - sections_found: section yang benar-benar berisi konten,
        - field_confidence: diisi heuristik sederhana bila tidak disuplai parser,
        - needs_review: field dengan confidence di bawah ambang (termasuk
          section kosong/missing)."""
        if not self.sections_found:
            self.sections_found = self._sections_with_content()
        if not self.field_confidence:
            self.field_confidence = self._default_field_confidence()
        self.needs_review = sorted(
            key for key, value in self.field_confidence.items() if value < NEEDS_REVIEW_THRESHOLD
        )
        return self

    def _sections_with_content(self) -> list[str]:
        found: list[str] = []
        if any(
            (
                self.contact.name,
                self.contact.email,
                self.contact.phone,
                self.contact.location,
                self.contact.links,
            )
        ):
            found.append("contact")
        if self.summary:
            found.append("summary")
        for key, items in (
            ("experience", self.experiences),
            ("education", self.education),
            ("skills", self.skills),
            ("certifications", self.certifications),
            ("languages", self.languages),
            ("projects", self.projects),
            ("awards", self.awards),
        ):
            if items:
                found.append(key)
        return found

    def _default_field_confidence(self) -> dict[str, float]:
        """Heuristik cadangan (jalur konfirmasi tanpa metadata parser):
        field terisi → confidence polos; section → rata-rata item."""

        def mean(items: list[BaseModel]) -> float:
            values = [float(getattr(item, "confidence", 0.0)) for item in items]
            return round(sum(values) / len(values), 4) if values else 0.0

        return {
            "name": 0.85 if self.contact.name else 0.0,
            "email": 0.95 if self.contact.email else 0.0,
            "phone": 0.9 if self.contact.phone else 0.0,
            "location": 0.9 if self.contact.location else 0.0,
            "summary": 0.8 if self.summary else 0.0,
            "experiences": mean(self.experiences),
            "education": mean(self.education),
            "skills": mean(self.skills),
            "certifications": mean(self.certifications),
            "languages": mean(self.languages),
        }

    def to_dict(self) -> dict:
        """Serialisasi ke dict JSON-safe (untuk kolom JSONB payload)."""
        return self.model_dump(mode="json")
