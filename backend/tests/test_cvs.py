"""Pengujian CV upload: validasi file, keamanan akses, primary, soft delete."""

import fitz  # pymupdf


def make_pdf(text: str = "Budi Santoso - Software Engineer") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    return doc.tobytes()


def test_upload_valid_pdf_becomes_primary_and_ready(client):
    _, headers = __import__("tests.helpers", fromlist=["make_candidate"]).make_candidate(client)
    resp = client.post(
        "/api/v1/cvs",
        files={"file": ("CV_Budi.pdf", make_pdf(), "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    # Respons langsung = 'pending' (ekstraksi async); task selesai sebelum request kembali.
    assert created["status"] == "pending"

    listing = client.get("/api/v1/cvs", headers=headers).json()
    cv = next(c for c in listing if c["id"] == created["id"])
    assert cv["status"] == "ready"
    assert cv["is_primary"] is True
    assert cv["page_count"] >= 1


def test_non_pdf_rejected(client):
    _, headers = __import__("tests.helpers", fromlist=["make_candidate"]).make_candidate(client)
    resp = client.post(
        "/api/v1/cvs",
        files={"file": ("cv.docx", b"ininya bukan pdf", "application/vnd.wordprocessing")},
        headers=headers,
    )
    assert resp.status_code == 400

    # Ekstensi pdf tapi isi bukan PDF (magic bytes gagal)
    resp = client.post(
        "/api/v1/cvs",
        files={"file": ("fake.pdf", b"bukan pdf sungguhan", "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 400


def test_oversize_rejected_413(client_small_cv_limit):
    from tests.helpers import make_candidate

    _, headers = make_candidate(client_small_cv_limit)
    # PDF ~ >500 byte (fixture membatasi 500 byte)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "x" * 3000)
    big_pdf = doc.tobytes()
    assert len(big_pdf) > 500

    resp = client_small_cv_limit.post(
        "/api/v1/cvs",
        files={"file": ("big.pdf", big_pdf, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_duplicate_content_rejected(client):
    from tests.helpers import make_candidate

    _, headers = make_candidate(client)
    pdf = make_pdf()
    resp = client.post(
        "/api/v1/cvs", files={"file": ("a.pdf", pdf, "application/pdf")}, headers=headers
    )
    assert resp.status_code == 201
    resp = client.post(
        "/api/v1/cvs", files={"file": ("b.pdf", pdf, "application/pdf")}, headers=headers
    )
    assert resp.status_code == 409


def test_invalid_pdf_content_marks_failed(client):
    from tests.helpers import make_candidate

    _, headers = make_candidate(client)
    resp = client.post(
        "/api/v1/cvs",
        files={"file": ("broken.pdf", b"%PDF-1.4 ini rusak", "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["status"] == "pending"  # sebelum task berjalan

    listing = client.get("/api/v1/cvs", headers=headers).json()
    cv = next(c for c in listing if c["id"] == created["id"])
    assert cv["status"] == "failed"  # ekstraksi gagal terekam (bukan diam-diam)


def test_second_cv_not_primary_then_promote(client):
    from tests.helpers import make_candidate

    _, headers = make_candidate(client)
    r1 = client.post(
        "/api/v1/cvs",
        files={"file": ("a.pdf", make_pdf("satu"), "application/pdf")},
        headers=headers,
    ).json()
    r2 = client.post(
        "/api/v1/cvs",
        files={"file": ("b.pdf", make_pdf("dua"), "application/pdf")},
        headers=headers,
    ).json()
    assert r1["is_primary"] is True and r2["is_primary"] is False

    resp = client.patch(f"/api/v1/cvs/{r2['id']}/primary", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_primary"] is True

    listing = client.get("/api/v1/cvs", headers=headers).json()
    primary = [cv for cv in listing if cv["is_primary"]]
    assert len(primary) == 1 and primary[0]["id"] == r2["id"]


def test_cv_access_control(client):
    from tests.helpers import make_candidate

    reg1, headers1 = make_candidate(client, email="own@example.com")
    reg2, headers2 = make_candidate(client, email="other@example.com")

    cv = client.post(
        "/api/v1/cvs",
        files={"file": ("cv.pdf", make_pdf(), "application/pdf")},
        headers=headers1,
    ).json()

    # Pemilik bisa unduh, isi = PDF asli
    resp = client.get(f"/api/v1/cvs/{cv['id']}/file", headers=headers1)
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")

    # Kandidat lain → 404 (jangan bocorkan keberadaan)
    assert client.get(f"/api/v1/cvs/{cv['id']}/file", headers=headers2).status_code == 404
    # Anonim → 401
    assert client.get(f"/api/v1/cvs/{cv['id']}/file").status_code == 401
    # HR juga tidak punya akses file kandidat di fase ini
    hr_reg, hr_headers, _ = __import__(
        "tests.helpers", fromlist=["make_hr_with_company"]
    ).make_hr_with_company(client)
    assert client.get(f"/api/v1/cvs/{cv['id']}/file", headers=hr_headers).status_code in (403, 404)


def test_soft_delete_promotes_new_primary(client):
    from tests.helpers import make_candidate

    _, headers = make_candidate(client)
    r1 = client.post(
        "/api/v1/cvs",
        files={"file": ("a.pdf", make_pdf("satu"), "application/pdf")},
        headers=headers,
    ).json()
    r2 = client.post(
        "/api/v1/cvs",
        files={"file": ("b.pdf", make_pdf("dua"), "application/pdf")},
        headers=headers,
    ).json()

    resp = client.delete(f"/api/v1/cvs/{r1['id']}", headers=headers)
    assert resp.status_code == 204

    listing = client.get("/api/v1/cvs", headers=headers).json()
    assert [cv["id"] for cv in listing] == [r2["id"]]
    assert listing[0]["is_primary"] is True  # dipromosikan otomatis
    # Riwayat file tetap di disk — soft delete tidak menghapus fisik (blueprint §5.1)


def test_hr_cannot_upload_cv(client):
    from tests.helpers import make_hr_with_company

    _, headers, _ = make_hr_with_company(client)
    resp = client.post(
        "/api/v1/cvs", files={"file": ("cv.pdf", make_pdf(), "application/pdf")}, headers=headers
    )
    assert resp.status_code == 403
