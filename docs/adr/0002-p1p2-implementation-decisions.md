# ADR 0002 — Keputusan Implementasi P1+P2

**Status:** Diterima (implementasi 4–5 November 2026, dalam scope persetujuan P1+P2)
**Konteks:** Fase identitas, profil, lowongan, dan CV. Keputusan berikut detail teknis
yang muncul saat implementasi dan tidak mengubah arsitektur blueprint.

---

## 1. Autentikasi: bcrypt + JWT HS256, refresh token berbasis server-side store

- Password: bcrypt (salt per-hash); panjang password dibatasi 8–72 karakter (batas
  bawaan bcrypt).
- Access token: JWT HS256, TTL 15 menit, klaim `sub/role/type/jti`.
- Refresh token: TTL 7 hari, **disimpan sebagai SHA-256 hash** di tabel
  `refresh_tokens` (token asli tidak pernah disimpan). **Rotasi one-time-use**:
  setiap `/auth/refresh` mencabut token lama dan menerbitkan pasangan baru.
  `/auth/logout` mencabut refresh token yang dikirim.
- `SECRET_KEY` wajib di prod (startup gagal bila kosong); dev/test memakai kunci
  sementara berlabel jelas.

## 2. Penyimpanan token di frontend

- **Access token di memori** (variabel modul) — tidak pernah masalah localStorage.
- **Refresh token di localStorage** — kompromi MVP: rentan XSS teoretis, dimitigasi
  rotasi one-time-use + TTL 7 hari + pencabutan saat logout. Jalur penguatan
  (httpOnly cookie + CSRF) tercatat sebagai post-MVP bila deployment memungkinkan
  same-site API.

## 3. Strategi test database: SQLite (lokal) / PostgreSQL+pgvector (CI)

- Mesin pengembangan tidak memiliki Docker/PostgreSQL → pytest lokal berjalan di
  **SQLite file sementara**; kolom `JSONB` memakai
  `JSONB().with_variant(JSON(), "sqlite")`.
- CI (GitHub Actions) menjalankan service **pgvector/pgvector:pg16** sungguhan:
  `alembic upgrade head` (validasi migrasi + CREATE EXTENSION) lalu pytest dengan
  `DATABASE_URL_TEST` → seluruh suite diuji terhadap PostgreSQL asli.
- Migrasi juga divalidasi lokal via `alembic upgrade head --sql` (offline SQL).
- In-memory + StaticPool **dipilih bukan**: satu koneksi dibagi antara session
  request dan background task menghasilkan race (dibuktikan saat development).

## 4. Enum via String + CHECK constraint (bukan sa.Enum native)

- `role`, `status` (jobs & cvs), `employment_type`, `work_mode` disimpan String(20)
  + `CheckConstraint`; validasi utama di Pydantic `Literal`.
- Alasan: migrasi lintas dialect ringkas, penambahan nilai tidak memerlukan
  `ALTER TYPE` khusus PostgreSQL.

## 5. Profil kandidat: JSONB terstruktur (bukan tabel relasional penuh)

- `skills` (list of string), `education/experience/certifications` (list of objek
  dengan kunci tetap, tervalidasi Pydantic), `links` (dict).
- Alasan: MVP butuh fleksibilitas form; struktur sudah "matching-ready"
  (fase AI membaca JSON yang sama). Normalisasi ke tabel relasional dapat
  dilakukan belakangan tanpa perubahan API.

## 6. Skills lowongan: flag `required` sekarang, bobot 60/40 di mesin matching

- `jobs.skills = [{name, required}]`; dedupe case-insensitive di validator;
  minimal 1 skill wajib. Pembobotan 60% wajib / 40% nilai tambah (Figma "Buat
  Lowongan Baru") diterapkan oleh matching engine (fase AI) — struktur data sudah
  memisahkan kedua kelompok.

## 7. Ekstraksi CV dasar sebagai boundary modul AI

- `app/ai/extraction/basic_pdf.py` (PyMuPDF, AGPL — dicatat di blueprint §12.2)
  mengekstrak `page_count` + `raw_text`; ditolak: PDF ber-password, 0 halaman,
  tanpa teks (hasil pindai), >20 halaman.
- Berjalan sebagai BackgroundTask dengan **session factory terpisah** (dependency
  `get_session_factory`) — session request sudah tertutup saat task berjalan.
- Kegagalan ekstraksi **tidak pernah diam-diam**: `cvs.status='failed'` +
  `cv_extractions.error_message`. Respons upload adalah `201 + status pending`
  (klien mem-poll daftar CV).

## 8. Keamanan objek: 404 bukan 403

- Akses lowongan/CV milik pihak lain mengembalikan **404** (bukan 403) agar
  keberadaan resource tidak terbocor; konsisten di seluruh endpoint (blueprint §5.4).

## 9. Frontend: React Router v7, tanpa state library

- Router + Context (`AuthProvider`) cukup untuk skala ini; server-state via axios
  + interceptor refresh. React Query dipertimbangkan saat halaman makin banyak
  (fase AI).

## 10. PyJWT (bukan python-jose)

- python-jose stagnan dan memiliki riwayat CVE algoritma-confusion; PyJWT aktif
  dikembangkan. Algoritma di-pin eksplisit `HS256` (anti `alg: none`).
