# ADR 0003 — E2E Browser Testing & Verifikasi Render Runtime

**Status:** Diterima (hasil post-implementation audit P1+P2, 5 November 2026)

## 1. Latar belakang: bug yang lolos dari build & unit test

Audit E2E menemukan **BLOCKER**: `App.tsx` memakai `<Routes>` tanpa pembungkus
`<BrowserRouter>` → seluruh SPA blank saat runtime (`useRoutes() may be used only
in the context of a <Router>`). `tsc --noEmit` dan 51 test pytest tidak mampu
menangkapnya karena keduanya tidak menjalankan aplikasi di browser.

**Pelajaran (wajib dipertahankan):** setiap fase yang mengubah frontend WAJIB
meluluskan E2E browser (Playwright) sebelum dinyatakan selesai. Build + unit test
saja bukan bukti aplikasi berjalan.

## 2. Stack E2E

- **Playwright** (`@playwright/test`, Chromium) dengan dua `webServer` nyata:
  backend uvicorn + frontend Vite dev (proxy `/api`).
- Database E2E: **SQLite file** (`backend/e2e.db`) via `scripts/bootstrap_e2e.py`
  (dihapus + create_all setiap run). **Ini bukan klaim kompatibilitas PostgreSQL** —
  kompatibilitas PG 16 + pgvector tetap diverifikasi CI (`alembic upgrade head` +
  pytest dengan `DATABASE_URL_TEST` pada image `pgvector/pgvector:pg16`).
- `build_engine` dibuat memilih `connect_args` per dialect agar URL sqlite sah.

## 3. Temuan lain dari E2E (diperbaiki)

1. **email-validator v2 menolak domain special-use TLD** (`.test`, `.invalid`,
   `.localhost`) — email E2E `@talentsync.test` ditolak backend (422). Data uji
   kini memakai `.dev`. Konsekuensi produk: form harus menampilkan detail
   validasi, bukan hanya "Payload tidak valid." → `extractDetailedErrorMessage`
   dipakai di auth UI.
2. **Strict-mode locator**: nav "Profil"/"CV Saya" bentrok dengan CTA dashboard
   ("Lengkapi profil →", "Kelola CV →") → locator E2E memakai `exact: true`;
   pelajaran UX: teks CTA dibuat tidak prefiks-sama dengan nav.

## 4. Cakupan E2E saat ini

- **HR flow:** register → login otomatis → buat perusahaan → buat lowongan
  (weighted skills) → terbitkan → edit → buat #2 → tutup → verifikasi katalog
  publik via API anonim (closed tidak muncul).
- **Candidate flow:** register → dashboard → update profil (skills) → browse →
  detail lowongan aktif → upload CV PDF → ekstraksi selesai (status Siap) +
  CV utama.

Belum tercakup: refresh-token rotasi di UI, sesi kedaluwarsa, responsivitas
mobile — kandidat penambahan saat fase berikutnya menyentuh area tersebut.
