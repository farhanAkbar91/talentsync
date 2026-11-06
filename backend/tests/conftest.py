"""Shared pytest fixtures & test database.

Strategi database (ADR 0002):
- Lokal (tanpa Docker/Postgres): SQLite in-memory via `JSONB().with_variant(JSON)`.
- CI: set `DATABASE_URL_TEST` (PostgreSQL 16 + pgvector) → fixture memakai Postgres
  sungguhan; migrasi Alembic divalidasi di step terpisah sebelum pytest.
"""

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 — daftarkan model
from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db, get_session_factory
from app.main import create_app

TEST_DATABASE_URL = os.environ.get("DATABASE_URL_TEST")


@pytest.fixture()
def db_engine() -> Generator:
    if TEST_DATABASE_URL:
        engine = create_engine(TEST_DATABASE_URL)
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
    else:
        # File sqlite sementara (bukan in-memory + StaticPool): setiap session
        # mendapat koneksi nyata sendiri, sehingga background task (session baru)
        # selalu melihat hasil commit request — semantik sama dengan PostgreSQL.
        tmp_dir = tempfile.mkdtemp(prefix="ts-test-")
        engine = create_engine(f"sqlite:///{Path(tmp_dir) / 'test.db'}")
        Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Generator[Session, None, None]:
    factory: sessionmaker[Session] = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )
    db = factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def seeded_taxonomy(db_session: Session) -> dict:
    """Taksonomi skill sudah di-seed ke db_session test (minta eksplisit, bukan autouse)."""
    from app.services.taxonomy_service import seed_from_json

    summary = seed_from_json(db_session)
    db_session.flush()
    return summary


def _make_settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        log_level="WARNING",
        cors_origins=["http://test"],
        secret_key="test-secret-key-not-for-production-0123456789abcdef",
        uploads_dir="test_uploads",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture()
def client_dead_db(db_engine) -> Generator[TestClient, None, None]:
    """App dengan DATABASE_URL yang pasti tidak dapat dijangkau (untuk test 503)."""
    settings = _make_settings(database_url="postgresql+psycopg://x:x@127.0.0.1:1/x")
    app = create_app(settings)

    factory: sessionmaker[Session] = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: factory

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client(db_engine) -> Generator[TestClient, None, None]:
    settings = _make_settings()
    app = create_app(settings)

    factory: sessionmaker[Session] = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: factory

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client_small_cv_limit(db_engine) -> Generator[TestClient, None, None]:
    """Client dengan batas ukuran CV kecil untuk pengujian 413."""
    settings = _make_settings(max_cv_size_bytes=500, uploads_dir="test_uploads_small")
    app = create_app(settings)

    factory: sessionmaker[Session] = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )

    def override_get_db() -> Generator[Session, None, None]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: factory

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
