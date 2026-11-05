"""Verifikasi integrasi backend ⇄ Supabase PostgreSQL — NON-DESTRUKTIF.

Dijalankan setelah migrasi & RLS (Tahap 2 P3.0) dan sebagai bagian quality gate
(Tahap 4). Bukan pengganti pytest SQLite (unit) atau CI PostgreSQL (parity) —
ini membuktikan aplikasi berjalan end-to-end di database cloud.

Langkah:
  1. Health/ready melalui TestClient dengan engine Supabase asli.
  2. RLS: semua tabel publik wajib ENABLE ROW LEVEL SECURITY.
  3. pgvector: ekstensi `vector` aktif.
  4. Smoke API nyata (register HR → perusahaan → job → publish → register
     kandidat → lihat job → upload CV sampel → ekstraksi selesai).
  5. Cleanup: seluruh baris uji dihapus ( CASCADE), hitung sisa = 0.

Jalankan dari backend/: .venv/Scripts/python scripts/verify_supabase_integration.py
"""

from __future__ import annotations

import io
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

REPO = Path(__file__).resolve().parents[2]
SAMPLE_CV = REPO / "frontend" / "e2e" / "fixtures" / "sample-cv.pdf"
MARK = "verify-"


def _fail(msg: str) -> None:
    print(f"  [GAGAL] {msg}")
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def main() -> None:
    from app.core.config import get_settings
    from app.db.base import Base
    from app.main import create_app

    settings = get_settings()
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 10})
    email_h = f"{MARK}hr-{uuid.uuid4().hex[:8]}@verify.talentsync.dev"
    email_c = f"{MARK}cand-{uuid.uuid4().hex[:8]}@verify.talentsync.dev"

    print("== Verifikasi integrasi Supabase (non-destruktif) ==")
    try:
        with engine.connect() as c:
            print("  koneksi:", c.execute(text("SELECT version()")).scalar().split(",")[0])
    except Exception as ex:
        _fail(f"koneksi database: {str(ex).splitlines()[0][:140]}")

    with engine.connect() as c:
        rls = {
            r[0]: r[1]
            for r in c.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname='public' AND c.relkind='r'"
                )
            ).all()
        }
        app_tables = [t for t in Base.metadata.tables]
        belum = [t for t in app_tables if not rls.get(t, False)]
        exts = [r[0] for r in c.execute(text("SELECT extname FROM pg_extension"))]
        if "vector" not in exts:
            _fail("ekstensi pgvector tidak aktif")
        _ok(f"pgvector aktif | tabel aplikasi: {len(app_tables)}")
        if belum:
            _fail(f"RLS belum aktif pada: {belum}")
        _ok(f"RLS aktif pada {len(app_tables)} tabel aplikasi")
        versi = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        _ok(f"alembic_version = {versi}")

    app = create_app(settings)
    app.state.engine = engine
    with TestClient(app) as client:
        r = client.get("/api/v1/health/ready")
        if r.status_code != 200:
            _fail(f"health/ready = {r.status_code}: {r.json()}")
        _ok("health/ready = 200 (database + pgvector)")

        # --- alur HR ---
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": email_h,
                "password": "Verify-Int-2026",
                "full_name": "Verify HR",
                "role": "hr",
            },
        )
        if r.status_code != 201:
            _fail(f"register HR: {r.status_code} {r.text[:140]}")
        hr_token = r.json()["access_token"]
        h = {"Authorization": f"Bearer {hr_token}"}
        r = client.post(
            "/api/v1/me/company",
            headers=h,
            json={"name": "Verify Integration Co", "industry": "tech", "location": "Jakarta"},
        )
        if r.status_code not in (200, 201):
            _fail(f"buat perusahaan: {r.status_code} {r.text[:140]}")
        r = client.post(
            "/api/v1/hr/jobs",
            headers=h,
            json={
                "title": "Verify Job Integration",
                "description": (
                    "Lowongan uji integrasi untuk memverifikasi alur API terhadap "
                    "database PostgreSQL (Supabase) — dibuat dan dihapus otomatis."
                ),
                "employment_type": "full_time",
                "work_mode": "remote",
                "location_text": "Jakarta",
                "closing_at": "2027-01-01T00:00:00Z",
                "skills": [{"name": "SQL", "required": True}],
            },
        )
        if r.status_code != 201:
            _fail(f"buat job: {r.status_code} {r.text[:140]}")
        job_id = r.json()["id"]
        r = client.post(f"/api/v1/hr/jobs/{job_id}/publish", headers=h)
        if r.status_code != 200:
            _fail(f"publish job: {r.status_code}")
        _ok("alur HR: register → perusahaan → job → publish")

        # --- alur kandidat + CV ---
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": email_c,
                "password": "Verify-Int-2026",
                "full_name": "Verify Kandidat",
                "role": "candidate",
            },
        )
        if r.status_code != 201:
            _fail(f"register kandidat: {r.status_code} {r.text[:140]}")
        c_token = r.json()["access_token"]
        ch = {"Authorization": f"Bearer {c_token}"}
        r = client.get("/api/v1/jobs")
        if job_id not in [it["id"] for it in r.json()["items"]]:
            _fail("job terpublish tidak terlihat di katalog publik")
        r = client.post(
            "/api/v1/cvs",
            headers=ch,
            files={
                "file": ("sample-cv.pdf", io.BytesIO(SAMPLE_CV.read_bytes()), "application/pdf")
            },
        )
        if r.status_code != 201:
            _fail(f"upload CV: {r.status_code} {r.text[:140]}")
        cv_id = r.json()["id"]
        r = client.get("/api/v1/cvs", headers=ch)
        # GET /cvs mengembalikan list CVOut langsung (bukan envelope pagination).
        status = next(cv["status"] for cv in r.json() if cv["id"] == cv_id)
        if status != "ready":
            _fail(f"ekstraksi CV status={status} (background task gagal?)")
        _ok("alur kandidat: register → katalog → upload CV → ekstraksi ready")

    # --- cleanup: FK tidak CASCADE di jobs.company_id & companies.created_by_user_id
    # (desain soft-delete), jadi urutannya jobs → companies → users. Sisanya
    # (profile, members, cvs, extractions, refresh_tokens) CASCADE dari users.
    with engine.begin() as c:
        n_job = c.execute(
            text(
                "DELETE FROM jobs WHERE company_id IN (SELECT id FROM companies WHERE "
                "created_by_user_id IN (SELECT id FROM users WHERE email LIKE :p)) RETURNING id"
            ),
            {"p": f"{MARK}%@verify.talentsync.dev"},
        ).rowcount
        n_company = c.execute(
            text(
                "DELETE FROM companies WHERE created_by_user_id IN "
                "(SELECT id FROM users WHERE email LIKE :p) RETURNING id"
            ),
            {"p": f"{MARK}%@verify.talentsync.dev"},
        ).rowcount
        n_user = c.execute(
            text("DELETE FROM users WHERE email LIKE :p RETURNING id"),
            {"p": f"{MARK}%@verify.talentsync.dev"},
        ).rowcount
        sisa = c.execute(
            text("SELECT count(*) FROM users WHERE email LIKE :p"), {"p": f"{MARK}%"}
        ).scalar()
        sisa_job = c.execute(
            text("SELECT count(*) FROM jobs WHERE title='Verify Job Integration'")
        ).scalar()
        sisa_company = c.execute(
            text("SELECT count(*) FROM companies WHERE name='Verify Integration Co'")
        ).scalar()
    engine.dispose()
    if sisa != 0 or sisa_job != 0 or sisa_company != 0:
        _fail(f"cleanup tidak lengkap: users={sisa}, jobs={sisa_job}, companies={sisa_company}")
    _ok(
        f"cleanup: {n_user} user uji + {n_company} perusahaan + {n_job} job uji "
        "dihapus, tidak ada baris uji tersisa"
    )
    print("== INTEGRASI SUPABASE: LULUS ==")


if __name__ == "__main__":
    main()
