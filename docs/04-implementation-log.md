# Log Implementasi TalentSync AI

Catatan progres per fase. Baseline perencanaan: `docs/01-technical-blueprint.md`,
`docs/02-decision-review.md`, `docs/03-final-scope-and-feasibility.md`.

---

## P0 — Project Foundation (4 November 2026)

**Status:** ✅ Selesai dan terverifikasi (dengan satu keterbatasan lingkungan, lihat "Kendala").

### Scope yang dikerjakan

- Struktur monorepo (`backend/`, `frontend/`, `docs/`, CI, compose) — sesuai rencana P0.
- Backend: FastAPI app factory, config `pydantic-settings` (`.env`), JSON logging dengan
  request-ID, error envelope konsisten (404/405/422/500/503), `GET /api/v1/health`
  (liveness), `GET /api/v1/health/ready` (cek DB + ekstensi pgvector), SQLAlchemy 2.0 base
  dengan naming convention, Alembic + migrasi `0001` (`CREATE EXTENSION vector`).
- Frontend: React 19 + Vite 7 + TypeScript (strict) + Tailwind v4 (tokens CSS), klien API
  (`/api/v1`), halaman status (API / Database / pgvector) sebagai bukti integrasi —
  placeholder, bukan desain Figma.
- Infra: `docker-compose.yml` (db pgvector/pg16 + api + web nginx), Dockerfile backend &
  frontend, `.env.example`, `.gitignore`, CI GitHub Actions (ruff + pytest; typecheck +
  build; validasi compose).
- Git repository diinisialisasi (`main`); **belum ada commit** (menunggu instruksi Anda).

### Hasil verifikasi (nyata, dijalankan)

| Pemeriksaan | Hasil |
|---|---|
| `pip install -e ".[dev]"` (Python 3.11 venv) | ✅ (fastapi 0.162, sqlalchemy 2.1.8, pydantic 2.14, psycopg 3.3.8) |
| `ruff check .` + `ruff format --check .` | ✅ All checks passed (18 file) |
| `pytest -q` | ✅ **5 passed** (liveness 200; ready→503 envelope saat DB down; 404/405 envelope; root) — 5,3 s |
| `uvicorn` smoke test + curl | ✅ `/health` 200 + `X-Request-ID`; `/health/ready` 503 envelope tanpa bocor DSN; `/` dan `/openapi.json` hidup |
| `npm install` (Node 24) | ✅ 0 vulnerabilities |
| `npm run build` (tsc --noEmit + vite build) | ✅ built in 3,1 s |
| Integrasi web→api: Vite proxy `/api` | ✅ JSON dari FastAPI lewat port 5173; ready 503 sesuai ekspektasi |
| `docker compose config` | ⚠️ **Tidak bisa dijalankan — Docker tidak terpasang di mesin ini**; sintaks YAML divalidasi via parser (services: api, db, web). Validasi penuh otomatis di CI job `compose` begitu repo di-push |

### Kendala & keputusan selama P0

1. **Docker tidak terpasang** → `docker compose up` belum terverifikasi di mesin lokal.
   File compose & Dockerfile disiapkan; verifikasi penuh memerlukan Docker Desktop
   (atau push ke GitHub dan biarkan CI memvalidasi). Tercatat sebagai risiko lingkungan.
2. **Koneksi DB mati menggantung di Windows** (SYN di-drop) → ditambahkan
   `connect_args={"connect_timeout": 5}` (ADR 0001 §8).
3. **Settings global tak bisa dioverride test** → `settings` dan `engine` kini terikat ke
   `app.state` per instance aplikasi (ADR 0001 §7); test menjadi deterministik.
4. Deprecation warning `starlette.testclient` (menyarankan `httpx2`) — hanya warning,
   tidak menggagalkan; ditunda ke P1 (bukan keputusan arsitektur).

### Cara menjalankan hasil P0

```bash
# Docker (sekali Docker Desktop terpasang):
docker compose up --build
#   web → http://localhost:3000   api → http://localhost:8000/docs

# Tanpa Docker (butuh PostgreSQL lokal bila ingin /health/ready = 200):
cd backend  && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev        # http://localhost:5173
```

Catatan: di mesin ini Vite dev server bind ke `localhost` (IPv6); akses via `localhost`,
bukan `127.0.0.1`.

### Belum dikerjakan (sesuai batas P0)

- P1: registrasi/login, JWT, RBAC, profil kandidat & perusahaan, akun demo, model
  SQLAlchemy pertama + migrasi.
- Pengiriman ke GitHub (remote belum ada) agar CI berjalan.

---

## P1+P2 — Identity, Profiles & Core Recruitment (4–5 November 2026)

**Status:** ✅ Selesai (M1–M5), backend 47/47 test hijau, frontend build hijau.

### M1 — Database & Identity
- Models: `users` (role candidate/hr, email lowercase-unique), `refresh_tokens`
  (SHA-256 hash, rotasi one-time-use), `candidate_profiles` (JSONB terstruktur,
  auto-create saat registrasi kandidat).
- Security: bcrypt + JWT HS256 (access 15 m / refresh 7 hari), RBAC via dependency
  `require_roles`, proteksi endpoint per peran.
- Endpoints: register/login/refresh/logout/me/me-summary.

### M2 — Profiles & Company
- PUT profil kandidat (skills dedupe, pendidikan/pengalaman/sertifikasi JSONB
  tervalidasi); perusahaan + keanggotaan (unique user_id → 1 HR = 1 perusahaan).

### M3 — Recruitment Core
- `jobs`: skills berbobot (flag required = 60% / preferred = 40%, struktur siap AI),
  lifecycle draft→active⇄paused→closed + soft delete (archived), index parsial
  katalog aktif.
- Publik: search judul (ILIKE), filter lokasi/tipe/mode, pagination; draft/paused/
  closed **tidak pernah** tampil ke kandidat; job perusahaan lain → 404.

### M4 — CV Management
- Upload PDF aman: ekstensi+MIME+magic bytes `%PDF-`, streaming cap 10 MB,
  sha256 dedupe per pemilik, nama uuid di `uploads/cvs/{user}/` (di luar root statis).
- Ekstraksi teks dasar PyMuPDF sebagai boundary `app/ai/extraction/` (background
  task + session factory terpisah); kegagalan terekam (status `failed` + pesan).
- Soft delete + promosi primary otomatis; unduh hanya oleh pemilik (404 untuk lain).

### M5 — Frontend Integration
- 11 halaman hidup (login, register, dashboard kandidat/HR, profil, discovery+detail,
  CV, perusahaan, tabel lowongan, form create/edit, detail+aksi lifecycle),
  navigasi per-role + route guard, refresh-token interceptor.

### Hasil verifikasi
- `pytest`: **47 passed** (SQLite lokal; CI: PostgreSQL+pgvector asli).
- `ruff check` + `ruff format --check`: bersih.
- `alembic upgrade head --sql`: rantai 0001→0004 valid (21 objek DDL).
- `npm run build`: typecheck strict + bundle sukses.
- Smoke integrasi web→api: ulang setelah fitur (health via proxy Vite).

### Keputusan & perbaikan selama fase (lihat ADR 0002)
- `SessionLocal` diperbaiki menjadi sessionmaker per-request (warisan P0).
- Settings & engine terikat `app.state` (endpoint tidak lagi membaca settings global).
- Test DB: file SQLite sementara (bukan StaticPool in-memory — race dengan
  background task); CI memakai PostgreSQL asli.
- Token storage: access di memori, refresh di localStorage (kompromi MVP tercatat).
- Warna-warni kegagalan ekstraksi PDF: terproteksi/0 halaman/tanpa teks → `failed`.

### Belum dikerjakan (sesuai batas fase)
- Alur lamaran (applications) — fase berikutnya.
- AI matching/rekomendasi/optimasi/ranking — fase AI.
- Ingestion pipeline — fase data.
- Browser E2E otomatis (Playwright) — smoke manual + pytest e2e sebagai gantinya.

## Post-Implementation Audit — Quality Gate P1+P2 (5 November 2026)

**Status:** ✅ Audit selesai — 4 bug diperbaiki (1 di antaranya BLOCKER), seluruh gate hijau.

### Temuan & perbaikan
1. **BLOCKER (FIXED):** SPA blank saat runtime — `<Routes>` tanpa `<BrowserRouter>`
   di `App.tsx`. Lolos dari `tsc` + 51 test pytest; tertangkap oleh E2E browser baru.
2. **FIXED:** email-validator v2 menolak TLD special-use (`.test`) → data uji kini
   `.dev`; UI auth kini menampilkan detail validasi (`extractDetailedErrorMessage`).
3. **FIXED:** race dedupe upload CV (check-then-insert) → partial unique index
   `uq_cvs_owner_sha_active` (migrasi 0005) + catch IntegrityError → 409; file yatim
   dihapus saat commit gagal.
4. **FIXED:** parity model↔migrasi — kolom JSONB `nullable=True` di migrasi vs
   NOT NULL di model (0002/0003 dikoreksi + server_default).
5. **FIXED:** nama file CV disanitasi (anti header injection Content-Disposition) + test.
6. **FIXED:** race condition pencarian kandidat (seq guard + debounce 350 ms);
   refresh-token gagal kini membersihkan state user (`setUnauthorizedHandler`).
7. **FIXED (konsistensi):** seluruh router/deps membaca settings dari
   `request.app.state.settings` (bukan get_settings() global); `build_engine`
   memilih connect_args per dialect (sqlite sah untuk E2E).

### Hasil gate akhir
- pytest: **51 passed** (termasuk 4 test audit keamanan baru: JWT kunci asing,
  alg=none, sanitasi filename, salt unik bcrypt).
- ruff check + format: bersih. Alembic: 0001→0005 valid (23 objek DDL).
- npm run build: hijau. **Playwright E2E: 2/2 passed via Chromium nyata**
  (alur HR & kandidat lengkap — lihat docs/adr/0003).

### Masih menunggu verifikasi lingkungan
- `docker compose up` + `alembic upgrade head` + pytest pada PostgreSQL 16 asli
  (Docker tidak terpasang lokal) — otomatis tervalidasi job CI `backend` saat repo
  di-push (service pgvector/pgvector:pg16 + DATABASE_URL_TEST).

## Persiapan Handover (5 November 2026)

**Status:** ✅ Dokumen handover selesai; tidak ada perubahan kode.

- `docs/07-project-handover.md` — peta konteks: overview, baseline keputusan (F1–F7, D1–D17), status implementasi aktual (berjalan/sebagian/belum), arsitektur, ringkasan audit, keputusan teknis, batasan lingkungan, peta dokumen.
- `docs/08-next-phase-roadmap.md` — rencana P3 terperinci: 9 modul AI Engine (tujuan, I/O, dependensi, komponen BE/FE, testing, acceptance, risiko) + prasyarat (kunci Groq, golden set, ekspor Figma), migrasi yang direncanakan (0006–0009), gelombang 10 minggu, Definition of Done. **Dependensi keras tercatat: Modul 9 (ranking HR) membutuhkan Applications (P4-inti) lebih dulu.**
- README: daftar dokumen diperbarui (07, 08).
- Tidak ada commit/push (menunggu persetujuan).

**Catatan untuk sesi baru:** baca docs/07 §D–§H lebih dulu; jalankan `pytest -q` dan `npx playwright test` untuk membuktikan baseline sebelum menyentuh kode; jangan mulai P3 sebelum checklist prasyarat docs/08 §0 disetujui.
