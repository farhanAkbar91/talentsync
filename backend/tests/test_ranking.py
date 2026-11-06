"""Test M9 — ranking & perbandingan pelamar (HR): urutan skor, CV belum
terkonfirmasi selalu terakhir dengan overall None, persist match_results,
idempoten recompute, cross-company 404, compare, RBAC.

Semua skor memakai embedder PALSU deterministik (bag-of-words hash dari
tests.test_embedding) — TIDAK memuat model sungguhan. Kandidat kuat (CV analis
data: SQL+Python) dijamin mengungguli kandidat lemah (CV barista) lewat faktor
skill_coverage + experience yang deterministik.
"""

import uuid
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db, get_session_factory
from app.main import create_app
from app.models.ai import MatchResult
from app.models.application import Application
from app.models.cv import CV
from app.services import embedding_service
from tests.helpers import create_job, make_candidate, make_hr_with_company
from tests.test_embedding import _fake_factory, _svc_settings
from tests.test_extraction_api import get_extraction, make_multiline_pdf, upload_cv

# CV KUAT — analisis data: SQL & Python (wajib lowongan) + pengalaman relevan.
CV_LINES_STRONG = [
    "Andi Pratama - analis data",
    "andi.pratama@example.dev | Jakarta | +62 8121-1111-1111",
    "RINGKASAN",
    "Data Analyst dengan pengalaman SQL, Python, dan pandas.",
    "PENGALAMAN",
    "Data Analyst - PT Data Cerdas (2024-01 - sekarang)",
    "- Membuat laporan analisa data dengan SQL dan Python.",
    "PENDIDIKAN",
    "S1 Statistik, Universitas A (2020-2024), IPK 3.40",
    "KEAHLIAN",
    "SQL, Python, pandas, Excel, Tableau",
]

# CV LEMAH — barista: tanpa skill wajib lowongan, pengalaman tak relevan.
CV_LINES_WEAK = [
    "Bella Kusuma - barista senior",
    "bella.kusuma@example.dev | Bandung | +62 8121-2222-2222",
    "RINGKASAN",
    "Barista senior dengan pengalaman espresso dan latte art.",
    "PENGALAMAN",
    "Barista Senior - Kafe Enak (2023-01 - sekarang)",
    "- Menyajikan kopi dan mengelola kasir harian.",
    "PENDIDIKAN",
    "S1 Manajemen, Universitas B (2019-2023), IPK 3.10",
    "KEAHLIAN",
    "Kopi, Espresso, Latte Art, Kasir",
]

JOB_PAYLOAD = dict(
    title="Data Analyst Senior",
    description="Menganalisa data penjualan dan membangun dashboard. Pengalaman 2+ tahun.",
    requirements="Mahir SQL dan Python.",
    responsibilities="Laporan analisa mingguan.",
    skills=[
        {"name": "SQL", "required": True},
        {"name": "Python", "required": True},
        {"name": "Tableau", "required": False},
    ],
)


def _make_ranking_client(db_engine, monkeypatch) -> TestClient:
    """Client ala conftest.client, tapi embedding aktif + embedder palsu."""
    monkeypatch.setattr(embedding_service, "get_embedder", _fake_factory)
    settings = _svc_settings(uploads_dir=f"test_uploads_rank_{uuid.uuid4().hex[:8]}")
    app = create_app(settings)
    factory: sessionmaker[Session] = sessionmaker(
        bind=db_engine, autoflush=False, expire_on_commit=False
    )

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: factory
    return TestClient(app)


def _candidate_with_confirmed_cv(client: TestClient, lines: list[str]) -> tuple[dict, dict, dict]:
    reg, headers = make_candidate(client)
    cv = upload_cv(client, headers, make_multiline_pdf(lines))
    get_extraction(client, headers, cv["id"])
    resp = client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=headers)
    assert resp.status_code == 200, resp.text
    return reg, headers, cv


def _apply(client: TestClient, headers: dict, job_id: str) -> dict:
    resp = client.post(f"/api/v1/jobs/{job_id}/apply", json={}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@contextmanager
def _ranking_context(db_engine, seeded_taxonomy, monkeypatch):
    """Lowongan aktif SQL+Python + dua pelamar (kuat & lemah) + HR pemilik.

    Menghasilkan (client, hr_headers, app_strong, app_weak, job) — app_* adalah
    respons apply (kontrak {id, job_id, status, cover_letter})."""
    with _make_ranking_client(db_engine, monkeypatch) as client:
        _reg, hr_headers, _company = make_hr_with_company(client)
        job = create_job(client, hr_headers, **JOB_PAYLOAD)
        resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=hr_headers)
        assert resp.status_code == 200, resp.text

        _reg_a, strong_headers, _cv_strong = _candidate_with_confirmed_cv(client, CV_LINES_STRONG)
        _reg_b, weak_headers, _cv_weak = _candidate_with_confirmed_cv(client, CV_LINES_WEAK)
        app_strong = _apply(client, strong_headers, job["id"])
        app_weak = _apply(client, weak_headers, job["id"])
        yield client, hr_headers, app_strong, app_weak, job


# =====================================================================
# 1. Ranking
# =====================================================================


class TestRanking:
    def test_ranking_order_skills_and_persistence(
        self, db_engine, seeded_taxonomy, monkeypatch, db_session
    ):
        with _ranking_context(db_engine, seeded_taxonomy, monkeypatch) as (
            client,
            hr_headers,
            app_strong,
            app_weak,
            job,
        ):
            resp = client.get(f"/api/v1/hr/jobs/{job['id']}/ranking", headers=hr_headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert set(body) == {"job_id", "model_version", "computed_at", "total", "items"}
            assert body["job_id"] == job["id"]
            assert body["total"] == 2
            assert body["model_version"].startswith("m4v1|emb:fake-model-untuk-tes|")

            items = body["items"]
            assert len(items) == 2
            first, second = items
            assert set(first) == {
                "application_id",
                "candidate_user_id",
                "candidate_name",
                "cv_id",
                "status",
                "overall",
                "label",
                "factors",
                "matched_required",
                "total_required",
                "matched_skills",
                "missing_critical",
                "model_version",
                "reason",
            }

            # Kandidat kuat (SQL+Python terpenuhi) di atas kandidat lemah.
            assert first["application_id"] == app_strong["id"]
            assert second["application_id"] == app_weak["id"]
            assert first["overall"] > second["overall"]
            assert 0.0 <= first["overall"] <= 100.0
            assert set(first["factors"]) == {
                "semantic",
                "skill_coverage",
                "experience",
                "education",
            }
            assert first["matched_required"] == 2
            assert first["total_required"] == 2
            assert "SQL" in first["matched_skills"] and "Python" in first["matched_skills"]
            assert len(first["matched_skills"]) <= 5
            assert first["label"] in ("Sangat Cocok", "Cocok", "Cukup", "Kurang")
            assert first["reason"] is None

            # Kandidat lemah: kedua skill wajib hilang (kritis), tanpa matched.
            assert second["matched_required"] == 0
            assert second["total_required"] == 2
            assert second["missing_critical"] == 2
            assert second["matched_skills"] == []

            # Persist: dua baris match_results (per CV lamaran, model aktif) —
            # cv_id lamaran konsisten dengan yang dilaporkan item ranking.
            rows = db_session.scalars(
                select(MatchResult).where(MatchResult.job_id == uuid.UUID(job["id"]))
            ).all()
            assert {str(row.cv_id) for row in rows} == {first["cv_id"], second["cv_id"]}
            assert first["cv_id"] is not None and second["cv_id"] is not None
            assert {row.model_version for row in rows} == {body["model_version"]}

    def test_ranking_unconfirmed_cv_last_with_none_score(
        self, db_engine, seeded_taxonomy, monkeypatch, db_session
    ):
        with _ranking_context(db_engine, seeded_taxonomy, monkeypatch) as (
            client,
            hr_headers,
            app_strong,
            app_weak,
            job,
        ):
            # Pelamar ketiga: CV dikonfirmasi saat apply, LALU status konfirmasi
            # dicabut (simulasi alur konfirmasi ulang yang belum selesai).
            _reg_c, cand_c_headers, _cv_c = _candidate_with_confirmed_cv(client, CV_LINES_STRONG)
            app_c = _apply(client, cand_c_headers, job["id"])

            app_c_row = db_session.get(Application, uuid.UUID(app_c["id"]))
            cv_row = db_session.get(CV, app_c_row.cv_id)
            cv_row.extraction.confirmed_at = None
            db_session.commit()

            resp = client.get(f"/api/v1/hr/jobs/{job['id']}/ranking", headers=hr_headers)
            assert resp.status_code == 200, resp.text
            items = resp.json()["items"]
            assert resp.json()["total"] == 3
            assert len(items) == 3

            last = items[-1]
            assert last["application_id"] == app_c["id"]
            assert last["overall"] is None
            assert last["label"] is None
            assert last["factors"] is None
            assert last["matched_skills"] == []
            assert last["matched_required"] == 0
            assert last["missing_critical"] == 0
            assert last["reason"] == "CV belum terkonfirmasi"
            # Dua pelamar berskor tetap di depan dan terurut DESC.
            assert items[0]["overall"] >= items[1]["overall"] > 0.0

            # Tak ada MatchResult untuk CV tak terkonfirmasi.
            rows = db_session.scalars(
                select(MatchResult).where(MatchResult.job_id == uuid.UUID(job["id"]))
            ).all()
            assert {str(row.cv_id) for row in rows} == {items[0]["cv_id"], items[1]["cv_id"]}

    def test_ranking_recompute_idempotent(
        self, db_engine, seeded_taxonomy, monkeypatch, db_session
    ):
        with _ranking_context(db_engine, seeded_taxonomy, monkeypatch) as (
            client,
            hr_headers,
            _app_strong,
            _app_weak,
            job,
        ):
            first = client.get(f"/api/v1/hr/jobs/{job['id']}/ranking", headers=hr_headers).json()
            second = client.get(f"/api/v1/hr/jobs/{job['id']}/ranking", headers=hr_headers).json()

            assert second["model_version"] == first["model_version"]
            assert second["total"] == first["total"]
            assert [(i["application_id"], i["overall"]) for i in second["items"]] == [
                (i["application_id"], i["overall"]) for i in first["items"]
            ]
            # Replace per (cv_id, job_id, model_version) — tidak menumpuk baris.
            rows = db_session.scalars(
                select(MatchResult).where(MatchResult.job_id == uuid.UUID(job["id"]))
            ).all()
            assert len(rows) == 2

    def test_ranking_empty_job_and_missing_job(self, db_engine, seeded_taxonomy, monkeypatch):
        with _make_ranking_client(db_engine, monkeypatch) as client:
            _reg, hr_headers, _company = make_hr_with_company(client)
            job = create_job(client, hr_headers)
            resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=hr_headers)
            assert resp.status_code == 200

            # Belum ada pelamar → 200 kosong (tanpa sentuh vektor lowongan).
            resp = client.get(f"/api/v1/hr/jobs/{job['id']}/ranking", headers=hr_headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["total"] == 0
            assert body["items"] == []

            # Job milik orang lain / tidak ada → 404.
            _reg2, hr_b_headers, _company_b = make_hr_with_company(client, company_name="PT Lain")
            resp = client.get(f"/api/v1/hr/jobs/{job['id']}/ranking", headers=hr_b_headers)
            assert resp.status_code == 404
            resp = client.get(f"/api/v1/hr/jobs/{uuid.uuid4()}/ranking", headers=hr_headers)
            assert resp.status_code == 404

    def test_ranking_rbac(self, db_engine, seeded_taxonomy, monkeypatch):
        with _make_ranking_client(db_engine, monkeypatch) as client:
            _reg, hr_headers, _company = make_hr_with_company(client)
            job = create_job(client, hr_headers)

            _reg2, cand_headers, _cv = _candidate_with_confirmed_cv(client, CV_LINES_STRONG)
            resp = client.get(f"/api/v1/hr/jobs/{job['id']}/ranking", headers=cand_headers)
            assert resp.status_code == 403
            assert resp.json()["error"]["code"] == "FORBIDDEN"
            resp = client.get(f"/api/v1/hr/jobs/{job['id']}/ranking")
            assert resp.status_code == 401

            resp = client.get(f"/api/v1/hr/jobs/{job['id']}/compare", headers=cand_headers)
            assert resp.status_code == 403
            resp = client.get(f"/api/v1/hr/jobs/{job['id']}/compare")
            assert resp.status_code == 401


# =====================================================================
# 2. Compare
# =====================================================================


class TestCompare:
    def test_compare_both_sides_full_detail(self, db_engine, seeded_taxonomy, monkeypatch):
        with _ranking_context(db_engine, seeded_taxonomy, monkeypatch) as (
            client,
            hr_headers,
            app_strong,
            app_weak,
            job,
        ):
            ranking = client.get(f"/api/v1/hr/jobs/{job['id']}/ranking", headers=hr_headers).json()
            url = f"/api/v1/hr/jobs/{job['id']}/compare?ids={app_strong['id']},{app_weak['id']}"
            resp = client.get(url, headers=hr_headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert set(body) == {"a", "b"}

            by_rank = {item["application_id"]: item for item in ranking["items"]}
            side_a = body["a"]  # id pertama query → sisi a (bukan berdasar skor)
            side_b = body["b"]
            assert side_a["application_id"] == app_strong["id"]
            assert side_b["application_id"] == app_weak["id"]
            # Skor konsisten dengan ranking (blok skor yang sama).
            assert side_a["overall"] == by_rank[app_strong["id"]]["overall"]
            assert side_b["overall"] == by_rank[app_weak["id"]]["overall"]
            assert side_a["overall"] > side_b["overall"]

            # Detail penuh di sisi compare.
            assert side_a["matched_skills"], "detail matched tidak dipangkas 5"
            for skill in side_a["matched_skills"]:
                assert set(skill) == {"name", "display", "required", "match_type", "evidence"}
            for skill in side_b["missing_skills"]:
                assert set(skill) == {"name", "display", "required", "severity"}
            assert side_b["missing_critical"] == 2
            assert side_a["explanation"]
            for side in (side_a, side_b):
                assert set(side) == {
                    "application_id",
                    "candidate_user_id",
                    "candidate_name",
                    "cv_id",
                    "status",
                    "overall",
                    "label",
                    "factors",
                    "matched_required",
                    "total_required",
                    "matched_skills",
                    "missing_skills",
                    "missing_critical",
                    "top_experiences",
                    "explanation",
                    "reason",
                }

    def test_compare_order_flexible(self, db_engine, seeded_taxonomy, monkeypatch):
        """Urutan query ditukar → a/b ikut ditukar (bukan urut skor)."""
        with _ranking_context(db_engine, seeded_taxonomy, monkeypatch) as (
            client,
            hr_headers,
            app_strong,
            app_weak,
            job,
        ):
            url = f"/api/v1/hr/jobs/{job['id']}/compare?ids={app_weak['id']},{app_strong['id']}"
            body = client.get(url, headers=hr_headers).json()
            assert body["a"]["application_id"] == app_weak["id"]
            assert body["b"]["application_id"] == app_strong["id"]

    def test_compare_validation_and_404(self, db_engine, seeded_taxonomy, monkeypatch):
        with _ranking_context(db_engine, seeded_taxonomy, monkeypatch) as (
            client,
            hr_headers,
            app_strong,
            app_weak,
            job,
        ):
            base = f"/api/v1/hr/jobs/{job['id']}/compare"

            # Id sama dua kali → 400.
            resp = client.get(
                f"{base}?ids={app_strong['id']},{app_strong['id']}", headers=hr_headers
            )
            assert resp.status_code == 400
            # Bukan 2 UUID → 400.
            resp = client.get(f"{base}?ids={app_strong['id']}", headers=hr_headers)
            assert resp.status_code == 400
            resp = client.get(f"{base}?ids=bukan-uuid,juga-bukan", headers=hr_headers)
            assert resp.status_code == 400

            # Lamaran lowongan lain (milik HR yang sama) → 404.
            job2 = create_job(client, hr_headers, title="Data Analyst Junior")
            resp = client.post(f"/api/v1/hr/jobs/{job2['id']}/publish", headers=hr_headers)
            assert resp.status_code == 200
            _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client, CV_LINES_STRONG)
            other_app = _apply(client, cand_headers, job2["id"])
            resp = client.get(
                f"{base}?ids={app_strong['id']},{other_app['id']}", headers=hr_headers
            )
            assert resp.status_code == 404

            # Lowongan milik perusahaan lain → 404.
            _reg2, hr_b_headers, _company_b = make_hr_with_company(client, company_name="PT Lain")
            resp = client.get(
                f"{base}?ids={app_strong['id']},{app_weak['id']}", headers=hr_b_headers
            )
            assert resp.status_code == 404
