"""Service matching (M4): skor kompatibilitas CV utama kandidat vs lowongan aktif.

Aturan main:
- Kandidat hanya melihat lowongan AKTIF & belum dihapus (404 selain itu).
- Sumber data: CV PRIMER (is_primary, tidak dihapus) dengan ekstraksi
  TERKONFIRMASI — belum ada → 400 kode MATCH_UNAVAILABLE (envelope DomainError,
  lihat core.errors).
- Vektor dibaca dari CvEmbedding/JobEmbedding model aktif; hilang → embed on the
  fly via embedding_service lalu baca ulang; tetap hilang → MATCH_UNAVAILABLE.
- Skill lowongan di-resolve ke slug via skill_service.normalize_job_skills
  (mirror normalisasi job_skills); skill kandidat dari baris CandidateSkill
  status != rejected; explicit = extraction_method 'explicit'.
- Result disimpan ke match_results (replace per (cv, job, model_version)) lalu
  dikembalikan sebagai dict kontrak API compatibility/gap.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.matching import gap, scorer
from app.ai.matching.calibration import load_calibration
from app.ai.matching.explainer import build_explanation, label_for
from app.ai.matching.scorer import score_pair
from app.core.config import Settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.ai import CvEmbedding, JobEmbedding, MatchResult
from app.models.cv import CV
from app.models.job import Job
from app.models.skill import CandidateSkill, CanonicalSkill
from app.models.user import User
from app.services import embedding_service, skill_service

logger = logging.getLogger(__name__)

# Versi model scoring: embedding + bobot (x100) + versi kalibrasi — perubahan
# salah satunya menghasilkan model_version baru (baris lama retensi, bukan timpa).
# Kode pendek model embedding: kolom match_results.model_version adalah
# String(60) — nama panjang model tetap tersimpan utuh di CvEmbedding.model
# (keputusan Lead, Wave 3).
EMBEDDING_CODES = {
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": "minilm-l12-v2",
}
MODEL_VERSION_FMT = "m4v1|emb:{emb}|w:{a}-{b}-{c}-{d}|cal:{calv}"

# Lokasi taksonomi default (mirror taxonomy_service.DEFAULT_TAXONOMY_JSON).
_TAXONOMY_JSON = (
    Path(__file__).resolve().parents[1] / "ai" / "extraction" / "taxonomy" / "skills_v1.json"
)


class MatchUnavailableError(BadRequestError):
    """400 dengan kode MATCH_UNAVAILABLE — prasyarat matching belum terpenuhi.

    Mengikuti pola DomainError (core/exceptions.py): code atribut kelas →
    envelope core.errors memuat {"error": {"code": "MATCH_UNAVAILABLE", ...}}.
    """

    code = "MATCH_UNAVAILABLE"
    default_message = "Konfirmasi CV utama terlebih dahulu untuk melihat kecocokan."


# --- Loader taksonomi terkait (cache per proses) ---

_RELATED_CACHE: dict[str, frozenset[str]] | None = None


def reset_taxonomy_related_cache() -> None:
    """Kosongkan cache peta related (untuk test — produksi tidak perlu)."""
    global _RELATED_CACHE
    _RELATED_CACHE = None


def load_taxonomy_related() -> dict[str, set[str]]:
    """Peta slug → himpunan slug terkait dari skills_v1.json (cache per proses).

    Membaca berkas langsung (edge `related` adalah data statis; DB hanya salinan
    seed). Berkas hilang/korup → peta kosong (skor related aman: tidak ada kredit).
    """
    global _RELATED_CACHE
    if _RELATED_CACHE is None:
        try:
            data = json.loads(_TAXONOMY_JSON.read_text(encoding="utf-8"))
            mapping: dict[str, frozenset[str]] = {}
            for item in data.get("skills") or []:
                slug = str(item.get("slug") or "")
                if slug:
                    mapping[slug] = frozenset(str(s) for s in (item.get("related") or []))
            _RELATED_CACHE = mapping
        except (OSError, ValueError, json.JSONDecodeError):
            logger.warning("skills_v1.json tidak terbaca — kredit related dinonaktifkan.")
            _RELATED_CACHE = {}
    return {slug: set(related) for slug, related in _RELATED_CACHE.items()}


# --- Helper data matching ---


def _get_active_job(db: Session, job_id: uuid.UUID) -> Job:
    """Lowongan yang boleh dilihat kandidat: ada, aktif, tidak dihapus → 404 selain itu."""
    job = db.get(Job, job_id)
    if job is None or job.status != "active" or job.deleted_at is not None:
        raise NotFoundError("Lowongan tidak ditemukan atau sudah tidak aktif.")
    return job


def _get_primary_cv(db: Session, user: User) -> CV:
    """CV primer kandidat (bukan soft delete) + ekstraksi terkonfirmasi.

    Tidak ada / belum konfirmasi / payload kosong → MATCH_UNAVAILABLE (400).
    """
    cv = db.scalar(
        select(CV).where(
            CV.candidate_user_id == user.id,
            CV.is_primary.is_(True),
            CV.deleted_at.is_(None),
        )
    )
    if cv is None:
        raise MatchUnavailableError()
    extraction = cv.extraction
    if extraction is None or extraction.confirmed_at is None or extraction.payload is None:
        raise MatchUnavailableError()
    return cv


def _load_vector(
    db: Session,
    model_cls: type[CvEmbedding] | type[JobEmbedding],
    doc_field: str,
    doc_id: uuid.UUID,
    text_kind: str,
    settings: Settings,
) -> list[float] | None:
    row = db.scalar(
        select(model_cls).where(
            getattr(model_cls, doc_field) == doc_id,
            model_cls.model == settings.embedding_model,
            model_cls.text_kind == text_kind,
        )
    )
    return list(row.embedding) if row is not None else None


def _resolve_vectors(
    db: Session, cv: CV, job: Job, settings: Settings
) -> tuple[list[float], list[float], list[float], list[list[float]]]:
    """(cv_vec, job_vec, job_title_vec, cv_title_vecs) model aktif.

    Vektor dokumen di-embed on the fly bila belum ada. Semua JUDUL (judul
    lowongan + judul pengalaman CV) di-encode dalam SATU panggilan batch —
    vektor judul CV dihitung SEKALI per CV (sejajar urutan payload experiences)
    dan diteruskan ke score_pair sebagai `cv_title_vecs` (amandemen performa
    M4: jangan encode ulang judul per pasangan). Kosong → list kosong.
    """
    cv_vec = _load_vector(db, CvEmbedding, "cv_id", cv.id, "profile", settings)
    if cv_vec is None:
        embedding_service.embed_cv(db, cv.id, settings)
        cv_vec = _load_vector(db, CvEmbedding, "cv_id", cv.id, "profile", settings)
        if cv_vec is None:
            raise MatchUnavailableError()

    job_vec = _load_vector(db, JobEmbedding, "job_id", job.id, "job", settings)
    if job_vec is None:
        embedding_service.embed_job(db, job.id, settings)
        job_vec = _load_vector(db, JobEmbedding, "job_id", job.id, "job", settings)
        if job_vec is None:
            raise MatchUnavailableError()

    payload = cv.extraction.payload or {}
    experience_titles = [
        str(exp.get("title") or "") if isinstance(exp, dict) else ""
        for exp in payload.get("experiences") or []
    ]
    embedder = embedding_service.get_embedder(settings.embedding_model)
    encoded = embedder.encode([job.title, *experience_titles])
    job_title_vec = encoded[0]
    cv_title_vecs = [list(vector) for vector in encoded[1:]]
    return cv_vec, job_vec, job_title_vec, cv_title_vecs


def _resolve_job_skills(db: Session, job: Job) -> list[dict]:
    """Skill lowongan → [{"name": raw, "slug"|None, "display", "required"}].

    Mirror normalisasi job_skills (dedupe per slug, OR-merge required; raw tanpa
    padanan tetap dilaporkan dengan slug None — dikecualikan dari coverage).
    """
    normalized = skill_service.normalize_job_skills(db, job.skills or [])
    ids = {item["canonical_skill_id"] for item in normalized if item["canonical_skill_id"]}
    canon_by_id: dict[uuid.UUID, CanonicalSkill] = {}
    if ids:
        rows = db.scalars(select(CanonicalSkill).where(CanonicalSkill.id.in_(ids)))
        canon_by_id = {canon.id: canon for canon in rows}

    resolved: list[dict] = []
    for item in normalized:
        canon = canon_by_id.get(item["canonical_skill_id"]) if item["canonical_skill_id"] else None
        resolved.append(
            {
                "name": item["raw_name"],
                "slug": canon.slug if canon is not None else None,
                "display": canon.name if canon is not None else item["raw_name"],
                "required": bool(item["required"]),
            }
        )
    return resolved


def _load_candidate_slugs(db: Session, user: User) -> tuple[set[str], set[str]]:
    """(candidate_slugs, explicit_slugs) dari CandidateSkill status != rejected."""
    rows = db.execute(
        select(CandidateSkill, CanonicalSkill)
        .join(CanonicalSkill, CandidateSkill.canonical_skill_id == CanonicalSkill.id)
        .where(
            CandidateSkill.candidate_user_id == user.id,
            CandidateSkill.status != "rejected",
        )
    ).all()
    slugs = {canon.slug for _row, canon in rows}
    explicit = {canon.slug for row, canon in rows if row.extraction_method == "explicit"}
    return slugs, explicit


def _category_maps(
    db: Session, candidate_slugs: set[str], job_slugs: list[str]
) -> tuple[list[str], dict[str, list[str]], dict[str, list[str]]]:
    """(daftar kategori taksonomi, peta kategori→slug kandidat, →slug lowongan)."""
    rows = db.execute(select(CanonicalSkill.slug, CanonicalSkill.category)).all()
    slug_category = {slug: category for slug, category in rows}
    taxonomy_categories = sorted({category for _slug, category in rows})

    def build(slugs) -> dict[str, list[str]]:
        mapping: dict[str, list[str]] = {}
        for slug in slugs:
            category = slug_category.get(slug)
            if category is not None:
                mapping.setdefault(category, []).append(slug)
        return mapping

    return taxonomy_categories, build(candidate_slugs), build(job_slugs)


def build_model_version(settings: Settings) -> str:
    """model_version = embedding + bobot (x100) + versi kalibrasi aktif."""
    weights = settings.match_weights
    emb_code = EMBEDDING_CODES.get(settings.embedding_model, settings.embedding_model[:20])
    return MODEL_VERSION_FMT.format(
        emb=emb_code,
        a=int(round(weights[0] * 100)),
        b=int(round(weights[1] * 100)),
        c=int(round(weights[2] * 100)),
        d=int(round(weights[3] * 100)),
        calv=load_calibration()["version"],
    )


def _persist_match_result(
    db: Session,
    cv_id: uuid.UUID,
    job_id: uuid.UUID,
    model_version: str,
    result: dict,
    explanation: str,
) -> None:
    """Replace baris match_results untuk (cv, job, model_version) — tidak commit."""
    stale = db.scalars(
        select(MatchResult).where(
            MatchResult.cv_id == cv_id,
            MatchResult.job_id == job_id,
            MatchResult.model_version == model_version,
        )
    ).all()
    for row in stale:
        db.delete(row)
    db.flush()
    db.add(
        MatchResult(
            cv_id=cv_id,
            job_id=job_id,
            overall=float(result["overall"]),
            factors=result["factors"],
            matched_skills=result["matched"],
            missing_skills=result["missing"],
            evidence=None,
            top_experiences=result["top_experiences"],
            explanation=explanation,
            model_version=model_version,
        )
    )


# --- API publik service ---


def compute_match(db: Session, user: User, job_id: uuid.UUID, settings: Settings) -> dict:
    """Hitung + persist skor kompatibilitas CV primer kandidat vs lowongan aktif.

    Mengembalikan dict lengkap (kontrak API compatibility + kunci `gap` untuk
    endpoint /gap). Commit di akhir — satu transaksi untuk persist hasil.
    """
    job = _get_active_job(db, job_id)
    cv = _get_primary_cv(db, user)

    candidate_slugs, explicit_slugs = _load_candidate_slugs(db, user)
    job_skills = _resolve_job_skills(db, job)
    cv_vec, job_vec, job_title_vec, cv_title_vecs = _resolve_vectors(db, cv, job, settings)

    # Encoder judul terikat model aktif — hanya fallback bila cv_title_vecs
    # tidak sejajar (normalnya tidak pernah dipanggil, lihat _resolve_vectors).
    scorer.set_title_encoder(
        lambda texts, _model=settings.embedding_model: embedding_service.get_embedder(
            _model
        ).encode(list(texts))
    )

    job_dict = {
        "title": job.title,
        "skills": job_skills,
        "description": job.description,
        "requirements": job.requirements,
        "responsibilities": job.responsibilities,
        "seniority": job.seniority,
    }
    result = score_pair(
        cv_payload=cv.extraction.payload or {},
        job=job_dict,
        cv_vec=cv_vec,
        job_vec=job_vec,
        job_title_vec=job_title_vec,
        candidate_slugs=candidate_slugs,
        explicit_slugs=explicit_slugs,
        weights=tuple(settings.match_weights),
        taxonomy_related=load_taxonomy_related(),
        cv_title_vecs=cv_title_vecs,
    )

    years_have = scorer.compute_years_have(cv.extraction.payload or {})
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

    taxonomy_categories, candidate_map, job_map = _category_maps(
        db, candidate_slugs, [skill["slug"] for skill in job_skills if skill["slug"]]
    )
    gap_result = gap.build_gap(result, taxonomy_categories, candidate_map, job_map)

    model_version = build_model_version(settings)
    _persist_match_result(db, cv.id, job.id, model_version, result, explanation)
    db.commit()

    weights_dict = {
        "semantic": float(settings.match_weights[0]),
        "skill_coverage": float(settings.match_weights[1]),
        "experience": float(settings.match_weights[2]),
        "education": float(settings.match_weights[3]),
    }
    return {
        "job_id": job.id,
        "cv_id": cv.id,
        "model_version": model_version,
        "overall": float(result["overall"]),
        "label": label_for(result["overall"]),
        "factors": result["factors"],
        "weights": weights_dict,
        "matched_skills": result["matched"],
        "missing_skills": result["missing"],
        "top_experiences": result["top_experiences"],
        "explanation": explanation,
        "computed_at": datetime.now(UTC),
        "gap": gap_result,
    }


def compatibility_payload(result: dict) -> dict:
    """Potong kunci gap → dict kontrak endpoint /compatibility."""
    return {key: value for key, value in result.items() if key != "gap"}


def get_gap(db: Session, user: User, job_id: uuid.UUID, settings: Settings) -> dict:
    """Kontrak endpoint /gap — reuse compute_match (hasil tetap dipersist)."""
    result = compute_match(db, user, job_id, settings)
    return {
        "job_id": result["job_id"],
        "model_version": result["model_version"],
        "overall": result["overall"],
        "matrix": result["gap"]["matrix"],
        "items": result["gap"]["items"],
        "learning_suggestions": result["gap"]["learning_suggestions"],
        "explanation": result["explanation"],
    }


# --- Invalidation hooks (pemanggil yang commit) ---


def invalidate_cv(db: Session, cv_id: uuid.UUID) -> int:
    """Hapus semua MatchResult milik CV (payload/skill berubah → skor basi).

    Flush saja, TIDAK commit — hook dipanggil di dalam transaksi pemanggil
    (confirm_extraction) agar atomik dengan perubahan lainnya.
    """
    rows = db.scalars(select(MatchResult).where(MatchResult.cv_id == cv_id)).all()
    for row in rows:
        db.delete(row)
    db.flush()
    return len(rows)


def invalidate_job(db: Session, job_id: uuid.UUID) -> int:
    """Hapus semua MatchResult milik lowongan (konten berubah → skor basi)."""
    rows = db.scalars(select(MatchResult).where(MatchResult.job_id == job_id)).all()
    for row in rows:
        db.delete(row)
    db.flush()
    return len(rows)
