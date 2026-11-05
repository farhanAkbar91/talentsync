"""Helper untuk test: registrasi cepat, header auth, payload lowongan."""

import uuid

from fastapi.testclient import TestClient

PASSWORD = "RahasiaKuat123"


def register(
    client: TestClient,
    role: str = "candidate",
    email: str | None = None,
    full_name: str = "Budi Santoso",
    password: str = PASSWORD,
) -> dict:
    email = email or f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"role": role, "full_name": full_name, "email": email, "password": password},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def make_candidate(client: TestClient, email: str | None = None) -> tuple[dict, dict]:
    reg = register(client, role="candidate", email=email)
    return reg, auth_headers(reg)


def make_hr_with_company(
    client: TestClient, email: str | None = None, company_name: str = "PT Teknologi Maju"
) -> tuple[dict, dict, dict]:
    reg = register(client, role="hr", email=email, full_name="Dewi Lestari")
    headers = auth_headers(reg)
    resp = client.post(
        "/api/v1/me/company",
        json={"name": company_name, "industry": "Teknologi", "location": "Jakarta"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return reg, headers, resp.json()


def make_job_payload(**overrides) -> dict:
    payload = {
        "title": "Senior Full-Stack Engineer",
        "description": "Membangun dan merawat aplikasi web end-to-end bersama tim produk.",
        "responsibilities": "Merancang API, memimpin code review.",
        "requirements": "Pengalaman 3+ tahun React dan Python.",
        "skills": [
            {"name": "React", "required": True},
            {"name": "Python", "required": True},
            {"name": "Docker", "required": False},
        ],
        "employment_type": "full_time",
        "work_mode": "hybrid",
        "location_text": "Jakarta Selatan",
        "salary_min": 15000000,
        "salary_max": 30000000,
    }
    payload.update(overrides)
    return payload


def create_job(client: TestClient, headers: dict, **overrides) -> dict:
    resp = client.post("/api/v1/hr/jobs", json=make_job_payload(**overrides), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()
