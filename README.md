# TalentSync AI

Platform rekrutmen cerdas: CV analysis, semantic job matching, dan CV optimization berbasis NLP.
Proyek akademik — Inovasi Sistem Informasi dan Teknologi (SI-I2), Kelompok 6, Universitas Airlangga.

**Status implementasi:** P0 (fondasi) ✅ · P1+P2 (identitas, profil, lowongan, CV) ✅ · Post-implementation audit ✅ (lihat log) · AI Engine & Ingestion = fase berikutnya.


**Platform rekrutmen cerdas** — analisis CV, matching explainable, rekomendasi,
skill gap, optimasi CV berbasis LLM (dengan validator anti-fabrikasi), alur
lamaran, dan ranking kandidat untuk HR.

**Status AI Engine (M1–M9): selesai & teruji** — 354 pytest · Playwright 3/3 ·
CI GitHub lulus. Semua metrik evaluasi nyata (bukan klaim pemasaran):
**[EVALUATION.md](EVALUATION.md)**.

Fitur utama:
- **M1** Parsing CV PDF → payload terstruktur + confidence + provenance
- **M2** Normalisasi skill bilingual (352 canonical / 610 alias) + autocomplete HR
- **M3–M4** Semantic matching explainable 40/30/20/10 (MiniLM + pgvector, kalibrasi v1.1)
- **M5** Skill gap + saran belajar statis
- **M6** Rekomendasi lowongan + alasan per item
- **M7** Diagnosis CV deterministik (8 aturan)
- **M8** Optimasi CV via LLM (Groq gpt-oss-120b) dengan grounding validator — CV asli immutable
- **Applications + M9** Lamaran → status → ranking kandidat HR + compare

## Struktur Monorepo

```
talentsync/
├── backend/           FastAPI + SQLAlchemy 2 + Alembic (modular monolith)
│   ├── app/
│   │   ├── core/      config, security (bcrypt/JWT), deps (RBAC), logging, errors
│   │   ├── db/        Base, engine, session
│   │   ├── models/    user, profile, company, job, cv (+cv_extractions)
│   │   ├── schemas/   Pydantic request/response
│   │   ├── services/  business logic (auth, profile, job, cv)
│   │   ├── ai/        extraction/ (boundary AI — fase berikutnya menambah matching/optimization)
│   │   └── api/v1/    routers: auth, profiles, jobs, hr_jobs, cvs, health
│   ├── alembic/       migrasi (0001 pgvector → 0004 cvs)
│   ├── scripts/       seed_demo_data.py
│   └── tests/         pytest (47 test)
├── frontend/          React 19 + Vite 7 + TypeScript strict + Tailwind v4
│   └── src/           lib/api (klien + refresh), lib/auth (sesi), pages (auth/candidate/hr)
├── docs/              blueprint, decision review, feasibility, ADR, log, database-and-api
└── docker-compose.yml db (PostgreSQL 16 + pgvector) + api + web
```

Dokumentasi utama: [01-blueprint](docs/01-technical-blueprint.md) ·
[02-decision-review](docs/02-decision-review.md) · [03-feasibility](docs/03-final-scope-and-feasibility.md) ·
[05-database-and-api](docs/05-database-and-api.md) · [07-handover](docs/07-project-handover.md) ·
[08-roadmap-P3](docs/08-next-phase-roadmap.md) · [ADR](docs/adr/) · [log implementasi](docs/04-implementation-log.md)

## Menjalankan dengan Docker (cara utama)

```bash
cp .env.example .env      # sesuaikan bila perlu
docker compose up --build
```

| Layanan | URL | Keterangan |
|---|---|---|
| web | http://localhost:3000 | Frontend (nginx, proxy `/api` ke api) |
| api | http://localhost:8000/docs | API + dokumentasi OpenAPI |
| db | 127.0.0.1:5432 | PostgreSQL 16 + pgvector (hanya localhost) |

Migrasi dijalankan otomatis oleh container `api` (`alembic upgrade head`, termasuk CREATE EXTENSION pgvector).

## Menjalankan tanpa Docker (development)

Diperlukan PostgreSQL 16 + pgvector yang bisa dijangkau (`DATABASE_URL` di `.env`).

**Backend:**

```bash
cd backend
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m ruff format .
.venv/Scripts/python -m pytest -q                       # lokal: SQLite otomatis
.venv/Scripts/python -m alembic upgrade head            # butuh PostgreSQL
.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxy /api → localhost:8000)
npm run build      # typecheck + production build
```

## Akun Demo (seed)

Password TIDAK di-hardcode — lewat env/argumen:

```bash
cd backend
SEED_DEMO_PASSWORD="DemoTalent2026" .venv/Scripts/python -m scripts.seed_demo_data
```

- HR: `dewi.lestari@demo.talentsync.id` (+ perusahaan & 3 lowongan contoh: active/draft/closed)
- Kandidat: `sarah.wijaya@demo.talentsync.id` (+ profil terisi)

## Testing

- Backend: `cd backend && .venv/Scripts/python -m pytest -q` — 51 test
  (lokal: SQLite otomatis; CI: PostgreSQL+pgvector asli via `DATABASE_URL_TEST`).
- Frontend: `npm run build` (typecheck strict + bundle).
- Lint: `ruff check .` + `ruff format --check .` di `backend/`.

## E2E Browser (Playwright)

Dua alur diuji lewat browser nyata (Chromium) melawan backend + frontend yang berjalan:

```bash
cd frontend
npx playwright test        # HR flow + Candidate flow (backend SQLite E2E otomatis disiapkan)
```

Kompatibilitas PostgreSQL tetap diverifikasi CI; jalur SQLite E2E hanya agar browser
test dapat berjalan tanpa Docker (lihat docs/adr/0003).

## CI

GitHub Actions (`.github/workflows/ci.yml`):

- **backend** — ruff → `alembic upgrade head` (PostgreSQL 16+pgvector asli) → pytest
- **frontend** — `npm ci`, typecheck + build (Node 22)
- **compose** — validasi `docker compose config`

## Konvensi

- API: prefix `/api/v1`, envelope error `{error: {code, message, details, request_id}}`.
- Secret hanya via environment (`SECRET_KEY`, `DATABASE_URL`, `SEED_DEMO_PASSWORD`) — tidak pernah di source.
- Keputusan teknis: [docs/adr/](docs/adr/) · progres: [docs/04-implementation-log.md](docs/04-implementation-log.md)
