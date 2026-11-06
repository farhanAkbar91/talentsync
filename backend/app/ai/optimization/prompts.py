"""Perakit prompt optimasi CV (M8) — aturan grounding BEKU + skema JSON keluaran.

Kontrak beku (Wave 5):
- system: peran + aturan grounding (hanya parafrase/restrukturisasi/penekanan
  konten yang SUDAH ADA di CV; DILARANG menambah perusahaan/skill/sertifikasi/
  tanggal/angka baru; tiap edit merujuk teks asli; maksimal 8 edit) + skema
  JSON keluaran eksplisit.
- user: teks CV berlabel (build_cv_text) + teks lowongan (build_job_text) +
  ringkasan gap skill (bila tersedia) sebagai referensi penekanan.
"""

from __future__ import annotations

import json

from app.ai.matching.embedder import build_cv_text, build_job_text

# Versi prompt — bagian dari kunci cache kuota optimasi (ubah = cache basi).
PROMPT_VERSION = "v1"
MAX_EDITS = 8

# change_type yang diizinkan (sumber tunggal; validator memakai konstanta ini).
CHANGE_TYPES = ("reword", "reorder", "emphasize", "quantify")

# Skema JSON keluaran — dipakai di teks prompt DAN response_format json_schema
# strict Groq (llm_client). additionalProperties=False + required lengkap adalah
# syarat mode strict.
EDITS_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "edits": {
            "type": "array",
            "maxItems": MAX_EDITS,
            "items": {
                "type": "object",
                "properties": {
                    "suggestion_id": {"type": "string"},
                    "source_ref": {"type": "string"},
                    "section": {"type": "string"},
                    "original_text": {"type": "string"},
                    "suggested_text": {"type": "string"},
                    "rationale": {"type": "string"},
                    "change_type": {"type": "string", "enum": list(CHANGE_TYPES)},
                },
                "required": [
                    "suggestion_id",
                    "source_ref",
                    "section",
                    "original_text",
                    "suggested_text",
                    "rationale",
                    "change_type",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["edits"],
    "additionalProperties": False,
}

_SYSTEM_TEMPLATE = """Anda asisten pengoptimal CV berbahasa Indonesia untuk TalentSync AI. \
Tugas Anda menyusun saran perbaikan CV agar lebih selaras dengan lowongan yang dituju.

ATURAN GROUNDING (BEKU — pelanggaran membuat saran ditolak sistem):
1. Hanya boleh memparafrase (reword), merestrukturisasi (reorder), menekankan \
(emphasize), atau menata ulang penekanan (quantify) atas konten yang SUDAH ADA di CV. \
Tidak boleh mengarang narasi baru di luar isi CV.
2. DILARANG KERAS menambahkan: perusahaan baru, jabatan/institusi baru, skill baru, \
sertifikasi baru, pendidikan baru, bahasa baru, tanggal/tahun baru, atau angka baru.
3. Setiap edit WAJIB merujuk teks asli: `original_text` adalah kutipan persis (tanpa \
penanda poin "-") dari teks CV, dan `source_ref` adalah awalan literal dari \
`original_text` yang dapat dilokalisasi pada baris teks CV.
4. `change_type` hanya boleh salah satu dari: reword, reorder, emphasize, quantify.
5. Maksimal {max_edits} edit. Bila tidak ada perbaikan yang berharga, kembalikan \
daftar `edits` kosong.
6. Keluarkan HANYA JSON valid (tanpa teks penjelasan) sesuai skema berikut:

{schema}"""

_USER_TEMPLATE = """=== CV KANDIDAT (SATU-SATUNYA SUMBER KONTEN) ===
{cv_text}

=== LOWONGAN YANG DITUJU ===
{job_text}
{gap_block}
=== INSTRUKSI ===
Hasilkan JSON dengan kunci `edits` (maksimal {max_edits} item). Setiap item memuat \
suggestion_id, source_ref, section, original_text, suggested_text, rationale, dan \
change_type. `suggested_text` adalah versi perbaikan dari `original_text` — sama \
panjang semangatnya, tanpa konten baru."""


def _skill_names(job: dict) -> list[str]:
    """Ekstrak nama skill dari job dict (terima dict {"name": ...} atau string)."""
    names: list[str] = []
    for skill in job.get("skills") or []:
        if isinstance(skill, dict):
            name = str(skill.get("name") or skill.get("display") or "").strip()
        else:
            name = str(skill).strip()
        if name:
            names.append(name)
    return names


def _gap_block(gap: dict | None) -> str:
    """Ringkasan gap skill untuk konteks user prompt (kosong bila gap None)."""
    items = (gap or {}).get("items") or []
    lines: list[str] = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("display") or item.get("name") or "").strip()
        if not name:
            continue
        severity = str(item.get("severity") or "").strip()
        lines.append(f"- {name}" + (f" ({severity})" if severity else ""))
    if not lines:
        return ""
    return (
        "=== GAP SKILL (REFERENSI PENEKANAN — BUKAN IZIN MENAMBAH SKILL BARU) ===\n"
        + "\n".join(lines)
        + "\n"
    )


def build_messages(cv_payload: dict, job: dict, gap: dict | None) -> tuple[str, str]:
    """Rakit (system, user) untuk panggilan LLM optimasi.

    `cv_payload` adalah payload M1 terkonfirmasi; `job` dict berisi title/skills/
    description/requirements/responsibilities; `gap` hasil match_service.get_gap
    (boleh None). Fungsi murni — total terhadap input kosong.
    """
    system = _SYSTEM_TEMPLATE.format(
        max_edits=MAX_EDITS, schema=json.dumps(EDITS_JSON_SCHEMA, indent=2, ensure_ascii=False)
    )

    cv_text = build_cv_text(cv_payload) or "(CV kosong)"
    job_text = build_job_text(
        title=str(job.get("title") or "Tanpa judul"),
        skill_names=_skill_names(job),
        description=str(job.get("description") or ""),
        requirements=str(job.get("requirements")) if job.get("requirements") else None,
        responsibilities=str(job.get("responsibilities")) if job.get("responsibilities") else None,
    )
    user = _USER_TEMPLATE.format(
        cv_text=cv_text,
        job_text=job_text,
        gap_block=_gap_block(gap),
        max_edits=MAX_EDITS,
    )
    return system, user
