"""Normalizer: bentuk antara sumber → payload insert tabel `jobs`.

Fungsi TOTAL (kontrak): input API liar apa pun tidak pernah melempar exception —
item yang tidak layak (tanpa judul/perusahaan/external_id) dilewati, field
dipangkas ke batas kolom, dan hasil selalu list payload valid.

Aturan pemetaan (Task 2):
- deskripsi: strip HTML sederhana + unescape entity (input terbatas, cap 20.000
  karakter — sama dengan batas JobIn.description);
- title cap 200; external_id cap 160; source_url cap 500 (kolom 0013);
- tags → skills [{name, required}] — dedupe case-insensitive, maks 10, nama ≤ 50
  (selaras SkillIn); semua skill hasil tags bersifat preferred (required=False);
- work_mode: "remote" bila sumber/item menandai remote (RemoteOK & Remotive =
  papan remote penuh; Arbeitnow per item), selain itu "onsite";
- employment_type: None — API sumber tidak menyediakan nilai terstandar;
  ingest_service yang memutuskan nilai DB (kolom NOT NULL + CHECK enum).
"""

import html
import re
from datetime import datetime

# Batas kolom/kontak (selaras migrasi 0013, 0003, dan schemas/job.py).
MAX_TITLE_CHARS = 200
MAX_DESCRIPTION_CHARS = 20_000
MAX_SKILLS = 10
MAX_SKILL_NAME_CHARS = 50
MAX_EXTERNAL_ID_CHARS = 160
MAX_SOURCE_URL_CHARS = 500
MAX_COMPANY_CHARS = 255
MAX_LOCATION_CHARS = 255

# Tag blok umum → newline agar teks hasil strip tidak menempel jadi satu kata.
_BLOCK_TAG_RE = re.compile(r"(?i)</?(?:p|div|br|li|ul|ol|h[1-6]|tr|table)[^>]*>")
# Sisa tag apa pun → spasi.
_TAG_RE = re.compile(r"<[^>]+>")
_SPACES_RE = re.compile(r"[ \t\r\f\v]+")


def strip_html(raw: object, *, max_chars: int = MAX_DESCRIPTION_CHARS) -> str:
    """Buang tag HTML sederhana + unescape entity; kosong → "".

    Urutan: unescape dulu (menangani deskripsi ter-encode ganda "&lt;p&gt;")
    lalu strip tag — sekaligus aman: markup tersembunyi ikut terbuang. Dipakai
    hanya pada input terbatas dari konektor (bukan parser HTML lengkap).
    """
    if not raw:
        return ""
    text = html.unescape(str(raw))
    text = _BLOCK_TAG_RE.sub("\n", text)
    text = _TAG_RE.sub(" ", text)
    # Rapikan spasi per baris dan buang baris kosong beruntun.
    lines = (_SPACES_RE.sub(" ", line).strip() for line in text.split("\n"))
    cleaned = "\n".join(line for line in lines if line)
    return cleaned[:max_chars].strip()


def _clean_text(value: object, max_chars: int) -> str:
    """Coerce ke str ter-trim dengan batas panjang; None/kosong → ""."""
    if value is None:
        return ""
    return str(value).strip()[:max_chars]


def _skills_from_tags(tags: object) -> list[dict]:
    """tags (biasanya list[str]) → [{"name", "required": False}].

    Dedupe case-insensitive, maks MAX_SKILLS, nama dipangkas ke batas SkillIn.
    Tipe lain (None/str/list campur) ditangani tanpa error.
    """
    if not isinstance(tags, (list, tuple)):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for tag in tags:
        name = _clean_text(tag, MAX_SKILL_NAME_CHARS)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "required": False})
        if len(out) >= MAX_SKILLS:
            break
    return out


def _parse_datetime(value: object) -> datetime | None:
    """Terima datetime atau string ISO 8601 (termasuk sufiks 'Z'); gagal → None."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def to_job_payloads(source_type: str, raw_items: list[dict]) -> list[dict]:
    """Bentuk antara (sources.py) → payload insert `jobs`.

    Skip item tanpa title/company/external_id (tidak layak dedupe/tampil).
    Payload memuat kunci: title, company, location_text, description, skills,
    source_type, external_id, source_url, employment_type (None), work_mode,
    posted_at (datetime | None).
    """
    payloads: list[dict] = []
    if not raw_items:
        return payloads
    stype = str(source_type or "").strip() or "unknown"
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        title = _clean_text(raw.get("title"), MAX_TITLE_CHARS)
        company = _clean_text(raw.get("company"), MAX_COMPANY_CHARS)
        external_id = _clean_text(raw.get("external_id"), MAX_EXTERNAL_ID_CHARS)
        if not title or not company or not external_id:
            continue  # item tidak layak: tanpa identitas sumber / judul / perusahaan
        payloads.append(
            {
                "title": title,
                "company": company,
                "location_text": _clean_text(raw.get("location"), MAX_LOCATION_CHARS) or None,
                "description": strip_html(raw.get("description")),
                "skills": _skills_from_tags(raw.get("tags")),
                "source_type": stype,
                "external_id": external_id,
                "source_url": _clean_text(raw.get("url"), MAX_SOURCE_URL_CHARS) or None,
                # API sumber tidak menyediakan tipe kepegawaian terstandar —
                # keputusan nilai DB ada di ingest_service (kolom NOT NULL).
                "employment_type": None,
                "work_mode": "remote" if bool(raw.get("remote")) else "onsite",
                "posted_at": _parse_datetime(raw.get("posted_at")),
            }
        )
    return payloads
