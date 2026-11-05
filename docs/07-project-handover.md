# TalentSync AI — Project Handover

**Tanggal:** 5 November 2026 · **Fase terakhir:** P1+P2 + post-implementation audit (lolos)
**Tujuan dokumen:** memungkinkan sesi baru melanjutkan pengembangan tanpa kehilangan konteks teknis maupun keputusan. Dokumen ini ringkasan-peta; detail hidup di dokumen yang dirujuk.

---

## A. Project Overview

- **Apa:** Platform rekrutmen cerdas — analisis CV, semantic matching CV↔lowongan, skill gap analysis yang *explainable*, dan optimasi CV berbasis LLM dengan persetujuan manusia. Proyek akademik mata kuliah Inovasi Sistem Informasi dan Teknologi (SI-I2), Kelompok 6, Universitas Airlangga (2026).
- **Masalah yang diselesaikan:** (1) screening CV manual yang lambat & bias, (2) keyword matching ATS yang membuang kandidat relevan, (3) ketidaktahuan kandidat atas skill gap-nya. Solusi bukan pada kebaruan algoritme, melainkan **integrasi sistem yang terukur** (lihat §8.2 docs/01 & rencana evaluasi docs/03 §4).
- **Target pengguna:** HR/Talent Acquisition (pasang lowongan, ranking kandidat, gap analysis) dan pencari kerja (CV, rekomendasi, gap, optimasi CV).
- **Status:** Fondasi + core recruitment **selesai & teraudit**. AI Engine (matching/LLM) dan Data Ingestion = fase berikutnya (docs/08).

## B. Planning Baseline

| Dokumen | Isi | Status |
|---|---|---|
| `docs/01-technical-blueprint.md` | Arsitektur, skema DB, desain AI/NLP, pipeline, risiko | Baseline (tidak diubah) |
| `docs/02-decision-review.md` | 17 keputusan D1–D17 + prioritas Critical/Important/Optional | Disetujui |
| `docs/03-final-scope-and-feasibility.md` | Keputusan final F1–F7, feasibility 12 minggu, protokol kalibrasi & golden set, keamanan | Disetujui |
| `docs/adr/0001–0003` | Keputusan teknis implementasi (fondasi, P1+P2, E2E) | Aktif |

**Keputusan yang mengikat (ringkas):** modular monolith (bukan microservices) · PostgreSQL 16 + pgvector · embedding lokal `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, **configurable** per F2) · LLM **Groq** via adapter agnostik (F1, free-tier, tim memegang kunci) · CV **PDF-only** MVP (D2) · ingestion hanya sumber berizin (F3) · CV Builder & HR bulk upload **ditunda** bukan dibatalkan (F4) · deployment Docker Compose lokal (F6) · klaim marketing diganti metrik terukur (F7) · UI Bahasa Indonesia (D1) · skill berbobot 60% wajib / 40% tambahan · golden set & kalibrasi sesuai docs/03 §4.

## C. Implementation Status

### P0 — Foundation ✅ selesai & teraudit
Monorepo, FastAPI app factory + error envelope + request-ID + JSON logging, SQLAlchemy 2 + Alembic, Docker Compose (db pgvector + api + web nginx), CI, health/ready endpoints.

### P1 — Identity & Profiles ✅ selesai & teraudit
Registrasi/login/logout, JWT access 15m + refresh 7d (**rotasi one-time-use**, disimpan sebagai hash), RBAC `candidate`/`hr`, profil kandidat (JSONB terstruktur), perusahaan + keanggotaan (1 HR = 1 perusahaan), akun demo via seed script.

### P2 — Recruitment Core & CV ✅ selesai & teraudit
CRUD lowongan + lifecycle (draft→active⇄paused→closed→archived, soft delete), skills berbobot (flag required), katalog publik + search/filter/pagination, unggah CV PDF aman (magic bytes, ≤10MB, sha256 dedupe, soft delete + primary), **ekstraksi teks dasar PyMuPDF** (async), frontend 11 halaman terintegrasi dengan navigasi per-role.

### Sudah berjalan penuh (dibuktikan test + E2E browser)
Auth & sesi · profil kedua peran · lowongan end-to-end · pencarian publik · unggah/unduh/hapus CV · ekstraksi teks mentah · dashboard agregat.

### Sebagian / persiapan
- `app/ai/extraction/` — hanya teks mentah (`pymupdf-basic-v1`); **belum**: segmentasi section, taksonomi skill, entity terstruktur, UI review & koreksi ekstraksi (frame Figma 13).
- `jobs.skills` menyimpan flag required — **belum** ada kanonikalisasi/bobot hitung (bagian AI Engine).
- Halaman Figma yang **belum dibangun**: kompatibilitas kandidat (frame 16), rekomendasi (14/15), skill gap (10), review optimasi CV (17), ranking HR (8), detail kandidat HR (9).
- `cv_optimizations`, `match_results`, tabel embedding — **belum ada** (migrasi 0006+ di docs/08).

### Belum diimplementasikan (sesuai batas fase)
AI matching/rekomendasi/optimasi/ranking · applications workflow · ingestion pipeline · pembayaran · dark mode · Google OAuth (D7 tunda) · DOCX (D2 tunda).

## D. Current Architecture

### Struktur repositori
```
talentsync/
├── backend/          FastAPI (app: core, db, models, schemas, services, ai, api/v1)
│   ├── alembic/      0001 pgvector → 0005 cv-dedupe-guard
│   ├── scripts/      seed_demo_data.py · bootstrap_e2e.py
│   └── tests/        51 pytest (lokal SQLite / CI PostgreSQL asli)
├── frontend/         React 19 + Vite 7 + TS strict + Tailwind v4
│   ├── src/lib/      api/ (klien + refresh interceptor), auth.tsx, format.ts
│   ├── src/pages/    auth(2) · candidate(5) · hr(5)
│   └── e2e/          Playwright (2 alur, Chromium) + fixtures/sample-cv.pdf
├── docs/             01–05, 07, 08, adr/, design/frame-crops/
├── docker-compose.yml  db(pgvector/pg16) + api + web(nginx)
└── .github/workflows/ci.yml
```

### Backend
Modular monolith. Pola permintaan: **router** (HTTP) → **service** (bisnis, melempar `DomainError`) → **model** (SQLAlchemy 2.0 typed). Settings & engine terikat `app.state` per aplikasi; dependency `get_db` (session per request) dan `get_session_factory` (background task). Error konsisten `{error:{code,message,details,request_id}}`. Detail: docs/05 + ADR 0001–0003.

### Frontend
SPA + React Router v7. Sesi: access token di memori, refresh di localStorage dengan **rotasi**; interceptor 401→refresh→ulang; `setUnauthorizedHandler` membersihkan state saat sesi mati. Komponen UI bersama di `components/ui.tsx`; layout per peran + `RequireRole`.

### Database & API
**8 tabel** (users, refresh_tokens, candidate_profiles, companies, company_members, jobs, cvs, cv_extractions), **30 endpoint** `/api/v1` — skema, relasi, dan daftar endpoint lengkap: **docs/05-database-and-api.md** (sumber kebenaran).

### AI module (saat ini)
```
app/ai/extraction/basic_pdf.py   # P2: raw_text + page_count (pymupdf-basic-v1)
                                 # P3: tambah segmenter, taksonomi, payload terstruktur (docs/08)
```

### Infrastructure & CI
`docker compose up --build` = db+api+web lengkap (migrasi auto). CI: backend (ruff → **alembic upgrade head di PostgreSQL 16+pgvector asli** → pytest via `DATABASE_URL_TEST`) · frontend (npm build) · compose validate. Lokal tanpa Docker: pytest otomatis SQLite; E2E Playwright memakai SQLite khusus (`scripts/bootstrap_e2e.py`) — **bukan** klaim kompatibilitas PG.

## E. Audit Results (ringkasan — detail docs/04 entri "Post-Implementation Audit")

- **BLOCKER diperbaiki:** SPA blank — `<Routes>` tanpa `<BrowserRouter>`; lolos dari tsc+pytest, tertangkap E2E browser. Pelajaran: E2E browser wajib tiap fase frontend (ADR 0003).
- **Diperbaiki juga:** race dedupe CV (partial unique index 0005 + IntegrityError→409), race register/perusahaan (IntegrityError→409), sanitasi nama berkas (header injection), parity nullable JSONB (0002/0003), konsistensi settings `app.state`, `build_engine` per-dialect, race pencarian frontend (seq guard + debounce), pembersihan state saat refresh gagal.
- **Security lolos:** bcrypt+salt unik, JWT pin HS256 (tolak `alg:none`/kunci asing — teruji), rotasi refresh, RBAC 404-untuk-cross-owner, unggah aman, log bebas PII/DSN.
- **Remaining (WARNING, tidak menghalangi P3):** rate limiting, verifikasi email, sweep `refresh_tokens` kedaluwarsa, trigram index (skala besar), mobile layout.
- **PostgreSQL:** diverifikasi lewat CI (service pgvector/pg16 + alembic + pytest); lokal menunggu Docker.
- **Testing aktual:** pytest **51/51** · Playwright **2/2** (alur HR & kandidat via Chromium) · ruff bersih · build hijau.

## F. Technical Decisions

| Area | Keputusan | Referensi |
|---|---|---|
| Stack | FastAPI 0.162 · SQLAlchemy 2.1.8 · Pydantic 2.14 · psycopg 3.3.8 · Alembic 1.20 · React 19 · Vite 7.3.7 · Tailwind v4 · React Router 7 · axios | ADR 0001–0002 |
| Auth | bcrypt (8–72 byte), JWT HS256 access 15m / refresh 7d rotasi, hash SHA-256 di DB, refresh localStorage (kompromi MVP), access di memori | ADR 0002 §1–2 |
| Enum | String + CHECK constraint (bukan sa.Enum native) | ADR 0002 §4 |
| Profil | JSONB terstruktur tervalidasi Pydantic (matching-ready) | ADR 0002 §5 |
| Test DB | SQLite file utk pytest/E2E lokal; PostgreSQL asli di CI — **dibedakan eksplisit** | ADR 0002 §3, ADR 0003 |
| Ekstraksi | Deterministik-first; LLM tidak dipakai untuk parsing; human-in-the-loop review | ADR 0002 §7, blueprint §6 |
| Lisensi | PyMuPDF AGPL (OK akademik; fallback pdfplumber MIT) | blueprint §12.2 |
| Lingkungan dev | Windows 10 + Git Bash; Python venv 3.11 (container 3.12); Node 24; **Docker/Postgres tidak terpasang**; Groq kunci belum didaftarkan (milik tim) | docs/03 §6, F1 |

## G. Upcoming Development

Urutan fase berikutnya & rencana terperinci: **docs/08-next-phase-roadmap.md** (9 modul AI Engine dengan input/output, dependensi, komponen, testing, acceptance criteria, risiko). Ringkas:
1. **P3 Wave 1** — parsing lanjutan + taksonomi skill (+ UI review ekstraksi).
2. **P3 Wave 2** — semantic matching + explainable scoring + skill gap + rekomendasi (pgvector, kalibrasi golden set).
3. **P3 Wave 3** — CV diagnosis + LLM CV optimization (Groq, grounding validator) + HR candidate ranking.
4. **P4** — applications workflow + ingestion (RemoteOK/Remotive terverifikasi) + final integration.
Aturan: jangan ubah arsitektur/scope tanpa persetujuan; E2E browser wajib tiap fase frontend; migrasi via Alembic selalu.

## H. Known Constraints

- **Hardware/lingkungan:** tanpa Docker & PostgreSQL lokal → jalur test SQLite + CI PostgreSQL; proses anak Windows kadang tidak mati saat task dihentikan (bersihkan port 8000/5173 dengan `netstat`+`taskkill` sebelum jalankan server); Vite dev bind `localhost` (IPv6) — akses via `localhost`, bukan `127.0.0.1`.
- **Model lokal:** MiniLM ±0,5 GB, CPU ok; konteks pendek (±128 token) → chunking wajib (docs/08 M3).
- **LLM:** Groq free-tier (kuota/rate limit) → 1 panggilan per generasi + cache + status "coba lagi"; kunci belum didaftarkan.
- **Data ingestion:** hanya sumber berizin (RemoteOK wajib atribusi follow-link; Remotive volume kecil ±11/bulan terobservasi; Arbeitnow 300/hal); **nol scraping** Jobstreet/Glints/LinkedIn; lowongan lokal dari seed berlabel.
- **Risiko aktif:** lihat docs/03 §5.5 + docs/01 §10; tambahan audit: kuota Groq saat demo (generate sebelum demo), agreement rater golden set.
- **Git:** repositori ter-init (`main`), **nol commit**, tanpa remote — commit pertama menunggu persetujuan pemilik proyek.

## Peta Dokumen

01 blueprint (baseline) · 02 decision review · 03 feasibility & keputusan final · 04 implementation log (kronologis, termasuk audit) · 05 database & API (sumber kebenaran skema/endpoint) · **07 handover (dokumen ini)** · **08 roadmap P3** · adr/0001–0003 · design/frame-crops (hasil analisis Figma).
