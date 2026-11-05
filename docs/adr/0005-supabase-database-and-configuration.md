# ADR 0005 — Adopsi Supabase PostgreSQL, Konfigurasi Environment, & Hardening

**Status:** Diterima (P3.0, 6 November 2026; keputusan pemilik proyek)

## 1. Konteks

P0–P2 diasumsikan PostgreSQL lokal via Docker Compose; Docker tidak pernah
terpasang di mesin dev dan PostgreSQL asli hanya diverifikasi CI. Pemilik proyek
memindahkan database ke **Supabase (PostgreSQL 17.11, region ap-southeast-1)**.
Audit lingkungan menemukan 5 masalah konfigurasi (duplikasi `DATABASE_URL`,
`.env` salah lokasi, crash parsing `cors_origins`, interpolasi Alembic pada
password ter-encode, dan `GROQ_API_KEY` tidak terbaca).

## 2. Keputusan

### 2.1 Database
- **Supabase Project A** (`postgres.llvyurqazuhhrevpfikm@aws-0-ap-southeast-1.pooler.supabase.com`)
  adalah database dev/prod utama — disetujui pemilik proyek.
- **Koneksi: session pooler `:5432`** + `sslmode=require` (TLS leg klien→pooler).
  Transaction pooler `:6543` hanya cadangan. Direct connection (`db.<ref>.supabase.co`)
  dihindari (IPv6-only). `connect_timeout` naik 5→10 dtk.
- Skema **hanya** dibentuk lewat migrasi Alembic (0001–0005 terverifikasi jalan
  di Supabase; migrasi P3 0006–0009 dijalankan bertahap).

### 2.2 Testing (keputusan pemilik proyek #6)
- **Unit/E2E: SQLite lokal** (tidak berubah, ADR 0002/0003).
- **Integration: Supabase** — TIDAK lewat `DATABASE_URL_TEST` (conftest melakukan
  `drop_all` — dilarang ke database bersama), melainkan **skrip verifikasi
  integrasi non-destruktif & self-cleaning** (`scripts/verify_supabase_integration.py`).
- CI tetap PostgreSQL 16 + pgvector asli (parity image).

### 2.3 Strategi `.env` dua peran
- **`backend/.env`** = satu-sumber konfigurasi APLIKASI (DATABASE_URL, SECRET_KEY,
  GROQ_*, EMBEDDING_*, MATCH_WEIGHTS). Path di-anchor di `config.py`
  (`BACKEND_DIR / ".env"`) sehingga uvicorn/alembic/scripts/pytest membaca file
  yang sama dari working directory mana pun. Template: `backend/.env.example`.
- **Root `.env`** = hanya variabel substitusi Docker Compose (POSTGRES_* lokal).
  Service `api` memuat `backend/.env` via `env_file` (required: false) dan
  menimpa `DATABASE_URL` ke service `db` lokal pada mode Docker.
- Password database **wajib ter-URL-encode** (`#` → `%23`); dokumentasi di
  `backend/.env.example`.

### 2.4 Perbaikan kode (audit lingkungan)
1. `config.py`: `cors_origins` & `match_weights` memakai `Annotated[..., NoDecode]`
   + validator before — pydantic-settings tidak lagi mencoba `json.loads` pada
   string comma-format (sumber crash). Field baru: `groq_api_key`, `groq_model`,
   `groq_model_fallback`, `embedding_model`, `embedding_dim`, `match_weights`
   (validasi 4 nilai, rentang [0,1], total 1.0).
2. `alembic/env.py`: engine dibangun langsung dari `get_settings()` — menghapus
   `config.set_main_option` yang di-interpolate configparser dan crash pada
   password berisi `%`.
3. `docker-compose.yml`: `env_file` + `required: false` untuk `backend/.env`.

### 2.5 Security hardening
- **RLS di-enable pada SEMUA tabel** tanpa policy = PostgREST (Data API) menolak
  semua akses anon/authenticated; backend lolos karena terhubung sebagai owner
  (`postgres`, tanpa `FORCE ROW LEVEL SECURITY`). Data API exposure di dashboard
  tidak lagi relevan secara keamanan, namun boleh juga dimatikan.
- **Rotasi password database** sebelum kredensial dipakai lebih lanjut — catatan:
  role `postgres` Supabase TIDAK berhak `ALTER USER` sendiri (teruji: permission
  denied) → rotasi via **Dashboard Supabase** (Settings → Database → Reset
  database password), lalu isi password baru ke `backend/.env`.

## 3. Konsekuensi & risiko
- `db` service Compose menjadi opsional (dev offline saja); CI tetap memakai
  image pgvector untuk parity.
- Koneksi cloud menambah ±1 dtk latensi koneksi awal; `pool_pre_ping` sudah aktif.
- Semua perubahan database (termasuk RLS) hanya boleh lewat skrip terdokumentasi.
