"""Service skill kandidat & lowongan (M2 Wave 2B): normalisasi + persistensi.

Alur data:
- `extract_skills_from_payload`: payload ekstraksi (JSONB) -> daftar skill
  ternormalisasi, TANPA menulis DB (murni baca+normalisasi) — dipakai bersama
  oleh hook confirm CV dan pipeline evaluasi.
- `persist_cv_skills`: simpan `candidate_skills` status 'suggested' secara
  idempoten (baris accepted/rejected tidak pernah tersentuh).
- `apply_skills_to_profile`: kandidat menerima saran -> 'accepted' + merge nama
  kanon ke `candidate_profiles.skills` (JSONB, maks 30).
- `normalize_job_skills` + dipasang di job_service: skill lowongan -> `job_skills`.

Prinsip (kontrak taxonomy_service): item TANPA padanan kanon tidak pernah
dipaksa persist (FK canonical NOT NULL) — ia tetap dilaporkan ke pemanggil
dengan needs_review=True agar bisa direview manual.
"""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.profile import CandidateProfile
from app.models.skill import CandidateSkill, CanonicalSkill
from app.models.user import User
from app.services import cv_service, profile_service, taxonomy_service

# Confidence tetap untuk skill inferred (temuan kamus di narasi CV).
INFERRED_CONFIDENCE = 0.7

# Batas read-time: baris dengan confidence di bawah ini dihitung ulang
# needs_review/suggestions-nya via normalize_skill (re-derivasi murah, tanpa cache).
REVIEW_REDERIVE_BELOW = 0.85

# Batas jumlah skill di candidate_profiles.skills (mirror schemas/profile.py).
PROFILE_SKILLS_LIMIT = 30

# Panjang bukti maksimum yang disimpan agar baris tetap ringkas di UI.
EVIDENCE_MAX_CHARS = 200

# Karakter yang dianggap "bagian dari kata" saat menentukan batas kata pada
# pemindaian inferred — sinkron dengan _KEEP_INSIDE_WORD taxonomy_service agar
# "c++", "c#", ".net", "node.js", "ci/cd" tercari utuh (bukan terpotong).
_WORDISH = r"[\w+#./-]"

# Urutan tampil per extraction_method (explicit dulu, lalu inferred, lainnya akhir).
_METHOD_ORDER = {"explicit": 0, "inferred": 1}

# Hasil normalize bila taksonomi belum di-seed (indeks alias kosong) — dipakai
# penjagaan agar normalize_skill tidak dipanggil tanpa kamus.
_NO_MATCH: dict = {
    "canonical": None,
    "confidence": 0.0,
    "method": "none",
    "needs_review": True,
    "suggestions": [],
}


# --- Ekstraksi + normalisasi dari payload (tanpa tulis DB) ---


def _normalize_with_index(db: Session, raw: str, index: dict) -> dict:
    """normalize_skill dengan penjagaan taksonomi kosong: indeks alias tanpa
    entri berarti tidak mungkin ada padanan — kembalikan hasil 'none' tanpa
    memanggil normalize_skill (asumsinya taksonomi sudah di-seed)."""
    if not index:
        return dict(_NO_MATCH)
    return taxonomy_service.normalize_skill(db, raw)


def _build_scan_regex(
    index: dict[str, CanonicalSkill],
) -> tuple[re.Pattern, dict[str, CanonicalSkill]]:
    """Gabungkan seluruh kunci kamus (nama kanon + alias, ternormalisasi) menjadi
    SATU regex alternatif; kunci terpanjang dicoba lebih dulu agar frasa spesifik
    ("power bi") menang atas substring-nya ("bi"). Batas kata memakai lookaround
    (bukan \\b) karena kunci bisa diawasi/diakhiri karakter non-alfanumerik
    ("c++", ".net") — dan agar "javascript" TIDAK terpotong jadi "java"."""
    key_map: dict[str, CanonicalSkill] = {}
    for key, skill in index.items():
        nk = taxonomy_service.normalize_text(key)
        if not nk:
            continue
        # Nama kanon selalu menang atas alias bila bertabrakan setelah normalisasi.
        if nk == taxonomy_service.normalize_text(skill.name):
            key_map[nk] = skill
        else:
            key_map.setdefault(nk, skill)

    body = "|".join(re.escape(key) for key in sorted(key_map, key=len, reverse=True))
    # Batas kata: tidak boleh bersentuhan dengan karakter "wordish" di kedua sisi.
    # Efek samping yang diinginkan: "sql/python" (pemisah '/') tidak dicocokkan
    # per-bagian — konsisten dengan perlakuan "ci/cd" sebagai satu istilah.
    pattern = re.compile(rf"(?<!{_WORDISH})(?:{body})(?!{_WORDISH})")
    return pattern, key_map


def _scan_section(
    lines: list[str],
    section: str,
    pattern: re.Pattern,
    key_map: dict[str, CanonicalSkill],
    inferred: list[dict],
    seen_slugs: set[str],
) -> None:
    """Pindai tiap baris teks dengan regex kamus; kecocokan pertama per slug
    menang (urutan section pemanggil menentukan). Bukti = baris asli (dipotong)."""
    if pattern is None:  # taksonomi kosong — tidak ada yang bisa dicocokkan
        return
    for line in lines:
        if not line:
            continue
        normalized = taxonomy_service.normalize_text(line)
        if not normalized:
            continue
        for match in pattern.finditer(normalized):
            skill = key_map.get(match.group(0))
            if skill is None or skill.slug in seen_slugs:
                continue
            seen_slugs.add(skill.slug)
            inferred.append(
                {
                    "canonical": {
                        "slug": skill.slug,
                        "name": skill.name,
                        "category": skill.category,
                        "skill_type": skill.skill_type,
                    },
                    "raw_name": match.group(0),
                    "confidence": INFERRED_CONFIDENCE,
                    "evidence": line.strip()[:EVIDENCE_MAX_CHARS],
                    "source_section": section,
                    "extraction_method": "inferred",
                    "needs_review": False,
                    "suggestions": [],
                }
            )


def extract_skills_from_payload(db: Session, payload: dict | None) -> list[dict]:
    """Normalisasi skill dari payload ekstraksi (MURNI baca — tanpa tulis DB).

    - EXPLICIT: tiap item `payload["skills"]` dinormalisasi via normalize_skill.
      Item tanpa padanan kanon TETAP dimasukkan ke hasil (canonical None,
      confidence 0.0, needs_review) — bisa dihitung/dilaporkan pemanggil, tapi
      tidak persistable (FK canonical NOT NULL).
    - INFERRED: pindai `experiences[*].bullets`, `projects[*].description`, dan
      `summary` memakai kamus alias (whole-word/phrase, case-insensitive).
      Confidence 0.7; bukti = baris yang memuat (dipotong 200 karakter).
    - Dedupe per slug kanon: explicit menang atas inferred; inferred tercatat
      lebih dulu menang atas yang belakangan (urutan section pemanggilan).
    - Urutan hasil: explicit -> inferred -> item mentah tanpa padanan.
    """
    if not payload:
        return []

    # Indeks alias dimuat SEKALI untuk seluruh proses (explicit + inferred).
    index = taxonomy_service.load_alias_index(db)

    matched: list[dict] = []
    inferred: list[dict] = []
    unmatched: list[dict] = []
    seen_slugs: set[str] = set()
    seen_raw: set[str] = set()

    # 1) EXPLICIT — section skills payload.
    for item in payload.get("skills") or []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("name") or "").strip()
        if not raw:
            continue
        norm = _normalize_with_index(db, raw, index)
        canon = norm["canonical"]
        if canon is None:
            # Tanpa padanan: confidence tetap 0.0 (confidence payload item TIDAK
            # dipakai — ia mengukur kualitas ekstraksi, bukan kecocokan taksonomi).
            key = raw.lower()
            if key in seen_raw:
                continue
            seen_raw.add(key)
            unmatched.append(
                {
                    "canonical": None,
                    "raw_name": raw,
                    "confidence": 0.0,
                    "evidence": item.get("evidence"),
                    "source_section": "skills",
                    "extraction_method": "explicit",
                    "needs_review": True,
                    "suggestions": norm["suggestions"],
                }
            )
            continue
        if canon.slug in seen_slugs:
            continue  # dedupe: kemunculan pertama menang
        seen_slugs.add(canon.slug)
        matched.append(
            {
                "canonical": {
                    "slug": canon.slug,
                    "name": canon.name,
                    "category": canon.category,
                    "skill_type": canon.skill_type,
                },
                "raw_name": raw,
                "confidence": float(norm["confidence"]),
                "evidence": item.get("evidence"),
                "source_section": "skills",
                "extraction_method": "explicit",
                "needs_review": bool(norm["needs_review"]),
                "suggestions": norm["suggestions"],
            }
        )

    # 2) INFERRED — pindai narasi; slug yang sudah explicit dilewati.
    if index:
        pattern, key_map = _build_scan_regex(index)
    else:
        pattern, key_map = None, {}
    for experience in payload.get("experiences") or []:
        if isinstance(experience, dict):
            _scan_section(
                [str(b) for b in (experience.get("bullets") or [])],
                "experience",
                pattern,
                key_map,
                inferred,
                seen_slugs,
            )
    for project in payload.get("projects") or []:
        if isinstance(project, dict) and project.get("description"):
            _scan_section(
                [str(project["description"])],
                "projects",
                pattern,
                key_map,
                inferred,
                seen_slugs,
            )
    if pattern is not None and payload.get("summary"):
        _scan_section([str(payload["summary"])], "summary", pattern, key_map, inferred, seen_slugs)

    return matched + inferred + unmatched


# --- Persistensi skill kandidat ---


def persist_cv_skills(db: Session, user: User, cv_id: uuid.UUID, extraction) -> None:
    """Simpan hasil ekstraksi sebagai `candidate_skills` status 'suggested'.

    - Hapus dulu baris suggested milik CV ini (accepted/rejected dipertahankan),
      lalu sisipkan ulang dari payload terbaru → pemanggilan berulang idempoten.
    - Hormati UNIQUE(candidate, canonical): baris yang sudah ada untuk pasangan
      (kandidat, skill kanon) tidak pernah diduplikasi — accepted (dari CV mana
      pun) dan rejected dilewati; suggested dari CV lain juga dilewati.
    - TIDAK commit — pemanggil (confirm_extraction) yang commit agar hook tetap
      atomik dengan penyimpanan payload; di sini hanya flush.
    """
    payload = extraction.payload if extraction is not None else None
    items = extract_skills_from_payload(db, payload)

    # 1) Usulan lama milik CV ini diganti; keputusan kandidat (accepted/rejected)
    #    tidak pernah dibuang oleh konfirmasi ulang.
    stale = list(
        db.scalars(
            select(CandidateSkill).where(
                CandidateSkill.candidate_user_id == user.id,
                CandidateSkill.source_cv_id == cv_id,
                CandidateSkill.status == "suggested",
            )
        )
    )
    for row in stale:
        db.delete(row)
    db.flush()

    if not items:
        return

    # 2) Peta baris (kandidat, kanon) yang tersisa setelah penghapusan di atas.
    existing = {
        row.canonical_skill_id: row
        for row in db.scalars(
            select(CandidateSkill).where(CandidateSkill.candidate_user_id == user.id)
        )
    }

    # 3) Upsert item yang punya padanan kanon; item canonical None dilewati.
    for item in items:
        if item["canonical"] is None:
            continue
        canon = db.scalar(
            select(CanonicalSkill).where(CanonicalSkill.slug == item["canonical"]["slug"])
        )
        if canon is None:  # defensif: slug tidak ada di taksonomi aktif
            continue
        row = existing.get(canon.id)
        if row is not None:
            if row.status == "suggested" and row.source_cv_id == cv_id:
                # Defensif (normalnya sudah terhapus di langkah 1): segarkan jejak.
                row.raw_name = item["raw_name"][:160]
                row.confidence = float(item["confidence"])
                row.evidence = item["evidence"]
                row.source_section = item["source_section"]
                row.extraction_method = item["extraction_method"]
            continue  # accepted/rejected/suggested-CV-lain: hormati state existing
        db.add(
            CandidateSkill(
                candidate_user_id=user.id,
                canonical_skill_id=canon.id,
                source_cv_id=cv_id,
                raw_name=item["raw_name"][:160],
                confidence=float(item["confidence"]),
                evidence=item["evidence"],
                source_section=item["source_section"],
                extraction_method=item["extraction_method"],
                status="suggested",
            )
        )
    db.flush()


def apply_skills_to_profile(
    db: Session, user: User, cv_id: uuid.UUID, skill_ids: list[uuid.UUID]
) -> int:
    """Kandidat menerima saran skill dari CV: suggested -> accepted + merge nama
    kanon ke `candidate_profiles.skills` (JSONB, dedupe case-insensitive, maks 30).

    Baris dari CV lain diabaikan; baris yang sudah accepted tidak dihitung ulang
    (idempoten — panggilan kedua mengembalikan 0). Mengembalikan jumlah baris
    yang baru berpindah suggested -> accepted pada panggilan ini.
    """
    cv = cv_service._owned_cv(db, user, cv_id)

    ids: list[uuid.UUID] = []
    for skill_id in skill_ids or []:
        if skill_id not in ids:
            ids.append(skill_id)
    if not ids:
        return 0

    rows = db.execute(
        select(CandidateSkill, CanonicalSkill)
        .join(CanonicalSkill, CandidateSkill.canonical_skill_id == CanonicalSkill.id)
        .where(
            CandidateSkill.candidate_user_id == user.id,
            CandidateSkill.id.in_(ids),
            CandidateSkill.source_cv_id == cv.id,  # baris dari CV lain diabaikan
        )
    ).all()
    to_apply = [(skill, canon) for skill, canon in rows if skill.status == "suggested"]
    if not to_apply:
        return 0

    profile = profile_service.get_candidate_profile(db, user)
    current = list(profile.skills or [])
    lowered = {str(name).strip().lower() for name in current}
    new_names: list[str] = []
    for _skill, canon in to_apply:
        name = canon.name
        if name.strip().lower() not in lowered:
            lowered.add(name.strip().lower())
            new_names.append(name)

    if len(current) + len(new_names) > PROFILE_SKILLS_LIMIT:
        raise BadRequestError("Melebihi batas 30 skill profil.")

    # Lolos guard batas — baru ubah state (transaksi bersih bila gagal).
    for skill, _canon in to_apply:
        skill.status = "accepted"
    profile.skills = current + new_names
    db.commit()
    return len(to_apply)


def get_cv_skills(db: Session, user: User, cv_id: uuid.UUID) -> list[CandidateSkill]:
    """Baris skill milik satu CV + baris accepted pengguna yang kanonnya belum
    terwakili di CV ini (agar UI bisa menandai "Sudah diterapkan")."""
    cv = cv_service._owned_cv(db, user, cv_id)
    cv_rows = list(
        db.scalars(
            select(CandidateSkill).where(
                CandidateSkill.candidate_user_id == user.id,
                CandidateSkill.source_cv_id == cv.id,
            )
        )
    )
    represented = {row.canonical_skill_id for row in cv_rows}
    stmt = select(CandidateSkill).where(
        CandidateSkill.candidate_user_id == user.id,
        CandidateSkill.status == "accepted",
    )
    if represented:
        stmt = stmt.where(CandidateSkill.canonical_skill_id.not_in(represented))
    other_accepted = list(db.scalars(stmt))

    rows = cv_rows + other_accepted
    rows.sort(key=lambda r: (_METHOD_ORDER.get(r.extraction_method, 2), -(r.confidence or 0.0)))
    return rows


def list_my_skills(db: Session, user: User) -> list[CandidateSkill]:
    """Seluruh skill accepted milik kandidat, urut nama kanon."""
    return list(
        db.scalars(
            select(CandidateSkill)
            .join(CanonicalSkill, CandidateSkill.canonical_skill_id == CanonicalSkill.id)
            .where(CandidateSkill.candidate_user_id == user.id, CandidateSkill.status == "accepted")
            .order_by(CanonicalSkill.name)
        )
    )


def delete_my_skill(db: Session, user: User, skill_id: uuid.UUID) -> None:
    """Hapus satu skill milik kandidat + bersihkan nama kanon dari JSONB profil
    (best-effort — profil bisa tidak memuat nama tersebut)."""
    row = db.get(CandidateSkill, skill_id)
    if row is None or row.candidate_user_id != user.id:
        raise NotFoundError("Skill tidak ditemukan.")
    canon = db.get(CanonicalSkill, row.canonical_skill_id)
    db.delete(row)
    if canon is not None:
        profile = db.get(CandidateProfile, user.id)
        if profile is not None and profile.skills:
            target = canon.name.strip().lower()
            kept = [name for name in profile.skills if str(name).strip().lower() != target]
            if len(kept) != len(profile.skills):
                profile.skills = kept
    db.commit()


# --- Skill lowongan (dipasang di job_service) ---


def normalize_job_skills(db: Session, skills: list[dict]) -> list[dict]:
    """Normalisasi skill lowongan {name, required} -> baris job_skills.

    Dedupe per slug kanon dengan precedence REQUIRED (mirror schemas/job.py);
    nama tanpa padanan didedupe per raw_name (case-insensitive), tetap ada di
    hasil dengan canonical_skill_id None (tidak persistable — FK NOT NULL).
    """
    result: list[dict] = []
    by_slug: dict[str, dict] = {}
    by_raw: dict[str, dict] = {}
    index = taxonomy_service.load_alias_index(db)
    for skill in skills or []:
        name = str(skill.get("name") or "").strip()
        if not name:
            continue
        required = bool(skill.get("required"))
        norm = _normalize_with_index(db, name, index)
        if norm["canonical"] is not None:
            slug = norm["canonical"].slug
            if slug in by_slug:
                by_slug[slug]["required"] = by_slug[slug]["required"] or required
                continue
            item = {
                "canonical_skill_id": norm["canonical"].id,
                "raw_name": name,
                "required": required,
                "evidence": None,
                "confidence": float(norm["confidence"]),
                "needs_review": bool(norm["needs_review"]),
            }
            by_slug[slug] = item
            result.append(item)
        else:
            key = name.lower()
            if key in by_raw:
                by_raw[key]["required"] = by_raw[key]["required"] or required
                continue
            item = {
                "canonical_skill_id": None,
                "raw_name": name,
                "required": required,
                "evidence": None,
                "confidence": float(norm["confidence"]),
                "needs_review": True,
            }
            by_raw[key] = item
            result.append(item)
    return result


# --- Serialisasi respons (dipakai endpoint cvs.py & profiles.py) ---


def canonical_map_for_rows(
    db: Session, rows: list[CandidateSkill]
) -> dict[uuid.UUID, CanonicalSkill]:
    """Peta id skill kanon -> objeknya untuk sekumpulan baris candidate_skills."""
    ids = {row.canonical_skill_id for row in rows}
    if not ids:
        return {}
    canons = db.scalars(select(CanonicalSkill).where(CanonicalSkill.id.in_(ids)))
    return {canon.id: canon for canon in canons}


def serialize_candidate_skill(
    db: Session, row: CandidateSkill, canonical: CanonicalSkill | None
) -> dict:
    """Bentuk item respons skill kandidat. needs_review & suggestions dihitung
    ulang read-time HANYA untuk baris confidence < 0.85 (re-derivasi murah)."""
    needs_review = False
    suggestions: list[dict] = []
    if row.confidence is not None and row.confidence < REVIEW_REDERIVE_BELOW:
        norm = _normalize_with_index(db, row.raw_name, taxonomy_service.load_alias_index(db))
        needs_review = bool(norm["needs_review"])
        suggestions = [{"slug": s["slug"], "name": s["name"]} for s in (norm["suggestions"] or [])]
    return {
        "id": row.id,
        "canonical": None
        if canonical is None
        else {
            "slug": canonical.slug,
            "name": canonical.name,
            "category": canonical.category,
            "skill_type": canonical.skill_type,
        },
        "raw_name": row.raw_name,
        "confidence": float(row.confidence or 0.0),
        "evidence": row.evidence,
        "source_section": row.source_section,
        "extraction_method": row.extraction_method,
        "status": row.status,
        "needs_review": needs_review,
        "suggestions": suggestions,
    }


def build_skill_items(db: Session, rows) -> list[dict]:
    """Bentuk daftar item respons (dict) untuk sekumpulan baris candidate_skills."""
    canonical_map = canonical_map_for_rows(db, list(rows))
    return [
        serialize_candidate_skill(db, row, canonical_map.get(row.canonical_skill_id))
        for row in rows
    ]
