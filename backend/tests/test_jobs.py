"""Pengujian manajemen lowongan (HR) & katalog publik (kandidat)."""

from tests.helpers import (
    auth_headers,
    create_job,
    make_hr_with_company,
    register,
)


def test_hr_without_company_cannot_create_job(client):
    reg = register(client, role="hr")
    headers = auth_headers(reg)
    from tests.helpers import make_job_payload

    resp = client.post("/api/v1/hr/jobs", json=make_job_payload(), headers=headers)
    assert resp.status_code == 400
    assert "perusahaan" in resp.json()["error"]["message"].lower()


def test_job_lifecycle_draft_publish_pause_resume_close(client):
    reg, headers, _ = make_hr_with_company(client)
    job = create_job(client, headers)

    # Draft: tidak terlihat di katalog publik
    resp = client.get("/api/v1/jobs")
    assert resp.json()["total"] == 0

    resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    assert resp.json()["posted_at"] is not None

    resp = client.get("/api/v1/jobs")
    assert resp.json()["total"] == 1

    resp = client.post(f"/api/v1/hr/jobs/{job['id']}/pause", headers=headers)
    assert resp.json()["status"] == "paused"
    assert client.get("/api/v1/jobs").json()["total"] == 0  # paused tidak tampil

    resp = client.post(f"/api/v1/hr/jobs/{job['id']}/resume", headers=headers)
    assert resp.json()["status"] == "active"

    resp = client.post(f"/api/v1/hr/jobs/{job['id']}/close", headers=headers)
    assert resp.json()["status"] == "closed"
    assert client.get("/api/v1/jobs").json()["total"] == 0


def test_invalid_transition_rejected(client):
    reg, headers, _ = make_hr_with_company(client)
    job = create_job(client, headers)
    # pause langsung dari draft → 409
    resp = client.post(f"/api/v1/hr/jobs/{job['id']}/pause", headers=headers)
    assert resp.status_code == 409


def test_publish_with_past_closing_date_rejected(client):
    reg, headers, _ = make_hr_with_company(client)
    job = create_job(client, headers, closing_at="2020-01-01T00:00:00Z")
    resp = client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=headers)
    assert resp.status_code == 409
    assert "batas akhir" in resp.json()["error"]["message"].lower()


def test_edit_job(client):
    reg, headers, _ = make_hr_with_company(client)
    job = create_job(client, headers)
    resp = client.put(
        f"/api/v1/hr/jobs/{job['id']}",
        json={
            "title": "Lead Full-Stack Engineer",
            "description": "Deskripsi diperbarui yang cukup panjang untuk lolos validasi.",
            "skills": [{"name": "Go", "required": True}],
            "employment_type": "full_time",
            "work_mode": "remote",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Lead Full-Stack Engineer"
    assert resp.json()["work_mode"] == "remote"
    assert resp.json()["skills"] == [{"name": "Go", "required": True}]


def test_edit_closed_job_rejected(client):
    reg, headers, _ = make_hr_with_company(client)
    job = create_job(client, headers)
    client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=headers)
    client.post(f"/api/v1/hr/jobs/{job['id']}/close", headers=headers)
    resp = client.put(
        f"/api/v1/hr/jobs/{job['id']}",
        json={
            "title": "Judul Baru",
            "description": "Deskripsi pengganti yang cukup panjang untuk validasi.",
            "skills": [{"name": "Go", "required": True}],
            "employment_type": "full_time",
            "work_mode": "onsite",
        },
        headers=headers,
    )
    assert resp.status_code == 409


def test_other_hr_cannot_access_or_modify_foreign_job(client):
    reg1, headers1, _ = make_hr_with_company(client, email="hr1@example.com")
    reg2, headers2, _ = make_hr_with_company(
        client, email="hr2@example.com", company_name="PT Lain"
    )
    job = create_job(client, headers1)

    from tests.helpers import make_job_payload

    attempts = [
        ("get", f"/api/v1/hr/jobs/{job['id']}", None),
        ("put", f"/api/v1/hr/jobs/{job['id']}", make_job_payload()),
        ("post", f"/api/v1/hr/jobs/{job['id']}/publish", None),
        ("post", f"/api/v1/hr/jobs/{job['id']}/close", None),
        ("delete", f"/api/v1/hr/jobs/{job['id']}", None),
    ]
    for method, path, json_body in attempts:
        kwargs: dict = {"headers": headers2}
        if json_body is not None:
            kwargs["json"] = json_body
        resp = getattr(client, method)(path, **kwargs)
        assert resp.status_code == 404, f"{method} {path} → {resp.status_code}: {resp.text}"


def test_job_skills_validation(client):
    reg, headers, _ = make_hr_with_company(client)
    # Tanpa skill required → ditolak
    resp = client.post(
        "/api/v1/hr/jobs",
        json={
            "title": "X Y Z",
            "description": "a" * 30,
            "skills": [{"name": "Go", "required": False}],
        },
        headers=headers,
    )
    assert resp.status_code == 422
    # Skill duplikat case-insensitive → digabung, required menang
    resp = client.post(
        "/api/v1/hr/jobs",
        json={
            "title": "X Y Z",
            "description": "a" * 30,
            "skills": [
                {"name": "go", "required": False},
                {"name": "Go", "required": True},
                {"name": "go ", "required": False},
            ],
            "employment_type": "full_time",
            "work_mode": "onsite",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["skills"] == [{"name": "go", "required": True}]  # nama kemunculan pertama


def test_public_search_filters_and_pagination(client):
    reg, headers, _ = make_hr_with_company(client)
    jobs = [
        create_job(client, headers, title="Backend Engineer", location_text="Jakarta Selatan"),
        create_job(
            client, headers, title="Frontend Engineer", location_text="Bandung", work_mode="remote"
        ),
        create_job(
            client,
            headers,
            title="Data Engineer",
            location_text="Jakarta Pusat",
            employment_type="contract",
        ),
    ]
    for j in jobs:
        client.post(f"/api/v1/hr/jobs/{j['id']}/publish", headers=headers)

    resp = client.get("/api/v1/jobs")
    assert resp.json()["total"] == 3

    resp = client.get("/api/v1/jobs", params={"q": "engineer"})
    assert resp.json()["total"] == 3
    resp = client.get("/api/v1/jobs", params={"q": "frontend"})
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["title"] == "Frontend Engineer"

    resp = client.get("/api/v1/jobs", params={"location": "jakarta"})
    assert resp.json()["total"] == 2

    resp = client.get("/api/v1/jobs", params={"employment_type": "contract"})
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["title"] == "Data Engineer"

    resp = client.get("/api/v1/jobs", params={"work_mode": "remote"})
    assert resp.json()["total"] == 1

    # Pagination
    resp = client.get("/api/v1/jobs", params={"size": 2, "page": 1})
    assert len(resp.json()["items"]) == 2
    assert resp.json()["pages"] == 2
    resp = client.get("/api/v1/jobs", params={"size": 2, "page": 2})
    assert len(resp.json()["items"]) == 1


def test_public_detail_visibility(client):
    reg, headers, _ = make_hr_with_company(client)
    job = create_job(client, headers)

    # Draft → 404 di detail publik
    assert client.get(f"/api/v1/jobs/{job['id']}").status_code == 404

    client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=headers)
    resp = client.get(f"/api/v1/jobs/{job['id']}")
    assert resp.status_code == 200
    assert resp.json()["company"]["name"] == "PT Teknologi Maju"
    assert "posted_by_user_id" not in resp.json()  # field internal tidak bocor

    client.post(f"/api/v1/hr/jobs/{job['id']}/close", headers=headers)
    assert client.get(f"/api/v1/jobs/{job['id']}").status_code == 404


def test_archive_job_soft_delete(client):
    reg, headers, _ = make_hr_with_company(client)
    job = create_job(client, headers)
    client.post(f"/api/v1/hr/jobs/{job['id']}/publish", headers=headers)

    resp = client.delete(f"/api/v1/hr/jobs/{job['id']}", headers=headers)
    assert resp.status_code == 204

    # Hilang dari daftar HR & katalog publik
    assert client.get("/api/v1/hr/jobs", headers=headers).json()["total"] == 0
    assert client.get("/api/v1/jobs").json()["total"] == 0
    assert client.get(f"/api/v1/jobs/{job['id']}").status_code == 404


def test_hr_job_list_status_filter_and_stats(client):
    reg, headers, _ = make_hr_with_company(client)
    j1 = create_job(client, headers, title="A B C")
    j2 = create_job(client, headers, title="D E F")
    client.post(f"/api/v1/hr/jobs/{j1['id']}/publish", headers=headers)

    resp = client.get("/api/v1/hr/jobs", params={"status": "draft"}, headers=headers)
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["id"] == j2["id"]

    resp = client.get("/api/v1/hr/jobs/stats", headers=headers)
    stats = resp.json()
    assert stats["total"] == 2
    assert stats["by_status"]["draft"] == 1
    assert stats["by_status"]["active"] == 1
