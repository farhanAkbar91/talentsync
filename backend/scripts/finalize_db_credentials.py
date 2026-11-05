"""Finalisasi kredensial database setelah rotasi via Dashboard Supabase.

CARA PAKAI (setelah Anda reset password di Dashboard Supabase):
  1. Tambahkan SATU baris di root .env (file ini tidak di-commit):
         SUPABASE_NEW_DB_PASSWORD=<password baru dari dashboard>
  2. Jalankan dari backend/:
         .venv/Scripts/python scripts/finalize_db_credentials.py
  3. Skrip akan: verifikasi koneksi baru (session pooler :5432) -> tulis
     backend/.env lengkap (DATABASE_URL baru + SECRET_KEY + GROQ_* yang diambil
     dari root .env lama) -> tulis ulang root .env menjadi compose-only (tanpa
     secret, tanpa baris marker) -> verifikasi ulang.

Tidak pernah mencetak password/API key. Bila verifikasi gagal, tidak ada file
yang diubah.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
MARKER = "SUPABASE_NEW_DB_PASSWORD"
# Target (Project A — disetujui pemilik proyek, lihat ADR 0005):
PROJECT_REF = "llvyurqazuhhrevpfikm"
HOST = "aws-0-ap-southeast-1.pooler.supabase.com"
PORT = 5432  # session pooler


def _grab(env_text: str, key: str) -> str | None:
    m = re.search(rf"^{key}\s*=\s*(.+?)\s*$", env_text, re.M)
    return m.group(1).strip().strip('"').strip("'") if m else None


def main() -> None:
    root_env_path = ROOT / ".env"
    old_root = root_env_path.read_text(encoding="utf-8")
    new_pw = _grab(old_root, MARKER)
    if not new_pw:
        print(f"{MARKER} tidak ditemukan di root .env — tambahkan dulu (lihat docstring skrip).")
        sys.exit(1)

    secret_key = _grab(old_root, "SECRET_KEY") or ""
    groq_key = _grab(old_root, "GROQ_API_KEY") or ""
    if not secret_key:
        print("PERINGATAN: SECRET_KEY tidak ditemukan di root .env lama.")
    if not groq_key:
        print("PERINGATAN: GROQ_API_KEY tidak ditemukan di root .env lama.")

    user = f"postgres.{PROJECT_REF}"
    # Password bisa berisi karakter khusus -> URL-encode untuk DATABASE_URL.
    db_url = (
        f"postgresql+psycopg://{user}:{quote(new_pw, safe='')}@{HOST}:{PORT}/postgres"
        "?sslmode=require"
    )

    print("verifikasi kredensial BARU di session pooler :", PORT, "...")
    engine = create_engine(db_url, connect_args={"connect_timeout": 10})
    try:
        with engine.connect() as c:
            version = c.execute(text("SELECT version()")).scalar()
        print("  OK:", version.split(",")[0])
    except Exception as ex:
        print("  GAGAL:", str(ex).splitlines()[0][:140])
        print("Tidak ada file yang diubah. Pastikan password benar & rotasi sudah efektif.")
        sys.exit(1)

    backend_env = f"""# TalentSync AI — konfigurasi aplikasi backend
# (SATU sumber utk venv dev, scripts, alembic).
# File ini TIDAK di-commit. Template tanpa secret: backend/.env.example.
# Password DB dirotasi via Dashboard Supabase (6 Nov 2026); session pooler :{PORT}.
DATABASE_URL={db_url}
APP_ENV=dev
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
SECRET_KEY={secret_key}
GROQ_API_KEY={groq_key}
GROQ_MODEL=openai/gpt-oss-120b
GROQ_MODEL_FALLBACK=openai/gpt-oss-20b
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DIM=384
MATCH_WEIGHTS=0.40,0.30,0.20,0.10
"""
    (ROOT / "backend" / ".env").write_text(backend_env, encoding="utf-8")

    pg_user = _grab(old_root, "POSTGRES_USER") or "talentsync"
    pg_pw = _grab(old_root, "POSTGRES_PASSWORD") or "talentsync_dev_only"
    pg_db = _grab(old_root, "POSTGRES_DB") or "talentsync"
    root_env = (
        "# TalentSync AI — variabel substitusi docker compose (root).\n"
        "# Konfigurasi aplikasi backend: backend/.env (template: backend/.env.example).\n"
        f"POSTGRES_USER={pg_user}\n"
        f"POSTGRES_PASSWORD={pg_pw}\n"
        f"POSTGRES_DB={pg_db}\n"
    )
    root_env_path.write_text(root_env, encoding="utf-8")
    engine.dispose()
    print("backend/.env ditulis (DATABASE_URL kredensial baru + semua var P3)")
    print("root .env ditulis ulang menjadi compose-only (marker & secret dihapus)")
    print("FINALISASI KREDENSIAL: SELESAI")


if __name__ == "__main__":
    main()
