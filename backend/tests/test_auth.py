"""Pengujian autentikasi, JWT, dan RBAC."""

from sqlalchemy import select

from app.models.user import User
from tests.helpers import (
    PASSWORD,
    login,
    make_candidate,
    make_hr_with_company,
    register,
)


def test_register_success_candidate(client):
    data = register(client, role="candidate", full_name="Sarah Wijaya")
    assert data["user"]["role"] == "candidate"
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["token_type"] == "bearer"


def test_register_duplicate_email_conflict(client):
    register(client, email="dup@example.com")
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "role": "candidate",
            "full_name": "Lain",
            "email": "DUP@example.com",
            "password": PASSWORD,
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


def test_register_invalid_role_rejected(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"role": "admin", "full_name": "X Y", "email": "a@example.com", "password": PASSWORD},
    )
    assert resp.status_code == 422


def test_register_weak_password_rejected(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "role": "candidate",
            "full_name": "X Y",
            "email": "w@example.com",
            "password": "pendek",
        },
    )
    assert resp.status_code == 422


def test_login_success_and_failure(client):
    reg = register(client, email="login@example.com")
    tokens = login(client, reg["user"]["email"])
    assert tokens["access_token"]

    resp = client.post(
        "/api/v1/auth/login", json={"email": reg["user"]["email"], "password": "SalahTotal123"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    resp = client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": PASSWORD}
    )
    assert resp.status_code == 401  # pesan generik, tidak membocorkan keberadaan email


def test_me_requires_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401

    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bukan-token"})
    assert resp.status_code == 401


def test_me_returns_current_user(client):
    reg, headers = make_candidate(client)
    resp = client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == reg["user"]["email"]


def test_access_token_cannot_be_used_as_refresh(client):
    reg, _ = make_candidate(client)
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": reg["access_token"]})
    assert resp.status_code == 401  # type claim 'access' ≠ 'refresh'


def test_refresh_rotation_single_use(client):
    reg = register(client)
    first = client.post("/api/v1/auth/refresh", json={"refresh_token": reg["refresh_token"]})
    assert first.status_code == 200
    assert first.json()["refresh_token"] != reg["refresh_token"]

    # Token lama sudah dicabut → rotasi kedua dengan token lama ditolak.
    second = client.post("/api/v1/auth/refresh", json={"refresh_token": reg["refresh_token"]})
    assert second.status_code == 401


def test_logout_revokes_refresh_token(client):
    reg = register(client)
    resp = client.post("/api/v1/auth/logout", json={"refresh_token": reg["refresh_token"]})
    assert resp.status_code == 204
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": reg["refresh_token"]})
    assert resp.status_code == 401


def test_password_never_stored_in_plaintext(client, db_session):
    reg = register(client, email="hash@example.com", password=PASSWORD)
    user = db_session.scalar(select(User).where(User.email == reg["user"]["email"]))
    assert user is not None
    assert user.password_hash != PASSWORD
    assert user.password_hash.startswith("$2b$")


def test_rbac_candidate_cannot_access_hr_endpoints(client):
    _, headers = make_candidate(client)
    resp = client.get("/api/v1/hr/jobs", headers=headers)
    assert resp.status_code == 403
    resp = client.post("/api/v1/hr/jobs", json={}, headers=headers)
    assert resp.status_code == 403


def test_rbac_hr_cannot_access_candidate_profile(client):
    _, headers, _ = make_hr_with_company(client)
    resp = client.get("/api/v1/me/candidate-profile", headers=headers)
    assert resp.status_code == 403
    resp = client.put("/api/v1/me/candidate-profile", json={}, headers=headers)
    assert resp.status_code == 403


def test_me_summary_by_role(client):
    cand, cand_headers = make_candidate(client)
    resp = client.get("/api/v1/auth/me/summary", headers=cand_headers)
    assert resp.status_code == 200
    assert "candidate_profile" in resp.json()

    hr, hr_headers, company = make_hr_with_company(client)
    resp = client.get("/api/v1/auth/me/summary", headers=hr_headers)
    assert resp.status_code == 200
    assert resp.json()["company"]["id"] == company["id"]
