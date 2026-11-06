"""Endpoint profil: kandidat & perusahaan (HR), plus skill kandidat (M2) dan
rekomendasi lowongan (M6)."""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.user import User
from app.schemas.company import CompanyIn, CompanyOut
from app.schemas.job import RecommendationOut
from app.schemas.profile import CandidateProfileIn, CandidateProfileOut
from app.schemas.skill import CandidateSkillItemOut, CandidateSkillListOut
from app.services import profile_service, recommendation_service, skill_service

router = APIRouter(prefix="/me", tags=["profiles"])


@router.get("/candidate-profile", response_model=CandidateProfileOut)
def get_candidate_profile(
    user: User = Depends(require_roles("candidate")), db: Session = Depends(get_db)
) -> CandidateProfileOut:
    profile = profile_service.get_candidate_profile(db, user)
    return CandidateProfileOut(
        user_id=profile.user_id,
        full_name=user.full_name,
        email=user.email,
        phone=profile.phone,
        location=profile.location,
        headline=profile.headline,
        summary=profile.summary,
        skills=profile.skills or [],
        education=profile.education or [],
        experience=profile.experience or [],
        certifications=profile.certifications or [],
        links=profile.links or {},
        updated_at=profile.updated_at,
    )


@router.put("/candidate-profile", response_model=CandidateProfileOut)
def update_candidate_profile(
    payload: CandidateProfileIn,
    user: User = Depends(require_roles("candidate")),
    db: Session = Depends(get_db),
) -> CandidateProfileOut:
    profile = profile_service.update_candidate_profile(db, user, payload)
    return CandidateProfileOut(
        user_id=profile.user_id,
        full_name=user.full_name,
        email=user.email,
        phone=profile.phone,
        location=profile.location,
        headline=profile.headline,
        summary=profile.summary,
        skills=profile.skills or [],
        education=profile.education or [],
        experience=profile.experience or [],
        certifications=profile.certifications or [],
        links=profile.links or {},
        updated_at=profile.updated_at,
    )


@router.get("/candidate-skills", response_model=CandidateSkillListOut)
def list_my_candidate_skills(
    user: User = Depends(require_roles("candidate")), db: Session = Depends(get_db)
) -> CandidateSkillListOut:
    """Seluruh skill yang sudah diterima kandidat (status accepted), urut nama."""
    rows = skill_service.list_my_skills(db, user)
    raw_items = skill_service.build_skill_items(db, rows)
    items = [CandidateSkillItemOut.model_validate(i) for i in raw_items]
    return CandidateSkillListOut(items=items, total=len(items))


@router.delete("/candidate-skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_candidate_skill(
    skill_id: uuid.UUID,
    user: User = Depends(require_roles("candidate")),
    db: Session = Depends(get_db),
) -> None:
    """Hapus satu skill milik kandidat + bersihkan namanya dari profil."""
    skill_service.delete_my_skill(db, user, skill_id)


@router.get("/recommendations", response_model=RecommendationOut)
def get_my_recommendations(
    request: Request,
    limit: int = Query(default=10, ge=1, le=25, description="Jumlah item rekomendasi (1-25)"),
    user: User = Depends(require_roles("candidate")),
    db: Session = Depends(get_db),
) -> RecommendationOut:
    """Rekomendasi lowongan aktif untuk CV primer kandidat (M6).

    Dihitung on request — TANPA persist ke match_results (jalur persistensi
    tetap endpoint /jobs/{id}/compatibility). Belum ada CV primer terkonfirmasi
    → 400 kode MATCH_UNAVAILABLE (gate sama dengan match_service).
    """
    result = recommendation_service.recommend_jobs(
        db, user, request.app.state.settings, limit=limit
    )
    return RecommendationOut(**result)


@router.get("/company", response_model=CompanyOut)
def get_company(
    user: User = Depends(require_roles("hr")), db: Session = Depends(get_db)
) -> CompanyOut:
    company = profile_service.get_my_company(db, user)
    if company is None:
        raise NotFoundError("Profil perusahaan belum dibuat.")
    return CompanyOut.model_validate(company)


@router.post("/company", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyIn,
    user: User = Depends(require_roles("hr")),
    db: Session = Depends(get_db),
) -> CompanyOut:
    company = profile_service.create_company(db, user, payload)
    return CompanyOut.model_validate(company)


@router.put("/company", response_model=CompanyOut)
def update_company(
    payload: CompanyIn,
    user: User = Depends(require_roles("hr")),
    db: Session = Depends(get_db),
) -> CompanyOut:
    company = profile_service.update_company(db, user, payload)
    return CompanyOut.model_validate(company)
