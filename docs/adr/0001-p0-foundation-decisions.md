# ADR 0001 — Keputusan Fondasi P0

**Status:** Diterima (bagian dari persetujuan implementasi P0, 4 November 2026)
**Konteks:** Kick-off implementasi berdasarkan docs/01–03. Keputusan berikut adalah
detail teknis yang tidak membaca ulang arsitektur blueprint, hanya menetapkan parameternya.

---

## 1. Driver database: psycopg v3

- **Konteks:** SQLAlchemy 2.0+ mendukung psycopg 3 sebagai dialect `postgresql+psycopg`.
- **Keputusan:** gunakan `psycopg[binary]` (v3), bukan `psycopg2`.
- **Konsekuensi:** native binary wheel tersedia untuk Windows/Linux; syntax placeholder
  modern; URL memakai skema `postgresql+psycopg://`.

## 2. pgvector: image resmi + aktivasi via migrasi Alembic

- **Konteks:** extension vektor harus aktif sebelum kolom `vector` dibuat (P4).
- **Keputusan:** image Docker `pgvector/pgvector:pg16` (db + pgvector sekaligus);
  migrasi `0001` menjalankan `CREATE EXTENSION IF NOT EXISTS vector`; container `api`
  mengeksekusi `alembic upgrade head` sebelum uvicorn start.
- **Konsekuensi:** satu jalur setup untuk lokal, CI, dan deployment mana pun;
  `/health/ready` memverifikasi keberadaan extension sehingga kelalaian migrasi
  terdeteksi otomatis.

## 3. Versi Python: 3.12 di container, 3.11 di venv lokal

- **Konteks:** mesin pengembang memiliki Python 3.14 (default) dan 3.11. Wheel ekosistem
  paling stabil ada di ≤3.12.
- **Keputusan:** Dockerfile memakai `python:3.12-slim`; CI menguji di 3.12; venv lokal
  dibuat dengan 3.11; `requires-python = ">=3.11"`.
- **Konsekuensi:** hindari edge-case wheel Python 3.14; rentang dukungan tetap luas.

## 4. Tailwind CSS v4 via plugin Vite (tanpa tailwind.config)

- **Konteks:** blueprint menetapkan Tailwind; v4 memindahkan konfigurasi theme ke CSS.
- **Keputusan:** `@tailwindcss/vite` + `@theme` tokens di `src/styles/index.css`
  (nilai awal dari blueprint §2.6; finalisasi menunggu akses token Figma).
- **Konsekuensi:** tidak ada file config JS; token = satu file CSS; kelas kustom
  (`bg-primary-600`, dll.) dihasilkan otomatis dari variabel `--color-primary-*`.

## 5. Topologi Compose: db + api + web (nginx proxy)

- **Konteks:** P0 menjanjikan tiga layanan dapat berjalan dengan satu perintah.
- **Keputusan:** `db` (pgvector/pg16, hanya expose 127.0.0.1) + `api` (uvicorn, port 8000)
  + `web` (build SPA → nginx:alpine, port 3000, proxy `/api` → `api:8000`).
  Development tanpa Docker memakai Vite dev server dengan proxy yang setara.
- **Konsekuensi:** origin API konsisten (`/api/v1`) di dev maupun "production-like";
  healthcheck `pg_isready` menjadikan urutan start deterministik.

## 6. Error envelope + request ID sejak hari pertama

- **Keputusan:** semua error (404/405/422/500/503) mengikuti envelope
  `{ error: { code, message, details, request_id } }`; middleware `X-Request-ID`
  mengalir ke contextvar logging.
- **Konsekuensi:** frontend dapat mengandalkan satu bentuk error sejak P1; debugging
  lintas frontend–backend–log memakai request ID yang sama.

## 7. Settings & engine terikat ke instance aplikasi (`app.state`)

- **Konteks:** `get_settings()` ber-`lru_cache` (global) tidak bisa dioverride per-test;
  engine global juga membuat pengujian bergantung pada keberadaan Postgres lokal.
- **Keputusan:** `create_app(settings)` menaruh `settings` dan `engine` yang dibangun
  dari settings tersebut di `app.state`; endpoint membaca dari `request.app.state`.
  Instance global di `app.db.session` tetap ada untuk pemakaian CLI/scripts.
- **Konsekuensi:** test terisolasi penuh (tidak menyentuh DB lokal); pola dependency
  ini menjadi preseden untuk service layer di P1+.

## 8. Timeout koneksi DB eksplisit

- **Konteks:** saat verifikasi, koneksi ke port mati di Windows menggantung sangat lama
  (SYN di-drop tanpa RST).
- **Keputusan:** `connect_args={"connect_timeout": 5}` di semua engine.
- **Konsekuensi:** readiness check gagal cepat dan jelas; request tidak menggantung.

---

*Keputusan arsitektur tingkat tinggi (monolith, pgvector, MiniLM lokal, dst.) tetap
merujuk docs/01–03; ADR ini hanya mencatat parameterisasi P0.*
