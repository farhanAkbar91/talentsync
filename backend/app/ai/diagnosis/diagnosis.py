"""Aturan diagnosis CV deterministik (M7) — tanpa LLM, tanpa database.

Fungsi murni: payload ekstraksi (dict JSONB dari `cv_extractions.payload`,
bentuk sesuai `app.ai.extraction.payload_schema`) dinilai dengan 8 aturan beku
menghasilkan skor kualitas 0–100, label, kekuatan (aturan lolos), dan
perbaikan (aturan gagal beserta severity). Semua evaluasi aturan TOTAL —
aman terhadap payload kosong, field hilang, atau nilai None.

Skor: mulai 100; −12 per perbaikan "penting", −6 per "saran"; dasar 0.
Label: ≥80 "Baik", ≥60 "Cukup", <60 "Perlu Perbaikan".
"""

from typing import Any

# --- Konstanta aturan (kontrak beku, jangan diubah tanpa sinkronisasi FE) ---

RULE_ORDER = (
    "contact_email",
    "contact_phone",
    "summary_present",
    "exp_metrics",
    "skills_breadth",
    "education_present",
    "bullet_length",
    "certifications_present",
)

SEVERITY_PENTING = "penting"
SEVERITY_SARAN = "saran"

# Batas konten per aturan.
SUMMARY_MIN_LEN = 40
SUMMARY_MAX_LEN = 800
BULLET_MIN_LEN = 40
BULLET_MAX_LEN = 250
SKILLS_MIN_COUNT = 5

# Skoring.
SCORE_START = 100
SCORE_FLOOR = 0
PENALTY_PENTING = 12
PENALTY_SARAN = 6

# Label kualitas (band skor).
LABEL_BAIK_MIN = 80
LABEL_CUKUP_MIN = 60

# Teks positif untuk aturan yang lolos (muncul di `strengths`).
_PASS_TEXTS: dict[str, str] = {
    "contact_email": "Email tercantum — memudahkan HR menghubungi Anda.",
    "contact_phone": "Nomor telepon tercantum — HR mudah menghubungi Anda.",
    "summary_present": "Ringkasan profesional tersedia dengan panjang yang ideal.",
    "exp_metrics": "Ada pencapaian terukur dengan angka — kuat untuk ATS.",
    "skills_breadth": "Daftar skill cukup beragam (5+) — menunjukkan rentang keahlian.",
    "education_present": "Riwayat pendidikan sudah terisi.",
    "bullet_length": "Semua bullet pengalaman padat dan jelas (40–250 karakter).",
    "certifications_present": "Sertifikasi relevan tercantum — nilai tambah di mata HR.",
}

# Teks perbaikan untuk aturan yang gagal (muncul di `improvements`) + severity.
_FAIL_TEXTS: dict[str, tuple[str, str]] = {
    "contact_email": (
        "Email belum tercantum — HR tidak dapat menghubungi Anda.",
        SEVERITY_PENTING,
    ),
    "contact_phone": ("Nomor telepon belum tercantum.", SEVERITY_SARAN),
    "summary_present": (
        "Ringkasan profesional belum ada atau terlalu pendek/panjang — tulis 2–4 kalimat.",
        SEVERITY_PENTING,
    ),
    "exp_metrics": (
        "Belum ada pencapaian terukur — tambahkan angka (%, jumlah pengguna, Rp) "
        "pada bullet pengalaman.",
        SEVERITY_PENTING,
    ),
    "skills_breadth": (
        "Skill kurang dari 5 — daftar keahlian teknis dan perangkat yang dikuasai.",
        SEVERITY_SARAN,
    ),
    "education_present": ("Riwayat pendidikan belum terisi.", SEVERITY_PENTING),
    "bullet_length": (
        "Ada bullet pengalaman terlalu singkat (<40 karakter) — jelaskan kontribusi dan hasilnya.",
        SEVERITY_SARAN,
    ),
    "certifications_present": (
        "Belum ada sertifikasi — tambahkan sertifikasi relevan bila ada.",
        SEVERITY_SARAN,
    ),
}


# --- Helper normalisasi None-safe (evaluasi aturan harus TOTAL) ---


def _text(value: Any) -> str:
    """Nilai teks None-safe: string di-strip, selain itu string kosong."""
    return value.strip() if isinstance(value, str) else ""


def _as_list(value: Any) -> list[Any]:
    """Nilai daftar None-safe: list apa adanya, selain itu daftar kosong."""
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    """Nilai objek None-safe: dict apa adanya, selain itu dict kosong."""
    return value if isinstance(value, dict) else {}


def _all_bullets(payload: dict[str, Any]) -> list[str]:
    """Semua bullet pengalaman (teks ter-strip, item rusak/None dilewati)."""
    bullets: list[str] = []
    for experience in _as_list(payload.get("experiences")):
        for bullet in _as_list(_as_dict(experience).get("bullets")):
            text = _text(bullet)
            if text:
                bullets.append(text)
    return bullets


# --- Evaluasi per aturan (True = lolos) ---


def _rule_contact_email(payload: dict[str, Any]) -> bool:
    return bool(_text(_as_dict(payload.get("contact")).get("email")))


def _rule_contact_phone(payload: dict[str, Any]) -> bool:
    return bool(_text(_as_dict(payload.get("contact")).get("phone")))


def _rule_summary_present(payload: dict[str, Any]) -> bool:
    summary = _text(payload.get("summary"))
    return bool(summary) and SUMMARY_MIN_LEN <= len(summary) <= SUMMARY_MAX_LEN


def _rule_exp_metrics(payload: dict[str, Any]) -> bool:
    """Minimal satu bullet memuat angka (pencapaian terukur: %, jumlah, Rp)."""
    return any(any(ch.isdigit() for ch in bullet) for bullet in _all_bullets(payload))


def _rule_skills_breadth(payload: dict[str, Any]) -> bool:
    return len(_as_list(payload.get("skills"))) >= SKILLS_MIN_COUNT


def _rule_education_present(payload: dict[str, Any]) -> bool:
    return len(_as_list(payload.get("education"))) >= 1


def _rule_bullet_length(payload: dict[str, Any]) -> bool:
    """Hanya dievaluasi bila ada pengalaman. Tanpa bullet sama sekali → lolos
    (tidak ada bullet yang bisa diberi teks perbaikan "terlalu singkat")."""
    if not _as_list(payload.get("experiences")):
        return True
    return all(BULLET_MIN_LEN <= len(bullet) <= BULLET_MAX_LEN for bullet in _all_bullets(payload))


def _rule_certifications_present(payload: dict[str, Any]) -> bool:
    return len(_as_list(payload.get("certifications"))) >= 1


_RULE_EVALUATORS = {
    "contact_email": _rule_contact_email,
    "contact_phone": _rule_contact_phone,
    "summary_present": _rule_summary_present,
    "exp_metrics": _rule_exp_metrics,
    "skills_breadth": _rule_skills_breadth,
    "education_present": _rule_education_present,
    "bullet_length": _rule_bullet_length,
    "certifications_present": _rule_certifications_present,
}


def score_label(score: int) -> str:
    """Band skor → label kualitas (≥80 "Baik", ≥60 "Cukup", <60 "Perlu Perbaikan")."""
    if score >= LABEL_BAIK_MIN:
        return "Baik"
    if score >= LABEL_CUKUP_MIN:
        return "Cukup"
    return "Perlu Perbaikan"


def compute_score(improvements: list[dict[str, str]]) -> int:
    """Skor akhir: 100 dikurangi penalti per perbaikan, di-floor ke 0."""
    score = SCORE_START
    for improvement in improvements:
        penalty = PENALTY_PENTING if improvement["severity"] == SEVERITY_PENTING else PENALTY_SARAN
        score -= penalty
    return max(score, SCORE_FLOOR)


def diagnose_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Nilai payload ekstraksi (dict) → {quality_score, label, strengths, improvements}.

    Total terhadap payload kosong/parsial/rusak: field hilang berarti gagal
    aturan terkait (kecuali bullet_length yang hanya dievaluasi bila ada
    pengalaman). Urutan strengths/improvements konsisten dengan RULE_ORDER.
    """
    data = _as_dict(payload)
    strengths: list[dict[str, str]] = []
    improvements: list[dict[str, str]] = []

    for rule_id in RULE_ORDER:
        if _RULE_EVALUATORS[rule_id](data):
            strengths.append({"rule_id": rule_id, "text": _PASS_TEXTS[rule_id]})
        else:
            text, severity = _FAIL_TEXTS[rule_id]
            improvements.append({"rule_id": rule_id, "text": text, "severity": severity})

    quality_score = compute_score(improvements)
    return {
        "quality_score": quality_score,
        "label": score_label(quality_score),
        "strengths": strengths,
        "improvements": improvements,
    }
