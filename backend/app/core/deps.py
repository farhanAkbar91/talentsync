"""Dependency FastAPI: autentikasi & RBAC."""

import uuid

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ForbiddenError, UnauthenticatedError
from app.core.security import ACCESS_TYPE, decode_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token (Bearer)")


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthenticatedError("Autentikasi diperlukan.")
    settings: Settings = request.app.state.settings
    payload = decode_token(credentials.credentials, ACCESS_TYPE, settings)
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except ValueError as exc:
        raise UnauthenticatedError("Token tidak valid atau kedaluwarsa.") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthenticatedError("Akun tidak ditemukan atau tidak aktif.")
    return user


def require_roles(*roles: str):
    """Factory dependency: batasi endpoint untuk peran tertentu."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise ForbiddenError("Akses ditolak untuk peran Anda.")
        return user

    return dependency
