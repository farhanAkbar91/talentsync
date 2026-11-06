"""Skema respons API taksonomi skill + skill kandidat (M2 Wave 2B)."""

import uuid

from pydantic import BaseModel, Field


class SkillTaxonomyCategoryOut(BaseModel):
    name: str
    count: int


class SkillTaxonomyOut(BaseModel):
    version: str | None
    categories: list[SkillTaxonomyCategoryOut]
    total: int


class SkillAutocompleteItem(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    slug: str
    name: str
    category: str
    skill_type: str


class SkillAutocompleteOut(BaseModel):
    items: list[SkillAutocompleteItem]


class SkillDetailOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    category: str
    skill_type: str
    description: str | None
    related: list[str] | None
    aliases: list[str]
    taxonomy_version: str


# --- Skill kandidat (M2 Wave 2B) ---


class CandidateSkillCanonicalOut(BaseModel):
    slug: str
    name: str
    category: str
    skill_type: str


class CandidateSkillSuggestionOut(BaseModel):
    slug: str
    name: str


class CandidateSkillItemOut(BaseModel):
    """Satu baris skill kandidat. Persisted rows selalu punya canonical (FK NOT
    NULL); None hanya toleransi kontrak frontend (keputusan terdokumentasi:
    hanya item berpadanan kanon yang disimpan)."""

    id: uuid.UUID
    canonical: CandidateSkillCanonicalOut | None = None
    raw_name: str
    confidence: float
    evidence: str | None = None
    source_section: str | None = None
    extraction_method: str
    status: str
    needs_review: bool = False
    suggestions: list[CandidateSkillSuggestionOut] = []


class CandidateSkillListOut(BaseModel):
    items: list[CandidateSkillItemOut]
    total: int


class SkillApplyIn(BaseModel):
    skill_ids: list[uuid.UUID] = Field(default_factory=list)


class SkillApplyOut(BaseModel):
    applied: int
