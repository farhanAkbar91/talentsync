"""API test hasil ekstraksi CV (M1): payload otomatis saat upload, akses
pemilik, konfirmasi (dengan/tanpa koreksi payload), 409 & RBAC."""

import copy

import fitz  # pymupdf

from app.ai.extraction.payload_schema import PAYLOAD_PARSER_VERSION
from tests.helpers import make_candidate, make_hr_with_company

# Teks CV untuk PDF uji (ASCII murni — font dasar PDF tidak mendukung em dash).
CV_LINES = [
    "Budi Santoso - analis data junior",
    "budi.santoso@example.dev | Jakarta | +62 8121-3188-4851",
    "RINGKASAN",
    "Data Analyst dengan pengalaman SQL, Python, dan pandas.",
    "PENGALAMAN",
    "Data Analyst Junior - PT Teknologi Cerdas (2025-01 - sekarang)",
    "- Menangani pekerjaan analis data menggunakan SQL dan Python.",
    "PENDIDIKAN",
    "S1 Data Analyst, Universitas Airlangga (2021-2025), IPK 3.01",
    "KEAHLIAN",
    "SQL, Python, pandas, Excel, Power BI",
]


def make_multiline_pdf(lines: list[str]) -> bytes:
    """Pola sama dengan tests.test_cvs.make_pdf, tapi banyak baris."""
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 16
    return doc.tobytes()


def upload_cv(client, headers: dict, content: bytes, filename: str = "cv.pdf") -> dict:
    resp = client.post(
        "/api/v1/cvs",
        files={"file": (filename, content, "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def get_extraction(client, headers: dict, cv_id: str) -> dict:
    resp = client.get(f"/api/v1/cvs/{cv_id}/extraction", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_upload_produces_heuristic_payload(client):
    _, headers = make_candidate(client)
    cv = upload_cv(client, headers, make_multiline_pdf(CV_LINES))

    # CVOut memuat status ekstraksi & jejak konfirmasi (default None → False).
    listing = client.get("/api/v1/cvs", headers=headers).json()
    mine = next(c for c in listing if c["id"] == cv["id"])
    assert mine["status"] == "ready"
    assert mine["extraction_status"] == "done"
    assert mine["extraction_confirmed"] is False

    data = get_extraction(client, headers, cv["id"])
    assert data["cv_id"] == cv["id"]
    assert data["status"] == "done"
    assert data["parser_version"] == PAYLOAD_PARSER_VERSION
    assert data["confirmed_at"] is None and data["confirmed_by"] is None

    payload = data["payload"]
    assert payload is not None
    assert payload["contact"]["name"] == "Budi Santoso"
    assert payload["contact"]["email"] == "budi.santoso@example.dev"
    assert payload["experiences"][0]["company"] == "PT Teknologi Cerdas"
    assert payload["experiences"][0]["current"] is True
    assert payload["education"][0]["degree"] == "S1"


def test_extraction_access_control(client):
    from uuid import uuid4

    _, headers_owner = make_candidate(client, email="owner-ext@example.com")
    _, headers_other = make_candidate(client, email="other-ext@example.com")
    cv = upload_cv(client, headers_owner, make_multiline_pdf(CV_LINES))

    # Kandidat lain → 404 (jangan bocorkan keberadaan).
    assert (
        client.get(f"/api/v1/cvs/{cv['id']}/extraction", headers=headers_other).status_code == 404
    )
    # Anonim → 401.
    assert client.get(f"/api/v1/cvs/{cv['id']}/extraction").status_code == 401
    # CV tidak ada → 404.
    assert client.get(f"/api/v1/cvs/{uuid4()}/extraction", headers=headers_owner).status_code == 404
    # HR bukan kandidat → 403.
    _, hr_headers, _ = make_hr_with_company(client)
    assert client.get(f"/api/v1/cvs/{cv['id']}/extraction", headers=hr_headers).status_code == 403
    assert (
        client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=hr_headers).status_code
        == 403
    )


def test_confirm_sets_confirmed_at_and_by(client):
    reg, headers = make_candidate(client)
    cv = upload_cv(client, headers, make_multiline_pdf(CV_LINES))

    resp = client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["confirmed_at"] is not None
    assert data["confirmed_by"] == reg["user"]["id"]
    # Konfirmasi ulang diperbolehkan (timestamp diperbarui).
    resp = client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=headers)
    assert resp.status_code == 200

    listing = client.get("/api/v1/cvs", headers=headers).json()
    mine = next(c for c in listing if c["id"] == cv["id"])
    assert mine["extraction_confirmed"] is True

    # is_confirmed pada model (properti) konsisten dengan kolom.
    from app.models.cv import CvExtraction

    assert CvExtraction(confirmed_at=None).is_confirmed is False
    assert CvExtraction(confirmed_at=data["confirmed_at"]).is_confirmed is True


def test_confirm_with_edited_payload_saves_edits(client):
    _, headers = make_candidate(client)
    cv = upload_cv(client, headers, make_multiline_pdf(CV_LINES))
    payload = get_extraction(client, headers, cv["id"])["payload"]

    edited = copy.deepcopy(payload)
    edited["parser_version"] = "versi-lain-yang-dipaksa-kembali"
    edited["contact"]["name"] = "Nama Koreksi Manual"
    edited["summary"] = "Ringkasan hasil koreksi kandidat."

    resp = client.put(
        f"/api/v1/cvs/{cv['id']}/extraction/confirm",
        json={"payload": edited},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Suntingan tersimpan; parser_version dipaksa kembali ke versi parser.
    assert data["payload"]["contact"]["name"] == "Nama Koreksi Manual"
    assert data["payload"]["summary"] == "Ringkasan hasil koreksi kandidat."
    assert data["parser_version"] == PAYLOAD_PARSER_VERSION
    assert data["confirmed_at"] is not None

    # Tersimpan persisten di database (GET kembali).
    refetched = get_extraction(client, headers, cv["id"])
    assert refetched["payload"]["contact"]["name"] == "Nama Koreksi Manual"


def test_confirm_invalid_payload_returns_400(client):
    _, headers = make_candidate(client)
    cv = upload_cv(client, headers, make_multiline_pdf(CV_LINES))
    resp = client.put(
        f"/api/v1/cvs/{cv['id']}/extraction/confirm",
        json={"payload": {"experiences": "bukan-daftar"}},
        headers=headers,
    )
    assert resp.status_code == 400


def test_confirm_before_done_returns_409(client):
    _, headers = make_candidate(client)
    # PDF rusak → ekstraksi gagal (status bukan done).
    cv = upload_cv(client, headers, b"%PDF-1.4 ini bukan pdf utuh", filename="broken.pdf")
    listing = client.get("/api/v1/cvs", headers=headers).json()
    assert listing[0]["status"] == "failed"

    # GET ekstraksi tetap 200 (barisnya ada), status failed & payload null.
    data = get_extraction(client, headers, cv["id"])
    assert data["status"] == "failed"
    assert data["payload"] is None

    resp = client.put(f"/api/v1/cvs/{cv['id']}/extraction/confirm", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"
