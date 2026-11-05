"""Seed akun demo TalentSync AI (idempoten).

Kredensial TIDAK di-hardcode di source: password diambil dari environment
`SEED_DEMO_PASSWORD` atau argumen `--password` (min. 8 karakter).

Pemakaian (butuh PostgreSQL yang berjalan + DATABASE_URL terpasang):
    cd backend
    SEED_DEMO_PASSWORD="DemoTalent2026" .venv/Scripts/python -m scripts.seed_demo_data

Menghasilkan:
    - HR:        dewi.lestari@demo.talentsync.id  (+ perusahaan & 3 lowongan)
    - Kandidat:  sarah.wijaya@demo.talentsync.id  (+ profil terisi)
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.company import Company, CompanyMember  # noqa: E402
from app.models.job import Job  # noqa: E402
from app.models.profile import CandidateProfile  # noqa: E402
from app.models.user import User  # noqa: E402

HR_EMAIL = "dewi.lestari@demo.talentsync.id"
CANDIDATE_EMAIL = "sarah.wijaya@demo.talentsync.id"


def get_or_create_user(
    db: Session, *, email: str, full_name: str, role: str, password: str
) -> tuple[User, bool]:
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return user, False
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
    )
    db.add(user)
    db.flush()
    if role == "candidate":
        db.add(CandidateProfile(user_id=user.id))
    db.commit()
    db.refresh(user)
    return user, True


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed akun demo TalentSync AI")
    parser.add_argument("--password", default=os.environ.get("SEED_DEMO_PASSWORD", ""))
    args = parser.parse_args()

    password = args.password
    if not password or len(password) < 8:
        print("ERROR: set SEED_DEMO_PASSWORD atau --password (min. 8 karakter).")
        return 1

    db = SessionLocal()
    try:
        hr, hr_created = get_or_create_user(
            db,
            email=HR_EMAIL,
            full_name="Dewi Lestari",
            role="hr",
            password=password,
        )
        candidate, cand_created = get_or_create_user(
            db,
            email=CANDIDATE_EMAIL,
            full_name="Sarah Wijaya",
            role="candidate",
            password=password,
        )

        company = db.scalar(select(Company).where(Company.created_by_user_id == hr.id))
        if company is None:
            company = Company(
                name="PT Teknologi Nusantara (Demo)",
                description="Perusahaan teknologi contoh untuk demo TalentSync AI.",
                industry="Teknologi",
                location="Jakarta Selatan",
                website="https://demo.talentsync.id",
                contact_email=HR_EMAIL,
                created_by_user_id=hr.id,
            )
            db.add(company)
            db.flush()
            db.add(CompanyMember(company_id=company.id, user_id=hr.id, role_in_company="owner"))
            db.commit()
            db.refresh(company)

        now = datetime.now(UTC)
        seed_jobs = [
            dict(
                title="Senior Full-Stack Engineer",
                description=(
                    "Memimpin pengembangan aplikasi web end-to-end bersama tim produk. "
                    "Fokus pada arsitektur API, kualitas kode, dan mentoring engineer junior."
                ),
                skills=[
                    {"name": "React", "required": True},
                    {"name": "Python", "required": True},
                    {"name": "PostgreSQL", "required": True},
                    {"name": "Docker", "required": False},
                    {"name": "AWS", "required": False},
                ],
                employment_type="full_time",
                work_mode="hybrid",
                location_text="Jakarta Selatan (Hybrid 3 Hari)",
                salary_min=22_000_000,
                salary_max=35_000_000,
                status="active",
                posted_at=now - timedelta(days=2),
            ),
            dict(
                title="Product Designer",
                description=(
                    "Merancang pengalaman produk fintech dari riset hingga handoff. "
                    "Bekerja erat dengan PM dan engineer dalam sprint dua mingguan."
                ),
                skills=[
                    {"name": "Figma", "required": True},
                    {"name": "Design System", "required": True},
                    {"name": "User Research", "required": False},
                ],
                employment_type="full_time",
                work_mode="remote",
                location_text="Remote (Indonesia)",
                salary_min=15_000_000,
                salary_max=25_000_000,
                status="draft",
                posted_at=None,
            ),
            dict(
                title="Data Analyst",
                description=(
                    "Menganalisis data produk dan menyusun dashboard untuk tim bisnis. "
                    "Lowongan contoh dengan status ditutup."
                ),
                skills=[
                    {"name": "SQL", "required": True},
                    {"name": "Python", "required": True},
                    {"name": "Tableau", "required": False},
                ],
                employment_type="contract",
                work_mode="onsite",
                location_text="Surabaya",
                salary_min=10_000_000,
                salary_max=15_000_000,
                status="closed",
                posted_at=now - timedelta(days=30),
            ),
        ]

        created_jobs = 0
        for spec in seed_jobs:
            exists = db.scalar(
                select(Job).where(Job.title == spec["title"], Job.company_id == company.id)
            )
            if exists:
                continue
            closing = now + timedelta(days=21) if spec["status"] == "active" else None
            db.add(
                Job(
                    company_id=company.id,
                    posted_by_user_id=hr.id,
                    title=spec["title"],
                    description=spec["description"],
                    skills=spec["skills"],
                    employment_type=spec["employment_type"],
                    work_mode=spec["work_mode"],
                    location_text=spec["location_text"],
                    salary_min=spec["salary_min"],
                    salary_max=spec["salary_max"],
                    status=spec["status"],
                    posted_at=spec["posted_at"],
                    last_seen_at=spec["posted_at"],
                    closing_at=closing,
                )
            )
            created_jobs += 1
        db.commit()

        print("Seed selesai:")
        print(f"  HR       : {HR_EMAIL} {'(baru)' if hr_created else '(sudah ada)'}")
        print(f"  Kandidat : {CANDIDATE_EMAIL} {'(baru)' if cand_created else '(sudah ada)'}")
        print(f"  Lowongan baru dibuat: {created_jobs} (status: active/draft/closed)")
        print("  Password: dari SEED_DEMO_PASSWORD/--password (tidak ditampilkan).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
