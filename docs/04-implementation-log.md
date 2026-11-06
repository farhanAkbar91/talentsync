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

## P3.0 — Infrastruktur AI Engine (6 November 2026)

**Status:** ✅ Selesai dan terverifikasi penuh — gate lokal hijau + migrasi
0006–0009 diterapkan ke Supabase + RLS aktif + integrasi end-to-end lulus.

### Keputusan pemilik proyek (pra-P3.0)
1. Supabase Project A (`postgres.llvyurqazuhhrevpfikm`, ap-southeast-1) = database utama.
2. Rotasi password DB sebelum kredensial dipakai lanjut (**ternyata tidak bisa via
   SQL** — role postgres tanpa hak ALTER USER; wajib via Dashboard Supabase).
3. LLM: `openai/gpt-oss-120b` utama + `openai/gpt-oss-20b` fallback (benchmark live).
4. Model via environment variables (fleksibel per F2).
5. Benchmark embedding e5-small vs MiniLM sebelum model final dibekukan.
6. SQLite utk unit test; Supabase utk integration test **non-destruktif**.
7. Perbaikan konfigurasi + security hardening disetujui.

### Temuan audit lingkungan (teratasi / berjalan)
- Duplikat `DATABASE_URL` (baris kedua = project mati) + `backend/.env` tidak ada →
  strategi `.env` dua peran baru (ADR 0005 §2.3).
- Crash pydantic-settings pada `cors_origins` comma-format → `NoDecode` + validator.
- Crash Alembic pada password berisi `%` → engine langsung dari Settings (env.py baru).
- `GROQ_API_KEY` sebelumnya tidak ada di `.env` → kini ada & tervalidasi (200 /models).

### Benchmark model (live, kunci akun)
- LLM: gpt-oss-120b terbaik (json_schema penuh, 0 fabrikasi, 2,3 dtk);
  qwen3.8-27b lemah (skills=0, 429); allam-2-7b **fabrikasi** → diskualifikasi;
  Llama tidak tersedia di akun. Detail: `backend/scripts/benchmark_results.json` + ADR 0006.
- Embedding: e5-small vs MiniLM pada golden set sintetis 84 pasangan —
  **MiniLM menang**: gap separasi 0,306 vs 0,062 (margin ±5×), acc 1,00 keduanya,
  latensi 55–58 vs 60–98 ms/teks → `EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2`
  dibekukan (ADR 0006 §3); e5 boleh diuji ulang saat kalibrasi dgn CV volunteer.

### Artefak P3.0
- Kode: `config.py` (field P3 + NoDecode + env_file anchor) · `session.py`
  (timeout 10) · `alembic/env.py` · **model `app/models/ai.py`** (4 tabel) +
  kolom `payload/confirmed_*` di `cv_extractions` · **migrasi 0006–0009** ·
  `pyproject` (+pgvector, +reportlab, extra `ai`: sentence-transformers) ·
  compose (`env_file` backend/.env, required false).
- Evaluasi: `eval/golden/` (12 CV + 30 job + 84 pasangan berlabel rubrik 0–3,
  sintetis, tanpa PII) · skrip `generate_golden_synthetic.py`,
  `benchmark_embedding_models.py`, `benchmark_groq_models.py`,
  `verify_supabase_integration.py` (non-destruktif, self-cleaning).
- Dokumen: ADR 0004 (vector dialect-aware) · ADR 0005 (Supabase & hardening) ·
  ADR 0006 (model AI) · docs/05 diperbarui (skema P3.0).
- Dependensi terpasang: torch 2.15.0+cpu, sentence-transformers 6.2.0,
  pgvector, reportlab.

### Gate lokal (Tahap 4 — bagian yang tidak butuh DB)
pytest **51/51** ✅ · ruff check+format bersih (69 file) ✅ · frontend tsc+build
hijau ✅ · secret scan file baru bersih, kedua `.env` ter-gitignore ✅.

### Finalisasi database (setelah rotasi password oleh pemilik proyek)
- `backend/.env` final dibuat pemilik proyek (port 5432 session pooler, password
  baru tanpa karakter khusus, semua var P3) — verifikasi Settings & koneksi ✅.
- **Migrasi 0006→0009 diterapkan bertahap** ke Supabase (verifikasi tiap langkah;
  head = `0009`, 13 tabel) ✅.
- **RLS ENABLE pada 13 tabel** (12 aplikasi + alembic_version) tanpa policy —
  PostgREST anon ditolak, akses owner backend tetap ✅ (ADR 0005 §2.5).
- **Integrasi end-to-end lulus** (`scripts/verify_supabase_integration.py`,
  non-destruktif): health/ready 200 · alur HR register→perusahaan→job→publish ·
  alur kandidat register→katalog→upload CV→ekstraksi ready · cleanup bersih
  (semua baris uji terhapus, termasuk residu percobaan awal) ✅.
- Perbaikan skrip selama verifikasi: `GET /cvs` mengembalikan list langsung (bukan
  envelope pagination); FK `companies.created_by_user_id` & `jobs.company_id`
  tidak CASCADE (desain soft-delete) → urutan cleanup jobs→companies→users.

### Catatan penutup P3.0
Tidak ada commit/push — menunggu persetujuan pemilik proyek. P3.0 selesai;
langkah berikutnya: M1 — Advanced CV Parsing (docs/08 Wave 1).

## WAVE 1 — M1 Advanced CV Parsing (6 November 2026)

**Status:** ✅ Selesai & lolos seluruh gate (lokal + E2E browser) — menunggu
persetujuan Wave 2.

### WAVE 0 — Finalisasi Git P3.0
- Audit working tree (26 perubahan), scan secret (satu false-positive pada
  template placeholder `.env.example` — diverifikasi aman), gate penuh hijau,
  lalu **commit `5bac361`** `feat(ai): finalize AI engine infrastructure and
  evaluation foundation` — 70 file, 4.133 insertions; tanpa push/amend;
  `.env` terverifikasi tidak ter-track.
- Catatan: `docs/06-p1-p2-audit-report.md` yang dirujuk master prompt tidak ada
  sebagai file terpisah — audit P1+P2 terdokumentasi di docs/04 (tanpa dampak).

### Implementasi M1 (pipeline deterministik, tanpa LLM — ADR 0002 §7)
- `app/ai/extraction/`: `preprocess.py` (dehyphenate, normalisasi bullet,
  buang nomor halaman) → `segmenter.py` (10 kunci kanonik, alias heading
  ID/EN, pre-heading = zona kontak) → `entities.py` (kontak regex + nama
  "Nama — Headline", rentang tanggal ID/EN + `sekarang/present` → `YYYY-MM`,
  pendidikan S1/S2/BSc…+IPK, skills dedupe, sertifikasi, bahasa, proyek,
  penghargaan) → `payload_schema.py` (Pydantic, kontrak frozen) → `parser.py`
  (`build_payload`, per-section guarded — total function).
- Wire: `run_extraction` kini membangun payload (`pymupdf-heuristic-v1`,
  kegagalan payload tidak menggagalkan ekstraksi teks); service
  `extraction_service` (GET ownership-404, confirm 409/400, re-confirm
  allowed, `parser_version` dipaksa); endpoint `GET /cvs/{id}/extraction` +
  `PUT /cvs/{id}/extraction/confirm`; `CVOut` + `extraction_status/
  extraction_confirmed`; model property `is_confirmed`. **Gate matching:
  hanya CV terkonfirmasi** (dipakai M3+).
- Bug nyata tertangkap agent: regex email naive O(n²) pada baris panjang
  (250k char = 132 dtk) → linear scan + regex bounded, patologis < 0,7 dtk.

### Evaluasi (keputusan #target F1 ≥ 0,80)
- **Macro F1 = 1,000 (LULUS)** — nama/email/telepon 1,000 · skills
  set-F1 1,000 · recall pengalaman/pendidikan/sertifikasi 1,000 (12 CV).
- Temuan proses: golden set generator awalnya TIDAK merender telepon ke teks
  → parser jujur melaporkan null (provenance honesty bekerja); generator
  diperbaiki, golden set diregenerasi, evaluasi diulang. Normalisasi telepon
  evaluator diperbaiki untuk format 08xx (CV nyata).
- **Keterbatasan jujur (terdokumentasi di laporan):** korpus sintetis
  in-domain — angka belum merepresentasikan CV nyata; evaluasi volunteer CV
  menyusul (docs/03 §4.4). Laporan: `eval/reports/extraction_evaluation.json`.

### Frontend M1
- Halaman **Review Ekstraksi** `/app/cv/:id/review` (kartu per bagian, badge
  keyakinan hijau/amber/merah, kutipan `evidence`, outline merah untuk
  `needs_review`, edit per field, "Simpan & Konfirmasi" → PUT payload
  tersunting) · chip "Terkonfirmasi"/"Perlu review" di daftar CV · link
  "Review ekstraksi" · polling status diperbaiki (tetap jalan selama
  pending/processing).
- **Playwright E2E: 2/2 lulus** (alur HR utuh + kandidat
  register→…→upload→review→konfirmasi→chip hijau) via backend sungguhan.

### Gate akhir Wave 1
pytest **103/103** (51 lama + 52 baru) · ruff check+format bersih (78 file) ·
frontend tsc+build hijau · E2E 2/2 · evaluasi F1 1,000 (target 0,80) ·
tidak ada commit untuk Wave 1 (menunggu persetujuan setelah laporan).

## WAVE 2 — M2 Skill Extraction & Normalization (6 November 2026)

**Status:** ✅ Selesai & lolos seluruh gate — menunggu persetujuan Wave 3.
(Wave 1 belum di-commit sesuai instruksi pemilik proyek; Wave 2 dibangun di
atas perubahan Wave 1 tanpa amend/reset.)

### Implementasi
- **Taksonomi** (agent B1a): `app/ai/extraction/taxonomy/skills_v1.json` → DB
  via seed idempoten. **352 skill kanonik, 610 alias, 21 kategori (v1.1.0,
  termasuk Languages yang saya tambahkan setelah evaluasi menemukan gap)**.
  Validasi anti-false-positive: javascript∉java, react-native∉react,
  postgresql∉sql, deep-learning∉machine-learning, "pm" tak dipakai, alias
  unik global. Model `canonical_skills/skill_aliases/candidate_skills/
  job_skills` + **migrasi 0010** (diterapkan ke Supabase + RLS 17/17 tabel +
  seed produksi).
- **Normalizer** dictionary-first (ADR 0007): exact → alias → fuzzy
  terkendali (difflib ≥0,92, unik-terbaik) → needs_review + ≤3 saran —
  tidak pernah memaksa pemetaan; inferred ditandai & diberi catatan UI;
  provenance raw_name + evidence + source_section di semua item.
- **Integrasi** (agent B1b): confirm M1 → persist `candidate_skills`
  (suggested, idempoten, accepted dipelihara); job create/update → replace
  `job_skills` (JSONB tak diubah); API: taxonomy/autocomplete/detail,
  GET+apply skills per CV, GET/DELETE /me/candidate-skills;
  `GET /hr/jobs/{id}` + `skills_normalized`.
- **Frontend** (agent F): halaman "Skills terstandardisasi" (checkbox,
  badge Eksplisit/Inferred, confidence, saran ambigu, Terapkan ke Profil),
  section profil + hapus, **HR SkillPicker autocomplete** (debounce, keyboard,
  chip Wajib/Disarankan, fallback teks bebas "tidak dikenal" — payload form
  tak berubah), kartu "Pemetaan skill (kamus standar)" di JobDetail.

### Evaluasi (target: F1 ≥0,85 · canon ≥0,90 · false-map 0 · duplikat 0)
- **Extraction F1 macro: 0,980** (recall 1,0 semua CV; presisi 0,83–1,0 —
  inferred jujur menambah konteks "Data Analyst" yang tak tercantum GT)
- **Canonicalization accuracy: 0,923** · **false-map: 0** · **merges: LULUS**
  · **idempotensi: LULUS** · **duplikat: 0,000** — semua target terpenuhi.
- Perbaikan selama evaluasi: gap taksonomi bahasa (tambah 9 skill bahasa +
  kategori Languages, v1.1.0), duplikat alias "bahasa mandarin" (typo saya,
  tertangkap test B1a), ekspektasi slug di skrip evaluasi.
- Laporan: `eval/reports/skills_evaluation.json`. Keterbatasan jujur: korpus
  sintetis in-domain; evaluasi CV volunteer menyusul.

### Temuan & perbaikan E2E
1. E2E SQLite (`e2e.db`) tidak di-seed taksonomi → autocomplete kosong →
   `bootstrap_e2e.py` kini men-seed taksonomi (352 skill).
2. Fixture `sample-cv.pdf` hanya 3 baris tanpa bagian skills → parser jujur
   melaporkan nol skill → fixture diperkaya jadi CV realistis lengkap
   (RIWAYAT, PENDIDIKAN, KEAHLIAN, SERTIFIKASI, BAHASA).

### Gate akhir Wave 2
pytest **196/196** (103 + 93 baru: 50 taksonomi + 43 integrasi) · ruff bersih
(90 file) · frontend build hijau · **Playwright 2/2** (HR: autocomplete→
pemetaan skill; kandidat: upload→review→konfirmasi→skills→terapkan→profil) ·
Supabase: migrasi 0010 + RLS 17/17 + integrasi LULUS · evaluasi 5/5 target ·
Wave 2 belum di-commit (menunggu persetujuan).

## WAVE 3 — M3 Embedding + M4 Compatibility + M5 Skill Gap (6–7 November 2026)

**Status:** ✅ Selesai & lolos seluruh gate + security review — menunggu
persetujuan Wave 4. **Multi-agent orchestration aktif** (kebijakan pemilik
proyek): Lead orchestrator + 4 agent spesialis (AI/ML, FE, QA, Security) +
review independen + amandemen kontrak terkoordinasi.

### Implementasi (paralel per ownership)
- **T1 Embedding (AI agent)**: `ai/matching/{embedder,similarity}.py` —
  singleton lazy MiniLM (L2-norm, chunk ≤480 char mean-pool, batch),
  `embedding_service.embed_cv/embed_job` (hanya CV terkonfirmasi — hard gate;
  upsert per model, multi-versi dipertihara; SAVEPOINT agar gagal embed tak
  merusak transaksi), hook confirm/publish/update, `scripts/reembed_embeddings.py`
  (guard anti-Supabase tanpa --yes).
- **T2+T3 Scoring (BE agent)**: `scorer.py` (F_skill 0.6/0.4 class-neutral +
  exact/alias/related 1.0/0.5, F_exp regex→seniority fallback + title cosine,
  F_edu ordinal 100/90/55/25, severity kritis/menengah/minor frozen),
  `calibration.py`+JSON (piecewise-linear clamp), `explainer.py` narasi ID
  deterministik, `gap.py`+`learning_resources.json` (12 kategori × 3 sumber),
  `match_service` (gating MATCH_UNAVAILABLE, persist+invalidasi), endpoint
  compatibility+gap.
- **T4 Frontend (FE agent)**: halaman Kompatibilitas `/app/jobs/:id/
  compatibility` (ScoreRing 4-band, FactorBar + bobot, chips matched/missing,
  top experiences, panel "Mengapa skor ini?" — kaption "bukan LLM", GapMatrix
  shared component + saran belajar), tombol di JobDetail, E2E extension.
- **T5 QA (QA agent)**: `evaluate_matching.py` (nDCG@10/Spearman/P@5 + grid
  search Tahap 2 report-only) + `benchmark_matching.py` (1 CV vs 500 job).

### Evaluasi (real MiniLM, korpus sintetis 84 pasangan berlabel)
- **nDCG@10: 0,9425** (target ≥ 0,75) · **Spearman: 0,8663** (target ≥ 0,60)
- **P@5: 0,600 = plafon dataset** (3 relevan dari 7 per CV) — terdokumentasi
- **Benchmark: 0,81 dtk / 500 pasangan (1,62 ms/pair)** — target < 5 dtk ✅
- **Grid search Tahap 2**: bobot prior [40,30,20,10] terbukti optimal pada set
  validasi (kandidat terbaik [40,25,10,25] tanpa gain) → bobot TIDAK diubah.
- **Anchor kalibrasi dibekukan v1.1**: 0,4509→30, 0,7327→85 (dari distribusi
  cosine golden set; QA usulkan, Lead yang membekukan).

### Temuan & keputusan integrasi (Lead)
1. **Amandemen kontrak cache judul**: benchmark awal 9,34 dtk (95% = re-embed
   judul per pasangan) → `cv_title_vecs` dihitung sekali per CV → 0,81 dtk
   (46×), hasil identik (teruji).
2. **Security review (agent read-only)**: RBAC/ownership/RLS/injection PASS;
   **HIGH ReDoS** regex years_req pada teks HR 20k+20k char (34,6 dtk) →
   DIPERBAIKI (kuantifier bounded 1–4 + scan cap 4k → 3,1 ms); **MEDIUM** payload
   tanpa batas → MAX_DOCUMENT_CHARS 20k di kedua build_text; LOW terdokumentasi
   (negative cache, rate limiting → catatan M6+).
3. **model_version 88-char vs kolom String(60)** (temuan agent) → kode map
   `emb:minilm-l12-v2` (45 char; nama penuh tetap di kolom embedding).
4. **E2E**: E2E SQLite kini seed taksonomi; cold-start torch ±30 dtk dipindah
   dari request-pertama ke **pre-warm startup** (thread di produksi; SINKRON
   di E2E via EMBEDDING_PREWARM_SYNC); `get_embedder` + double-checked locking
   (race pre-warm vs request); fixture sample-cv diperkaya; E2E menambah skill
   Tableau (yang tak dimiliki kandidat) agar gap+saran belajar teruji nyata.

### Gate akhir Wave 3
pytest **249/249** (196 + 53: 20 embedding + 33 matching) · ruff bersih
(104 file) · frontend build hijau · **Playwright 2/2** (rantai penuh:
upload→review→konfirmasi→skills→terapkan→kompatibilitas→gap+saran belajar) ·
benchmark 0,81 dtk ✅ · security review: HIGH/MEDIUM selesai dipulihkan ·
Wave 3 belum di-commit (menunggu persetujuan).
