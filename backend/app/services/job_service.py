"""Service lowongan: CRUD HR, lifecycle status, dan katalog publik kandidat."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.company import Company, CompanyMember
from app.models.job import Job
from app.models.skill import JobSkill
from app.models.user import User
from app.schemas.job import JobIn
from app.services import skill_service

# Transisi lifecycle (blueprint §5.3, versi manual untuk P2 — sweep expired otomatis
# menyusul di fase ingestion):
_TRANSITIONS: dict[str, dict[str, str | None]] = {
    "publish": {"from": {"draft"}, "to": "active"},
    "pause": {"from": {"active"}, "to": "paused"},
    "resume": {"from": {"paused"}, "to": "active"},
    "close": {"from": {"active", "paused"}, "to": "closed"},
}


def _as_aware(dt: datetime) -> datetime:
    # SQLite mengembalikan naive datetime; normalisasi sebelum dibanding (lihat ADR 0002).
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def get_company_of(db: Session, user: User) -> Company:
    member = db.scalar(select(CompanyMember).where(CompanyMember.user_id == user.id))
    if member is None:
        raise BadRequestError("Buat profil perusahaan terlebih dahulu.")
    return member.company


def _replace_job_skills(db: Session, job_id: uuid.UUID, skills: list[dict]) -> None:
    """Ganti baris `job_skills` lowongan dengan hasil normalisasi taksonomi (M2).

    Nama tanpa padanan kanon tidak dibuatkan baris (FK canonical NOT NULL) — ia
    tetap tampil di `jobs.skills` (JSONB, sumber kebenaran tampilan). Tidak
    commit: mengikuti transaksi pemanggil (create/update)."""
    normalized = skill_service.normalize_job_skills(db, skills)
    for row in db.scalars(select(JobSkill).where(JobSkill.job_id == job_id)):
        db.delete(row)
    db.flush()
    for item in normalized:
        if item["canonical_skill_id"] is None:
            continue
        db.add(
            JobSkill(
                job_id=job_id,
                canonical_skill_id=item["canonical_skill_id"],
                raw_name=item["raw_name"],
                required=item["required"],
                evidence=item["evidence"],
                confidence=item["confidence"],
            )
        )


def create_job(db: Session, user: User, data: JobIn) -> Job:
    company = get_company_of(db, user)
    job = Job(
        company_id=company.id,
        posted_by_user_id=user.id,
        source_type="hr",
        status="draft",
        title=data.title,
        description=data.description,
        responsibilities=data.responsibilities,
        requirements=data.requirements,
        skills=[s.model_dump() for s in data.skills],
        category=data.category,
        employment_type=data.employment_type,
        work_mode=data.work_mode,
        seniority=data.seniority,
        location_text=data.location_text,
        salary_min=data.salary_min,
        salary_max=data.salary_max,
        salary_currency=data.salary_currency,
        closing_at=data.closing_at,
    )
    db.add(job)
    # M2: job harus punya id dulu sebelum baris job_skills disisipkan.
    db.flush()
    _replace_job_skills(db, job.id, [s.model_dump() for s in data.skills])
    db.commit()
    db.refresh(job)
    return job


def _owned_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    """Ambil job milik perusahaan HR peminta. Job milik perusahaan lain → 404
    (jangan bocorkan keberadaan resource — blueprint §5.3)."""
    company = get_company_of(db, user)
    job = db.get(Job, job_id)
    if job is None or job.company_id != company.id:
        raise NotFoundError("Lowongan tidak ditemukan.")
    return job


def get_job_for_company(db: Session, user: User, job_id: uuid.UUID) -> Job:
    return _owned_job(db, user, job_id)


def list_company_jobs(
    db: Session, user: User, *, status: str | None, page: int, size: int
) -> tuple[list[Job], int]:
    company = get_company_of(db, user)
    stmt = select(Job).where(Job.company_id == company.id, Job.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Job.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        db.scalars(stmt.order_by(Job.created_at.desc()).offset((page - 1) * size).limit(size))
        .unique()
        .all()
    )
    return list(rows), int(total)


def update_job(db: Session, user: User, job_id: uuid.UUID, data: JobIn) -> Job:
    job = _owned_job(db, user, job_id)
    if job.status not in ("draft", "active", "paused"):
        raise ConflictError(f"Lowongan berstatus '{job.status}' tidak dapat diubah.")
    job.title = data.title
    job.description = data.description
    job.responsibilities = data.responsibilities
    job.requirements = data.requirements
    job.skills = [s.model_dump() for s in data.skills]
    job.category = data.category
    job.employment_type = data.employment_type
    job.work_mode = data.work_mode
    job.seniority = data.seniority
    job.location_text = data.location_text
    job.salary_min = data.salary_min
    job.salary_max = data.salary_max
    job.salary_currency = data.salary_currency
    job.closing_at = data.closing_at
    job.updated_at = datetime.now(UTC)
    # M2: baris job_skills diganti penuh mengikuti daftar skill terbaru.
    _replace_job_skills(db, job.id, [s.model_dump() for s in data.skills])
    db.commit()
    db.refresh(job)
    return job


def transition_job(db: Session, user: User, job_id: uuid.UUID, action: str) -> Job:
    rule = _TRANSITIONS.get(action)
    if rule is None:
        raise BadRequestError("Aksi tidak dikenal.")
    job = _owned_job(db, user, job_id)
    if job.status not in rule["from"]:
        raise ConflictError(f"Aksi '{action}' tidak valid untuk lowongan berstatus '{job.status}'.")
    job.status = str(rule["to"])
    if action == "publish":
        now = datetime.now(UTC)
        if job.closing_at is not None and _as_aware(job.closing_at) <= now:
            raise ConflictError("Batas akhir lamaran sudah lewat. Perbarui tanggalnya dahulu.")
        job.posted_at = now
        job.last_seen_at = now
    if action == "close":
        job.closed_reason = "manual"
    db.commit()
    db.refresh(job)
    return job


def archive_job(db: Session, user: User, job_id: uuid.UUID) -> Job:
    """Soft delete: riwayat tetap tersimpan (blueprint §5.3)."""
    job = _owned_job(db, user, job_id)
    job.status = "archived"
    job.deleted_at = datetime.now(UTC)
    db.commit()
    db.refresh(job)
    return job


def company_job_stats(db: Session, user: User) -> dict:
    company = get_company_of(db, user)
    rows = db.execute(
        select(Job.status, func.count())
        .where(Job.company_id == company.id, Job.deleted_at.is_(None))
        .group_by(Job.status)
    ).all()
    by_status = {status: count for status, count in rows}
    return {"total": sum(by_status.values()), "by_status": by_status}


# --- Katalog publik (kandidat) ---


def _public_filters():
    return (Job.status == "active", Job.deleted_at.is_(None))


def list_public_jobs(
    db: Session,
    *,
    q: str | None,
    location: str | None,
    employment_type: str | None,
    work_mode: str | None,
    page: int,
    size: int,
) -> tuple[list[Job], int]:
    stmt = select(Job).where(*_public_filters())
    if q:
        stmt = stmt.where(Job.title.ilike(f"%{q.strip()}%"))
    if location:
        stmt = stmt.where(Job.location_text.ilike(f"%{location.strip()}%"))
    if employment_type:
        stmt = stmt.where(Job.employment_type == employment_type)
    if work_mode:
        stmt = stmt.where(Job.work_mode == work_mode)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        db.scalars(
            stmt.order_by(Job.posted_at.desc().nulls_last(), Job.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        .unique()
        .all()
    )
    return list(rows), int(total)


def get_public_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.status != "active" or job.deleted_at is not None:
        # Draft/closed tidak pernah tampil ke kandidat (arah direktif).
        raise NotFoundError("Lowongan tidak ditemukan atau sudah tidak aktif.")
    return job
