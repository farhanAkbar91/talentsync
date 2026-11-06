"""Test diagnosis CV deterministik (M7): 8 aturan beku (cabang lolos & gagal),
matematika skor (−12 penting / −6 saran / floor 0), band label, ketotalan pada
payload kosong/rusak, dan API GET /cvs/{cv_id}/diagnosis (200 pemilik, 404
non-pemilik, 409 ekstraksi belum done / payload kosong, RBAC HR → 403)."""

import uuid

import pytest
from sqlalchemy import select

from app.ai.diagnosis.diagnosis import RULE_ORDER, compute_score, diagnose_payload, score_label
from app.models.cv import CvExtraction
from tests.helpers import make_candidate, make_hr_with_company
from tests.test_extraction_api import CV_LINES, make_multiline_pdf, upload_cv

# --- Payload "ideal" (semua 8 aturan lolos), gaya eval/golden/cvs/CV-001.json ---

BULLET_METRIC = "Meningkatkan performa laporan 30% dengan optimasi query SQL."
BULLET_PLAIN = "Berkolaborasi dengan tim produk untuk merancang dasbor analitik."
SUMMARY_OK = (
    "Data Analyst dengan 1 tahun pengalaman SQL, Python, dan pandas serta "
    "terbiasa berkolaborasi dengan tim produk."
)


def make_payload(**overrides) -> dict:
    payload = {
        "contact": {
            "name": "Budi Santoso",
            "email": "budi.santoso@example.dev",
            "phone": "+62 8121-3188-4851",
            "location": "Jakarta",
        },
        "summary": SUMMARY_OK,
        "experiences": [
            {
                "title": "Data Analyst Junior",
                "company": "PT Teknologi Cerdas",
                "bullets": [BULLET_METRIC, BULLET_PLAIN],
            }
        ],
        "education": [{"degree": "S1", "institution": "Universitas Airlangga"}],
        "skills": [{"name": name} for name in ("SQL", "Python", "pandas", "Excel", "Power BI")],
        "certifications": [{"name": "Sertifikasi Data Analyst (2025)"}],
    }
    payload.update(overrides)
    return payload


# --- Aturan: cabang lolos (payload ideal) ---


def test_all_rules_pass():
    result = diagnose_payload(make_payload())
    assert result["quality_score"] == 100
    assert result["label"] == "Baik"
    assert result["improvements"] == []
    assert [s["rule_id"] for s in result["strengths"]] == list(RULE_ORDER)
    # Pin teks positif (kontrak beku yang dikonsumsi panel FE).
    assert [s["text"] for s in result["strengths"]] == [
        "Email tercantum — memudahkan HR menghubungi Anda.",
        "Nomor telepon tercantum — HR mudah menghubungi Anda.",
        "Ringkasan profesional tersedia dengan panjang yang ideal.",
        "Ada pencapaian terukur dengan angka — kuat untuk ATS.",
        "Daftar skill cukup beragam (5+) — menunjukkan rentang keahlian.",
        "Riwayat pendidikan sudah terisi.",
        "Semua bullet pengalaman padat dan jelas (40–250 karakter).",
        "Sertifikasi relevan tercantum — nilai tambah di mata HR.",
    ]
    assert list(result.keys()) == ["quality_score", "label", "strengths", "improvements"]


# --- Aturan: cabang gagal (teks & severity beku, skor turun sesuai severity) ---


@pytest.mark.parametrize(
    ("overrides", "rule_id", "severity", "text"),
    [
        (
            {"contact": {"name": "Budi", "phone": "+62 812"}},
            "contact_email",
            "penting",
            "Email belum tercantum — HR tidak dapat menghubungi Anda.",
        ),
        (
            {"contact": {"name": "Budi", "email": "budi@example.dev"}},
            "contact_phone",
            "saran",
            "Nomor telepon belum tercantum.",
        ),
        (
            {"summary": None},
            "summary_present",
            "penting",
            "Ringkasan profesional belum ada atau terlalu pendek/panjang — tulis 2–4 kalimat.",
        ),
        (
            {"experiences": [{"title": "Analis", "bullets": [BULLET_PLAIN]}]},
            "exp_metrics",
            "penting",
            "Belum ada pencapaian terukur — tambahkan angka (%, jumlah pengguna, Rp) "
            "pada bullet pengalaman.",
        ),
        (
            {"skills": [{"name": n} for n in ("SQL", "Python", "pandas", "Excel")]},
            "skills_breadth",
            "saran",
            "Skill kurang dari 5 — daftar keahlian teknis dan perangkat yang dikuasai.",
        ),
        (
            {"education": []},
            "education_present",
            "penting",
            "Riwayat pendidikan belum terisi.",
        ),
        (
            {"experiences": [{"title": "Analis", "bullets": [BULLET_METRIC, "Terlalu singkat."]}]},
            "bullet_length",
            "saran",
            "Ada bullet pengalaman terlalu singkat (<40 karakter) — jelaskan kontribusi "
            "dan hasilnya.",
        ),
        (
            {"certifications": []},
            "certifications_present",
            "saran",
            "Belum ada sertifikasi — tambahkan sertifikasi relevan bila ada.",
        ),
    ],
)
def test_rule_fail_branches(overrides, rule_id, severity, text):
    result = diagnose_payload(make_payload(**overrides))
    # Tepat satu aturan gagal: cabang gagal tiap aturan terisolasi.
    assert result["improvements"] == [{"rule_id": rule_id, "text": text, "severity": severity}]
    penalty = 12 if severity == "penting" else 6
    assert result["quality_score"] == 100 - penalty
    assert rule_id not in [s["rule_id"] for s in result["strengths"]]


# --- Batas panjang konten ---


@pytest.mark.parametrize(
    ("summary", "passes"),
    [("x" * 39, False), ("x" * 40, True), ("x" * 800, True), ("x" * 801, False), ("   ", False)],
)
def test_summary_length_boundaries(summary, passes):
    result = diagnose_payload(make_payload(summary=summary))
    failed = "summary_present" in [i["rule_id"] for i in result["improvements"]]
    assert failed is not passes


@pytest.mark.parametrize(
    ("bullet", "passes"),
    [("x" * 39, False), ("x" * 40, True), ("x" * 250, True), ("x" * 251, False)],
)
def test_bullet_length_boundaries(bullet, passes):
    # BULLET_METRIC memuat angka → exp_metrics tetap lolos; hanya panjang diuji.
    payload = make_payload(experiences=[{"title": "Analis", "bullets": [BULLET_METRIC, bullet]}])
    result = diagnose_payload(payload)
    failed = "bullet_length" in [i["rule_id"] for i in result["improvements"]]
    assert failed is not passes


# --- Perilaku khusus exp_metrics & bullet_length ---


def test_bullet_length_not_evaluated_without_experience():
    """bullet_length hanya dievaluasi bila ada pengalaman; tanpa pengalaman → lolos.
    exp_metrics tetap gagal (tidak ada bullet berangka sama sekali)."""
    result = diagnose_payload(make_payload(experiences=[]))
    assert [s["rule_id"] for s in result["strengths"]] == [
        "contact_email",
        "contact_phone",
        "summary_present",
        "skills_breadth",
        "education_present",
        "bullet_length",
        "certifications_present",
    ]
    assert [i["rule_id"] for i in result["improvements"]] == ["exp_metrics"]
    assert result["quality_score"] == 88


def test_bullet_length_passes_when_experience_has_no_bullets():
    """Pengalaman ada tetapi tanpa bullet → tidak ada bullet yang bisa dipersalahkan."""
    result = diagnose_payload(make_payload(experiences=[{"title": "Analis", "bullets": []}]))
    assert "bullet_length" in [s["rule_id"] for s in result["strengths"]]
    assert [i["rule_id"] for i in result["improvements"]] == ["exp_metrics"]


def test_exp_metrics_fails_without_any_bullet():
    result = diagnose_payload(make_payload(experiences=[{"title": "Analis"}]))
    assert [i["rule_id"] for i in result["improvements"]] == ["exp_metrics"]
    assert result["quality_score"] == 88


# --- Matematika skor & band label ---


def test_score_penalties_penting_and_saran():
    # Satu "penting" (email hilang) → −12.
    only_email_missing = {"contact": {"name": "Budi", "phone": "+62 812"}}
    assert diagnose_payload(make_payload(**only_email_missing))["quality_score"] == 88
    # Satu "saran" (telepon hilang) → −6.
    only_phone_missing = {"contact": {"name": "Budi", "email": "budi@example.dev"}}
    assert diagnose_payload(make_payload(**only_phone_missing))["quality_score"] == 94
    # Campuran: email (−12) + ringkasan (−12) + sertifikasi (−6) → 70.
    mixed = {"contact": {"name": "Budi", "phone": "+62 812"}, "summary": None, "certifications": []}
    result = diagnose_payload(make_payload(**mixed))
    assert result["quality_score"] == 70
    assert result["label"] == "Cukup"


def test_score_all_rules_fail():
    # 4 penting (−48) + 4 saran (−24) → 28; label merah.
    all_fail = {
        "contact": {"name": "Budi"},
        "summary": None,
        "experiences": [{"title": "A", "bullets": ["Pendek."]}],
        "education": [],
        "skills": [],
        "certifications": [],
    }
    result = diagnose_payload(all_fail)
    assert result["quality_score"] == 28
    assert result["label"] == "Perlu Perbaikan"
    assert result["strengths"] == []
    assert len(result["improvements"]) == 8


def test_score_floor_zero():
    """Floor 0: penalti melebihi 100 (tidak tercapai dengan 8 aturan beku) tetap ≥ 0."""
    assert compute_score([{"severity": "penting"}] * 9) == 0  # 100 − 108
    assert compute_score([{"severity": "saran"}] * 4) == 100 - 4 * 6
    assert compute_score([]) == 100


def test_label_bands():
    # Band tepat (tidak tersentuh skor nyata: skor selalu ≡ 100 mod 6).
    assert score_label(80) == "Baik"
    assert score_label(79) == "Cukup"
    assert score_label(60) == "Cukup"
    assert score_label(59) == "Perlu Perbaikan"
    # Lewat hasil diagnose_payload: 100 → Baik, 76 (−24) → Cukup, 58 (−42) → merah.
    assert diagnose_payload(make_payload())["label"] == "Baik"
    two_penting = {"contact": {"name": "Budi", "phone": "+62 812"}, "summary": None}
    assert diagnose_payload(make_payload(**two_penting))["label"] == "Cukup"  # 76
    three_penting_one_saran = {
        "contact": {"name": "Budi", "phone": "+62 812"},
        "summary": None,
        "education": [],
        "certifications": [],
    }
    result = diagnose_payload(make_payload(**three_penting_one_saran))  # 58
    assert result["quality_score"] == 58
    assert result["label"] == "Perlu Perbaikan"


# --- Ketotalan: payload kosong / rusak tidak boleh crash ---


def test_empty_payload_is_total():
    result = diagnose_payload({})
    # bullet_length tidak dievaluasi (tanpa pengalaman) → satu-satunya yang lolos.
    assert [s["rule_id"] for s in result["strengths"]] == ["bullet_length"]
    assert len(result["improvements"]) == 7
    # 4 penting (−48) + 3 saran (−18) → 34.
    assert result["quality_score"] == 34
    assert result["label"] == "Perlu Perbaikan"


def test_malformed_payload_is_total():
    """Field None / item rusak / bullet kosong semua ditangani tanpa exception."""
    payload = {
        "contact": None,
        "summary": None,
        "experiences": [None, {"bullets": None}, {"bullets": ["", "   ", "ok tanpa angka"]}],
        "education": None,
        "skills": None,
        "certifications": None,
        "unexpected_key": {"nested": "diabaikan saja"},
    }
    result = diagnose_payload(payload)
    # Semua 8 aturan gagal (bullet "ok tanpa angka" pendek & tanpa angka) → 28.
    assert result["quality_score"] == 28
    assert result["strengths"] == []
    assert len(result["improvements"]) == 8


# --- API GET /cvs/{cv_id}/diagnosis ---


def test_diagnosis_owner_200(client):
    _, headers = make_candidate(client)
    cv = upload_cv(client, headers, make_multiline_pdf(CV_LINES))

    resp = client.get(f"/api/v1/cvs/{cv['id']}/diagnosis", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["cv_id"] == cv["id"]
    # Payload CV_LINES: email/telepon/ringkasan (55 char)/5 skill/pendidikan/bullet
    # lolos; bullet tanpa angka (−12) & tanpa sertifikasi (−6) → 82 → "Baik".
    assert data["quality_score"] == 82
    assert data["label"] == "Baik"
    assert [s["rule_id"] for s in data["strengths"]] == [
        "contact_email",
        "contact_phone",
        "summary_present",
        "skills_breadth",
        "education_present",
        "bullet_length",
    ]
    assert [(i["rule_id"], i["severity"]) for i in data["improvements"]] == [
        ("exp_metrics", "penting"),
        ("certifications_present", "saran"),
    ]
    assert data["computed_at"]
    # Kontrak FE: strengths tanpa severity, improvements selalu punya severity.
    assert "severity" not in data["strengths"][0]
    assert "severity" in data["improvements"][0]


def test_diagnosis_works_without_confirmation(client):
    """Diagnosis informatif pra-konfirmasi: tidak menuntut extraction confirmed."""
    _, headers = make_candidate(client)
    cv = upload_cv(client, headers, make_multiline_pdf(CV_LINES))
    extraction = client.get(f"/api/v1/cvs/{cv['id']}/extraction", headers=headers).json()
    assert extraction["confirmed_at"] is None  # belum dikonfirmasi
    resp = client.get(f"/api/v1/cvs/{cv['id']}/diagnosis", headers=headers)
    assert resp.status_code == 200


def test_diagnosis_access_control(client):
    _, headers_owner = make_candidate(client, email="owner-diag@example.com")
    _, headers_other = make_candidate(client, email="other-diag@example.com")
    cv = upload_cv(client, headers_owner, make_multiline_pdf(CV_LINES))

    # Kandidat lain → 404 (jangan bocorkan keberadaan).
    assert client.get(f"/api/v1/cvs/{cv['id']}/diagnosis", headers=headers_other).status_code == 404
    # Anonim → 401; CV tidak ada → 404.
    assert client.get(f"/api/v1/cvs/{cv['id']}/diagnosis").status_code == 401
    assert (
        client.get(f"/api/v1/cvs/{uuid.uuid4()}/diagnosis", headers=headers_owner).status_code
        == 404
    )
    # HR bukan kandidat → 403.
    _, hr_headers, _ = make_hr_with_company(client)
    assert client.get(f"/api/v1/cvs/{cv['id']}/diagnosis", headers=hr_headers).status_code == 403


def test_diagnosis_409_when_extraction_not_done(client):
    _, headers = make_candidate(client)
    # PDF rusak → ekstraksi gagal (status bukan done) → tidak ada payload dinilai.
    cv = upload_cv(client, headers, b"%PDF-1.4 ini bukan pdf utuh", filename="broken.pdf")
    resp = client.get(f"/api/v1/cvs/{cv['id']}/diagnosis", headers=headers)
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["message"] == "Ekstraksi belum selesai — diagnosis butuh payload."


def test_diagnosis_409_when_payload_missing(client, db_session):
    _, headers = make_candidate(client)
    cv = upload_cv(client, headers, make_multiline_pdf(CV_LINES))
    # Ekstraksi done tetapi payload kosong (mis. gagal dibangun parser) → 409 juga.
    extraction = db_session.scalar(
        select(CvExtraction).where(CvExtraction.cv_id == uuid.UUID(cv["id"]))
    )
    extraction.payload = None
    db_session.commit()

    resp = client.get(f"/api/v1/cvs/{cv['id']}/diagnosis", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"
