"""Endpoint autentikasi: /register, /login, /refresh, /logout, /me."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AuthOut, LoginIn, LogoutIn, RefreshIn, RegisterIn, UserOut
from app.schemas.company import CompanyOut
from app.schemas.profile import CandidateProfileOut
from app.services import auth_service, profile_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)) -> AuthOut:
    settings: Settings = request.app.state.settings
    user = auth_service.register(
        db,
        role=payload.role,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
    )
    tokens = auth_service.issue_tokens(db, user, settings)
    return AuthOut(**tokens, user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthOut)
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)) -> AuthOut:
    settings: Settings = request.app.state.settings
    user = auth_service.authenticate(db, payload.email, payload.password)
    tokens = auth_service.issue_tokens(db, user, settings)
    return AuthOut(**tokens, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=AuthOut)
def refresh(payload: RefreshIn, request: Request, db: Session = Depends(get_db)) -> AuthOut:
    settings: Settings = request.app.state.settings
    tokens, user = auth_service.rotate_refresh(db, payload.refresh_token, settings)
    return AuthOut(**tokens, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutIn, db: Session = Depends(get_db)) -> None:
    auth_service.revoke_refresh(db, payload.refresh_token)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/me/summary")
def me_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Ringkasan sesuai peran — dipakai dashboard & guard frontend."""
    data: dict = {"user": UserOut.model_validate(user).model_dump()}
    if user.role == "candidate":
        profile = profile_service.get_candidate_profile(db, user)
        data["candidate_profile"] = CandidateProfileOut(
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
            updated_at=profile.updated_at or datetime.now(UTC),
        ).model_dump()
    else:
        company = profile_service.get_my_company(db, user)
        data["company"] = CompanyOut.model_validate(company).model_dump() if company else None
    return data
