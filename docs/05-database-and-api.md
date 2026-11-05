# Database & API — Status Setelah P1+P2

> Dokumen teknis hidup. Perubahan schema WAJIB lewat migrasi Alembic — dilarang
> mengubah database secara manual di luar migrasi.

## 1. Skema Database (migrasi 0001–0005) — **8 tabel**

```
users (1) ──< refresh_tokens            (CASCADE)
users (1) ──1 candidate_profiles        (CASCADE)   # auto-create saat registrasi kandidat
users (1) ──< company_members           (CASCADE)   # MVP: unique(user_id) → 1 HR = 1 perusahaan
companies (1) ──< company_members       (CASCADE)
companies (1) ──< jobs                              # posted_by_user_id → users
users (1) ──< cvs                       (CASCADE)   # parent_cv_id → cvs (rantai versi, fase AI)
cvs (1) ──1 cv_extractions              (CASCADE)
```

### users
| Kolom | Tipe | Catatan |
|---|---|---|
| id | UUID PK | |
| email | String(255) UNIQUE INDEX | selalu lowercase (dinormalisasi service) |
| password_hash | String(255) | bcrypt (`$2b$…`), plaintext tidak pernah disimpan |
| full_name | String(255) | |
| role | String(20) | CHECK `('candidate','hr')` |
| is_active | Boolean | default true |
| created_at / updated_at | TIMESTAMPTZ | server_default now() |

### refresh_tokens
`id` UUID PK · `user_id` FK CASCADE (index) · `token_hash` String(64) UNIQUE (SHA-256) ·
`expires_at` TIMESTAMPTZ · `revoked_at` nullable · `created_at`.
Rotasi one-time-use: `/auth/refresh` mencabut token lama; `/auth/logout` mencabut token.

### candidate_profiles
`user_id` PK/FK CASCADE · `phone` · `location` · `headline` · `summary` ·
`skills` JSONB (list string, dedupe) · `education` JSONB · `experience` JSONB ·
`certifications` JSONB · `links` JSONB · `updated_at`.
Struktur item tervalidasi Pydantic (schemas/profile.py) → langsung reusable matching engine.

### companies / company_members
companies: `id` · `name` · `description` · `industry` · `location` · `website` ·
`contact_email` · `created_by_user_id` FK · timestamps.
company_members: `id` · `company_id` FK CASCADE (index) · `user_id` FK CASCADE
**UNIQUE (MVP 1 HR = 1 perusahaan)** · `role_in_company` default `owner` · `created_at`.

### jobs
Kolom inti: `id` · `company_id` FK (index) · `posted_by_user_id` FK ·
`source_type` default `'hr'` (forward-compat ingestion) · `title` (index) ·
`description` · `responsibilities` · `requirements` · `skills` JSONB
`[{name, required}]` · `category` · `employment_type` · `work_mode` · `seniority` ·
`location_text` (index) · `salary_min/max` NUMERIC(14,2) · `salary_currency` default IDR ·
`status` · `closed_reason` · `posted_at` (index) · `closing_at` · `last_seen_at` ·
`deleted_at` (soft delete) · timestamps.

CHECK: status, employment_type, work_mode, `salary_min <= salary_max`.
Index parsial (PostgreSQL): `(status, closing_at) WHERE status='active' AND deleted_at IS NULL`.

**Lifecycle** (manual pada fase ini; sweep `expired` otomatis menyusul di fase ingestion):
```
draft ──publish──► active ⇄ paused      active|paused ──close──► closed (reason=manual)
draft/active/paused ──DELETE──► archived (soft delete, deleted_at terisi)
```
Kandidat hanya melihat `status='active'` dan `deleted_at IS NULL`.

### cvs / cv_extractions

Guard dedupe: partial unique index `uq_cvs_owner_sha_active (candidate_user_id, content_sha256) WHERE deleted_at IS NULL` (migrasi 0005) — dua upload identik bersamaan ditolak database, bukan hanya service.
cvs: `id` · `candidate_user_id` FK CASCADE (index) · `status`
CHECK `('pending','processing','ready','failed')` · `file_path` (uuid acak, di luar root
statis) · `original_filename` · `mime_type` · `file_size_bytes` · `content_sha256` (index,
dedupe per pemilik) · `is_primary` · `version` · `parent_cv_id` FK self (use_alter,
rantai versi optimasi fase AI) · `deleted_at` (soft delete) · timestamps.
cv_extractions: `id` · `cv_id` FK CASCADE UNIQUE · `status` (pending/done/failed) ·
`raw_text` · `page_count` · `parser_version` (`pymupdf-basic-v1`) · `error_message` · timestamps.

## 2. Daftar Endpoint API v1 — **30 endpoint** (termasuk 2 health)

### Auth
| Method | Path | Auth | Fungsi |
|---|---|---|---|
| POST | /auth/register | — | Registrasi (role `candidate`/`hr`), token langsung; profil kandidat auto-create |
| POST | /auth/login | — | Login email+password → token pair |
| POST | /auth/refresh | — | Rotasi refresh token (one-time use) |
| POST | /auth/logout | — | Cabut refresh token |
| GET | /auth/me | bearer | Data pengguna saat ini |
| GET | /auth/me/summary | bearer | Ringkasan per peran (profil/perusahaan) untuk dashboard |

### Profil
| Method | Path | Auth | Fungsi |
|---|---|---|---|
| GET | /me/candidate-profile | candidate | Profil kandidat (auto-create bila kosong) |
| PUT | /me/candidate-profile | candidate | Perbarui profil + full_name akun |
| GET | /me/company | hr | Perusahaan terhubung (404 bila belum) |
| POST | /me/company | hr | Buat perusahaan + keanggotaan owner (409 bila sudah ada) |
| PUT | /me/company | hr | Perbarui perusahaan |

### Lowongan (publik/kandidat)
| Method | Path | Auth | Fungsi |
|---|---|---|---|
| GET | /jobs | — | Katalog aktif: `q` (judul), `location`, `employment_type`, `work_mode`, `page`, `size` |
| GET | /jobs/{id} | — | Detail lowongan aktif (draft/closed → 404) |

### Lowongan (HR)
| Method | Path | Auth | Fungsi |
|---|---|---|---|
| GET | /hr/jobs/stats | hr | Agregat jumlah per status (milik perusahaan sendiri) |
| GET | /hr/jobs | hr | Daftar lowongan perusahaan, filter `status`, pagination |
| POST | /hr/jobs | hr | Buat lowongan (draft) |
| GET | /hr/jobs/{id} | hr | Detail (404 bila milik perusahaan lain) |
| PUT | /hr/jobs/{id} | hr | Edit (hanya draft/active/paused) |
| POST | /hr/jobs/{id}/publish | hr | draft → active (validasi closing_at masa depan) |
| POST | /hr/jobs/{id}/pause | hr | active → paused |
| POST | /hr/jobs/{id}/resume | hr | paused → active |
| POST | /hr/jobs/{id}/close | hr | active/paused → closed |
| DELETE | /hr/jobs/{id} | hr | Soft delete → archived |

### CV (kandidat)
| Method | Path | Auth | Fungsi |
|---|---|---|---|
| POST | /cvs | candidate | Upload PDF (≤10 MB, ≤20 hal., magic bytes, dedupe sha256) → ekstraksi async |
| GET | /cvs | candidate | Daftar CV aktif milik sendiri |
| PATCH | /cvs/{id}/primary | candidate | Jadikan CV utama |
| GET | /cvs/{id}/file | candidate | Unduh file (pemilik saja; non-pemilik → 404) |
| DELETE | /cvs/{id} | candidate | Soft delete; primary dipromosikan otomatis |

### Health

| Method | Path | Auth | Fungsi |
|---|---|---|---|
| GET | /api/v1/health | — | Liveness (tanpa dependensi) |
| GET | /api/v1/health/ready | — | Readiness: database + ekstensi pgvector aktif |

Konvensi: semua error memakai envelope `{error: {code, message, details, request_id}}`;
list endpoint memakai `{items, total, page, size, pages}`.

## 3. Halaman Frontend

| Route | Peran | Isi |
|---|---|---|
| /login · /register | publik | Login (toggle portal) & registrasi (pilih peran + strength meter) |
| /app | candidate | Dashboard: kelengkapan profil, status CV utama, CTA |
| /app/profile | candidate | Form profil lengkap (data diri, skills, pendidikan, pengalaman, sertifikasi, tautan) |
| /app/jobs · /app/jobs/:id | candidate | Pencarian + filter + pagination; detail + skill wajib/tambahan |
| /app/cv | candidate | Upload PDF, daftar dokumen, set primary, unduh, hapus |
| /hr | hr | Dashboard: statistik lowongan + daftar terbaru |
| /hr/company | hr | Buat/perbarui profil perusahaan |
| /hr/jobs · /hr/jobs/new · /hr/jobs/:id · /hr/jobs/:id/edit | hr | Tabel lowongan + filter; form create/edit (skills 60/40); detail + aksi lifecycle |

Navigasi adaptif per-role (top-nav kandidat / sidebar HR) + route guard berbasis JWT.
