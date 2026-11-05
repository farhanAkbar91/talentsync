"""Engine & session factory (SQLAlchemy 2.0, driver psycopg v3)."""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def build_engine(database_url: str) -> Engine:
    # connect_timeout hanya berlaku untuk psycopg (PostgreSQL); sqlite (test/E2E)
    # akan menolak opsi asing. 10 dtk: koneksi cloud (Supabase pooler) bisa lebih
    # lambat dari localhost — lihat ADR 0005.
    connect_args = {"connect_timeout": 10} if database_url.startswith("postgresql") else {}
    return create_engine(
        database_url,
        pool_pre_ping=True,
        # Readiness check dan request tidak boleh menggantung saat DB down
        # (Windows dapat mem-drop SYN tanpa RST → timeout OS sangat lama).
        connect_args=connect_args,
    )


# Instance default untuk penggunaan CLI/scripts (alembic membangun engine sendiri).
engine = build_engine(get_settings().database_url)

# Satu session BARU per request/pemakaian — jangan pernah berbagi instance Session.
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    """Dependency FastAPI: satu session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> sessionmaker[Session]:
    """Dependency untuk background task (butuh session baru di luar siklus request)."""
    return SessionLocal
