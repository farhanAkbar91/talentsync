"""Service ingestion: dedupe + insert lowongan eksternal hasil konektor publik.

Alur per run (Task 3):
1. normalisasi bentuk antara → payload (normalizer.to_job_payloads);
2. dedupe: (source_type, external_id) yang sudah ada → skip (dihitung `skipped`)
   dan last_seen_at diperbarui (dihitung `seen`) — tanda lowongan masih hidup
   di sumber;
3. lowongan baru: status 'active' (lowongan publik, langsung tampil di katalog),
   closing_at = now + INGEST_CLOSING_DAYS, ditandatangani identitas sistem, lalu
   baris job_skills dibuat lewat jalur yang SAMA dengan pembuatan lowongan HR
   (job_service._replace_job_skills → skill_service.normalize_job_skills →
   taxonomy_service.normalize_skill): nama tanpa padanan kanon tetap hidup di
   jobs.skills (JSONB) tanpa baris job_skills — aturan identik form HR;
4. embed terjaga (hanya bila settings.embeddings_enabled; gagal tidak membatalkan).

Idempoten: run kedua dengan data sama → inserted=0, skipped=jumlah run pertama;
UNIQUE index parsial uq_jobs_source_external menjadi jaring pengaman terakhir.

Catatan desain (dibanding blueprint Task):
- jobs.company_id NOT NULL (0003) → dibuat perusahaan wadah khusus ingestion
  (bukan perusahaan demo/HR sungguhan) di samping user sistem.
- jobs.employment_type NOT NULL + CHECK enum (0003) & JobPublicOut.employment_type
  wajib str → payload None dipetakan ke "full_time" (asumsi paling umum lowongan
  remote tech; keterbatasan ini didokumentasikan, bukan mengubah skema).
"""

import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.ingestion.normalizer import to_job_payloads
from app.models.company import Company, CompanyMember
from app.models.job import Job
from app.models.user import User
from app.services import embedding_service, job_service

logger = logging.getLogger(__name__)

# Batas akhir lamaran default lowongan ingestion: 30 hari sejak masuk. Konstanta
# modul — sengaja TIDAK menambah Settings (keputusan scope fase ini).
INGEST_CLOSING_DAYS = 30

# Identitas sistem: jobs.posted_by_user_id & jobs.company_id NOT NULL (0003) —
# lowongan hasil ingestion ditandatangani akun ini (role hr, tanpa perusahaan
# sungguhan). Password hash acak yang tidak pernah disimpan/dilog → tidak bisa
# dipakai login (bcrypt selalu gagal memverifikasi password apa pun).
INGESTION_SYSTEM_EMAIL = "system@ingestion.talentsync.dev"
INGESTION_SYSTEM_NAME = "TalentSync Ingestion System"
INGESTION_COMPANY_NAME = "TalentSync External Jobs"
INGESTION_COMPANY_DESC = (
    "Wadah lowongan hasil ingestion API publik (RemoteOK/Remotive/Arbeitnow) — "
    "bukan perusahaan HR sungguhan."
)


def get_or_create_system_identity(db: Session) -> tuple[User, Company]:
    """Ambil (atau buat sekali — idempoten) user sistem + perusahaan wadah.

    Dipanggil ulang setiap run tanpa efek samping: pencarian by email/nama
    unik, CompanyMember dijamin ada (unique user_id).
    """
    user = db.scalar(select(User).where(User.email == INGESTION_SYSTEM_EMAIL))
    if user is None:
        user = User(
            email=INGESTION_SYSTEM_EMAIL,
            # Bukan secret: plaintext acak sekali-pakai, langsung dibuang — akun
            # tidak untuk login (hash tak akan cocok dengan password apa pun).
            password_hash=hash_password(secrets.token_urlsafe(32)),
            full_name=INGESTION_SYSTEM_NAME,
            role="hr",
        )
        db.add(user)
        db.flush()

    company = db.scalar(
        select(Company).where(
            Company.name == INGESTION_COMPANY_NAME,
            Company.created_by_user_id == user.id,
        )
    )
    if company is None:
        company = Company(
            name=INGESTION_COMPANY_NAME,
            description=INGESTION_COMPANY_DESC,
            created_by_user_id=user.id,
        )
        db.add(company)
        db.flush()

    member = db.scalar(select(CompanyMember).where(CompanyMember.user_id == user.id))
    if member is None:
        db.add(CompanyMember(company_id=company.id, user_id=user.id, role_in_company="owner"))
        db.flush()

    return user, company


def _existing_jobs_by_external_id(
    db: Session, source_type: str, external_ids: list[str]
) -> dict[str, Job]:
    """Peta external_id → Job eksisting (belum soft-delete) utk dedupe cepat.

    Predikat selaras index parsial uq_jobs_source_external (external_id terisi
    dan deleted_at NULL) — lowongan arsip tidak menghalangi insert ulang.
    """
    if not external_ids:
        return {}
    rows = db.scalars(
        select(Job).where(
            Job.source_type == source_type,
            Job.external_id.in_(external_ids),
            Job.deleted_at.is_(None),
        )
    )
    return {job.external_id: job for job in rows if job.external_id is not None}


def ingest(
    db: Session,
    settings: Settings,
    *,
    source_type: str,
    items: list[dict],
    dry_run: bool = False,
) -> dict:
    """Ingest satu sumber: dedupe → insert baru → normalisasi skill → embed.

    Return {"inserted": n, "skipped": m, "seen": k, "source": source_type}:
    - inserted: lowongan baru dibuat;
    - skipped: item dilewati karena sudah ada di DB ATAU duplikat dalam batch;
    - seen: lowongan eksisting yang last_seen_at-nya diperbarui (lowongan masih
      terlihat di sumber). Dry-run: hitung saja, TIDAK ada tulisan ke DB
      (termasuk identitas sistem & last_seen_at).
    """
    payloads = to_job_payloads(source_type, items)

    # Dedupe dalam batch: external_id sama muncul dua kali → sekali diproses,
    # sisanya dihitung skipped (tidak menggandakan insert).
    skipped = 0
    unique: list[dict] = []
    seen_ids: set[str] = set()
    for payload in payloads:
        if payload["external_id"] in seen_ids:
            skipped += 1
            continue
        seen_ids.add(payload["external_id"])
        unique.append(payload)

    existing = _existing_jobs_by_external_id(db, source_type, list(seen_ids))

    inserted = 0
    seen = 0
    now = datetime.now(UTC)
    closing_at = now + timedelta(days=INGEST_CLOSING_DAYS)
    identity: tuple[User, Company] | None = None

    for payload in unique:
        job = existing.get(payload["external_id"])
        if job is not None:
            # Sudah ada → skip, tapi tandai lowongan masih terlihat di sumber.
            skipped += 1
            seen += 1
            if not dry_run:
                job.last_seen_at = now
            continue
        if dry_run:
            inserted += 1  # hitung saja — tanpa tulis apa pun
            continue

        if identity is None:
            # Identitas sistem dibuat hanya saat benar-benar insert (dibutuhkan
            # karena kolom company_id/posted_by_user_id NOT NULL).
            identity = get_or_create_system_identity(db)
        system_user, system_company = identity

        job = Job(
            company_id=system_company.id,
            posted_by_user_id=system_user.id,
            source_type=source_type,
            external_id=payload["external_id"],
            source_url=payload["source_url"],
            status="active",  # lowongan publik — langsung tampil di katalog
            title=payload["title"],
            description=payload["description"],
            skills=payload["skills"],
            # Kolom DB NOT NULL + CHECK enum (0003); payload None → default
            # "full_time" (lihat catatan desain di docstring modul).
            employment_type=payload["employment_type"] or "full_time",
            work_mode=payload["work_mode"],
            location_text=payload["location_text"],
            posted_at=payload["posted_at"] or now,
            closing_at=closing_at,
            last_seen_at=now,
        )
        db.add(job)
        # M2: job harus punya id dulu sebelum baris job_skills disisipkan.
        db.flush()
        # Normalisasi skill lewat jalur yang sama dengan pembuatan lowongan HR
        # — JANGAN duplikasi logika normalize di sini.
        job_service._replace_job_skills(db, job.id, payload["skills"])

        # M3: vektor lowongan menyusul (guard fitur — gagal embed tidak
        # menggagalkan ingestion, pola sama dengan job_service).
        if settings.embeddings_enabled:
            try:
                embedding_service.embed_job(db, job.id, settings)
            except Exception:
                logger.warning(
                    "Embedding job ingestion %s gagal — dilewati.", job.id, exc_info=True
                )

        inserted += 1

    if not dry_run and (inserted or seen):
        db.commit()
    return {"inserted": inserted, "skipped": skipped, "seen": seen, "source": source_type}


__all__ = ["INGEST_CLOSING_DAYS", "get_or_create_system_identity", "ingest"]
