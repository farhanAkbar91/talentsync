# ADR 0007 — Taksonomi Skill & Engine Normalisasi (M2)

**Status:** Diterima (Wave 2, 6 November 2026)

## 1. Konteks

M2 menyediakan lapisan skill kanonik yang menjadi fondasi M3–M6 dan M9
(docs/08). Kebutuhan: taksonomi bilingual ID/EN (≥300 entri), normalisasi
dictionary-first tanpa LLM, penanganan ambiguitas yang jujur (tidak pernah
memaksa pemetaan), alias dapat bertambah tanpa mengubah kode, dan jejak sumber
(provenance) hingga baris teks asal.

## 2. Keputusan

### 2.1 Penyimpanan taksonomi — JSON seed berversi → tabel DB
- **Sumber baseline:** `app/ai/extraction/taxonomy/skills_v1.json`
  (`version: 1.0.0`, 343 skill kanonik, 583 alias, 20 kategori) — ditinjau &
  ber-versi di repo.
- **Runtime membaca tabel DB** (`canonical_skills`, `skill_aliases`), di-seed
  idempoten via `scripts/seed_taxonomy.py` / `taxonomy_service.seed_from_json`.
  Alias baru cukup ditambah sebagai baris DB (`source='manual'`) — tanpa deploy.
- Kategori = kolom string pada `canonical_skills` (nilai dikendalikan seed),
  **bukan** tabel terpisah — tanpa kebutuhan CRUD kategori di MVP; diubah jadi
  tabel bila kategori dinamis benar-benar dibutuhkan.

### 2.2 Struktur data (migrasi 0010)
- `candidate_skills`: store kanonik per kandidat — UNIQUE(kandidat, canonical),
  `source_cv_id` (traceability ke CV sumber, SET NULL), `raw_name` + `evidence`
  + `source_section` + `extraction_method` (explicit/inferred/manual) +
  `status` (suggested/accepted/rejected).
- `job_skills`: proyeksi kanonik per lowongan — UNIQUE(job, canonical),
  `required` bool (precedence required saat dedupe), raw_name tetap disimpan.
- **`jobs.skills` JSONB TIDAK diubah** (tetap sumber tampilan & input form
  `{name, required}`); `job_skills` adalah proyeksi kanonik yang direplace saat
  create/update lowongan.
- **Skills tanpa pemetaan kanonik tidak di-bariskan** (FK canonical NOT NULL)
  — mereka TETAP TERLIHAT di payload ekstraksi M1 (kandidat) dan `jobs.skills`
  JSONB (HR), sehingga tidak hilang; keputusan ini sadar dan terdokumentasi.

### 2.3 Normalisasi dictionary-first (tanpa LLM)
Urutan: normalisasi teks (lowercase, spasi, tanda baca dengan pengecualian
`c++`/`ci/cd`/`.net`/`node.js`) → **exact name** (conf 0,95) → **alias**
(0,95) → **fuzzy terkendali** (difflib ratio ≥ `skill_fuzzy_threshold` 0,92,
hanya diterima bila unik-terbaik: second-best < best − 0,03; conf 0,8) →
**tidak dipetakan** (needs_review + ≤3 saran, confidence 0,0). Tidak pernah
memaksa pemetaan. Matching inferred memakai batas kata (`\b`) —
`javascript developer` tidak pernah mengenai `java`.

### 2.4 Kebijakan confidence & provenance
- exact/alias 0,95 · fuzzy 0,8 · inferred (dari bullet pengalaman/proyek)
  0,7 · unmatched 0,0.
- Skill **inferred ditandai eksplisit** (`extraction_method='inferred'`) dan di
  UI diberi catatan "dari deskripsi pengalaman/proyek — bukan pernyataan
  langsung" — tidak pernah disajikan seolah dinyatakan kandidat.
- Setiap item menyimpan `raw_name` + `evidence` (kutipan sumber) +
  `source_section`.

### 2.5 Alur data
- **Konfirmasi ekstraksi M1** → normalisasi → baris `candidate_skills`
  status `suggested` (idempoten: re-konfirmasi mengganti suggested, memelihara
  accepted/rejected).
- **Terapkan ke Profil** (kandidat memilih) → `status='accepted'` + merge nama
  display ke `candidate_profiles.skills` JSONB (dedupe case-insensitive, batas
  30) — dua store sinkron dalam satu commit; apply ulang = no-op (0).
- **Create/update lowongan** → normalisasi skills form → replace `job_skills`.

## 3. Konsekuensi & risiko
- Alias yang salah (salah ketik seed) dapat memetakan keliru — mitigasi: validasi
  unit test anti-tabrakan (javascript∉java dst.) + alias review manual sebelum
  seed produksi.
- Fuzzy difflib cukup untuk skala 343 entri; bila taksonomi tumbuh >2000,
  pertimbangkan rapidfuzz/index trigram (keputusan di masa depan, bukan kini).
- Evaluasi sintetis in-domain (F1/canon-acc) bukan performa produksi — evaluasi
  CV volunteer menyusul (docs/03 §4.4).
