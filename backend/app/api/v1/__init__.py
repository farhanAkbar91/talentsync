"""Router agregat /api/v1."""

from fastapi import APIRouter

from app.api.v1 import auth, cvs, health, hr_jobs, jobs, profiles, skills

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(profiles.router)
api_router.include_router(jobs.router)
api_router.include_router(hr_jobs.router)
api_router.include_router(cvs.router)
api_router.include_router(skills.router)
