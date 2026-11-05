"""Auth service: registrasi, autentikasi, penerbitan & rotasi token."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, UnauthenticatedError
from app.core.security import (
    REFRESH_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.profile import CandidateProfile
from app.models.user import RefreshToken, User


def _as_aware(dt: datetime) -> datetime:
    # SQLite mengembalikan naive datetime; normalisasi ke UTC-aware sebelum dibanding.
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def register(db: Session, *, role: str, full_name: str, email: str, password: str) -> User:
    email = email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise ConflictError("Email sudah terdaftar. Silakan masuk atau gunakan email lain.")

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        role=role,
    )
    db.add(user)
    if role == "candidate":
        db.add(CandidateProfile(user_id=user_id))
    try:
        db.commit()
    except IntegrityError as exc:
        # Race check-then-insert: unique constraint (email) yang menolak.
        db.rollback()
        raise ConflictError(
            "Email sudah terdaftar. Silakan masuk atau gunakan email lain."
        ) from exc
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        # Pesan sengaja generik — jangan membocorkan keberadaan email.
        raise UnauthenticatedError("Email atau kata sandi salah.")
    if not user.is_active:
        raise UnauthenticatedError("Akun tidak aktif. Hubungi dukungan.")
    return user


def _new_refresh_pair(db: Session, user: User, settings: Settings) -> str:
    token = create_refresh_token(user.id, user.role, settings)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    return token


def issue_tokens(db: Session, user: User, settings: Settings) -> dict:
    access = create_access_token(user.id, user.role, settings)
    refresh = _new_refresh_pair(db, user, settings)
    db.commit()
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


def rotate_refresh(db: Session, refresh_token: str, settings: Settings) -> tuple[dict, User]:
    """Rotasi: refresh token lama dicabut, pasangan baru diterbitkan (one-time use)."""
    payload = decode_token(refresh_token, REFRESH_TYPE, settings)
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
    )
    if row is None or row.revoked_at is not None:
        raise UnauthenticatedError("Refresh token tidak valid.")
    if _as_aware(row.expires_at) < datetime.now(UTC):
        raise UnauthenticatedError("Sesi berakhir. Silakan masuk kembali.")
    if str(row.user_id) != str(payload["sub"]):
        raise UnauthenticatedError("Refresh token tidak valid.")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise UnauthenticatedError("Akun tidak ditemukan atau tidak aktif.")

    row.revoked_at = datetime.now(UTC)
    tokens = issue_tokens(db, user, settings)
    return tokens, user


def revoke_refresh(db: Session, refresh_token: str) -> None:
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
    )
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        db.commit()
