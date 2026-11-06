"""Unit test pipeline ekstraksi CV (M1): preprocess, segmenter, entitas, payload.

Fixture berupa konstanta string modul — meniru korpus eval/golden/cvs (field
`_text`): CV bahasa Indonesia, bahasa Inggris, campuran bilingual, varian judul
section, dan teks sampah untuk memastikan parser TOTAL (tidak pernah melempar).
"""

import pytest

from app.ai.extraction.entities import (
    extract_certifications,
    extract_contact,
    extract_education,
    extract_experiences,
    extract_languages,
    extract_skills,
    parse_date_range,
)
from app.ai.extraction.parser import build_payload
from app.ai.extraction.payload_schema import PAYLOAD_PARSER_VERSION
from app.ai.extraction.preprocess import preprocess_text
from app.ai.extraction.segmenter import segment_sections

# (a) CV Indonesia — meniru format eval/golden/cvs/CV-001.json (_text),
# dengan duplikat "SQL" di keahlian untuk menguji dedupe.
CV_ID = """Budi Santoso — analis data junior
budi.santoso@example.dev | Jakarta | +62 8121-3188-4851
RINGKASAN
Data Analyst dengan 1 tahun pengalaman, terbiasa bekerja dengan SQL/Python/pandas dalam tim produk.
PENGALAMAN
Data Analyst Junior — PT Teknologi Cerdas (2025-01 - sekarang)
- Menangani pekerjaan analis data menggunakan SQL dan Python.
- Berkolaborasi dengan tim lintas fungsi untuk menghasilkan pandas yang terukur.
PENDIDIKAN
S1 Data Analyst, Universitas Airlangga (2021-2025), IPK 3.01
KEAHLIAN
SQL, Python, pandas, Excel, Power BI, SQL
SERTIFIKASI
- Sertifikasi Profesional Data Analyst (2025)
BAHASA
Bahasa Indonesia (native), Inggris (lancar)
"""

# (b) CV bahasa Inggris — WORK EXPERIENCE, "Jan 2023 – Present".
CV_EN = """John Doe — Software Engineer
john.doe@example.com | +1 555 0100 | https://github.com/johndoe
SUMMARY
Backend engineer with 5 years of experience.
WORK EXPERIENCE
Backend Engineer — Acme Corp (Jan 2023 – Present)
- Built payment APIs.
Software Engineer - Globex (2021-07 - 2022-12)
- Maintained billing services.
EDUCATION
BSc Computer Science, MIT (2015 - 2019), GPA 3.80
SKILLS
Go, Python, Docker, Kubernetes
"""

# (c)+(d) Bilingual & varian judul: RIWAYAT PEKERJAAN, CORE SKILLS, bullet unicode.
CV_BILINGUAL = """Siti Rahma — Full-Stack Developer
siti@example.dev | 0812-3456-7890
RIWAYAT PEKERJAAN
Frontend Developer — PT Digital Kreatif (2022-03 - 2024-05)
• Membangun komponen React.
CORE SKILLS
TypeScript; React; Node.js
RIWAYAT PENDIDIKAN
D3 Sistem Informasi, Politeknik Negeri (2018-2021)
"""

PAYLOAD_KEYS = {
    "parser_version",
    "generated_at",
    "contact",
    "summary",
    "experiences",
    "education",
    "skills",
    "certifications",
    "languages",
    "projects",
    "awards",
    "field_confidence",
    "needs_review",
    "sections_found",
}


# ---------------------------------------------------------------- preprocess
def test_preprocess_dehyphenate_bullets_and_page_numbers():
    raw = "keuangan-\nkerasan\n• poin satu\n- poin dua\n* poin tiga\n2\nHalaman 2/5\n\n\n\nparagraf"
    assert preprocess_text(raw) == [
        "keuangan-kerasan",
        "• poin satu",
        "• poin dua",
        "• poin tiga",
        "",
        "paragraf",
    ]


def test_preprocess_keeps_hyphen_when_next_line_uppercase():
    # De-hifen hanya bila baris berikutnya diawali huruf kecil.
    assert preprocess_text("Pengalaman-\nPengolahan data") == ["Pengalaman-", "Pengolahan data"]


def test_preprocess_empty_input():
    assert preprocess_text("") == []
    assert preprocess_text("   \n  \t ") == [""]


# ---------------------------------------------------------------- segmenter
def test_segmenter_golden_id_sections():
    sections = segment_sections(preprocess_text(CV_ID))
    assert "budi.santoso@example.dev | Jakarta | +62 8121-3188-4851" in sections["contact"]
    assert sections["summary"]
    assert sections["experience"]
    assert sections["education"]
    assert sections["skills"]
    assert sections["certifications"]
    assert sections["languages"]


def test_segmenter_bilingual_heading_variants():
    sections = segment_sections(preprocess_text(CV_BILINGUAL))
    assert sections["experience"]  # RIWAYAT PEKERJAAN
    assert sections["skills"]  # CORE SKILLS
    assert sections["education"]  # RIWAYAT PENDIDIKAN


def test_segmenter_unknown_caps_heading_goes_to_other():
    sections = segment_sections(preprocess_text("KEGIATAN SOSIAL\nPengabdian masyarakat\n"))
    assert sections["other"] == ["Pengabdian masyarakat"]


def test_segmenter_organisasi_alias_maps_to_other():
    sections = segment_sections(preprocess_text("ORGANISASI\nHIMA Informatika 2020\n"))
    assert sections["other"] == ["HIMA Informatika 2020"]


# ---------------------------------------------------------------- tanggal
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2023-01 - sekarang", ("2023-01", None, True)),
        ("2021-07 - 2022-12", ("2021-07", "2022-12", False)),
        ("Jan 2023 – Present", ("2023-01", None, True)),
        ("Januari 2023–Desember 2024", ("2023-01", "2024-12", False)),
        ("2022 – 2024", ("2022", "2024", False)),
        ("2023 - sekarang", ("2023", None, True)),
        ("2021-2025", ("2021", "2025", False)),
        ("2021 s.d. 2023", ("2021", "2023", False)),
        ("Agu 2023 sampai Des 2024", ("2023-08", "2024-12", False)),
        ("tanpa tanggal", None),
        ("", None),
    ],
)
def test_parse_date_range(text, expected):
    assert parse_date_range(text) == expected


# ---------------------------------------------------------------- contact
def test_contact_golden_id():
    contact = extract_contact(segment_sections(preprocess_text(CV_ID))["contact"])
    assert contact["name"] == "Budi Santoso"
    assert contact["email"] == "budi.santoso@example.dev"
    assert contact["phone"] == "+62 8121-3188-4851"
    assert contact["location"] is None  # tanpa awalan "Lokasi:" tidak dipercaya
    assert contact["confidence"]["email"] >= 0.6


def test_contact_name_rules_refinement():
    # Pola umum "Nama — Headline" → sisi kiri 1–4 kata, confidence 0.8.
    contact = extract_contact(["Budi Santoso — Analis Data Junior"])
    assert contact["name"] == "Budi Santoso"
    assert contact["confidence"]["name"] == 0.8
    # Pola pipe "Nama | Headline".
    contact = extract_contact(["Siti Rahma | Full-Stack Developer"])
    assert contact["name"] == "Siti Rahma"
    assert contact["confidence"]["name"] == 0.8
    # Tanpa pemisah: baris utuh 2–4 kata → confidence 0.9.
    contact = extract_contact(["Budi Santoso"])
    assert contact["name"] == "Budi Santoso"
    assert contact["confidence"]["name"] == 0.9
    # Tanpa kandidat valid → null + confidence 0.0.
    contact = extract_contact(["081234567890", "budi@x.com"])
    assert contact["name"] is None
    assert contact["confidence"]["name"] == 0.0


def test_contact_location_explicit_prefix():
    contact = extract_contact(["Lokasi: Bandung, Jawa Barat"])
    assert contact["location"] == "Bandung, Jawa Barat"
    assert contact["confidence"]["location"] == 0.9


def test_contact_links():
    contact = extract_contact(["github.com/budi | https://www.linkedin.com/in/budi"])
    assert "https://github.com/budi" in contact["links"]
    assert any("linkedin.com/in/budi" in link for link in contact["links"])


# ---------------------------------------------------------------- pengalaman
def test_experiences_golden_id():
    experiences = extract_experiences(segment_sections(preprocess_text(CV_ID))["experience"])
    assert len(experiences) == 1
    entry = experiences[0]
    assert entry["title"] == "Data Analyst Junior"
    assert entry["company"] == "PT Teknologi Cerdas"
    assert entry["period"] == "2025-01 - sekarang"
    assert entry["start"] == "2025-01"
    assert entry["end"] is None
    assert entry["current"] is True
    assert entry["bullets"] == [
        "Menangani pekerjaan analis data menggunakan SQL dan Python.",
        "Berkolaborasi dengan tim lintas fungsi untuk menghasilkan pandas yang terukur.",
    ]
    assert entry["confidence"] == 0.9


def test_experiences_english_two_entries():
    experiences = extract_experiences(segment_sections(preprocess_text(CV_EN))["experience"])
    assert len(experiences) == 2
    first, second = experiences
    assert first["company"] == "Acme Corp"
    assert first["start"] == "2023-01" and first["current"] is True
    assert first["bullets"] == ["Built payment APIs."]
    assert second["company"] == "Globex"
    assert second["start"] == "2021-07" and second["end"] == "2022-12"
    assert second["current"] is False


def test_experiences_pipe_header():
    # Pola spesifikasi: "Company | Title (period)".
    lines = ["PT Maju Jaya | Data Analyst (2020-01 - 2021-01)"]
    entry = extract_experiences(lines)[0]
    assert entry["company"] == "PT Maju Jaya"
    assert entry["title"] == "Data Analyst"


# ---------------------------------------------------------------- pendidikan
def test_education_golden_id():
    education = extract_education(segment_sections(preprocess_text(CV_ID))["education"])
    assert len(education) == 1
    item = education[0]
    assert item["degree"] == "S1"
    assert item["institution"] == "Universitas Airlangga"
    assert item["field"] == "Data Analyst"
    assert item["years"] == "2021-2025"
    assert item["gpa"] == 3.01
    assert item["confidence"] == 0.85


def test_education_english_bsc_gpa():
    education = extract_education(segment_sections(preprocess_text(CV_EN))["education"])
    assert education[0]["degree"] == "BSc"
    assert education[0]["institution"] == "MIT"
    assert education[0]["gpa"] == 3.8


def test_education_degree_only_low_confidence():
    education = extract_education(["S1 tanpa institusi jelas"])
    assert education[0]["degree"] == "S1"
    assert education[0]["institution"] is None
    assert education[0]["confidence"] == 0.5


# ---------------------------------------------------------------- keahlian
def test_skills_dedupe_case_insensitive():
    skills = extract_skills(segment_sections(preprocess_text(CV_ID))["skills"])
    assert [s["name"] for s in skills] == ["SQL", "Python", "pandas", "Excel", "Power BI"]
    assert all(s["confidence"] == 0.8 for s in skills)


def test_skills_drops_long_sentence_items():
    skills = extract_skills(["SQL", "kalimat panjang " * 5])
    assert [s["name"] for s in skills] == ["SQL"]


# ---------------------------------------------------------------- sertifikasi
def test_certifications_golden_id():
    certs = extract_certifications(segment_sections(preprocess_text(CV_ID))["certifications"])
    assert len(certs) == 1
    assert certs[0]["name"] == "Sertifikasi Profesional Data Analyst"
    assert certs[0]["year"] == 2025
    assert certs[0]["issuer"] is None
    assert certs[0]["confidence"] == 0.75


def test_certifications_with_issuer():
    certs = extract_certifications(["AWS Cloud Practitioner — Amazon Web Services (2022)"])
    assert certs[0]["name"] == "AWS Cloud Practitioner"
    assert certs[0]["issuer"] == "Amazon Web Services"
    assert certs[0]["year"] == 2022


# ---------------------------------------------------------------- bahasa
def test_languages_with_per_language_level():
    langs = extract_languages(segment_sections(preprocess_text(CV_ID))["languages"])
    pairs = {(item["language"], item["level"]) for item in langs}
    assert ("Bahasa Indonesia", "native") in pairs
    assert ("Inggris", "lancar") in pairs


def test_languages_without_level():
    langs = extract_languages(["Arab, Jepang"])
    assert {item["language"] for item in langs} == {"Arab", "Jepang"}
    assert all(item["level"] is None for item in langs)


# ---------------------------------------------------------------- payload utuh
def test_build_payload_golden_id():
    payload = build_payload(CV_ID)
    assert set(payload) == PAYLOAD_KEYS
    assert payload["parser_version"] == PAYLOAD_PARSER_VERSION
    assert payload["contact"]["email"] == "budi.santoso@example.dev"
    assert payload["experiences"][0]["company"] == "PT Teknologi Cerdas"
    assert payload["education"][0]["gpa"] == 3.01
    assert [s["name"] for s in payload["skills"]][:2] == ["SQL", "Python"]
    assert payload["field_confidence"]["email"] >= 0.6
    # lokasi tak terdeteksi → masuk needs_review.
    assert "location" in payload["needs_review"]
    assert payload["needs_review"] == sorted(payload["needs_review"])
    assert set(payload["sections_found"]) == {
        "contact",
        "summary",
        "experience",
        "education",
        "skills",
        "certifications",
        "languages",
    }


def test_build_payload_english():
    payload = build_payload(CV_EN)
    assert payload["contact"]["name"] == "John Doe"
    assert payload["contact"]["phone"] is None  # format +1 bukan telepon Indonesia
    assert "https://github.com/johndoe" in payload["contact"]["links"]
    assert len(payload["experiences"]) == 2
    assert payload["experiences"][0]["current"] is True
    assert payload["education"][0]["degree"] == "BSc"
    assert "location" in payload["needs_review"]
    assert "languages" in payload["needs_review"]  # section bahasa tidak ada


def test_build_payload_bilingual_variants():
    payload = build_payload(CV_BILINGUAL)
    assert payload["experiences"][0]["company"] == "PT Digital Kreatif"
    assert payload["experiences"][0]["start"] == "2022-03"
    assert [s["name"] for s in payload["skills"]] == ["TypeScript", "React", "Node.js"]
    assert payload["education"][0]["degree"] == "D3"
    assert "certifications" in payload["needs_review"]  # section tidak ada di CV


@pytest.mark.parametrize(
    "text",
    ["", "   ", "@@@ ### !!!", "====", "—", "•", "2023-01 - sekarang", "x" * 250_000],
)
def test_build_payload_never_raises_on_garbage(text):
    payload = build_payload(text)
    assert set(payload) == PAYLOAD_KEYS
    assert payload["experiences"] == []


def test_build_payload_deterministic():
    # Deterministik terhadap teks: hasil identik, kecuali timestamp generasi.
    first = build_payload(CV_ID)
    second = build_payload(CV_ID)
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second
