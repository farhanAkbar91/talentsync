"""Service optimasi CV berbasis LLM (M8): generasi saran ter-grounding + penerapan.

Alur (kontrak beku Wave 5):
- `start_generation`: kepemilikan CV (404) + prasyarat ekstraksi terkonfirmasi
  (MatchUnavailableError) + lowongan aktif (404). Cache kuota: baris completed
  dengan prompt_version aktif dikembalikan apa adanya (respons endpoint menandai
  cached=true, tanpa panggil LLM). Selain itu baris 'generating' dibuat dan
  endpoint menjadwalkan `run_generation` sebagai background task (pola upload CV).
- `run_generation`: background, TIDAK PERNAH melempar — rakit prompt (+ gap dari
  match_service, gagal → None), panggil klien Groq, validasi grounding R1-R4,
  simpan hasil/kegagalan ke baris optimasi.
- `apply_optimization`: terima keputusan pengguna per saran → gerbang grounding
  ulang (defense in depth) → bangun payload BARU (hanya sunting teks, lihat
  dokumentasi `_apply_edits_to_payload`) → CV versi baru (PDF ReportLab) +
  ekstraksi auto-confirm + embedding + invalidasi match (parent & CV baru).

Import service lain memakai pola repo yang ada (kepemilikan via
cv_service._owned_cv, lowongan via match_service._get_active_job — reuse
read-only, tanpa duplikasi aturan).
"""

from __future__ import annotations

import copy
import hashlib
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.matching.embedder import MAX_DOCUMENT_CHARS, build_cv_text
from app.ai.optimization.grounding_validator import ensure_suggestion_ids, validate_edits
from app.ai.optimization.llm_client import LLMError, build_client
from app.ai.optimization.pdf_renderer import render_cv_pdf
from app.ai.optimization.prompts import PROMPT_VERSION, build_messages
from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.ai import CvOptimization
from app.models.cv import CV, CvExtraction
from app.models.job import Job
from app.models.user import User
from app.services import cv_service, embedding_service, match_service
from app.services.match_service import MatchUnavailableError

logger = logging.getLogger(__name__)

# Versi parser ekstraksi untuk CV hasil optimasi (payload turunan terkonfirmasi).
OPTIMIZED_PARSER_VERSION = "optimized-v1"
MAX_EDITS = 8  # pengaman server, selaras aturan prompt
# Jalur fuzzy (normalized) hanya untuk kutipan cukup panjang — mencegah
# original_text pendek (mis. header "PENGALAMAN") menyambung ke string lain yang
# kebetulan memuat satu kata yang sama (mis. kata "pengalaman" di ringkasan);
# kutipan pendek yang gagal dipetakan → jatuh ke fallback append bullet.
MIN_FUZZY_MATCH_CHARS = 12


# =====================================================================
# 1. Generasi saran (start + background)
# =====================================================================


def start_generation(
    db: Session,
    user: User,
    cv_id: uuid.UUID,
    job_id: uuid.UUID,
    settings: Settings,
    *,
    regenerate: bool = False,
) -> CvOptimization:
    """Buat (atau ambil dari cache kuota) baris optimasi status 'generating'.

    Commit di sini; pemanggilan Groq dijadwalkan endpoint sebagai background
    task terpisah (session baru). Bila fitur LLM nonaktif (kunci kosong) →
    LLMError 503 tanpa membuat baris.
    """
    cv = cv_service._owned_cv(db, user, cv_id)
    extraction = cv.extraction
    if extraction is None or extraction.confirmed_at is None or extraction.payload is None:
        # Pola sama dengan match_service: prasyarat review belum terpenuhi.
        raise MatchUnavailableError(
            "Konfirmasi hasil ekstraksi CV terlebih dahulu sebelum meminta optimasi."
        )
    # 404 bila lowongan bukan milik katalog aktif (aturan akses kandidat).
    match_service._get_active_job(db, job_id)

    if not regenerate:
        # Cache kuota: hasil completed dengan prompt aktif dikembalikan apa adanya.
        cached = db.scalar(
            select(CvOptimization)
            .where(
                CvOptimization.cv_id == cv_id,
                CvOptimization.job_id == job_id,
                CvOptimization.status == "completed",
                CvOptimization.prompt_version == PROMPT_VERSION,
            )
            .order_by(CvOptimization.created_at.desc())
        )
        if cached is not None:
            return cached

    # Fitur nonaktif → gagal cepat dengan error jelas (tanpa baris yatim).
    client = build_client(settings)
    if client is None:
        raise LLMError("Fitur optimasi AI belum aktif pada lingkungan ini.")
    client.close()

    optimization = CvOptimization(cv_id=cv_id, job_id=job_id, status="generating")
    db.add(optimization)
    db.commit()
    db.refresh(optimization)
    return optimization


def run_generation(
    session_factory: sessionmaker[Session],
    opt_id: uuid.UUID,
    cv_id: uuid.UUID,
    job_id: uuid.UUID,
    settings: Settings,
) -> None:
    """Background task: panggil Groq + validasi grounding. Tidak pernah melempar —
    kegagalan terekam pada baris optimasi (status 'failed' + pesan aman)."""
    try:
        _run_generation(session_factory, opt_id, cv_id, job_id, settings)
    except Exception:  # noqa: BLE001 — kontrak background: jangan crash worker
        logger.exception("Generasi optimasi tak terduga gagal opt=%s", opt_id)


def _run_generation(
    session_factory: sessionmaker[Session],
    opt_id: uuid.UUID,
    cv_id: uuid.UUID,
    job_id: uuid.UUID,
    settings: Settings,
) -> None:
    with session_factory() as db:
        optimization = db.get(CvOptimization, opt_id)
        if optimization is None or optimization.status != "generating":
            return
        cv = db.get(CV, cv_id)
        job = db.get(Job, job_id)
        payload = cv.extraction.payload if cv is not None and cv.extraction else None
        if cv is None or job is None or not payload:
            optimization.status = "failed"
            optimization.error_message = "CV atau lowongan tidak lagi tersedia."
            db.commit()
            return

        # Gap skill sebagai konteks penekanan (guard: gagal → None, bukan batal).
        gap: dict | None = None
        user = db.get(User, cv.candidate_user_id)
        if user is not None:
            try:
                gap = match_service.get_gap(db, user, job_id, settings)
            except Exception:  # noqa: BLE001 — gap bersifat opsional
                logger.warning("Gap tidak tersedia untuk optimasi cv=%s — dilewati.", cv_id)
                gap = None

        client = build_client(settings)
        if client is None:
            optimization.status = "failed"
            optimization.error_message = "Fitur optimasi AI belum aktif pada lingkungan ini."
            db.commit()
            return

        try:
            system, user_message = build_messages(payload, _job_dict(job), gap)
            result = client.generate_optimizations(system, user_message)
            edits = result.get("edits")
            if not isinstance(edits, list):
                raise LLMError("Respons AI tidak berformat yang diharapkan.")
            # Pengaman server: batasi jumlah edit sesuai aturan prompt (maks 8).
            edits = ensure_suggestion_ids([edit for edit in edits if isinstance(edit, dict)])
            edits = edits[:MAX_EDITS]
            report = validate_edits(edits, payload, job.title)

            optimization.suggestions = edits
            optimization.grounding_report = {**report, "meta": client.last_meta}
            optimization.llm_provider = "groq"
            optimization.llm_model = client.last_model
            optimization.prompt_version = PROMPT_VERSION
            if report["passed"]:
                optimization.status = "completed"
                optimization.error_message = None
            else:
                optimization.status = "failed"
                optimization.error_message = (
                    f"Saran AI gagal pemeriksaan grounding "
                    f"({len(report['violations'])} pelanggaran). Silakan coba lagi."
                )
        except LLMError as exc:
            optimization.status = "failed"
            optimization.error_message = exc.message
        except Exception:  # noqa: BLE001 — jangan biarkan baris menggantung 'generating'
            logger.exception("Generasi optimasi gagal opt=%s", opt_id)
            optimization.status = "failed"
            optimization.error_message = "Gagal menghasilkan optimasi. Silakan coba lagi."
        finally:
            client.close()
        db.commit()


def _job_dict(job: Job) -> dict:
    """Job row → dict prompt (bentuk sama dengan match_service.compute_match)."""
    return {
        "title": job.title,
        "skills": job.skills or [],
        "description": job.description,
        "requirements": job.requirements,
        "responsibilities": job.responsibilities,
    }


def list_optimizations(db: Session, user: User, cv_id: uuid.UUID) -> list[CvOptimization]:
    """Riwayat optimasi milik CV kandidat, terbaru lebih dulu."""
    cv_service._owned_cv(db, user, cv_id)
    return list(
        db.scalars(
            select(CvOptimization)
            .where(CvOptimization.cv_id == cv_id)
            .order_by(CvOptimization.created_at.desc())
        ).all()
    )


def get_optimization(
    db: Session, user: User, cv_id: uuid.UUID, opt_id: uuid.UUID
) -> CvOptimization:
    """Satu baris optimasi milik CV kandidat; selain itu 404 (jangan bocorkan)."""
    cv = cv_service._owned_cv(db, user, cv_id)
    optimization = db.get(CvOptimization, opt_id)
    if optimization is None or optimization.cv_id != cv.id:
        raise NotFoundError("Hasil optimasi tidak ditemukan.")
    return optimization


# =====================================================================
# 2. Penerapan saran (apply)
# =====================================================================


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Casefold + collapse whitespace, dengan peta indeks hasil normalisasi →
    posisi karakter pada string asli (untuk replace lintas-format spasi)."""
    normalized: list[str] = []
    indices: list[int] = []
    previous_space = True
    for position, char in enumerate(text):
        if char.isspace():
            if previous_space:
                continue
            normalized.append(" ")
            indices.append(position)
            previous_space = True
        else:
            normalized.append(char.casefold())
            indices.append(position)
            previous_space = False
    while normalized and normalized[-1] == " ":
        normalized.pop()
        indices.pop()
    return "".join(normalized), indices


def _replace_in_text(field: str, original: str, suggested: str) -> str | None:
    """Ganti kemunculan `original` di `field` → string baru; None bila tidak ketemu.

    Pencarian: substring persis lebih dulu (tanpa syarat panjang), lalu normalized
    (case-insensitive + whitespace collapsed) dengan pemetaan balik ke indeks
    string asli — jalur fuzzy hanya untuk kutipan >= MIN_FUZZY_MATCH_CHARS
    (lihat konstanta; mencegah satu kata menyambung ke field mana pun).
    """
    if not field or not original or not suggested:
        return None
    if original in field:
        return field.replace(original, suggested, 1)
    normalized_field, indices = _normalize_with_map(field)
    normalized_original, _ = _normalize_with_map(original)
    if len(normalized_original) < MIN_FUZZY_MATCH_CHARS:
        return None
    position = normalized_field.find(normalized_original)
    if position < 0:
        return None
    start = indices[position]
    end = indices[position + len(normalized_original) - 1] + 1
    return field[:start] + suggested + field[end:]


def _choose_experience(payload: dict, original: str) -> dict | None:
    """Pengalaman dengan overlap token terbesar terhadap original_text (fallback).

    Tidak ada yang cocok / token kosong → pengalaman pertama. None bila payload
    tidak punya pengalaman sama sekali (fallback tidak bisa jalan).
    """
    experiences = [item for item in payload.get("experiences") or [] if isinstance(item, dict)]
    if not experiences:
        return None
    original_tokens = set(_normalize_with_map(original)[0].split())
    best: dict | None = None
    best_overlap = 0
    for experience in experiences:
        rendered = build_cv_text({"experiences": [experience]})
        tokens = set(_normalize_with_map(rendered or "")[0].split())
        overlap = len(original_tokens & tokens)
        if overlap > best_overlap:
            best = experience
            best_overlap = overlap
    return best if best is not None else experiences[0]


def _apply_edits_to_payload(payload: dict, edits: list[dict]) -> dict:
    """Bangun payload BARU dengan menerapkan edit teks (payload asli tak tersentuh).

    Pemetaan PRAGMATIS (dokumentasi kontrak apply, Wave 5):
    1. Suntingan teks hanya menyentuh string tempat `original_text` hidup:
       `summary`, `experiences[*].title`, dan `experiences[*].bullets[*]`.
       Kolom lain (skills, education, certifications, dst.) TIDAK diubah —
       aturan grounding melarang konten baru, jadi section non-teks tak tersentuh.
       Field `company` sengaja tidak pernah diganti (perusahaan tidak boleh
       berubah oleh saran AI).
    2. Pencarian field memakai pencocokan normalized (case-insensitive +
       whitespace collapsed) supaya kutipan LLM yang beda spasi tetap terpasang;
       jalur fuzzy ini hanya untuk kutipan >= 12 karakter agar kutipan pendek
       (satu kata) tidak menyambung ke field yang kebetulan memuat katanya.
    3. FALLBACK (baris teks CV yang tidak memetakan ke satu field, mis. hasil
       berasal dari baris header/label): `suggested_text` ditambahkan sebagai
       bullet baru pada pengalaman dengan overlap token terbesar terhadap
       `original_text`; tanpa kandidat → pengalaman pertama; tanpa pengalaman →
       edit dilewati (tidak pernah mengarang section baru).
    """
    new_payload = copy.deepcopy(payload)
    unmatched: list[dict] = []

    for edit in edits:
        original = str(edit.get("original_text") or "").strip()
        suggested = str(edit.get("suggested_text") or "").strip()
        if not suggested:
            continue
        placed = False

        summary = new_payload.get("summary")
        if isinstance(summary, str) and summary:
            replaced = _replace_in_text(summary, original, suggested)
            if replaced is not None:
                new_payload["summary"] = replaced
                placed = True

        if not placed:
            for experience in new_payload.get("experiences") or []:
                if not isinstance(experience, dict):
                    continue
                title = experience.get("title")
                if isinstance(title, str) and title:
                    replaced = _replace_in_text(title, original, suggested)
                    if replaced is not None:
                        experience["title"] = replaced
                        placed = True
                        break
                for index, bullet in enumerate(experience.get("bullets") or []):
                    replaced = _replace_in_text(str(bullet), original, suggested)
                    if replaced is not None:
                        experience["bullets"][index] = replaced
                        placed = True
                        break
                if placed:
                    break

        if not placed:
            unmatched.append(edit)

    for edit in unmatched:
        suggested = str(edit.get("suggested_text") or "").strip()
        if not suggested:
            continue
        target = _choose_experience(new_payload, str(edit.get("original_text") or ""))
        if target is None:
            continue
        bullets = target.setdefault("bullets", [])
        if isinstance(bullets, list):
            bullets.append(suggested)

    return new_payload


def apply_optimization(
    db: Session,
    user: User,
    cv_id: uuid.UUID,
    opt_id: uuid.UUID,
    decisions: dict[str, bool],
    settings: Settings,
) -> CV:
    """Terapkan saran yang diterima → CV versi baru (commit; kembalikan CV baru).

    - Baris harus milik kandidat (404) dan status 'completed' (else 409).
    - Tidak ada saran yang diterima → 400.
    - Gerbang grounding ulang atas edit yang diterima (defense in depth):
      pelanggaran → 400 dengan detail pelanggaran.
    - Hasil: CV baru (version+1, parent_cv_id, is_primary=True; CV lama turun),
      PDF ReportLab, ekstraksi auto-confirm, embedding (guard), invalidasi
      match untuk parent DAN CV baru.
    """
    cv = cv_service._owned_cv(db, user, cv_id)
    optimization = get_optimization(db, user, cv_id, opt_id)
    if optimization.status != "completed":
        raise ConflictError("Optimasi belum selesai atau sudah diterapkan.")

    suggestions = [item for item in optimization.suggestions or [] if isinstance(item, dict)]
    accepted = [
        item for item in suggestions if decisions.get(str(item.get("suggestion_id"))) is True
    ]
    if not accepted:
        raise BadRequestError("Tidak ada saran yang diterima.")

    parent_payload = cv.extraction.payload if cv.extraction else None
    if not parent_payload:
        raise ConflictError("Payload CV asal tidak tersedia.")

    job = db.get(Job, optimization.job_id)
    report = validate_edits(accepted, parent_payload, job.title if job else "")
    if not report["passed"]:
        raise BadRequestError(
            "Saran yang diterima gagal pemeriksaan grounding.",
            details=[
                {
                    "suggestion_id": item["suggestion_id"],
                    "rule": item["rule"],
                    "detail": item["detail"],
                }
                for item in report["violations"]
            ],
        )

    new_payload = _apply_edits_to_payload(parent_payload, accepted)
    pdf_bytes = render_cv_pdf(new_payload)

    target_dir = Path(settings.uploads_dir) / "cvs" / str(user.id)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{uuid.uuid4().hex}.pdf"
    file_path.write_bytes(pdf_bytes)

    new_version = cv.version + 1
    new_cv = CV(
        candidate_user_id=user.id,
        status="ready",
        file_path=str(file_path),
        original_filename=f"cv-optimasi-v{new_version}.pdf",
        mime_type="application/pdf",
        file_size_bytes=len(pdf_bytes),
        content_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        is_primary=True,
        version=new_version,
        parent_cv_id=cv.id,
    )
    cv.is_primary = False
    db.add(new_cv)
    db.flush()

    # AUTO-CONFIRM (keputusan desain M8): CV turunan langsung terkonfirmasi —
    # parent sudah lewat review kandidat dan setiap suntingan disetujui eksplisit
    # lewat `decisions`, jadi review kedua tidak menambah informasi; tanpa ini
    # gerbang matching (ekstraksi terkonfirmasi) akan menolak CV hasil optimasi.
    now = datetime.now(UTC)
    db.add(
        CvExtraction(
            cv_id=new_cv.id,
            status="done",
            payload=new_payload,
            parser_version=OPTIMIZED_PARSER_VERSION,
            raw_text=(build_cv_text(new_payload) or "")[:MAX_DOCUMENT_CHARS],
            confirmed_at=now,
            confirmed_by=user.id,
        )
    )

    # Jaga invarian satu CV primer: semua CV lain (termasuk parent) turun.
    for other in cv_service.list_cvs(db, user):
        if other.id != new_cv.id:
            other.is_primary = False

    # M3: vektor CV baru (guard — kegagalan embedding tidak membatalkan penerapan).
    try:
        embedding_service.embed_cv(db, new_cv.id, settings)
    except Exception:  # noqa: BLE001
        logger.warning("Embedding CV hasil optimasi %s gagal — dilewati.", new_cv.id, exc_info=True)

    # M4: parent is_primary berubah → skor lama basi; CV baru juga di-invalidasi
    # (defensif — memastikan tidak ada match_result yatim untuk cv_id baru).
    match_service.invalidate_cv(db, new_cv.id)
    match_service.invalidate_cv(db, cv.id)

    optimization.status = "applied"
    optimization.applied_cv_id = new_cv.id
    # Keputusan tersimpan utuh untuk semua saran (accepted true/false).
    optimization.decisions = {
        str(item.get("suggestion_id")): {
            "accepted": decisions.get(str(item.get("suggestion_id"))) is True
        }
        for item in suggestions
    }
    db.commit()
    db.refresh(new_cv)
    return new_cv
