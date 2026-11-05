"""SQLAlchemy models — impor semua modul agar metadata lengkap untuk Alembic."""

from app.models.ai import CvEmbedding, CvOptimization, JobEmbedding, MatchResult
from app.models.company import Company, CompanyMember
from app.models.cv import CV, CvExtraction
from app.models.job import Job
from app.models.profile import CandidateProfile
from app.models.user import RefreshToken, User

__all__ = [
    "CV",
    "CandidateProfile",
    "Company",
    "CompanyMember",
    "CvEmbedding",
    "CvExtraction",
    "CvOptimization",
    "Job",
    "JobEmbedding",
    "MatchResult",
    "RefreshToken",
    "User",
]
