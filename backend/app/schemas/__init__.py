"""Skema Pydantic (request/response) — API v1."""

from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenPairOut, UserOut
from app.schemas.common import Page
from app.schemas.company import CompanyIn, CompanyOut
from app.schemas.cv import CVOut
from app.schemas.job import JobHrOut, JobIn, JobPublicOut, SkillIn
from app.schemas.profile import CandidateProfileIn, CandidateProfileOut

__all__ = [
    "CVOut",
    "CandidateProfileIn",
    "CandidateProfileOut",
    "CompanyIn",
    "CompanyOut",
    "JobHrOut",
    "JobIn",
    "JobPublicOut",
    "LoginIn",
    "Page",
    "RefreshIn",
    "RegisterIn",
    "SkillIn",
    "TokenPairOut",
    "UserOut",
]
