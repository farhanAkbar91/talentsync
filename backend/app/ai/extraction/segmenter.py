"""Segmentasi baris CV menjadi section kanonik (heuristik judul bilingual).

Keterbatasan yang disengaja: layout dua kolom akan terlebur menjadi satu
urutan baris oleh PyMuPDF (flat per blok), sehingga judul section dari kolom
berbeda bisa muncul berurutan — hasil segmentasi tetap "best effort" dan TOTAL
(tidak pernah melempar; teks tanpa judul pun tetap tersegmentasi, masuk
bucket `contact` sebagai zona header).
"""

import re

CANONICAL_SECTIONS = (
    "contact",
    "summary",
    "experience",
    "education",
    "skills",
    "certifications",
    "languages",
    "projects",
    "awards",
    "other",
)

# Alias judul (huruf kecil, tanpa ":" di ujung) → kunci kanonik. Pencocokan
# eksak setelah strip, case-insensitive.
_SECTION_ALIASES: dict[str, str] = {
    # contact / personal
    "informasi pribadi": "contact",
    "personal information": "contact",
    "kontak": "contact",
    "contact": "contact",
    "data pribadi": "contact",
    # summary
    "ringkasan": "summary",
    "summary": "summary",
    "profil": "summary",
    "profile": "summary",
    "objective": "summary",
    "tujuan karier": "summary",
    "tentang saya": "summary",
    "about me": "summary",
    # experience
    "pengalaman": "experience",
    "experience": "experience",
    "work experience": "experience",
    "pengalaman kerja": "experience",
    "pengalaman profesional": "experience",
    "riwayat pekerjaan": "experience",
    "employment history": "experience",
    "riwayat profesi": "experience",
    # education
    "pendidikan": "education",
    "education": "education",
    "riwayat pendidikan": "education",
    "academic background": "education",
    # skills
    "keahlian": "skills",
    "skills": "skills",
    "keahlian teknis": "skills",
    "technical skills": "skills",
    "kompetensi": "skills",
    "competencies": "skills",
    "core skills": "skills",
    # certifications
    "sertifikasi": "certifications",
    "certifications": "certifications",
    "certification": "certifications",
    "lisensi": "certifications",
    "licenses": "certifications",
    # languages
    "bahasa": "languages",
    "languages": "languages",
    # projects
    "proyek": "projects",
    "projects": "projects",
    "project": "projects",
    "portofolio proyek": "projects",
    # awards
    "penghargaan": "awards",
    "awards": "awards",
    "achievements": "awards",
    "prestasi": "awards",
    # organisasi di luar lingkup ekstraksi terstruktur → other
    "organisasi": "other",
    "organization": "other",
}

_MAX_HEADING_LEN = 60
# Tanda baca kalimat di ujung baris (":" dikecualikan karena lazim pada judul).
_SENTENCE_END_RE = re.compile(r"[.!?;,]$")
# Baris "caps" (judul tak dikenal): ≥80% huruf kapital, minimal 2 huruf.
_LETTER_RE = re.compile(r"[A-Za-z]")


def segment_sections(lines: list[str]) -> dict[str, list[str]]:
    """Petakan baris bersih → {kunci kanonik: [baris section]}.

    - Baris sebelum judul pertama → `contact` (zona header: nama + kontak).
    - Section dengan kunci sama (muncul berulang) digabung.
    - Judul mirip-heading yang tidak dikenal (pendek, huruf kapital, tanpa
      tanda baca kalimat) membuka bucket `other` sampai judul dikenal berikutnya.
    """
    sections: dict[str, list[str]] = {key: [] for key in CANONICAL_SECTIONS}
    current = "contact"
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue  # baris kosong tidak dipakai extractor
        key = _match_heading(stripped)
        if key is not None:
            current = key
            continue
        if _is_unknown_caps_heading(stripped):
            current = "other"
            continue
        sections[current].append(stripped)
    return sections


def _match_heading(stripped: str) -> str | None:
    """Kembalikan kunci kanonik bila baris adalah judul section yang dikenal."""
    core = stripped.rstrip(":").strip().lower()
    if not core or len(core) > _MAX_HEADING_LEN:
        return None
    if _SENTENCE_END_RE.search(core):
        return None
    return _SECTION_ALIASES.get(core)


def _is_unknown_caps_heading(stripped: str) -> bool:
    """Judul tak dikenal: pendek, tanpa tanda baca kalimat, dan ditulis kapital."""
    core = stripped.rstrip(":").strip()
    if not core or len(core) > _MAX_HEADING_LEN:
        return False
    if _SENTENCE_END_RE.search(core):
        return False
    letters = _LETTER_RE.findall(core)
    if len(letters) < 2:
        return False
    upper = sum(1 for ch in letters if ch.isupper())
    return upper / len(letters) >= 0.8
