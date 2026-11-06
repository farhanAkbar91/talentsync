"""Service rekomendasi lowongan (M6): skor semua lowongan aktif vs CV primer.

Aturan main:
- Gate identik dengan match_service (M4): CV primer (tidak dihapus) dengan
  ekstraksi TERKONFIRMASI wajib — belum ada → MatchUnavailableError (400 kode
  MATCH_UNAVAILABLE, exception match_service yang SAMA, bukan duplikat).
- Dihitung on request TANPA persist — match_results TIDAK ditulis (keputusan
  terdokumentasi): endpoint /jobs/{id}/compatibility (M4) tetap satu-satunya
  jalur persistensi hasil match; hook invalidasi M4 tidak relevan di sini.
- cv_vec + cv_title_vecs dihitung SEKALI per permintaan; vektor judul SEMUA
  lowongan + judul pengalaman CV di-encode dalam SATU batch (mirror amandemen
  performa M4 — jangan encode ulang judul per pasangan).
- Vektor lowongan dibaca batch (satu query, bukan N+1 untuk yang sudah ada);
  yang hilang di-embed on the fly via embedding_service.embed_job (guarded);
  tetap gagal → lowongan DILEWATI (tidak ikut dinilai).
- `total` = jumlah lowongan aktif yang BERHASIL dinilai; `items` = top `limit`
  urut overall DESC (tie-break job_id agar deterministik).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.matching import scorer
from app.ai.matching.explainer import label_for
from app.ai.matching.scorer import score_pair
from app.core.config import Settings
from app.models.ai import CvEmbedding, JobEmbedding
from app.models.job import Job
from app.models.user import User
from app.services import embedding_service, match_service

logger = logging.getLogger(__name__)

# Batas item rekomendasi (kontrak API M6): default 10, cap 25. Endpoint sudah
# memvalidasi lewat Query(ge=1, le=25); service menjaga ulang agar fungsi ini
# aman dipanggil langsung (skrip/evaluasi) tanpa lapisan API.
DEFAULT_LIMIT = 10
MAX_LIMIT = 25

# Maksimal nama skill yang tampil di satu item rekomendasi.
MAX_MATCHED_SKILLS = 5


def _load_job_vectors(
    db: Session, job_ids: list[uuid.UUID], settings: Settings
) -> dict[uuid.UUID, list[float]]:
    """Vektor lowongan model aktif untuk SEKUMPUNGAN id — satu query (anti N+1).

    Hanya baris text_kind 'job' milik model aktif (mirror _load_vector di
    match_service, tapi batch). Baris model lama tidak pernah disentuh.
    """
    if not job_ids:
        return {}
    rows = db.scalars(
        select(JobEmbedding).where(
            JobEmbedding.job_id.in_(job_ids),
            JobEmbedding.model == settings.embedding_model,
            JobEmbedding.text_kind == embedding_service.TEXT_KIND_JOB,
        )
    ).all()
    return {row.job_id: list(row.embedding) for row in rows}


def _build_reason(
    overall: float, matched_required: int, total_required: int, missing_critical: int
) -> str:
    """Narasi dua bagian deterministik (tanpa LLM) — kontrak frontend M6.

    Bagian 1 selalu tampil; bagian 2 hanya bila ada skill wajib kritis yang
    belum ada. Input sama → string identik (mudah diuji & stabil di UI).
    """
    base = f"Skor {overall:.0f} — {matched_required} dari {total_required} skill wajib terpenuhi"
    if missing_critical > 0:
        return f"{base}; {missing_critical} skill wajib belum ada."
    return f"{base}."


def _build_item(job: Job, result: dict) -> dict:
    """Satu item rekomendasi dari hasil score_pair + metadata lowongan."""
    matched = result["matched"]
    missing = result["missing"]
    matched_required = sum(1 for item in matched if item.get("required"))
    total_required = matched_required + sum(1 for item in missing if item.get("required"))
    missing_critical = sum(1 for item in missing if item.get("severity") == "kritis")
    overall = float(result["overall"])
    # Skill WAJIB lebih dulu, lalu diutamakan (urutan asal dipertahankan —
    # sort Python stabil), dipangkas ke MAX_MATCHED_SKILLS nama tampilan.
    ordered = sorted(matched, key=lambda item: not item.get("required"))
    return {
        "job_id": job.id,
        "title": job.title,
        "company": job.company.name if job.company is not None else None,
        "location": job.location_text,
        "employment_type": job.employment_type,
        "overall": overall,
        "label": label_for(overall),
        "matched_required": matched_required,
        "total_required": total_required,
        "matched_skills": [
            str(item.get("display") or item.get("name") or "")
            for item in ordered[:MAX_MATCHED_SKILLS]
        ],
        "missing_critical": missing_critical,
        "reason": _build_reason(overall, matched_required, total_required, missing_critical),
    }


def recommend_jobs(
    db: Session, user: User, settings: Settings, *, limit: int = DEFAULT_LIMIT
) -> dict:
    """Rekomendasi lowongan aktif untuk CV primer kandidat (dihitung on request).

    Mengembalikan dict kontrak API GET /me/recommendations: cv_id,
    model_version, computed_at, total (lowongan aktif yang berhasil dinilai),
    items (top `limit`, urut overall DESC). TIDAK menulis match_results dan
    TIDAK commit — satu-satunya efek tulis adalah vektor on the fly di
    cv/job_embeddings (commit internal embedding_service, pola M4).
    """
    limit = max(1, min(int(limit), MAX_LIMIT))

    # 1) Gate + data kandidat — reuse helper match_service agar gate & sumber
    #    slug PERSIS sama dengan /compatibility (status != rejected; explicit =
    #    extraction_method 'explicit').
    cv = match_service._get_primary_cv(db, user)
    candidate_slugs, explicit_slugs = match_service._load_candidate_slugs(db, user)

    cv_vec = match_service._load_vector(db, CvEmbedding, "cv_id", cv.id, "profile", settings)
    if cv_vec is None:
        embedding_service.embed_cv(db, cv.id, settings)
        cv_vec = match_service._load_vector(db, CvEmbedding, "cv_id", cv.id, "profile", settings)
        if cv_vec is None:
            raise match_service.MatchUnavailableError()

    payload = cv.extraction.payload or {}
    # Sejajar urutan payload experiences APA ADANYA (termasuk entri tanpa judul)
    # agar len(cv_title_vecs) == len(experiences — kontrak score_pair).
    experience_titles = [
        str(exp.get("title") or "") if isinstance(exp, dict) else ""
        for exp in payload.get("experiences") or []
    ]
    taxonomy_related = match_service.load_taxonomy_related()

    # 2) Lowongan eligible: aktif & belum dihapus (draft/closed/paused di luar).
    jobs = list(
        db.scalars(select(Job).where(Job.status == "active", Job.deleted_at.is_(None))).all()
    )

    # 3) Vektor lowongan: batch load → embed on the fly yang hilang → baca ulang.
    job_vecs = _load_job_vectors(db, [job.id for job in jobs], settings)
    for job in jobs:
        if job.id in job_vecs:
            continue
        try:
            embedding_service.embed_job(db, job.id, settings)
        except Exception:
            db.rollback()  # bersihkan transaksi; lowongan ini saja yang dilewati
            logger.warning("Embed on the fly lowongan %s gagal — dilewati.", job.id, exc_info=True)
    still_missing = [job.id for job in jobs if job.id not in job_vecs]
    job_vecs.update(_load_job_vectors(db, still_missing, settings))

    eligible = [job for job in jobs if job.id in job_vecs]
    cv_title_vecs: list[list[float]] = []
    if eligible:
        # Encoder judul terikat model aktif — fallback defensif bila vektor judul
        # tak sejajar (normalnya tidak pernah dipakai, mirror match_service).
        scorer.set_title_encoder(
            lambda texts, _model=settings.embedding_model: embedding_service.get_embedder(
                _model
            ).encode(list(texts))
        )
        # SATU batch untuk semua judul: judul lowongan (per pasangan) + judul
        # pengalaman CV (sekali per request) — tanpa encode ulang per pasangan.
        encoded = embedding_service.get_embedder(settings.embedding_model).encode(
            [*(job.title for job in eligible), *experience_titles]
        )
        n_jobs = len(eligible)
        job_title_vecs = [list(vector) for vector in encoded[:n_jobs]]
        cv_title_vecs = [list(vector) for vector in encoded[n_jobs:]]

    # 4) Skor per pasangan — skill lowongan di-resolve per job (mirror M4).
    scored: list[tuple[Job, dict]] = []
    for job, job_title_vec in zip(eligible, job_title_vecs, strict=True):
        job_dict = {
            "title": job.title,
            "skills": match_service._resolve_job_skills(db, job),
            "description": job.description,
            "requirements": job.requirements,
            "responsibilities": job.responsibilities,
            "seniority": job.seniority,
        }
        result = score_pair(
            cv_payload=payload,
            job=job_dict,
            cv_vec=cv_vec,
            job_vec=job_vecs[job.id],
            job_title_vec=job_title_vec,
            candidate_slugs=candidate_slugs,
            explicit_slugs=explicit_slugs,
            weights=tuple(settings.match_weights),
            taxonomy_related=taxonomy_related,
            cv_title_vecs=cv_title_vecs,
        )
        scored.append((job, result))

    # 5) Urut overall DESC (tie-break job_id → deterministik), ambil top limit.
    scored.sort(key=lambda pair: (-float(pair[1]["overall"]), pair[0].id))
    items = [_build_item(job, result) for job, result in scored[:limit]]

    return {
        "cv_id": cv.id,
        "model_version": match_service.build_model_version(settings),
        "computed_at": datetime.now(UTC),
        "total": len(scored),
        "items": items,
    }
