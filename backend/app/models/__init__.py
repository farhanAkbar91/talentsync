"""SQLAlchemy models — impor semua modul agar metadata lengkap untuk Alembic."""

from app.models.ai import CvEmbedding, CvOptimization, JobEmbedding, MatchResult
from app.models.company import Company, CompanyMember
from app.models.cv import CV, CvExtraction
from app.models.job import Job
from app.models.profile import CandidateProfile
from app.models.skill import CandidateSkill, CanonicalSkill, JobSkill, SkillAlias
from app.models.user import RefreshToken, User

__all__ = [
    "CV",
    "CandidateProfile",
    "CandidateSkill",
    "CanonicalSkill",
    "Company",
    "CompanyMember",
    "CvEmbedding",
    "CvExtraction",
    "CvOptimization",
    "Job",
    "JobEmbedding",
    "JobSkill",
    "MatchResult",
    "RefreshToken",
    "SkillAlias",
    "User",
]
