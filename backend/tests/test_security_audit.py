"""Test audit keamanan tambahan (hasil post-implementation audit).

- JWT yang ditandatangani kunci asing → 401 (bukan diterima).
- Nama file CV dengan karakter berbahaya disanitasi (anti header injection).
- Dua pengguna dengan password sama menghasilkan hash berbeda (salt unik).
"""

import jwt

from tests.helpers import PASSWORD, make_candidate, register


def test_jwt_signed_with_foreign_key_rejected(client):
    reg = register(client, email="forge@example.com")
    forged = jwt.encode(
        {"sub": reg["user"]["id"], "role": "candidate", "type": "access"},
        "kunci-palsu-yang-tidak-terdaftar-0123456789",
        algorithm="HS256",
    )
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401


def test_token_with_alg_none_rejected(client):
    reg = register(client, email="algnone@example.com")
    unsigned = jwt.encode(
        {"sub": reg["user"]["id"], "role": "candidate", "type": "access"},
        key="",
        algorithm="none",
    )
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {unsigned}"})
    assert resp.status_code == 401


def test_cv_filename_with_dangerous_chars_sanitized(client):
    _, headers = make_candidate(client, email="sanitize@example.com")
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "x")
    pdf = doc.tobytes()

    evil_name = 'cv"; rm -rf\r\n.pdf'
    resp = client.post(
        "/api/v1/cvs",
        files={"file": (evil_name, pdf, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    listing = client.get("/api/v1/cvs", headers=headers).json()
    stored = listing[0]["original_filename"]
    assert stored.endswith(".pdf")
    for bad in ('"', "\r", "\n", ";", "\t", "\\"):
        assert bad not in stored, f"karakter berbahaya lolos: {bad!r}"

    # Unduhan tetap aman (Content-Disposition tidak membawa karakter mentah)
    dl = client.get(f"/api/v1/cvs/{listing[0]['id']}/file", headers=headers)
    assert dl.status_code == 200
    disposition = dl.headers["content-disposition"]
    assert "\r" not in disposition and "\n" not in disposition


def test_same_password_different_hash(client, db_session):
    """Dua pengguna dengan password identik → hash bcrypt berbeda (salt unik)."""
    from sqlalchemy import select

    from app.models.user import User

    register(client, email="salt1@example.com", password=PASSWORD)
    register(client, email="salt2@example.com", password=PASSWORD)
    users = db_session.scalars(select(User).where(User.role == "candidate")).all()
    assert len(users) == 2
    assert users[0].password_hash != users[1].password_hash  # salt unik per pengguna
    for user in users:
        assert user.password_hash.startswith("$2b$")
