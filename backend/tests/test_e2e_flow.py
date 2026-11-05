"""E2E flow: perjalanan lengkap HR & kandidat pada satu suite (integrasi modul)."""

from tests.helpers import (
    PASSWORD,
    create_job,
    login,
    make_candidate,
    make_hr_with_company,
)


def test_full_recruitment_flow(client):
    # 1. HR: daftar → perusahaan → buat 2 lowongan → publikasikan 1
    hr, hr_headers, company = make_hr_with_company(client, email="dewi@example.com")
    job1 = create_job(
        client,
        hr_headers,
        title="Senior Full-Stack Engineer",
        location_text="Jakarta Selatan",
        work_mode="hybrid",
    )
    create_job(client, hr_headers, title="QA Automation Lead", location_text="Bandung")
    client.post(f"/api/v1/hr/jobs/{job1['id']}/publish", headers=hr_headers)

    # 2. Kandidat: daftar → lengkapi profil
    cand, cand_headers = make_candidate(client, email="sarah@example.com")
    client.put(
        "/api/v1/me/candidate-profile",
        json={
            "full_name": "Sarah Wijaya",
            "headline": "Full-Stack Engineer",
            "skills": ["React", "Python", "PostgreSQL"],
            "location": "Jakarta",
        },
        headers=cand_headers,
    )

    # 3. Kandidat menemukan lowongan aktif (publik, tanpa & dengan auth)
    assert client.get("/api/v1/jobs").json()["total"] == 1
    detail = client.get(f"/api/v1/jobs/{job1['id']}").json()
    assert detail["company"]["name"] == company["name"]
    assert any(s["name"] == "React" for s in detail["skills"])

    results = client.get("/api/v1/jobs", params={"q": "full-stack"}, headers=cand_headers).json()
    assert results["total"] == 1

    # 4. Kandidat mengunggah CV → ekstraksi selesai (async) + jadi primary
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Sarah Wijaya - React Python PostgreSQL")
    resp = client.post(
        "/api/v1/cvs",
        files={"file": ("CV_Sarah.pdf", doc.tobytes(), "application/pdf")},
        headers=cand_headers,
    )
    assert resp.status_code == 201
    listing = client.get("/api/v1/cvs", headers=cand_headers).json()
    assert listing and listing[0]["status"] == "ready" and listing[0]["is_primary"] is True

    # 5. Sesi: login ulang keduanya; refresh & logout bekerja
    hr_login = login(client, "dewi@example.com", PASSWORD)
    cand_login = login(client, "sarah@example.com", PASSWORD)
    assert hr_login["user"]["role"] == "hr"
    assert cand_login["user"]["role"] == "candidate"

    client.post("/api/v1/auth/logout", json={"refresh_token": cand_login["refresh_token"]})
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": cand_login["refresh_token"]}
        ).status_code
        == 401
    )

    # 6. HR melihat lowongannya + statistik
    assert client.get("/api/v1/hr/jobs", headers=hr_headers).json()["total"] == 2
    stats = client.get("/api/v1/hr/jobs/stats", headers=hr_headers).json()
    assert stats["by_status"].get("active") == 1
    assert stats["by_status"].get("draft") == 1
