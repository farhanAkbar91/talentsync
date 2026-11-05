"""Primitif keamanan: password hashing (bcrypt) + JWT (HS256).

- Password: bcrypt dengan salt acak per-hash; plaintext tidak pernah disimpan.
- Token: access (menit) & refresh (hari). Refresh disimpan sebagai SHA-256 hash
  di tabel refresh_tokens agar dapat dirotasi/dicabut (lihat services/auth_service).
- Kunci signing dari Settings.jwt_secret() — prod menolak startup tanpa SECRET_KEY.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import Settings
from app.core.exceptions import UnauthenticatedError

ACCESS_TYPE = "access"
REFRESH_TYPE = "refresh"
ALGORITHM = "HS256"


# --- Password ---


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def hash_token(token: str) -> str:
    """Hash untuk penyimpanan refresh token (token asli tidak pernah disimpan)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# --- JWT ---


def _encode(claims: dict[str, Any], settings: Settings, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        **claims,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret(), algorithm=ALGORITHM)


def create_access_token(user_id: uuid.UUID, role: str, settings: Settings) -> str:
    return _encode(
        {"sub": str(user_id), "role": role, "type": ACCESS_TYPE, "jti": uuid.uuid4().hex},
        settings,
        timedelta(minutes=settings.access_token_minutes),
    )


def create_refresh_token(user_id: uuid.UUID, role: str, settings: Settings) -> str:
    return _encode(
        {"sub": str(user_id), "role": role, "type": REFRESH_TYPE, "jti": uuid.uuid4().hex},
        settings,
        timedelta(days=settings.refresh_token_days),
    )


def decode_token(token: str, expected_type: str, settings: Settings) -> dict[str, Any]:
    """Dekode + validasi. Melempar UnauthenticatedError untuk token apa pun yang gagal."""
    try:
        payload = jwt.decode(token, settings.jwt_secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise UnauthenticatedError("Token tidak valid atau kedaluwarsa.") from exc
    if payload.get("type") != expected_type:
        raise UnauthenticatedError("Token tidak valid atau kedaluwarsa.")
    return payload
