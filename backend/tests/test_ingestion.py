"""Uji pipeline ingestion lowongan eksternal (Task 5).

Cakupan:
- konektor per sumber (RemoteOK legal-skip, Remotive, Arbeitnow) — SEMUA lewat
  httpx.MockTransport, TIDAK ADA panggilan jaringan sungguhan;
- normalizer (strip HTML, slug→external_id, tags→skills, skip item rusak);
- ingest_service (insert, dedupe idempoten, last_seen_at, dry-run, normalisasi
  skill matched + raw, identitas sistem idempoten);
- paritas migrasi 0013 ↔ model Job (kolom + index parsial).

Fixture API: konstanta modul berisi contoh realistis kecil per sumber, dibangun
dari bentuk field API terdokumentasi (docs/03-final-scope-and-feasibility.md §3).
"""

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy import func, select

from app.core.config import Settings
from app.ingestion import ingest_service, normalizer, sources
from app.models.company import Company
from app.models.job import Job
from app.models.skill import JobSkill
from app.models.user import User

# --- Fixture API per sumber (bentuk field sesuai probe docs/03 §3) ---

# RemoteOK: elemen PERTAMA adalah notice legal (wajib dilewati), sisanya
# lowongan: slug/id, position, company, location, description, url, tags, date/epoch.
REMOTEOK_SAMPLE = [
    {"legal": ["<p>legal notice</p>"], "id": "legal", "slug": "legal"},
    {
        "slug": "senior-python-engineer",
        "id": 31337,
        "position": "Senior Python Engineer",
        "company": "Acme Remote Co",
        "location": "Remote Worldwide",
        "description": "<p>We need a <b>Python</b> pro — remote first &amp; friendly.</p>",
        "url": "https://remoteok.com/remote-jobs/31337-senior-python-engineer",
        "tags": ["python", "django", "python", "postgresql"],
        "date": "2026-11-05T10:00:00",
        "epoch": 1793959200,
    },
    {
        "slug": "no-title-job",
        "id": 31338,
        "company": "Ghost Co",
        "description": "<p>lowongan tanpa judul</p>",
        "url": "https://remoteok.com/remote-jobs/31338",
        "tags": [],
        "epoch": 1793959201,
    },
]

# Remotive: {job-count, jobs[].{id, title, company_name, candidate_required_location,
# description, url, tags, publication_date}}.
REMOTIVE_SAMPLE = {
    "job-count": 1,
    "jobs": [
        {
            "id": 5512345,
            "url": "https://remotive.com/remote-jobs/qa/qa-engineer",
            "title": "QA Engineer",
            "company_name": "Beta Softworks",
            "category": "Quality Assurance",
            "candidate_required_location": "Worldwide",
            "description": "<div>Test all the things &mdash; carefully.</div>",
            "publication_date": "2026-11-02T08:30:00",
            "tags": ["qa", "selenium"],
        }
    ],
}

# Arbeitnow: {meta, data[].{slug, company_name, title, description, remote, url,
# tags, created_at}} — 300 lowongan/halaman.
ARBEITNOW_SAMPLE = {
    "meta": {"total": 2, "page": 1},
    "data": [
        {
            "slug": "backend-engineer-berlin-4711",
            "company_name": "Gamma GmbH",
            "title": "Backend Engineer (m/f/d)",
            "description": "<p>Go &amp; Kubernetes.<br>Hybrid Berlin.</p>",
            "remote": True,
            "url": "https://www.arbeitnow.com/view/4711",
            "tags": ["go", "kubernetes"],
            "created_at": "2026-11-01T09:00:00",
        },
        {
            "slug": "office-manager-4712",
            "company_name": "Gamma GmbH",
            "title": "Office Manager",
            "description": "Onsite role.",
            "remote": False,
            "url": "https://www.arbeitnow.com/view/4712",
            "tags": ["office"],
            "created_at": "2026-11-01T09:05:00",
        },
    ],
}

MIGRATION_0013_PATH = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0013_job_source_tracking.py"
)


def _json_transport(payload) -> httpx.MockTransport:
    """Transport test: selalu 200 + body JSON fixture."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def _broken_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("koneksi gagal (simulasi test)")

    return httpx.MockTransport(handler)


@pytest.fixture()
def ingest_settings() -> Settings:
    """Settings ingestion: embedding MATI (unit test ringan), tanpa secret asli."""
    return Settings(
        app_env="test",
        log_level="WARNING",
        cors_origins=["http://test"],
        secret_key="test-secret-key-not-for-production-0123456789abcdef",
        uploads_dir="test_uploads",
        embeddings_enabled=False,
    )


# --- Konektor (sources.py) ---


class TestKonektorSumber:
    def test_remoteok_skip_legal_dan_map_field(self):
        items = sources.fetch_remoteok(transport=_json_transport(REMOTEOK_SAMPLE))
        # Notice legal terlewati di konektor; item tanpa judul baru dibuang oleh
        # normalizer (pemisahan tanggung jawab).
        assert len(items) == 2
        item = items[0]
        assert item["external_id"] == "senior-python-engineer"  # slug menang atas id
        assert item["title"] == "Senior Python Engineer"  # position → title
        assert item["company"] == "Acme Remote Co"
        # Atribusi wajib (docs/03 §3): url balik remoteok.com dipertahankan.
        assert item["url"] == "https://remoteok.com/remote-jobs/31337-senior-python-engineer"
        assert item["tags"] == ["python", "django", "python", "postgresql"]
        assert item["posted_at"] == "2026-11-05T10:00:00"
        assert item["remote"] is True

    def test_remotive_map_field(self):
        items = sources.fetch_remotive(transport=_json_transport(REMOTIVE_SAMPLE))
        assert len(items) == 1
        item = items[0]
        assert item["external_id"] == "5512345"
        assert item["title"] == "QA Engineer"
        assert item["company"] == "Beta Softworks"  # company_name → company
        assert item["location"] == "Worldwide"  # candidate_required_location → location
        assert item["remote"] is True

    def test_arbeitnow_map_field(self):
        items = sources.fetch_arbeitnow(transport=_json_transport(ARBEITNOW_SAMPLE))
        assert [i["external_id"] for i in items] == [
            "backend-engineer-berlin-4711",
            "office-manager-4712",
        ]
        assert [i["remote"] for i in items] == [True, False]  # flag per item
        assert items[0]["company"] == "Gamma GmbH"
        assert items[0]["posted_at"] == "2026-11-01T09:00:00"

    def test_limit_slice_lokal_dan_param_remotive(self):
        recorded: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            recorded.append(str(request.url))
            return httpx.Response(200, json=REMOTIVE_SAMPLE)

        remoteok = sources.fetch_remoteok(transport=_json_transport(REMOTEOK_SAMPLE), limit=1)
        assert len(remoteok) == 1  # dipotong lokal, URL API tidak berubah
        assert recorded == []  # remoteok test tidak menyentuh transport lain

        remotive = sources.fetch_remotive(transport=httpx.MockTransport(handler), limit=1)
        assert len(remotive) == 1
        assert recorded == [f"{sources.REMOTIVE_API_URL}?limit=1"]  # limit via param API

    def test_error_jaringan_tidak_raise(self):
        # Satu sumber mati → list kosong + warning, TIDAK exception ke pemanggil.
        for fetch in (sources.fetch_remoteok, sources.fetch_remotive, sources.fetch_arbeitnow):
            assert fetch(transport=_broken_transport()) == []

    def test_status_non_200_ditoleransi(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        transport = httpx.MockTransport(handler)
        for fetch in (sources.fetch_remoteok, sources.fetch_remotive, sources.fetch_arbeitnow):
            assert fetch(transport=transport) == []

    def test_oversize_ditolak(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sources, "MAX_RESPONSE_BYTES", 10)  # sanity jadi ketat
        for fetch in (sources.fetch_remoteok, sources.fetch_remotive, sources.fetch_arbeitnow):
            payload = (
                REMOTEOK_SAMPLE
                if fetch is sources.fetch_remoteok
                else (REMOTIVE_SAMPLE if fetch is sources.fetch_remotive else ARBEITNOW_SAMPLE)
            )
            assert fetch(transport=_json_transport(payload)) == []

    def test_json_rusak_ditoleransi(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>bukan json</html>")

        transport = httpx.MockTransport(handler)
        for fetch in (sources.fetch_remoteok, sources.fetch_remotive, sources.fetch_arbeitnow):
            assert fetch(transport=transport) == []


# --- Normalizer ---


class TestNormalizer:
    def test_strip_html_entity_dan_baris(self):
        text = normalizer.strip_html(
            "<p>Halo &amp; selamat</p><div>datang di <b>remote</b> work</div>"
        )
        assert text == "Halo & selamat\ndatang di remote work"
        assert "<" not in text and ">" not in text

    def test_strip_html_encoded_ganda(self):
        # Deskripsi ter-encode ganda: "&lt;b&gt;" setelah unescape → tag → terbuang.
        assert normalizer.strip_html("&lt;b&gt;tebal&lt;/b&gt;") == "tebal"

    def test_strip_html_kosong_dan_cap(self):
        assert normalizer.strip_html(None) == ""
        assert normalizer.strip_html("") == ""
        assert len(normalizer.strip_html("x" * 30_000)) == normalizer.MAX_DESCRIPTION_CHARS

    def test_payload_remoteok_pemetaan_penuh(self):
        # Normalizer makan output konektor (bentuk antara), bukan payload API mentah.
        items = sources.fetch_remoteok(transport=_json_transport(REMOTEOK_SAMPLE))
        payloads = normalizer.to_job_payloads("remoteok", items)
        assert len(payloads) == 1  # item tanpa judul terlewati
        p = payloads[0]
        assert p["source_type"] == "remoteok"
        assert p["external_id"] == "senior-python-engineer"
        assert p["title"] == "Senior Python Engineer"
        assert p["description"] == "We need a Python pro — remote first & friendly."
        # Dedupe tag case-insensitive; semua skill hasil tags = preferred.
        assert p["skills"] == [
            {"name": "python", "required": False},
            {"name": "django", "required": False},
            {"name": "postgresql", "required": False},
        ]
        assert p["work_mode"] == "remote"  # RemoteOK seluruhnya remote
        assert p["employment_type"] is None  # API tidak menyediakan
        assert p["source_url"].startswith("https://remoteok.com/")  # atribusi
        assert p["posted_at"] == datetime(2026, 11, 5, 10, 0)
        assert p["location_text"] == "Remote Worldwide"

    def test_payload_batas_panjang_dan_maks_skill(self):
        raw = [
            {
                "external_id": "cap-1",
                "title": "T" * 300,  # cap 200
                "company": "C",
                "description": "ok",
                "url": "https://s.example/x",
                "tags": [f"skill{i}" for i in range(12)],  # cap 10
                "remote": True,
            }
        ]
        (p,) = normalizer.to_job_payloads("remoteok", raw)
        assert len(p["title"]) == normalizer.MAX_TITLE_CHARS
        assert len(p["skills"]) == normalizer.MAX_SKILLS
        assert p["work_mode"] == "remote"

    def test_payload_dedupe_tag_case_insensitive(self):
        raw = [
            {
                "external_id": "x1",
                "title": "Dev",
                "company": "C",
                "tags": ["Python", "PYTHON", "python"],
            }
        ]
        (p,) = normalizer.to_job_payloads("remoteok", raw)
        assert p["skills"] == [{"name": "Python", "required": False}]

    def test_payload_skip_item_tidak_lengkap(self):
        raw = [
            {"external_id": "a", "title": "Ada", "company": "Co", "tags": []},
            {"external_id": "b", "company": "Co"},  # tanpa title
            {"external_id": "c", "title": "T"},  # tanpa company
            {"title": "T", "company": "Co"},  # tanpa external_id
            "bukan-dict",  # tipe asing diabaikan
        ]
        payloads = normalizer.to_job_payloads("remotive", raw)
        assert [p["external_id"] for p in payloads] == ["a"]
        assert normalizer.to_job_payloads("remotive", []) == []
        assert normalizer.to_job_payloads("remotive", None) == []  # total function

    def test_payload_arbeitnow_work_mode_per_item(self):
        items = sources.fetch_arbeitnow(transport=_json_transport(ARBEITNOW_SAMPLE))
        payloads = normalizer.to_job_payloads("arbeitnow", items)
        assert [p["work_mode"] for p in payloads] == ["remote", "onsite"]
        assert payloads[0]["posted_at"] == datetime(2026, 11, 1, 9, 0)
        assert payloads[0]["company"] == "Gamma GmbH"


# --- Ingest service ---


def _get_job(db, source_type: str, external_id: str) -> Job:
    return db.scalar(
        select(Job).where(Job.source_type == source_type, Job.external_id == external_id)
    )


class TestIngestService:
    def _remoteok_items(self) -> list[dict]:
        """Bentuk antara hasil konektor (MockTransport) — bentuk yang diterima ingest."""
        return sources.fetch_remoteok(transport=_json_transport(REMOTEOK_SAMPLE))

    def test_insert_lowongan_aktif_dengan_provenance(
        self, db_session, seeded_taxonomy, ingest_settings
    ):
        result = ingest_service.ingest(
            db_session, ingest_settings, source_type="remoteok", items=self._remoteok_items()
        )
        assert result == {"inserted": 1, "skipped": 0, "seen": 0, "source": "remoteok"}

        job = _get_job(db_session, "remoteok", "senior-python-engineer")
        assert job is not None
        assert job.status == "active"  # lowongan publik langsung tampil
        assert job.title == "Senior Python Engineer"
        assert job.source_url.startswith("https://remoteok.com/")
        assert job.work_mode == "remote"
        assert job.employment_type == "full_time"  # fallback kolom NOT NULL (lihat docstring)
        assert job.location_text == "Remote Worldwide"
        # PG TIMESTAMPTZ mengembalikan datetime aware; SQLite naive.
        # Normalisasi ke UTC sebelum membandingkan (sumber naive = UTC).
        posted = job.posted_at
        if posted.tzinfo is not None:
            posted = posted.astimezone(UTC).replace(tzinfo=None)
        assert posted == datetime(2026, 11, 5, 10, 0)
        assert job.deleted_at is None
        assert job.last_seen_at is not None

        # Identitas sistem: posted_by_user_id & company_id NOT NULL diisi akun sistem.
        system_user = db_session.scalar(
            select(User).where(User.email == ingest_service.INGESTION_SYSTEM_EMAIL)
        )
        assert system_user is not None and system_user.role == "hr"
        assert job.posted_by_user_id == system_user.id
        system_company = db_session.get(Company, job.company_id)
        assert system_company is not None
        assert system_company.name == ingest_service.INGESTION_COMPANY_NAME

        # closing_at = now + INGEST_CLOSING_DAYS (30 hari).
        closing = job.closing_at
        assert closing is not None
        if closing.tzinfo is None:
            closing = closing.replace(tzinfo=UTC)
        delta = closing - datetime.now(UTC)
        assert timedelta(days=29, hours=23) < delta < timedelta(days=31)

    def test_idempoten_run_kedua_tanpa_duplikat(self, db_session, seeded_taxonomy, ingest_settings):
        first = ingest_service.ingest(
            db_session, ingest_settings, source_type="remoteok", items=self._remoteok_items()
        )
        assert first["inserted"] == 1

        second = ingest_service.ingest(
            db_session, ingest_settings, source_type="remoteok", items=self._remoteok_items()
        )
        # Kontrak: inserted=0, skipped & seen = jumlah run pertama.
        assert second["inserted"] == 0
        assert second["skipped"] == 1
        assert second["seen"] == 1

        jobs = db_session.scalars(select(Job).where(Job.source_type == "remoteok")).all()
        assert len(jobs) == 1  # UNIQUE index + cek eksplisit → tanpa duplikat

        # Identitas sistem TIDAK digandakan.
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(User)
                .where(User.email == ingest_service.INGESTION_SYSTEM_EMAIL)
            )
            == 1
        )
        assert (
            db_session.scalar(
                select(func.count())
                .select_from(Company)
                .where(Company.name == ingest_service.INGESTION_COMPANY_NAME)
            )
            == 1
        )

    def test_last_seen_at_diperbarui(self, db_session, seeded_taxonomy, ingest_settings):
        ingest_service.ingest(
            db_session, ingest_settings, source_type="remoteok", items=self._remoteok_items()
        )
        job = _get_job(db_session, "remoteok", "senior-python-engineer")
        old = datetime(2020, 1, 1, tzinfo=UTC)
        job.last_seen_at = old
        db_session.commit()

        ingest_service.ingest(
            db_session, ingest_settings, source_type="remoteok", items=self._remoteok_items()
        )
        db_session.expire_all()  # pastikan dibaca ulang dari DB
        refreshed = _get_job(db_session, "remoteok", "senior-python-engineer")
        seen = refreshed.last_seen_at.replace(tzinfo=UTC)
        assert (seen - old).total_seconds() > 0  # last_seen_at maju

    def test_dry_run_tanpa_tulis(self, db_session, seeded_taxonomy, ingest_settings):
        jobs_before = db_session.scalar(select(func.count()).select_from(Job))
        users_before = db_session.scalar(select(func.count()).select_from(User))

        result = ingest_service.ingest(
            db_session,
            ingest_settings,
            source_type="remotive",
            items=sources.fetch_remotive(transport=_json_transport(REMOTIVE_SAMPLE)),
            dry_run=True,
        )
        assert result == {"inserted": 1, "skipped": 0, "seen": 0, "source": "remotive"}

        db_session.expire_all()
        assert db_session.scalar(select(func.count()).select_from(Job)) == jobs_before == 0
        assert db_session.scalar(select(func.count()).select_from(User)) == users_before == 0

        # Setelah dry-run, ingest sungguhan tetap menganggap item baru.
        real = ingest_service.ingest(
            db_session,
            ingest_settings,
            source_type="remotive",
            items=sources.fetch_remotive(transport=_json_transport(REMOTIVE_SAMPLE)),
        )
        assert real["inserted"] == 1

    def test_normalisasi_skill_matched_dan_raw_disimpan(
        self, db_session, seeded_taxonomy, ingest_settings
    ):
        raw = [
            {
                "slug": "fullstack-dev",
                "id": 7,
                "position": "Fullstack Developer",
                "company": "Delta Tech",
                "description": "<p>Build stuff.</p>",
                "url": "https://remoteok.com/remote-jobs/7",
                "tags": ["python", "SQL", "totally-fake-skill-xyz"],
                "date": "2026-11-05T10:00:00",
            }
        ]
        items = sources.fetch_remoteok(transport=_json_transport(raw))
        ingest_service.ingest(db_session, ingest_settings, source_type="remoteok", items=items)

        job = _get_job(db_session, "remoteok", "fullstack-dev")
        # Baris job_skills HANYA utk nama yang punya padanan kanon (python & sql).
        rows = db_session.scalars(select(JobSkill).where(JobSkill.job_id == job.id)).all()
        slugs = {row.canonical_skill_id for row in rows}
        assert len(rows) == 2 and len(slugs) == 2

        # Nama tanpa padanan tetap hidup di jobs.skills (JSONB) — aturan form HR.
        names = {s["name"].lower() for s in job.skills}
        assert names == {"python", "sql", "totally-fake-skill-xyz"}

    def test_dedupe_per_sumber(self, db_session, seeded_taxonomy, ingest_settings):
        # external_id sama di dua sumber ≠ duplikat: kunci dedupe = (source_type, external_id).
        items = [{"external_id": "same-slug", "title": "Dev", "company": "Co", "tags": []}]
        r1 = ingest_service.ingest(db_session, ingest_settings, source_type="remoteok", items=items)
        r2 = ingest_service.ingest(db_session, ingest_settings, source_type="remotive", items=items)
        assert r1["inserted"] == 1 and r2["inserted"] == 1
        assert (
            db_session.scalar(
                select(func.count()).select_from(Job).where(Job.external_id == "same-slug")
            )
            == 2
        )

    def test_duplikat_dalam_batch_dihitung_skipped(
        self, db_session, seeded_taxonomy, ingest_settings
    ):
        item = {"external_id": "twice", "title": "Dev", "company": "Co", "tags": []}
        result = ingest_service.ingest(
            db_session, ingest_settings, source_type="arbeitnow", items=[item, dict(item)]
        )
        assert result["inserted"] == 1
        assert result["skipped"] == 1
        assert (
            db_session.scalar(
                select(func.count()).select_from(Job).where(Job.external_id == "twice")
            )
            == 1
        )

    def test_sumber_tanpa_item_aman(self, db_session, seeded_taxonomy, ingest_settings):
        # Konektor gagal → items=[] → hasil nol, tanpa error & tanpa tulis.
        result = ingest_service.ingest(
            db_session, ingest_settings, source_type="remoteok", items=[]
        )
        assert result == {"inserted": 0, "skipped": 0, "seen": 0, "source": "remoteok"}
        assert db_session.scalar(select(func.count()).select_from(Job)) == 0


# --- Paritas migrasi 0013 ↔ model ---


def _load_migration_0013():
    spec = importlib.util.spec_from_file_location("mig_0013", MIGRATION_0013_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestParitasMigrasi0013:
    def test_kolom_model_sesuai_0013(self):
        columns = Job.__table__.columns
        external_id = columns["external_id"]
        source_url = columns["source_url"]
        assert isinstance(external_id.type, sa.String)
        assert external_id.type.length == 160
        assert external_id.nullable is True
        assert source_url.type.length == 500
        assert source_url.nullable is True

    def test_index_parsial_model(self):
        index = next(i for i in Job.__table__.indexes if i.name == "uq_jobs_source_external")
        assert index.unique is True
        assert [c.name for c in index.columns] == ["source_type", "external_id"]
        where = str(index.dialect_options["postgresql"]["where"])
        assert "external_id IS NOT NULL" in where and "deleted_at IS NULL" in where

    def test_file_migrasi_0013(self):
        module = _load_migration_0013()
        assert module.revision == "0013"
        assert module.down_revision == "0012"
        text = MIGRATION_0013_PATH.read_text(encoding="utf-8")
        # Kolom + index parsial di upgrade; dibersihkan di downgrade.
        for expected in (
            '"external_id", sa.String(length=160), nullable=True',
            '"source_url", sa.String(length=500), nullable=True',
            '"uq_jobs_source_external"',
            "postgresql_where=sa.text(",
            "external_id IS NOT NULL AND deleted_at IS NULL",
            'op.drop_index("uq_jobs_source_external"',
            'op.drop_column("jobs", "source_url")',
            'op.drop_column("jobs", "external_id")',
        ):
            assert expected in text, f"pola migrasi hilang: {expected}"
