"""Health endpoints.

- GET /health       : liveness — proses API hidup (tanpa cek dependensi).
- GET /health/ready : readiness — database dapat dijangkau & pgvector aktif.
"""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

from app.core.config import APP_VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
def liveness(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": APP_VERSION,
    }


@router.get("/health/ready")
def readiness(request: Request) -> dict:
    engine = request.app.state.engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            has_vector = conn.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            ).scalar()
    except Exception:
        # Detail exception (termasuk DSN) tidak dikirim ke klien.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database tidak dapat dijangkau.",
        ) from None

    if not has_vector:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ekstensi pgvector belum aktif. Jalankan 'alembic upgrade head'.",
        )

    return {"status": "ok", "database": "ok", "pgvector": True}
