"""Service profil kandidat & perusahaan."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.models.company import Company, CompanyMember
from app.models.profile import CandidateProfile
from app.models.user import User
from app.schemas.company import CompanyIn
from app.schemas.profile import CandidateProfileIn

# --- Profil kandidat ---


def get_candidate_profile(db: Session, user: User) -> CandidateProfile:
    profile = db.get(CandidateProfile, user.id)
    if profile is None:  # pertahanan: dibuat otomatis saat registrasi
        profile = CandidateProfile(user_id=user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def update_candidate_profile(db: Session, user: User, data: CandidateProfileIn) -> CandidateProfile:
    profile = get_candidate_profile(db, user)
    user.full_name = data.full_name.strip()
    profile.phone = data.phone
    profile.location = data.location
    profile.headline = data.headline
    profile.summary = data.summary
    profile.skills = data.skills
    profile.education = [item.model_dump(exclude_none=True) for item in data.education]
    profile.experience = [item.model_dump(exclude_none=True) for item in data.experience]
    profile.certifications = [item.model_dump(exclude_none=True) for item in data.certifications]
    profile.links = data.links.model_dump(exclude_none=True)
    db.commit()
    db.refresh(profile)
    return profile


# --- Perusahaan (HR) ---


def get_my_company(db: Session, user: User) -> Company | None:
    member = db.scalar(select(CompanyMember).where(CompanyMember.user_id == user.id))
    return member.company if member else None


def create_company(db: Session, user: User, data: CompanyIn) -> Company:
    if get_my_company(db, user) is not None:
        raise ConflictError("Anda sudah terhubung dengan satu perusahaan.")
    company = Company(
        name=data.name,
        description=data.description,
        industry=data.industry,
        location=data.location,
        website=data.website,
        contact_email=data.contact_email,
        created_by_user_id=user.id,
    )
    db.add(company)
    db.flush()
    db.add(CompanyMember(company_id=company.id, user_id=user.id, role_in_company="owner"))
    try:
        db.commit()
    except IntegrityError as exc:
        # Race check-then-insert: unique(user_id) yang menolak.
        db.rollback()
        raise ConflictError("Anda sudah terhubung dengan satu perusahaan.") from exc
    db.refresh(company)
    return company


def update_company(db: Session, user: User, data: CompanyIn) -> Company:
    company = get_my_company(db, user)
    if company is None:
        raise NotFoundError("Profil perusahaan belum dibuat.")
    company.name = data.name
    company.description = data.description
    company.industry = data.industry
    company.location = data.location
    company.website = data.website
    company.contact_email = data.contact_email
    db.commit()
    db.refresh(company)
    return company
