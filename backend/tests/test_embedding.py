"""Test M3 — embedding engine: chunking, perakitan teks, pooling, cosine,
service embedding (gate & upsert), hook confirm/publish, dan re-embed massal.

Semua test memakai embedder PALSU deterministik (bag-of-words hash → 384 dim,
L2-normalized) — TIDAK memuat model sungguhan agar suite tetap cepat.
"""

import math
import uuid
from datetime import UTC, datetime
from hashlib import md5

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.matching import embedder as embedder_module
from app.ai.matching.embedder import TextEmbedder, build_cv_text, build_job_text, chunk_text
from app.ai.matching.similarity import cosine
from app.core.config import Settings
from app.db.session import get_db, get_session_factory
from app.main import create_app
from app.models.ai import CvEmbedding, JobEmbedding
from app.models.company import Company, CompanyMember
from app.models.cv import CV, CvExtraction
from app.models.job import Job
from app.models.user import User
from app.services import embedding_service
from tests.helpers import create_job, make_candidate, make_hr_with_company
from tests.test_extraction_api import CV_LINES, get_extraction, make_multiline_pdf, upload_cv

DIM = 384
MODEL_NAME = "fake-model-untuk-test"


# --- Embedder palsu deterministik ---


def _token_vector(token: str) -> list[float]:
    """Vektor deterministik per token: dua posisi hash → dimensi 384."""
    digest = int(md5(token.encode("utf-8")).hexdigest(), 16)
    vec = [0.0] * DIM
    vec[digest % DIM] += 1.0 + (digest >> 16) % 10 / 10.0
    vec[(digest // DIM) % DIM] += 0.5
    return vec


class FakeTextEmbedder:
    """Embedder tingkat teks: bag-of-words hash → dim 384, L2-normalized."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vec = [0.0] * DIM
            for token in text.lower().split():
                for i, weight in enumerate(_token_vector(token)):
                    vec[i] += weight
            norm = math.sqrt(sum(v * v for v in vec))
            if norm:
                vec = [v / norm for v in vec]
            vectors.append(vec)
        return vectors


class FakeChunkModel:
    """Pengganti SentenceTransformer (tingkat CHUNK) untuk menguji pipeline
    encode asli TextEmbedder: chunk → batch → mean pool → L2."""

    def __init__(self):
        self.batches: list[list[str]] = []

    def encode(self, sentences, **kwargs):  # noqa: ARG002 — tanda tangan model nyata
        self.batches.append(list(sentences))
        rows = []
        for sentence in sentences:
            vec = [0.0] * DIM
            for token in sentence.lower().split():
                for i, weight in enumerate(_token_vector(token)):
                    vec[i] += weight
            rows.append(vec)
        import numpy as np

        return np.asarray(rows, dtype=float)


def _fake_factory(model_name: str) -> FakeTextEmbedder:
    """Pabrik embedder palsu (menggantikan get_embedder di embedding_service)."""
    return FakeTextEmbedder(model_name)


# --- Settings & seed data helper ---


def _svc_settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        log_level="WARNING",
        cors_origins=["http://test"],
        secret_key="test-secret-key-not-for-production-0123456789abcdef",
        uploads_dir="test_uploads",
        embeddings_enabled=True,
        embedding_model=MODEL_NAME,
    )
    base.update(overrides)
    return Settings(**base)


PAYLOAD_M3 = {
    "contact": {
        "name": "Budi Santoso",
        "email": "budi@example.dev",
        "phone": "+62 8121-3188-4851",
        "location": "Jakarta",
        "links": [],
    },
    "summary": "Analisa data dengan SQL dan Python.",
    "experiences": [
        {
            "title": "Data Analyst Junior",
            "company": "PT Cerdas",
            "period": "2025-01 - sekarang",
            "bullets": ["Menangani SQL dan Python."],
        }
    ],
    "education": [
        {
            "degree": "S1",
            "field": "Data Analyst",
            "institution": "Universitas A",
            "years": "2021-2025",
            "gpa": 3.01,
        }
    ],
    "skills": [
        {"name": "SQL", "evidence": "", "confidence": 1.0},
        {"name": "Python", "evidence": "", "confidence": 1.0},
    ],
    "certifications": [],
    "languages": [{"language": "Indonesia", "level": "Native"}],
    "projects": [],
    "awards": [],
}


def _seed_user(db: Session, email: str, role: str = "candidate") -> User:
    user = User(email=email, password_hash="hash-palsu", full_name="Budi Santoso", role=role)
    db.add(user)
    db.flush()
    return user


def _seed_company(db: Session, hr: User) -> Company:
    company = Company(name="PT Uji Coba", created_by_user_id=hr.id)
    db.add(company)
    db.flush()
    db.add(CompanyMember(company_id=company.id, user_id=hr.id))
    db.flush()
    return company


def _seed_cv(
    db: Session,
    user: User,
    *,
    confirmed: bool = True,
    payload: dict | None = PAYLOAD_M3,
    deleted: bool = False,
) -> CV:
    cv = CV(
        candidate_user_id=user.id,
        status="ready",
        file_path="uploads/cvs/uji.pdf",
        original_filename="cv.pdf",
        mime_type="application/pdf",
        file_size_bytes=1000,
        content_sha256=uuid.uuid4().hex,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    db.add(cv)
    db.flush()
    db.add(
        CvExtraction(
            cv_id=cv.id,
            status="done",
            parser_version="pymupdf-heuristic-v1",
            payload=payload,
            confirmed_at=datetime.now(UTC) if confirmed else None,
        )
    )
    db.commit()
    return cv


def _seed_job(
    db: Session,
    hr: User,
    company: Company,
    *,
    status: str = "active",
    deleted: bool = False,
) -> Job:
    job = Job(
        company_id=company.id,
        posted_by_user_id=hr.id,
        source_type="hr",
        status=status,
        title="Data Analyst Senior",
        description="Menganalisa data penjualan bersama tim.",
        requirements="SQL dan Python.",
        responsibilities="Laporan mingguan.",
        skills=[{"name": "SQL", "required": True}, {"name": "Python", "required": True}],
        employment_type="full_time",
        work_mode="hybrid",
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    db.add(job)
    db.commit()
    return job


def _session_factory(db) -> sessionmaker[Session]:
    return sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)


# --- chunk_text ---


def test_chunk_text_splits_on_blank_lines():
    text = "paragraf satu.\n\nparagraf dua.\n \nparagraf tiga."
    assert chunk_text(text) == ["paragraf satu.", "paragraf dua.", "paragraf tiga."]


def test_chunk_text_hard_wraps_at_word_boundaries():
    words = [f"kata{index:03d}" for index in range(150)]
    text = " ".join(words)  # ±1.2 ribu karakter > 480
    chunks = chunk_text(text, max_chars=480)
    assert len(chunks) > 1
    assert all(len(chunk) <= 480 for chunk in chunks)
    # Tidak ada kata yang hilang atau terpotong di tengah.
    assert " ".join(chunks).split() == words
    assert all(chunk == chunk.strip() for chunk in chunks)


def test_chunk_text_never_returns_empty_list():
    assert chunk_text("") == [""]
    assert chunk_text("   \n\n   ") == [""]
    assert chunk_text("satu kalimat pendek.") == ["satu kalimat pendek."]


# --- build_cv_text / build_job_text ---


def test_build_cv_text_contains_expected_sections():
    text = build_cv_text(PAYLOAD_M3)
    for expected in (
        "NAMA: Budi Santoso",
        "KONTAK:",
        "budi@example.dev",
        "RINGKASAN",
        "PENGALAMAN",
        "Data Analyst Junior — PT Cerdas (2025-01 - sekarang)",
        "- Menangani SQL dan Python.",
        "PENDIDIKAN",
        "IPK 3.01",
        "KEAHLIAN",
        "SQL, Python",
        "BAHASA",
        "Indonesia (Native)",
    ):
        assert expected in text, expected


def test_build_cv_text_includes_sections_only_when_present():
    text = build_cv_text({"summary": "Hanya ringkasan."})
    assert "RINGKASAN" in text and "Hanya ringkasan." in text
    for absent in ("PENGALAMAN", "PENDIDIKAN", "KEAHLIAN", "SERTIFIKASI", "BAHASA", "PROYEK"):
        assert absent not in text, absent


def test_build_cv_text_project_and_certification_lines():
    payload = {
        "certifications": [{"name": "Sertifikasi Data", "issuer": "IBM", "year": 2025}],
        "projects": [{"name": "Dashboard Penjualan", "description": "Dashboard interaktif."}],
    }
    text = build_cv_text(payload)
    assert "SERTIFIKASI" in text and "- Sertifikasi Data (IBM, 2025)" in text
    assert "PROYEK" in text and "- Dashboard Penjualan: Dashboard interaktif." in text


def test_build_job_text_sections():
    text = build_job_text(
        title="Senior Full-Stack Engineer",
        skill_names=["React", "Python"],
        description="Membangun aplikasi web end-to-end.",
        requirements="Pengalaman 3+ tahun.",
        responsibilities="Merancang API.",
    )
    assert "POSISI" in text and "Senior Full-Stack Engineer" in text
    assert "Membangun aplikasi web end-to-end." in text
    assert "KUALIFIKASI" in text and "Pengalaman 3+ tahun." in text
    assert "KEAHLIAN" in text and "React, Python" in text
    assert "TANGGUNG JAWAB" in text and "Merancang API." in text


def test_build_job_text_skips_empty_optional_sections():
    text = build_job_text(title="Data Analyst", skill_names=[], description="Deskripsi saja.")
    for absent in ("KUALIFIKASI", "KEAHLIAN", "TANGGUNG JAWAB"):
        assert absent not in text, absent


# --- TextEmbedder: mean pooling + L2 (model chunk palsu, tanpa model nyata) ---


def test_text_embedder_mean_pool_and_l2_determinism(monkeypatch):
    embedder = TextEmbedder(MODEL_NAME)
    fake_model = FakeChunkModel()
    monkeypatch.setattr(embedder, "_load_model", lambda: fake_model)

    # Determinisme: input sama → vektor identik.
    first = embedder.encode(["alpha beta gamma"])[0]
    second = embedder.encode(["alpha beta gamma"])[0]
    assert first == second
    assert len(first) == DIM
    # L2-normalized: norma ≈ 1.
    assert math.sqrt(sum(v * v for v in first)) == pytest.approx(1.0)

    # Mean pooling antar chunk: "alpha\n\nbeta" (2 chunk) menghasilkan arah yang
    # sama dengan teks satu paragraf berisi kata yang sama (rata-rata vektor
    # chunk ≈ jumlah token yang sama), dan berbeda dari teks berbeda.
    pooled = embedder.encode(["alpha\n\nbeta"])[0]
    single = embedder.encode(["alpha beta"])[0]
    assert cosine(pooled, single) == pytest.approx(1.0, abs=1e-9)
    different = embedder.encode(["perawat rumah sakit"])[0]
    assert cosine(first, different) < 0.5

    # Semua chunk dari semua teks dikirim dalam SATU batch.
    embedder.encode(["alpha\n\nbeta", "gamma delta"])
    assert fake_model.batches[-1] == ["alpha", "beta", "gamma delta"]


def test_text_embedder_encode_empty_input(monkeypatch):
    embedder = TextEmbedder(MODEL_NAME)

    def _boom():  # model tidak boleh dimuat untuk input kosong
        raise AssertionError("model tidak seharusnya dimuat")

    monkeypatch.setattr(embedder, "_load_model", _boom)
    assert embedder.encode([]) == []


def test_get_embedder_is_lazy_singleton_per_model():
    first = embedder_module.get_embedder("model-a")
    second = embedder_module.get_embedder("model-a")
    other = embedder_module.get_embedder("model-b")
    assert first is second  # muat sekali per model_name
    assert first is not other  # kunci per model
    assert isinstance(first, TextEmbedder)
    embedder_module._EMBEDDER_CACHE.clear()  # bersihkan cache antar test


# --- similarity.cosine ---


def test_cosine_orthogonal_identical_and_zero_vector():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert cosine(a, b) == 0.0  # ortogonal
    assert cosine(a, a) == pytest.approx(1.0)  # identik
    assert cosine([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]) == 0.0  # vektor nol
    assert cosine([], []) == 0.0
    # Anti-paralel → -1 (dijepit ke rentang [-1, 1]).
    assert cosine([1.0, 2.0], [-1.0, -2.0]) == pytest.approx(-1.0)


# --- embedding_service.embed_cv / embed_job ---


def test_embed_cv_skips_unconfirmed_disabled_deleted(db_session, monkeypatch):
    monkeypatch.setattr(embedding_service, "get_embedder", _fake_factory)
    user = _seed_user(db_session, "gate@example.dev")

    cv_unconfirmed = _seed_cv(db_session, user, confirmed=False)
    cv_no_payload = _seed_cv(db_session, user, payload=None)
    cv_deleted = _seed_cv(db_session, user, deleted=True)
    cv_confirmed = _seed_cv(db_session, user)  # kontrol: layak

    settings = _svc_settings()
    for cv in (cv_unconfirmed, cv_no_payload, cv_deleted):
        embedding_service.embed_cv(db_session, cv.id, settings)
    assert db_session.scalars(select(CvEmbedding)).all() == []

    # Fitur mati → skip walau CV terkonfirmasi.
    embedding_service.embed_cv(db_session, cv_confirmed.id, _svc_settings(embeddings_enabled=False))
    assert db_session.scalars(select(CvEmbedding)).all() == []

    # Layak → baris tercipta dengan model & text_kind benar.
    embedding_service.embed_cv(db_session, cv_confirmed.id, settings)
    rows = db_session.scalars(select(CvEmbedding)).all()
    assert len(rows) == 1
    assert rows[0].cv_id == cv_confirmed.id
    assert rows[0].model == MODEL_NAME
    assert rows[0].text_kind == "profile"
    assert len(rows[0].embedding) == DIM


def test_embed_cv_replaces_row_not_duplicate(db_session, monkeypatch):
    monkeypatch.setattr(embedding_service, "get_embedder", _fake_factory)
    user = _seed_user(db_session, "upsert@example.dev")
    cv = _seed_cv(db_session, user)
    settings = _svc_settings()

    embedding_service.embed_cv(db_session, cv.id, settings)
    embedding_service.embed_cv(db_session, cv.id, settings)
    rows = db_session.scalars(select(CvEmbedding)).all()
    assert len(rows) == 1  # upsert: timpa, bukan duplikat

    # Baris model LAMA tidak tersentuh — retensi multi-versi.
    db_session.add(
        CvEmbedding(
            cv_id=cv.id,
            model="model-lama-v0",
            text_kind="profile",
            embedding=FakeTextEmbedder(MODEL_NAME).encode(["lama"])[0],
        )
    )
    db_session.commit()
    embedding_service.embed_cv(db_session, cv.id, settings)
    rows = db_session.scalars(select(CvEmbedding)).all()
    assert {row.model for row in rows} == {"model-lama-v0", MODEL_NAME}
    assert len(rows) == 2


def test_embed_job_creates_and_replaces_row(db_session, monkeypatch):
    monkeypatch.setattr(embedding_service, "get_embedder", _fake_factory)
    hr = _seed_user(db_session, "hr-embed@example.dev", role="hr")
    company = _seed_company(db_session, hr)
    job = _seed_job(db_session, hr, company, status="active")
    settings = _svc_settings()

    embedding_service.embed_job(db_session, job.id, settings)
    rows = db_session.scalars(select(JobEmbedding)).all()
    assert len(rows) == 1
    assert rows[0].job_id == job.id
    assert rows[0].model == MODEL_NAME
    assert rows[0].text_kind == "job"
    assert len(rows[0].embedding) == DIM

    # Re-embed (misal konten berubah) → tetap satu baris.
    embedding_service.embed_job(db_session, job.id, settings)
    assert len(db_session.scalars(select(JobEmbedding)).all()) == 1


# --- Hook API: confirm CV & publish/update lowongan (embedder palsu) ---


def _make_client(db_engine, monkeypatch, *, embeddings_enabled=True, factory=_fake_factory):
    """App test ala conftest `client`, tapi embeddings_enabled dikontrol +
    get_embedder dipalsukan — hook M3 aktif tanpa model nyata."""
    monkeypatch.setattr(embedding_service, "get_embedder", factory)
    settings = Settings(
        app_env="test",
        log_level="WARNING",
        cors_origins=["http://test"],
        secret_key="test-secret-key-not-for-production-0123456789abcdef",
        uploads_dir=f"test_uploads_emb_{uuid.uuid4().hex[:8]}",
        embeddings_enabled=embeddings_enabled,
    )
    app = create_app(settings)
    session_factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    return TestClient(app)


def test_confirm_hook_creates_cv_embedding(db_engine, monkeypatch):
    with _make_client(db_engine, monkeypatch) as client:
        reg, cand_headers = make_candidate(client)
        cv = upload_cv(client, cand_headers, make_multiline_pdf(CV_LINES))
        data = get_extraction(client, cand_headers, cv["id"])
        assert data["payload"] is not None

        resp = client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=cand_headers)
        assert resp.status_code == 200, resp.text

        db = Session(bind=db_engine)
        try:
            rows = db.scalars(select(CvEmbedding)).all()
            assert len(rows) == 1
            assert str(rows[0].cv_id) == cv["id"]
            assert rows[0].model == client.app.state.settings.embedding_model
            assert rows[0].text_kind == "profile"
            assert len(rows[0].embedding) == DIM
        finally:
            db.close()
        assert reg["user"]["role"] == "candidate"  # sanity registrasi


def test_confirm_hook_failure_does_not_break_confirmation(db_engine, monkeypatch):
    def _boom_factory(model_name: str):
        raise RuntimeError("model gagal dimuat (simulasi)")

    with _make_client(db_engine, monkeypatch, factory=_boom_factory) as client:
        _, headers = make_candidate(client)
        cv = upload_cv(client, headers, make_multiline_pdf(CV_LINES))
        resp = client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=headers)
        # Konfirmasi tetap sukses walau embedding gagal (guarded hook).
        assert resp.status_code == 200, resp.text
        assert resp.json()["confirmed_at"] is not None

        db = Session(bind=db_engine)
        try:
            assert db.scalars(select(CvEmbedding)).all() == []
        finally:
            db.close()


def test_publish_and_update_hooks_manage_job_embedding(db_engine, monkeypatch):
    with _make_client(db_engine, monkeypatch) as client:
        _, headers, _ = make_hr_with_company(client)
        job = create_job(client, headers)  # draft: belum ada embedding

        db = Session(bind=db_engine)
        try:
            assert db.scalars(select(JobEmbedding)).all() == []
        finally:
            db.close()

        # Publish → hook menulis vektor lowongan.
        resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=headers)
        assert resp.status_code == 200, resp.text
        db = Session(bind=db_engine)
        try:
            rows = db.scalars(select(JobEmbedding)).all()
            assert len(rows) == 1
            assert str(rows[0].job_id) == job["id"]
            assert rows[0].model == client.app.state.settings.embedding_model
            assert rows[0].text_kind == "job"
        finally:
            db.close()

        # Update → baris DITIMPA (tetap satu, bukan duplikat).
        payload = {
            "title": "Lead Data Engineer",
            "description": "Memimpin tim data dan merancang pipeline analitik.",
            "responsibilities": "Arsitektur pipeline.",
            "requirements": "SQL, Python, Spark.",
            "skills": [{"name": "Python", "required": True}],
            "employment_type": "full_time",
            "work_mode": "remote",
        }
        resp = client.put(f"/api/v1/hr/jobs/{job['id']}", json=payload, headers=headers)
        assert resp.status_code == 200, resp.text
        db = Session(bind=db_engine)
        try:
            rows = db.scalars(select(JobEmbedding)).all()
            assert len(rows) == 1
        finally:
            db.close()


# --- reembed_all (fungsi level; CLI hanya pembungkus tipis) ---


def test_reembed_all_processes_only_eligible_rows(db_session, monkeypatch):
    monkeypatch.setattr(embedding_service, "get_embedder", _fake_factory)
    candidate = _seed_user(db_session, "cand-reembed@example.dev")
    hr = _seed_user(db_session, "hr-reembed@example.dev", role="hr")
    company = _seed_company(db_session, hr)

    cv_ok = _seed_cv(db_session, candidate)
    _seed_cv(db_session, candidate, confirmed=False)  # tidak terkonfirmasi → skip
    _seed_cv(db_session, candidate, deleted=True)  # dihapus → skip
    job_active = _seed_job(db_session, hr, company, status="active")
    job_paused = _seed_job(db_session, hr, company, status="paused")
    _seed_job(db_session, hr, company, status="draft")  # draft → skip
    _seed_job(db_session, hr, company, status="active", deleted=True)  # dihapus → skip

    summary = embedding_service.reembed_all(_session_factory(db_session), _svc_settings())

    assert summary["cvs_eligible"] == 1
    assert summary["cvs_embedded"] == 1
    assert summary["jobs_eligible"] == 2
    assert summary["jobs_embedded"] == 2
    assert summary["errors"] == 0

    cv_rows = db_session.scalars(select(CvEmbedding)).all()
    assert [row.cv_id for row in cv_rows] == [cv_ok.id]
    job_rows = db_session.scalars(select(JobEmbedding)).all()
    assert {row.job_id for row in job_rows} == {job_active.id, job_paused.id}


def test_reembed_all_respects_guard_and_force_bypass(db_session, monkeypatch):
    monkeypatch.setattr(embedding_service, "get_embedder", _fake_factory)
    candidate = _seed_user(db_session, "cand-guard@example.dev")
    hr = _seed_user(db_session, "hr-guard@example.dev", role="hr")
    company = _seed_company(db_session, hr)
    cv = _seed_cv(db_session, candidate)
    job = _seed_job(db_session, hr, company, status="active")
    factory = _session_factory(db_session)

    # Guard standar: embeddings_enabled=False → tidak ada baris ditulis.
    summary = embedding_service.reembed_all(factory, _svc_settings(embeddings_enabled=False))
    assert summary["cvs_eligible"] == 1 and summary["cvs_embedded"] == 0
    assert summary["jobs_eligible"] == 1 and summary["jobs_embedded"] == 0
    assert db_session.scalars(select(CvEmbedding)).all() == []
    assert db_session.scalars(select(JobEmbedding)).all() == []

    # --force: bypass guard → kedua baris terisi.
    summary = embedding_service.reembed_all(
        factory, _svc_settings(embeddings_enabled=False), force=True
    )
    assert summary["cvs_embedded"] == 1
    assert summary["jobs_embedded"] == 1
    assert len(db_session.scalars(select(CvEmbedding)).all()) == 1
    assert len(db_session.scalars(select(JobEmbedding)).all()) == 1
    assert cv.id and job.id  # pemakaian variabel agar jelas baris ini miliknya
