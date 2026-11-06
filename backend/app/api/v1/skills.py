"""Endpoint taksonomi skill (semua peran yang terautentikasi)."""

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.skill import CanonicalSkill, SkillAlias
from app.models.user import User
from app.schemas.skill import (
    SkillAutocompleteItem,
    SkillAutocompleteOut,
    SkillDetailOut,
    SkillTaxonomyCategoryOut,
    SkillTaxonomyOut,
)
from app.services import taxonomy_service

router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("/taxonomy", response_model=SkillTaxonomyOut)
def get_taxonomy(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("candidate", "hr")),
) -> SkillTaxonomyOut:
    """Ringkasan taksonomi: versi, jumlah skill per kategori, dan total."""
    total = int(
        db.scalar(select(func.count()).select_from(CanonicalSkill).where(CanonicalSkill.is_active))
    )
    categories = [
        SkillTaxonomyCategoryOut(name=category, count=count)
        for category, count in db.execute(
            select(CanonicalSkill.category, func.count())
            .where(CanonicalSkill.is_active)
            .group_by(CanonicalSkill.category)
            .order_by(CanonicalSkill.category)
        ).all()
    ]
    versions = db.scalars(select(CanonicalSkill.taxonomy_version).distinct()).all()
    # Satu seed = satu versi; bila ada lebih dari satu (seed campuran), ambil terbaru.
    version = max(versions, key=_version_key) if versions else None
    return SkillTaxonomyOut(version=version, categories=categories, total=total)


def _version_key(version: str) -> tuple[int, ...]:
    # "1.2.10" > "1.2.9" — bandingkan per komponen numerik.
    parts = version.split(".")
    try:
        return tuple(int(part) for part in parts)
    except ValueError:
        return (0,)


@router.get("/autocomplete", response_model=SkillAutocompleteOut)
def get_autocomplete(
    q: str = Query(default="", max_length=100, description="Kata kunci skill (min. 2 karakter)"),
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("candidate", "hr")),
) -> SkillAutocompleteOut:
    """Saran skill untuk kolom pencarian.

    Kontrak q < 2 karakter: HTTP 200 dengan `items: []` (bukan 422) — kosong
    dianggap kondisi normal saat pengguna belum selesai mengetik.
    """
    skills = taxonomy_service.autocomplete(db, q, limit=limit)
    return SkillAutocompleteOut(
        items=[SkillAutocompleteItem.model_validate(skill) for skill in skills]
    )


@router.get("/{skill_id}", response_model=SkillDetailOut)
def get_skill(
    skill_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("candidate", "hr")),
) -> SkillDetailOut:
    """Detail satu skill kanon beserta seluruh aliasnya."""
    skill = db.get(CanonicalSkill, skill_id)
    if skill is None:
        raise NotFoundError("Skill tidak ditemukan.")
    aliases = db.scalars(
        select(SkillAlias.alias)
        .where(SkillAlias.canonical_skill_id == skill.id)
        .order_by(SkillAlias.alias)
    ).all()
    return SkillDetailOut(
        id=skill.id,
        slug=skill.slug,
        name=skill.name,
        category=skill.category,
        skill_type=skill.skill_type,
        description=skill.description,
        related=skill.related,
        aliases=list(aliases),
        taxonomy_version=skill.taxonomy_version,
    )
