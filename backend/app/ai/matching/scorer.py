"""Scorer kompatibilitas (M4): fungsi MURNI perhitungan skor CV vs lowongan.

Tanpa DB, tanpa I/O wajib — semua data disuntikkan pemanggil (service M4 atau
skrip evaluasi). Rumus BEKU (kontrak M4, jangan diubah sepihak):

- F_semantic   = map_cosine(cosine(cv_vec, job_vec))               (kalibrasi M4)
- F_skill      = 100·Σ(w_i·Cov_i)/Σ(w_i) dengan w_req=0.6, w_pref=0.4;
                 kredit per skill lowongan: 1.0 exact/alias, 0.5 related, 0 kosong.
                 Kelas kosong netral (bobotnya dibagi ke kelas yang ada); skill
                 lowongan dengan slug None (tidak ter-resolve) DIKECUALIKAN.
- F_experience = 100·(0.6·min(years_have, years_req)/max(years_req, 1) + 0.4·title_similarity)
- F_education  = ordinal jenjang (kandidat vs syarat lowongan).
- Overall      = Σ w_i·F_i dengan bobot dinormalisasi ke jumlah 1 (dijaga div nol).

Catatan title_similarity: teks judul pengalaman perlu di-embed sebelum cosine —
pemanggil bervolume tinggi (match_service) menghitung `cv_title_vecs` SEKALI per
CV dan menyuntikkannya ke `score_pair`; tanpa itu (atau panjang tak cocok),
fallback `set_title_encoder`/`get_settings().embedding_model` dipakai per
pemanggilan (jalur evaluasi/skrip). `calibration_version` diterima hanya untuk
traceability kontrak — anchor selalu dari berkas/parameter pemanggil.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime

from app.ai.extraction.entities import parse_date_range
from app.ai.matching.calibration import map_cosine
from app.ai.matching.similarity import cosine

# Bobot kelas coverage skill (BEKU).
W_REQUIRED = 0.6
W_PREFERRED = 0.4

# Bobot sub-faktor pengalaman (BEKU).
W_YEARS = 0.6
W_TITLE = 0.4

# Tahun pengalaman minimal per seniority (fallback bila regex tahun tak kena).
SENIORITY_YEARS: dict[str, int] = {
    "intern": 0,
    "junior": 1,
    "entry": 1,
    "mid": 3,
    "middle": 3,
    "senior": 5,
    "lead": 6,
    "manager": 6,
}
DEFAULT_YEARS_REQUIRED = 3

# Regex tahun pengalaman lowongan: "3+ tahun", "5 tahun", "2 years".
# SECURITY (audit Wave 3): kuantifier digit dibatasi 1-4 + whitespace maksimal
# 3 — regex linear; teks HR tak terbatas ("\d+" pada 16k digit = 34,6 dtk).
_SCAN_CAP_CHARS = 4_000
_YEARS_REQ_RE = re.compile(r"(\d{1,4})\s{0,3}\+?\s{0,3}(?:tahun|years)", re.IGNORECASE)

# ---------------------------------------------------------------- encoder judul

# Hook injeksi test/service: teks judul → vektor (model sama dgn embedding utama).
_TITLE_ENCODER: Callable[[list[str]], list[list[float]]] | None = None


def set_title_encoder(encoder: Callable[[list[str]], list[list[float]]] | None) -> None:
    """Pasang encoder vektor judul pengalaman (injeksi test/service; None = default)."""
    global _TITLE_ENCODER
    _TITLE_ENCODER = encoder


def _encode_titles(texts: list[str]) -> list[list[float]]:
    """Encode kumpulan judul pengalaman → vektor (satu batch).

    Default (tanpa injeksi): embedder singleton pada model dari Settings global —
    jalur skrip evaluasi. match_service selalu meng-inject encoder yang terikat
    ke settings.application agar konsisten dengan cv_vec/job_vec.
    """
    if _TITLE_ENCODER is not None:
        return list(_TITLE_ENCODER(texts))
    from app.ai.matching.embedder import get_embedder  # noqa: PLC0415 — impor berat malas
    from app.core.config import get_settings  # noqa: PLC0415

    return get_embedder(get_settings().embedding_model).encode(texts)


# ---------------------------------------------------------------- tahun pengalaman


def compute_years_required(job: dict) -> int:
    """Tahun pengalaman minimal lowongan: regex atas description+requirements,
    fallback peta seniority (default 3). Total/robust terhadap field kosong."""
    text = " ".join(str(job.get(key) or "") for key in ("description", "requirements"))
    match = _YEARS_REQ_RE.search(text[:_SCAN_CAP_CHARS])
    if match is not None:
        try:
            return max(0, int(match.group(1)))
        except ValueError:  # defensif — regex selalu digit, tapi jaga kontrak total
            pass
    seniority = str(job.get("seniority") or "").strip().lower()
    return SENIORITY_YEARS.get(seniority, DEFAULT_YEARS_REQUIRED)


_ANCHOR_RE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?$")


def _parse_anchor(anchor: str | None) -> tuple[int, int] | None:
    """Anchor tanggal payload ("YYYY-MM" atau "YYYY") → (tahun, bulan)."""
    if not anchor:
        return None
    match = _ANCHOR_RE.fullmatch(anchor.strip())
    if match is None:
        return None
    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else 1
    if not 1 <= month <= 12:
        return None
    return year, month


def _experience_months(experience: dict, today: tuple[int, int]) -> int:
    """Lama satu pengalaman dalam bulan (ujung-ke-ujung, tanpa hari).

    Prioritas teks `period` via parse_date_range (kontrak M4); fallback field
    terstruktur start/end/current bila period kosong. Rentang berjalan dihitung
    s.d. bulan berjalan. Rentang terbalik/negatif → 0 (robust).
    """
    start: tuple[int, int] | None = None
    end: tuple[int, int] | None = None
    ongoing = False

    parsed = parse_date_range(str(experience.get("period") or ""))
    if parsed is not None:
        start_raw, end_raw, ongoing = parsed
        start = _parse_anchor(start_raw)
        end = _parse_anchor(end_raw) if end_raw is not None else None
    else:
        start = _parse_anchor(str(experience.get("start") or ""))
        end = _parse_anchor(str(experience.get("end") or ""))
        ongoing = bool(experience.get("current")) or (start is not None and end is None)

    if start is None:
        return 0
    if ongoing or end is None:
        end = today
    months = (end[0] - start[0]) * 12 + (end[1] - start[1])
    return max(0, months)


def compute_years_have(cv_payload: dict) -> float:
    """Total span pengalaman (tahun pecahan) dari cv_payload["experiences"].

    Rentang berjalan dihitung s.d. hari ini; rentang TUMPANG-TINDIH dijumlahkan
    apa adanya (tanpa dedupe interval) — disengaja sesuai kontrak M4. Entri tanpa
    tanggal terbaca dihitung 0.
    """
    today_dt = datetime.now(UTC)
    today = (today_dt.year, today_dt.month)
    total_months = 0
    for experience in (cv_payload or {}).get("experiences") or []:
        if not isinstance(experience, dict):
            continue
        total_months += _experience_months(experience, today)
    return total_months / 12.0


# ---------------------------------------------------------------- faktor skill


def _payload_skill_evidence(cv_payload: dict, job_skill: dict) -> str | None:
    """Bukti literal dari section KEAHLIAN payload bila nama cocok (casefold).

    Dipakai hanya untuk match_type "exact" (skill kanon memang eksplisit di
    payload); alias/related tidak memiliki baris di section itu → None.
    """
    target_raw = str(job_skill.get("name") or "").strip().casefold()
    target_display = str(job_skill.get("display") or "").strip().casefold()
    for item in (cv_payload or {}).get("skills") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        folded = name.casefold()
        if folded == target_raw or (target_display and folded == target_display):
            evidence = str(item.get("evidence") or "").strip()
            return evidence or name
    return None


def evaluate_skills(
    cv_payload: dict,
    job: dict,
    candidate_slugs: set[str],
    explicit_slugs: set[str],
    taxonomy_related: dict[str, set[str]],
) -> tuple[float, list[dict], list[dict]]:
    """Hitung F_skill + daftar matched/missing (aturan BEKU M4).

    Mengembalikan (f_skill, matched, missing). matched hanya kredit penuh
    (exact/alias); skill lowongan yang hanya tersentuh skill TERKAIT tetap
    "missing" dengan severity lebih lunak (menengah utk required) — konsisten
    dengan aturan severity beku.
    """
    req_credits: list[float] = []
    pref_credits: list[float] = []
    matched: list[dict] = []
    missing: list[dict] = []

    for skill in (job or {}).get("skills") or []:
        if not isinstance(skill, dict):
            continue
        slug = skill.get("slug")
        if not slug:  # raw tak ter-resolve → dikecualikan dari coverage (dokumen)
            continue
        required = bool(skill.get("required"))
        display = str(skill.get("display") or skill.get("name") or slug)
        if slug in candidate_slugs:
            match_type = "exact" if slug in explicit_slugs else "alias"
            matched.append(
                {
                    "name": slug,
                    "display": display,
                    "required": required,
                    "match_type": match_type,
                    "evidence": (
                        _payload_skill_evidence(cv_payload, skill)
                        if match_type == "exact"
                        else None
                    ),
                }
            )
            credit = 1.0
        else:
            related_hit = bool(taxonomy_related.get(slug, set()) & candidate_slugs)
            credit = 0.5 if related_hit else 0.0
            if required:
                severity = "menengah" if related_hit else "kritis"
            else:
                severity = "minor"
            missing.append(
                {"name": slug, "display": display, "required": required, "severity": severity}
            )
        (req_credits if required else pref_credits).append(credit)

    weighted = 0.0
    total_weight = 0.0
    for credits, weight in ((req_credits, W_REQUIRED), (pref_credits, W_PREFERRED)):
        if credits:  # kelas kosong netral — bobotnya tidak ikut penyebut
            mean = sum(credits) / len(credits)
            weighted += weight * mean
            total_weight += weight
    f_skill = 100.0 * weighted / total_weight if total_weight > 0 else 0.0
    return f_skill, matched, missing


# ---------------------------------------------------------------- faktor pendidikan

# Jenjang kandidat → level ordinal (urutan dicek pada SATU string degree).
_CANDIDATE_LEVELS: tuple[tuple[str, int], ...] = (
    ("s3", 4),
    ("doktor", 4),
    ("phd", 4),
    ("ph.d", 4),
    ("s2", 3),
    ("magister", 3),
    ("master", 3),
    ("s1", 2),
    ("d4", 2),
    ("bachelor", 2),
    ("sarjana", 2),
    ("d3", 1),
    ("d2", 1),
    ("sma", 1),
    ("smk", 1),
    ("vocational", 1),
    ("diploma", 1),
)

# Syarat jenjang lowongan (BEKU): level 3 > 2 > 1; default 2.
_JOB_LEVEL_PATTERNS: tuple[tuple[int, str], ...] = (
    (3, r"\b(?:s2|master|magister)\b"),
    (2, r"\b(?:s1|bachelor|sarjana)\b"),
    (1, r"\b(?:d3|diploma|sma|smk)\b"),
)


def _candidate_education_level(cv_payload: dict) -> int:
    """Level ordinal tertinggi dari degree pendidikan payload (0 = tanpa pendidikan)."""
    highest = 0
    for item in (cv_payload or {}).get("education") or []:
        if not isinstance(item, dict):
            continue
        degree = str(item.get("degree") or "").strip().lower()
        if not degree:
            continue
        for token, level in _CANDIDATE_LEVELS:
            if re.search(rf"\b{re.escape(token)}\b", degree):
                highest = max(highest, level)
                break
    return highest


def compute_required_education(job: dict) -> int:
    """Level jenjang minimal lowongan dari description+requirements (default 2)."""
    text = " ".join(str(job.get(key) or "") for key in ("description", "requirements")).lower()
    highest = 0
    for level, pattern in _JOB_LEVEL_PATTERNS:
        if re.search(pattern, text):
            highest = max(highest, level)
    return highest if highest > 0 else 2


def evaluate_education(cv_payload: dict, job: dict) -> float:
    """F_education ordinal BEKU: di atas 100, pas 90, satu tingkat di bawah 55,
    ≥2 tingkat di bawah / tanpa pendidikan 25."""
    candidate_level = _candidate_education_level(cv_payload)
    if candidate_level == 0:
        return 25.0
    required_level = compute_required_education(job)
    if candidate_level > required_level:
        return 100.0
    if candidate_level == required_level:
        return 90.0
    if candidate_level == required_level - 1:
        return 55.0
    return 25.0


# ---------------------------------------------------------------- faktor pengalaman


def evaluate_experience(
    cv_payload: dict,
    job: dict,
    job_title_vec: list[float],
    cv_title_vecs: list[list[float]] | None = None,
) -> tuple[float, list[dict]]:
    """F_experience BEKU + top_experiences (judul ber-cosine tertinggi).

    `cv_title_vecs` = vektor judul pengalaman SEJAJAR dengan urutan
    cv_payload["experiences"] (dihitung pemanggil SEKALI per CV — jangan encode
    ulang per pasangan, lihat benchmark M4). None atau panjang tak cocok →
    fallback encode di sini (total, tidak crash). Mengembalikan
    (f_experience, top_experiences). Tanpa judul/vektor judul →
    title_similarity 0.0 (kontrak). Cosine negatif dijepit ke 0 (tanpa sinyal).
    """
    years_req = compute_years_required(job)
    years_have = compute_years_have(cv_payload)
    ratio = min(years_have, float(years_req)) / max(float(years_req), 1.0)
    ratio = max(0.0, min(1.0, ratio))

    # Enumerasi mentah: cv_title_vecs sejajar dengan payload APA ADANYA (termasuk
    # entri bukan-dict / tanpa judul) — indeks dipakai mengambil vektor pasangannya.
    raw_experiences = list((cv_payload or {}).get("experiences") or [])
    titled: list[tuple[int, dict]] = [
        (index, item)
        for index, item in enumerate(raw_experiences)
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    similarities: list[float] = []
    if titled and job_title_vec:
        if cv_title_vecs is not None and len(cv_title_vecs) == len(raw_experiences):
            vectors = [cv_title_vecs[index] for index, _item in titled]
        else:  # fallback: encode per pemanggilan (kompatibilitas panggilan langsung)
            vectors = _encode_titles([str(item["title"]).strip() for _index, item in titled])
        for vector, _pair in zip(vectors, titled, strict=False):  # robust: potong bila beda
            similarities.append(max(0.0, cosine(vector, job_title_vec)))
    title_similarity = max(similarities) if similarities else 0.0

    f_experience = 100.0 * (W_YEARS * ratio + W_TITLE * title_similarity)

    ranked = sorted(zip(titled, similarities, strict=False), key=lambda pair: pair[1], reverse=True)
    top_experiences = [
        {
            "title": str(item.get("title")),
            "company": str(item.get("company")) if item.get("company") else None,
            "period": str(item.get("period")) if item.get("period") else None,
            "relevance": round(float(sim), 4),
        }
        for (_index, item), sim in ranked[:3]
    ]
    return f_experience, top_experiences


# ---------------------------------------------------------------- skor pasangan


def normalize_weights(
    weights: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Normalisasi bobot ke jumlah 1 (guard pembagian: total ≤ 0 → rata 0.25)."""
    values = [float(weight) for weight in weights]
    total = sum(values)
    if total <= 0.0:
        return (0.25, 0.25, 0.25, 0.25)
    return tuple(value / total for value in values)  # type: ignore[return-value]


def score_pair(
    *,
    cv_payload: dict,
    job: dict,
    cv_vec: list[float],
    job_vec: list[float],
    job_title_vec: list[float],
    candidate_slugs: set[str],
    explicit_slugs: set[str],
    weights: tuple[float, float, float, float],
    taxonomy_related: dict[str, set[str]],
    calibration_version: str = "v1",
    cv_title_vecs: list[list[float]] | None = None,
) -> dict:
    """Skor kompatibilitas satu pasangan CV-lowongan (fungsi murni, kontrak BEKU).

    `job["skills"]` berbentuk [{"name": raw, "slug": slug|None, "display": nama
    kanon, "required": bool}] — slug sudah di-resolve pemanggil via taksonomi.
    `cv_title_vecs` (opsional): vektor judul pengalaman sejajar urutan
    cv_payload["experiences"] — WAJIB disediakan pemanggil bervolume tinggi
    (service) agar judul tidak di-embed ulang per pasangan; None/panjang tak
    cocok → fallback encode internal. `calibration_version` bersifat
    traceability (skor selalu dari anchor berkas/parameter). Semua fungsi
    total: field kosong/aneh → skor 0 tanpa exception.
    """
    del calibration_version  # traceability kontrak; anchor ditentukan map_cosine

    cv_payload = cv_payload or {}
    job = job or {}

    f_semantic = map_cosine(cosine(cv_vec, job_vec))
    f_skill, matched, missing = evaluate_skills(
        cv_payload, job, candidate_slugs, explicit_slugs, taxonomy_related or {}
    )
    f_experience, top_experiences = evaluate_experience(
        cv_payload, job, job_title_vec, cv_title_vecs
    )
    f_education = evaluate_education(cv_payload, job)

    norm = normalize_weights(weights)
    overall = (
        norm[0] * f_semantic + norm[1] * f_skill + norm[2] * f_experience + norm[3] * f_education
    )

    return {
        "factors": {
            "semantic": round(f_semantic, 4),
            "skill_coverage": round(f_skill, 4),
            "experience": round(f_experience, 4),
            "education": round(f_education, 4),
        },
        "overall": round(overall, 4),
        "matched": matched,
        "missing": missing,
        "top_experiences": top_experiences,
    }
