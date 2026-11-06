"""Service lamaran (M9): apply kandidat, daftar pelamar, transisi status,
ranking & perbandingan pelamar.

Aturan main:
- Apply: lowongan AKTIF (404 selain itu — reuse gate match_service); kandidat
  wajib punya CV PRIMER terkonfirmasi (mirror gate match_service, kode 400
  APPLICATION_UNAVAILABLE karena konteksnya melamar, bukan melihat skor);
  satu lamaran per (lowongan, kandidat) → 409.
- `cv_id` lamaran = CV primer SAAT MELAMAR (snapshot): ranking M9 selalu
  memakai CV YANG DIPAKAI SAAT MELAMAR — bukan CV primer kandidat saat ini.
- Akses HR: job milik perusahaan HR (reuse job_service.get_job_for_company;
  job perusahaan lain → 404, jangan bocorkan keberadaan resource).
- Ranking/compare: skor dibangun dari blok yang SAMA dengan match_service
  (score_pair + slug CandidateSkill + vektor tabel embedding — embed on the
  fly guarded, judul di-encode SATU batch) lalu PERSIST/replace ke
  match_results per (cv_id, job_id, model_version) — ranking adalah konsumen
  M9 dari match_results. CV lamaran tanpa payload terkonfirmasi → overall
  None + reason "CV belum terkonfirmasi", selalu urut paling akhir.
- Transisi status: hired/rejected TERMINAL (409 bila diubah lagi); selain itu
  bebas antar status (keputusan MVP — sengaja, bukan kelalaian).
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.matching import scorer
from app.ai.matching.explainer import build_explanation, label_for
from app.ai.matching.scorer import score_pair
from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.ai import CvEmbedding, JobEmbedding
from app.models.application import (
    APPLICATION_STATUSES,
    TERMINAL_APPLICATION_STATUSES,
    Application,
)
from app.models.cv import CV
from app.models.job import Job
from app.models.user import User
from app.services import embedding_service, job_service, match_service

logger = logging.getLogger(__name__)

# Maksimal nama skill yang tampil di satu item ranking (mirror M6).
MAX_MATCHED_SKILLS = 5

# Alasan deterministik untuk pelamar yang tidak bisa dinilai.
REASON_CV_UNCONFIRMED = "CV belum terkonfirmasi"


class ApplicationUnavailableError(BadRequestError):
    """400 dengan kode APPLICATION_UNAVAILABLE — prasyarat melamar belum terpenuhi.

    Mirror MatchUnavailableError (match_service): code atribut kelas → envelope
    core.errors memuat {"error": {"code": "APPLICATION_UNAVAILABLE", ...}}.
    """

    code = "APPLICATION_UNAVAILABLE"
    default_message = "Konfirmasi CV utama terlebih dahulu sebelum melamar lowongan."


# --- Helper gate & data ---


def _get_primary_confirmed_cv(db: Session, user: User) -> CV:
    """CV primer kandidat (bukan soft delete) + ekstraksi terkonfirmasi.

    Mirror gate match_service._get_primary_cv — direplikasi (bukan dipanggil)
    karena kode error-nya harus APPLICATION_UNAVAILABLE, bukan
    MATCH_UNAVAILABLE. Tidak ada / belum konfirmasi / payload kosong → 400.
    """
    cv = db.scalar(
        select(CV).where(
            CV.candidate_user_id == user.id,
            CV.is_primary.is_(True),
            CV.deleted_at.is_(None),
        )
    )
    if cv is None:
        raise ApplicationUnavailableError()
    extraction = cv.extraction
    if extraction is None or extraction.confirmed_at is None or extraction.payload is None:
        raise ApplicationUnavailableError()
    return cv


def _load_applicant_rows(
    db: Session,
    job_id: uuid.UUID,
    application_ids: list[uuid.UUID] | None = None,
) -> list[tuple[Application, CV | None, User]]:
    """(lamaran, CV saat melamar, kandidat) satu lowongan, terbaru dulu.

    CV di-join OUTER: cv_id bisa NULL (CV dihapus permanen — SET NULL)."""
    stmt = (
        select(Application, CV, User)
        .join(CV, Application.cv_id == CV.id, isouter=True)
        .join(User, Application.candidate_user_id == User.id)
        .where(Application.job_id == job_id)
        .order_by(Application.created_at.desc(), Application.id.desc())
    )
    if application_ids is not None:
        stmt = stmt.where(Application.id.in_(application_ids))
    return list(db.execute(stmt).all())


# --- API publik service: apply & daftar & status ---


def apply_to_job(
    db: Session,
    user: User,
    job_id: uuid.UUID,
    cover_letter: str | None,
    settings: Settings,
) -> Application:
    """Kandidat melamar lowongan aktif dengan CV primer terkonfirmasi.

    - 404 bila lowongan tidak ada / nonaktif / dihapus (gate match_service).
    - 400 APPLICATION_UNAVAILABLE bila belum ada CV primer terkonfirmasi.
    - 409 bila sudah pernah melamar (cek eksplisit + guard race UNIQUE).
    - Vektor CV primer disiapkan on the fly (guarded) agar ranking M9 bisa
      menghitung segera; kegagalan embed tidak pernah menggagalkan apply.
    """
    job = match_service._get_active_job(db, job_id)
    cv = _get_primary_confirmed_cv(db, user)

    existing = db.scalar(
        select(Application).where(
            Application.job_id == job.id,
            Application.candidate_user_id == user.id,
        )
    )
    if existing is not None:
        raise ConflictError("Anda sudah melamar lowongan ini.")

    application = Application(
        job_id=job.id,
        candidate_user_id=user.id,
        cv_id=cv.id,
        cover_letter=cover_letter,
        status="submitted",
    )
    db.add(application)
    try:
        db.commit()
    except IntegrityError as exc:
        # Race dedupe: UNIQUE(job_id, candidate_user_id) menolak apply serentak.
        db.rollback()
        raise ConflictError("Anda sudah melamar lowongan ini.") from exc
    db.refresh(application)

    if settings is not None:
        try:
            embedding_service.embed_cv(db, cv.id, settings)
        except Exception:
            db.rollback()
            logger.warning("Embed CV %s saat apply gagal — dilewati.", cv.id, exc_info=True)
    return application


def list_my_applications(db: Session, user: User) -> list[tuple[Application, Job]]:
    """Semua lamaran kandidat, terbaru dulu, + lowongan untuk tampilan
    (judul/perusahaan/status lowongan/lokasi). Lowongan yang sudah dihapus
    tetap tampil — riwayat lamaran tetap milik kandidat."""
    rows = db.execute(
        select(Application, Job)
        .join(Job, Application.job_id == Job.id)
        .where(Application.candidate_user_id == user.id)
        .order_by(Application.created_at.desc(), Application.id.desc())
    ).all()
    return [(application, job) for application, job in rows]


def list_job_applications(
    db: Session, user_hr: User, job_id: uuid.UUID
) -> list[tuple[Application, CV | None, User]]:
    """Pelamar satu lowongan milik perusahaan HR (404 bila lowongan milik
    perusahaan lain): (lamaran, CV saat melamar, kandidat), terbaru dulu."""
    job = job_service.get_job_for_company(db, user_hr, job_id)
    return _load_applicant_rows(db, job.id)


def update_status(
    db: Session, user_hr: User, application_id: uuid.UUID, new_status: str
) -> Application:
    """HR mengubah status lamaran milik perusahaannya.

    - Status tak dikenal → 400.
    - 404 bila lamaran tidak ada ATAU lowongannya milik perusahaan lain.
    - hired/rejected TERMINAL: perubahan apa pun → 409; selain itu bebas antar
      status (MVP).
    """
    if new_status not in APPLICATION_STATUSES:
        raise BadRequestError(f"Status '{new_status}' tidak dikenal.")
    application = db.get(Application, application_id)
    if application is None:
        raise NotFoundError("Lamaran tidak ditemukan.")
    job_service.get_job_for_company(db, user_hr, application.job_id)  # 404 bila bukan miliknya
    if application.status in TERMINAL_APPLICATION_STATUSES:
        raise ConflictError(
            f"Lamaran berstatus '{application.status}' sudah final dan tidak dapat diubah."
        )
    application.status = new_status
    db.commit()
    db.refresh(application)
    return application


# --- Mesin skor bersama ranking & compare (blok sama dengan match_service) ---


def _cv_confirmed_payload(cv: CV | None) -> bool:
    """CV lamaran layak diskor: ada dan payload ekstraksinya TERKONFIRMASI."""
    if cv is None:
        return False
    extraction = cv.extraction
    return (
        extraction is not None
        and extraction.confirmed_at is not None
        and extraction.payload is not None
    )


def _load_job_vector(db: Session, job: Job, settings: Settings) -> list[float]:
    """Vektor lowongan model aktif; embed on the fly guarded; gagal terus →
    MATCH_UNAVAILABLE (tanpa vektor lowongan, tak ada pelamar yang bisa diskor)."""
    job_vec = match_service._load_vector(
        db, JobEmbedding, "job_id", job.id, embedding_service.TEXT_KIND_JOB, settings
    )
    if job_vec is None:
        try:
            embedding_service.embed_job(db, job.id, settings)
        except Exception:
            db.rollback()
            logger.warning(
                "Embed lowongan %s saat ranking gagal — dilewati.", job.id, exc_info=True
            )
        job_vec = match_service._load_vector(
            db, JobEmbedding, "job_id", job.id, embedding_service.TEXT_KIND_JOB, settings
        )
        if job_vec is None:
            raise match_service.MatchUnavailableError(
                "Vektor lowongan belum siap. Coba beberapa saat lagi."
            )
    return job_vec


def _load_cv_vector(db: Session, cv: CV, settings: Settings) -> list[float] | None:
    """Vektor CV lamaran model aktif; embed on the fly guarded. embed_cv skip
    senyap bila CV dihapus / tak terkonfirmasi → kembalikan None (pelamar
    dilewatkan dari skor dengan reason, bukan error)."""
    cv_vec = match_service._load_vector(
        db, CvEmbedding, "cv_id", cv.id, embedding_service.TEXT_KIND_CV, settings
    )
    if cv_vec is None:
        try:
            embedding_service.embed_cv(db, cv.id, settings)
        except Exception:
            db.rollback()
            logger.warning("Embed CV %s saat ranking gagal — dilewati.", cv.id, exc_info=True)
        cv_vec = match_service._load_vector(
            db, CvEmbedding, "cv_id", cv.id, embedding_service.TEXT_KIND_CV, settings
        )
    return cv_vec


def _encode_title_vectors(
    job_title: str, payloads: list[dict], settings: Settings
) -> tuple[list[float], list[list[list[float]]]]:
    """(job_title_vec, cv_title_vecs per CV) — SEMUA judul di-encode dalam SATU
    panggilan batch (mirror amandemen performa M4: jangan encode ulang judul
    per pasangan). Urutan judul pengalaman sejajar urutan payload experiences
    APA ADANYA (termasuk entri tanpa judul) — kontrak score_pair."""
    flat: list[str] = [job_title]
    spans: list[tuple[int, int]] = []
    for payload in payloads:
        titles = [
            str(exp.get("title") or "") if isinstance(exp, dict) else ""
            for exp in payload.get("experiences") or []
        ]
        spans.append((len(flat), len(titles)))
        flat.extend(titles)
    encoded = embedding_service.get_embedder(settings.embedding_model).encode(flat)
    job_title_vec = list(encoded[0])
    per_cv = [[list(vector) for vector in encoded[start : start + count]] for start, count in spans]
    return job_title_vec, per_cv


def _score_application(
    db: Session,
    job: Job,
    job_dict: dict,
    job_vec: list[float],
    job_title_vec: list[float],
    cv_title_vecs: list[list[float]],
    application: Application,
    cv: CV,
    candidate: User,
    cv_vec: list[float],
    settings: Settings,
    taxonomy_related: dict[str, set[str]],
    model_version: str,
) -> dict:
    """Skor SATU pelamar dengan blok yang sama dengan match_service.compute_match
    dan PERSIST/replace MatchResult per (cv_id, job_id, model_version).

    Mengembalikan detail penuh (matched/missing utuh, top_experiences,
    explanation) — proyeksi ke item ranking / sisi compare dilakukan pemanggil.
    Tidak commit: pemanggil yang commit (satu transaksi untuk semua pelamar).
    """
    candidate_slugs, explicit_slugs = match_service._load_candidate_slugs(db, candidate)
    payload = cv.extraction.payload or {}
    result = score_pair(
        cv_payload=payload,
        job=job_dict,
        cv_vec=cv_vec,
        job_vec=job_vec,
        job_title_vec=job_title_vec,
        candidate_slugs=candidate_slugs,
        explicit_slugs=explicit_slugs,
        weights=tuple(settings.match_weights),
        taxonomy_related=taxonomy_related,
        cv_title_vecs=cv_title_vecs,
    )

    years_have = scorer.compute_years_have(payload)
    years_req = scorer.compute_years_required(job_dict)
    explanation = build_explanation(
        overall=result["overall"],
        factors=result["factors"],
        matched=result["matched"],
        missing=result["missing"],
        job_title=job.title,
        years_have=years_have,
        years_req=years_req,
    )

    match_service._persist_match_result(db, cv.id, job.id, model_version, result, explanation)

    matched = result["matched"]
    missing = result["missing"]
    matched_required = sum(1 for item in matched if item.get("required"))
    total_required = matched_required + sum(1 for item in missing if item.get("required"))
    overall = float(result["overall"])
    return {
        "application_id": application.id,
        "candidate_user_id": candidate.id,
        "candidate_name": candidate.full_name,
        "cv_id": cv.id,
        "status": application.status,
        "overall": overall,
        "label": label_for(overall),
        "factors": dict(result["factors"]),
        "matched_required": matched_required,
        "total_required": total_required,
        "matched_detail": list(matched),
        "missing_detail": list(missing),
        "missing_critical": sum(1 for item in missing if item.get("severity") == "kritis"),
        "top_experiences": list(result["top_experiences"]),
        "explanation": explanation,
        "reason": None,
        "model_version": model_version,
    }


def _unscorable_detail(
    application: Application,
    cv: CV | None,
    candidate: User,
    reason: str,
    model_version: str,
) -> dict:
    """Detail pelamar yang tidak bisa dinilai (CV hilang / belum terkonfirmasi):
    overall & factors None — selalu urut paling akhir, tanpa MatchResult."""
    return {
        "application_id": application.id,
        "candidate_user_id": candidate.id,
        "candidate_name": candidate.full_name,
        "cv_id": cv.id if cv is not None else None,
        "status": application.status,
        "overall": None,
        "label": None,
        "factors": None,
        "matched_required": 0,
        "total_required": 0,
        "matched_detail": [],
        "missing_detail": [],
        "missing_critical": 0,
        "top_experiences": [],
        "explanation": None,
        "reason": reason,
        "model_version": model_version,
    }


def _score_rows(
    db: Session,
    job: Job,
    rows: list[tuple[Application, CV | None, User]],
    settings: Settings,
) -> list[dict]:
    """Klasifikasi + skor sekumpulan (lamaran, CV, kandidat) untuk SATU lowongan.

    Urutan masuk dipertahankan pada hasil. Persist MatchResult terjadi di sini;
    commit oleh pemanggil. Pelamar tanpa CV terkonfirmasi / tanpa vektor
    dijumpai sebagai detail unscorable (overall None + reason)."""
    model_version = match_service.build_model_version(settings)
    taxonomy_related = match_service.load_taxonomy_related()

    details: list[dict] = []
    scorable: list[tuple[Application, CV, User, list[float]]] = []
    for application, cv, candidate in rows:
        if not _cv_confirmed_payload(cv):
            details.append(
                _unscorable_detail(application, cv, candidate, REASON_CV_UNCONFIRMED, model_version)
            )
            continue
        assert cv is not None  # _cv_confirmed_payload False bila cv None
        cv_vec = _load_cv_vector(db, cv, settings)
        if cv_vec is None:
            details.append(
                _unscorable_detail(application, cv, candidate, REASON_CV_UNCONFIRMED, model_version)
            )
            continue
        scorable.append((application, cv, candidate, cv_vec))
    if not scorable:
        return details

    job_vec = _load_job_vector(db, job, settings)
    job_dict = {
        "title": job.title,
        "skills": match_service._resolve_job_skills(db, job),
        "description": job.description,
        "requirements": job.requirements,
        "responsibilities": job.responsibilities,
        "seniority": job.seniority,
    }
    # Encoder judul terikat model aktif — fallback defensif bila vektor judul
    # tak sejajar (normalnya tidak pernah dipakai, mirror match_service).
    scorer.set_title_encoder(
        lambda texts, _model=settings.embedding_model: embedding_service.get_embedder(
            _model
        ).encode(list(texts))
    )
    payloads = [cv.extraction.payload or {} for _application, cv, _candidate, _cv_vec in scorable]
    job_title_vec, title_vecs_per_cv = _encode_title_vectors(job.title, payloads, settings)

    for (application, cv, candidate, cv_vec), cv_title_vecs in zip(
        scorable, title_vecs_per_cv, strict=True
    ):
        details.append(
            _score_application(
                db,
                job,
                job_dict,
                job_vec,
                job_title_vec,
                cv_title_vecs,
                application,
                cv,
                candidate,
                cv_vec,
                settings,
                taxonomy_related,
                model_version,
            )
        )
    return details


# --- API publik service: ranking & compare (M9) ---


def rank_job_applicants(
    db: Session, user_hr: User, job_id: uuid.UUID, settings: Settings
) -> list[dict]:
    """Ranking pelamar satu lowongan milik perusahaan HR (404 bila bukan).

    Item kontrak API: {application_id, candidate_user_id, candidate_name,
    cv_id, status, overall, label, factors, matched_required, total_required,
    matched_skills (maks 5 nama tampilan), missing_critical, model_version,
    reason}. Urut overall DESC; pelamar overall None (CV belum terkonfirmasi)
    selalu paling akhir. MatchResult dipersist per pelamar berskor — recompute
    berulang idempoten (replace per (cv_id, job_id, model_version))."""
    job = job_service.get_job_for_company(db, user_hr, job_id)
    rows = _load_applicant_rows(db, job.id)
    if not rows:
        return []

    details = _score_rows(db, job, rows, settings)
    # Urut overall DESC (None terakhir); tie-break: urutan asal (terbaru dulu)
    # dipertahankan — sort Python stabil.
    details.sort(key=lambda detail: (detail["overall"] is None, -(detail["overall"] or 0.0)))
    db.commit()

    items: list[dict] = []
    for detail in details:
        ordered = sorted(detail["matched_detail"], key=lambda item: not item.get("required"))
        items.append(
            {
                "application_id": detail["application_id"],
                "candidate_user_id": detail["candidate_user_id"],
                "candidate_name": detail["candidate_name"],
                "cv_id": detail["cv_id"],
                "status": detail["status"],
                "overall": detail["overall"],
                "label": detail["label"],
                "factors": detail["factors"],
                "matched_required": detail["matched_required"],
                "total_required": detail["total_required"],
                "matched_skills": [
                    str(item.get("display") or item.get("name") or "")
                    for item in ordered[:MAX_MATCHED_SKILLS]
                ],
                "missing_critical": detail["missing_critical"],
                "model_version": detail["model_version"],
                "reason": detail["reason"],
            }
        )
    return items


def compare_applicants(
    db: Session,
    user_hr: User,
    job_id: uuid.UUID,
    application_id_a: uuid.UUID,
    application_id_b: uuid.UUID,
    settings: Settings,
) -> dict:
    """Bandingkan dua pelamar satu lowongan milik perusahaan HR — detail skor
    penuh per sisi ({a, b}), blok skor & persist sama dengan ranking.

    404 bila lowongan milik perusahaan lain ATAU salah satu lamaran tidak
    ada / bukan lamaran lowongan ini; 400 bila kedua id identik."""
    if application_id_a == application_id_b:
        raise BadRequestError("Pilih dua pelamar yang berbeda untuk dibandingkan.")
    job = job_service.get_job_for_company(db, user_hr, job_id)
    rows = _load_applicant_rows(db, job.id, [application_id_a, application_id_b])
    found = {row[0].id for row in rows}
    for requested in (application_id_a, application_id_b):
        if requested not in found:
            raise NotFoundError("Lamaran tidak ditemukan pada lowongan ini.")

    details = _score_rows(db, job, rows, settings)
    db.commit()
    by_id = {detail["application_id"]: detail for detail in details}

    def _side(detail: dict) -> dict:
        return {
            "application_id": detail["application_id"],
            "candidate_user_id": detail["candidate_user_id"],
            "candidate_name": detail["candidate_name"],
            "cv_id": detail["cv_id"],
            "status": detail["status"],
            "overall": detail["overall"],
            "label": detail["label"],
            "factors": detail["factors"],
            "matched_required": detail["matched_required"],
            "total_required": detail["total_required"],
            "matched_skills": detail["matched_detail"],
            "missing_skills": detail["missing_detail"],
            "missing_critical": detail["missing_critical"],
            "top_experiences": detail["top_experiences"],
            "explanation": detail["explanation"],
            "reason": detail["reason"],
        }

    return {
        "a": _side(by_id[application_id_a]),
        "b": _side(by_id[application_id_b]),
    }


def get_applicant_cv_file(
    db: Session, user_hr: User, application_id: uuid.UUID
) -> tuple[Path, str]:
    """HR pemilik lowongan mengunduh CV pelamar (alur rekrutmen inti).

    Akses ditautkan ke lamaran: job harus milik perusahaan HR (404 bila bukan).
    CV yang sudah soft-delete tetap dapat diakses — bagian riwayat lamaran
    (integritas arsip; hard delete tidak ada di API)."""
    application = db.get(Application, application_id)
    if application is None:
        raise NotFoundError("Lamaran tidak ditemukan.")
    job_service.get_job_for_company(db, user_hr, application.job_id)
    if application.cv_id is None:
        raise NotFoundError("Lamaran tidak memuat CV.")
    cv = db.get(CV, application.cv_id)
    if cv is None:
        raise NotFoundError("CV pelamar tidak ditemukan.")
    return Path(cv.file_path), cv.original_filename
