"""Test M9 — lamaran: apply kandidat, daftar milik kandidat, daftar pelamar HR,
transisi status + terminal, RBAC seluruh endpoint lamaran.

Alur memakai API nyata (upload CV → ekstraksi → konfirmasi → apply) dengan
embeddings DISABLED (client conftest) — apply tidak membutuhkan vektor.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models.application import Application
from tests.helpers import create_job, make_candidate, make_hr_with_company
from tests.test_extraction_api import (
    CV_LINES,
    get_extraction,
    make_multiline_pdf,
    upload_cv,
)

# --- Helper alur ---


def _candidate_with_confirmed_cv(client: TestClient) -> tuple[dict, dict, dict]:
    """Kandidat + CV primer TERKONFIRMASI (jalur API nyata)."""
    reg, headers = make_candidate(client)
    cv = upload_cv(client, headers, make_multiline_pdf(CV_LINES))
    get_extraction(client, headers, cv["id"])
    resp = client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=headers)
    assert resp.status_code == 200, resp.text
    return reg, headers, cv


def _apply(client: TestClient, headers: dict, job_id: str, **payload) -> dict:
    resp = client.post(f"/api/v1/jobs/{job_id}/apply", json=payload or {}, headers=headers)
    return {"status_code": resp.status_code, "body": resp.json()}


def _hr_with_active_job(client: TestClient) -> tuple[dict, dict, dict]:
    """HR + perusahaan + lowongan AKTIF (terpublish)."""
    _reg, hr_headers, company = make_hr_with_company(client)
    job = create_job(client, hr_headers)
    resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=hr_headers)
    assert resp.status_code == 200, resp.text
    return hr_headers, company, job


# =====================================================================
# 1. POST /jobs/{job_id}/apply
# =====================================================================


class TestApply:
    def test_apply_happy_path_and_cv_snapshot(self, client, db_session, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)
        _reg, cand_headers, cv = _candidate_with_confirmed_cv(client)

        result = _apply(
            client, cand_headers, job["id"], cover_letter="Saya cocok untuk posisi ini."
        )
        assert result["status_code"] == 201, result["body"]
        body = result["body"]
        assert set(body) == {"id", "job_id", "status", "cover_letter"}
        assert body["job_id"] == job["id"]
        assert body["status"] == "submitted"
        assert body["cover_letter"] == "Saya cocok untuk posisi ini."

        # Snapshot CV: cv_id lamaran = CV primer saat melamar (bukan dinamis).
        row = db_session.scalar(select(Application).where(Application.id == uuid.UUID(body["id"])))
        assert row is not None
        assert row.job_id == uuid.UUID(job["id"])
        assert str(row.cv_id) == cv["id"]

    def test_apply_duplicate_409(self, client, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)
        _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client)

        first = _apply(client, cand_headers, job["id"])
        assert first["status_code"] == 201

        second = _apply(client, cand_headers, job["id"])
        assert second["status_code"] == 409
        assert second["body"]["error"]["code"] == "CONFLICT"
        assert second["body"]["error"]["message"] == "Anda sudah melamar lowongan ini."

        # Kandidat lain masih bisa melamar lowongan yang sama.
        _reg2, cand2_headers, _cv2 = _candidate_with_confirmed_cv(client)
        other = _apply(client, cand2_headers, job["id"])
        assert other["status_code"] == 201

    def test_apply_without_confirmed_cv_400(self, client, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)

        # Belum punya CV sama sekali.
        _reg, cand_headers = make_candidate(client)
        result = _apply(client, cand_headers, job["id"])
        assert result["status_code"] == 400
        assert result["body"]["error"]["code"] == "APPLICATION_UNAVAILABLE"
        assert result["body"]["error"]["message"] == (
            "Konfirmasi CV utama terlebih dahulu sebelum melamar lowongan."
        )

    def test_apply_unconfirmed_primary_400(self, client, seeded_taxonomy):
        """CV primer ada tapi BELUM dikonfirmasi → 400 APPLICATION_UNAVAILABLE."""
        hr_headers, _company, job = _hr_with_active_job(client)
        _reg, cand_headers = make_candidate(client)
        cv = upload_cv(client, cand_headers, make_multiline_pdf(CV_LINES))
        get_extraction(client, cand_headers, cv["id"])
        # Sengaja TIDAK memanggil confirm.

        result = _apply(client, cand_headers, job["id"])
        assert result["status_code"] == 400
        assert result["body"]["error"]["code"] == "APPLICATION_UNAVAILABLE"

    def test_apply_non_active_job_404(self, client, seeded_taxonomy):
        _reg, hr_headers, _company = make_hr_with_company(client)
        job = create_job(client, hr_headers)  # draft
        _reg2, cand_headers, _cv = _candidate_with_confirmed_cv(client)

        result = _apply(client, cand_headers, job["id"])
        assert result["status_code"] == 404
        assert result["body"]["error"]["code"] == "NOT_FOUND"

        # Terpublish → 201; lalu di-pause → 404 untuk kandidat berikutnya.
        resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=hr_headers)
        assert resp.status_code == 200
        result_ok = _apply(client, cand_headers, job["id"])
        assert result_ok["status_code"] == 201

        resp = client.post(f"/api/v1/hr/jobs/{job['id']}/pause", headers=hr_headers)
        assert resp.status_code == 200
        _reg3, cand3_headers, _cv3 = _candidate_with_confirmed_cv(client)
        result_paused = _apply(client, cand3_headers, job["id"])
        assert result_paused["status_code"] == 404

    def test_apply_rbac(self, client, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)

        resp = client.post(f"/api/v1/jobs/{job['id']}/apply", json={}, headers=hr_headers)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN"

        resp = client.post(f"/api/v1/jobs/{job['id']}/apply", json={})
        assert resp.status_code == 401


# =====================================================================
# 2. GET /applications/mine (kandidat)
# =====================================================================


class TestListMine:
    def test_list_mine_sorted_newest_first_with_job_info(self, client, db_session, seeded_taxonomy):
        _reg, hr_headers, company = make_hr_with_company(client)
        job_a = create_job(client, hr_headers, title="Analis Data A", location_text="Jakarta")
        job_b = create_job(client, hr_headers, title="Analis Data B", location_text="Bandung")
        for job in (job_a, job_b):
            resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=hr_headers)
            assert resp.status_code == 200

        _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client)
        first = _apply(client, cand_headers, job_a["id"])
        assert first["status_code"] == 201
        second = _apply(client, cand_headers, job_b["id"], cover_letter="Untuk posisi B.")
        assert second["status_code"] == 201

        # created_at yang sama persis dibuat deterministik: lamaran A dimundurkan.
        app_a = db_session.scalar(
            select(Application).where(Application.id == uuid.UUID(first["body"]["id"]))
        )
        app_a.created_at = datetime.now(UTC) - timedelta(hours=2)
        db_session.commit()

        resp = client.get("/api/v1/applications/mine", headers=cand_headers)
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert len(items) == 2
        # Terbaru dulu: job B (lamaran kedua) di atas.
        assert [item["job_id"] for item in items] == [job_b["id"], job_a["id"]]
        top = items[0]
        assert set(top) == {
            "id",
            "job_id",
            "status",
            "cover_letter",
            "cv_id",
            "job_title",
            "company",
            "job_status",
            "location",
            "created_at",
        }
        assert top["job_title"] == "Analis Data B"
        assert top["company"] == company["name"]
        assert top["job_status"] == "active"
        assert top["location"] == "Bandung"
        assert top["cover_letter"] == "Untuk posisi B."
        assert items[1]["job_title"] == "Analis Data A"
        assert items[1]["job_status"] == "active"

    def test_list_mine_only_own_applications(self, client, db_session, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)
        _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client)
        assert _apply(client, cand_headers, job["id"])["status_code"] == 201

        _reg2, cand2_headers, _cv2 = _candidate_with_confirmed_cv(client)
        resp = client.get("/api/v1/applications/mine", headers=cand2_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_mine_rbac(self, client, seeded_taxonomy):
        _reg, hr_headers, _company = make_hr_with_company(client)

        resp = client.get("/api/v1/applications/mine", headers=hr_headers)
        assert resp.status_code == 403
        resp = client.get("/api/v1/applications/mine")
        assert resp.status_code == 401


# =====================================================================
# 3. GET /applications/job/{job_id} (HR pemilik)
# =====================================================================


class TestHrApplicantList:
    def test_hr_list_applicants_newest_first(self, client, db_session, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)
        reg_a, cand_a_headers, _cv_a = _candidate_with_confirmed_cv(client)
        reg_b, cand_b_headers, _cv_b = _candidate_with_confirmed_cv(client)

        first = _apply(client, cand_a_headers, job["id"])
        second = _apply(client, cand_b_headers, job["id"], cover_letter="Lamaran B.")
        assert first["status_code"] == 201 and second["status_code"] == 201

        # Deterministikkan urutan: lamaran A lebih tua 2 jam.
        app_a = db_session.scalar(
            select(Application).where(Application.id == uuid.UUID(first["body"]["id"]))
        )
        app_a.created_at = datetime.now(UTC) - timedelta(hours=2)
        db_session.commit()

        resp = client.get(f"/api/v1/applications/job/{job['id']}", headers=hr_headers)
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert len(items) == 2
        assert [item["candidate_name"] for item in items] == [
            reg_b["user"]["full_name"],
            reg_a["user"]["full_name"],
        ]
        top = items[0]
        assert set(top) == {
            "id",
            "job_id",
            "status",
            "cover_letter",
            "candidate_user_id",
            "cv_id",
            "updated_at",
            "candidate_name",
            "cv_filename",
            "cv_confirmed",
            "created_at",
        }
        assert top["candidate_name"] == reg_b["user"]["full_name"]
        assert top["status"] == "submitted"
        assert top["cover_letter"] == "Lamaran B."
        assert top["cv_confirmed"] is True
        assert top["cv_filename"] == "cv.pdf"
        assert items[1]["cover_letter"] is None

    def test_hr_list_other_company_404(self, client, seeded_taxonomy):
        _reg, hr_a_headers, _company_a = make_hr_with_company(client)
        job = create_job(client, hr_a_headers)
        resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=hr_a_headers)
        assert resp.status_code == 200

        _reg2, hr_b_headers, _company_b = make_hr_with_company(client, company_name="PT Saingan")
        resp = client.get(f"/api/v1/applications/job/{job['id']}", headers=hr_b_headers)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    def test_hr_list_rbac(self, client, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)

        _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client)
        resp = client.get(f"/api/v1/applications/job/{job['id']}", headers=cand_headers)
        assert resp.status_code == 403
        resp = client.get(f"/api/v1/applications/job/{job['id']}")
        assert resp.status_code == 401


# =====================================================================
# 4. PATCH /applications/{id}/status (HR pemilik)
# =====================================================================


class TestUpdateStatus:
    def _application_id(self, client, cand_headers, job_id: str) -> str:
        result = _apply(client, cand_headers, job_id)
        assert result["status_code"] == 201
        return result["body"]["id"]

    def test_status_flow_then_terminal_409(self, client, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)
        _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client)
        app_id = self._application_id(client, cand_headers, job["id"])
        url = f"/api/v1/applications/{app_id}/status"

        # Maju bertahap: submitted → reviewed → shortlisted → hired.
        for expected in ("reviewed", "shortlisted", "hired"):
            resp = client.patch(url, json={"status": expected}, headers=hr_headers)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert set(body) == {
                "id",
                "job_id",
                "status",
                "cover_letter",
                "candidate_user_id",
                "cv_id",
                "updated_at",
            }
            assert body["status"] == expected
            assert body["id"] == app_id

        # hired TERMINAL: perubahan apa pun → 409.
        for target in ("reviewed", "rejected", "submitted"):
            resp = client.patch(url, json={"status": target}, headers=hr_headers)
            assert resp.status_code == 409
            assert resp.json()["error"]["code"] == "CONFLICT"

    def test_rejected_terminal_409(self, client, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)
        _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client)
        app_id = self._application_id(client, cand_headers, job["id"])
        url = f"/api/v1/applications/{app_id}/status"

        resp = client.patch(url, json={"status": "rejected"}, headers=hr_headers)
        assert resp.status_code == 200
        resp = client.patch(url, json={"status": "shortlisted"}, headers=hr_headers)
        assert resp.status_code == 409

    def test_status_unknown_value_422(self, client, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)
        _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client)
        app_id = self._application_id(client, cand_headers, job["id"])

        resp = client.patch(
            f"/api/v1/applications/{app_id}/status", json={"status": "fired"}, headers=hr_headers
        )
        assert resp.status_code == 422

    def test_status_other_company_404(self, client, seeded_taxonomy):
        hr_a_headers, _company_a, job = _hr_with_active_job(client)
        _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client)
        app_id = self._application_id(client, cand_headers, job["id"])

        _reg2, hr_b_headers, _company_b = make_hr_with_company(client, company_name="PT Lain")
        resp = client.patch(
            f"/api/v1/applications/{app_id}/status",
            json={"status": "reviewed"},
            headers=hr_b_headers,
        )
        assert resp.status_code == 404

    def test_status_missing_application_404(self, client, seeded_taxonomy):
        _reg, hr_headers, _company = make_hr_with_company(client)
        resp = client.patch(
            f"/api/v1/applications/{uuid.uuid4()}/status",
            json={"status": "reviewed"},
            headers=hr_headers,
        )
        assert resp.status_code == 404

    def test_status_rbac(self, client, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)
        _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client)
        app_id = self._application_id(client, cand_headers, job["id"])
        url = f"/api/v1/applications/{app_id}/status"

        resp = client.patch(url, json={"status": "reviewed"}, headers=cand_headers)
        assert resp.status_code == 403
        resp = client.patch(url, json={"status": "reviewed"})
        assert resp.status_code == 401


class TestApplicantCvDownload:
    """HR pemilik lowongan mengunduh CV pelamar (alur rekrutmen inti)."""

    def test_hr_owner_downloads_applicant_cv(self, client, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)
        _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client)
        result = _apply(client, cand_headers, job["id"])
        assert result["status_code"] == 201

        listed = client.get(f"/api/v1/applications/job/{job['id']}", headers=hr_headers)
        assert listed.status_code == 200
        app_id = listed.json()[0]["id"]

        resp = client.get(f"/api/v1/applications/{app_id}/cv", headers=hr_headers)
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/pdf")
        assert resp.headers.get("content-disposition") is not None

    def test_hr_other_company_gets_404(self, client, seeded_taxonomy):
        hr_headers, _company, job = _hr_with_active_job(client)
        _reg, cand_headers, _cv = _candidate_with_confirmed_cv(client)
        result = _apply(client, cand_headers, job["id"])
        assert result["status_code"] == 201

        listed = client.get(f"/api/v1/applications/job/{job['id']}", headers=hr_headers)
        app_id = listed.json()[0]["id"]

        # HR lain (perusahaan berbeda) — email unik
        _r2, other_headers, _c2 = make_hr_with_company(client, email="hr-lain-e2e@talentsync.dev")
        resp = client.get(f"/api/v1/applications/{app_id}/cv", headers=other_headers)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"
