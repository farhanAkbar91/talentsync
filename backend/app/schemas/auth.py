"""Skema autentikasi & pengguna."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

ROLES = ("candidate", "hr")


class RegisterIn(BaseModel):
    role: str
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    # bcrypt bekerja pada maksimum 72 byte; batasi eksplisit (ADR 0002).
    password: str = Field(min_length=8, max_length=72)

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError("Peran harus 'candidate' atau 'hr'.")
        return v

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nama lengkap tidak boleh kosong.")
        return v


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutIn(RefreshIn):
    pass


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthOut(TokenPairOut):
    user: "UserOut"


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


AuthOut.model_rebuild()
