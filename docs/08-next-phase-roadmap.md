# TalentSync AI — Roadmap Fase Berikutnya (P3 AI Engine + Penjembatan P4)

**Status:** dokumen persiapan/handover — **belum ada implementasi** dari dokumen ini.
**Prinsip:** semua di bawah tunduk pada persetujuan pemilik proyek; arsitektur & keputusan docs/01–03 tetap mengikat; aturan main: migrasi selalu via Alembic, E2E browser wajib untuk setiap halaman baru, klaim kemampuan hanya boleh setelah teruji.

**Sumber teknis:** docs/01 §6 (desain AI), docs/03 §4 (kalibrasi, golden set, keamanan LLM), docs/05 (skema aktual), ADR 0001–0003, hasil audit (docs/04).

---

## 0. Prasyarat Sebelum Mulai P3 (checklist)

| # | Prasyarat | Pemilik |
|---|---|---|
| 1 | Persetujuan dokumen ini (scope & urutan) | Pemilik proyek |
| 2 | Registrasi akun **Groq** + kunci API di `.env` (`GROQ_API_KEY`, `GROQ_MODEL`) — dibutuhkan Modul 8 | Pemilik proyek |
| 3 | Ekspor frame Figma 8–17 (atau token baca) untuk tokens akurat | Pemilik proyek |
| 4 | Formulir persetujuan volunteer CV (golden set) — docs/03 §4.4 | Tim |
| 5 | Keputusan lokasi model embedding (venv lokal ±0,5 GB — default) | Tim |

**Infrastruktur bersama yang dibangun lebih dulu (bagian dari Modul 1–3):**

- Migrasi **0006**: `cv_extractions.payload JSONB` (terstruktur), `confirmed_at`/`confirmed_by`; **0007**: tabel `cv_embeddings` & `job_embeddings` (`vector(384)`, kolom `model`, `text_kind`, UNIQUE(kolom FK, model, text_kind)); **0008**: tabel `match_results` (overall, factors JSONB, matched/missing JSONB, evidence JSONB, explanation, model_version, UNIQUE(cv_id, job_id, model_version)); **0009**: tabel `cv_optimizations` (suggestions JSONB + keputusan per-edit, llm_provider/model/prompt_version, grounding_report) — nomor final menyesuaikan urutan kerja.
- Dependensi baru: `sentence-transformers`, `pgvector` (python), `reportlab`, SDK Groq (atau HTTP langsung), `structlog` (opsional).
- Env baru: `GROQ_API_KEY`, `GROQ_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `MATCH_WEIGHTS` (override opsional, default 40/30/20/10).
- **Eval harness** (wajib sebelum matching dirilis): `scripts/evaluate_matching.py`, `scripts/evaluate_extraction.py`, `scripts/audit_optimization.py` + folder `eval/golden/` — protokol lengkap di docs/03 §4 (rubrik 0–3, rater buta, κ ≥ 0.6, split 70/30, freeze `model_version`).

**Urutan gelombang (10 minggu):**

```
W1 (mgg 1–3):  [M1 Parsing Lanjutan] → [M2 Skill Extraction]
W2 (mgg 4–7):  [M3 Embedding] → [M4 Matching Explainable] → [M5 Skill Gap] → [M6 Rekomendasi]
W3 (mgg 8–10): [M7 Diagnosis CV] → [M8 LLM Optimasi CV] → (P4-inti: Applications) → [M9 Ranking HR]
```

Dependensi kunci: **M9 membutuhkan Applications** (pelamar nyata) — karena HR bulk upload ditunda (F4) dan tidak ada pelamar tanpa alur apply, M9 dijadwalkan setelah inti Applications (P4) tersedia. Jangan memajukan M9 sebelum itu.

---

## Modul 1 — Advanced CV Parsing

- **Tujuan:** mengubah `raw_text` menjadi payload terstruktur tervalidasi (kontak, skills mentah, pendidikan, pengalaman, sertifikasi, bahasa) dengan confidence per field, lalu **konfirmasi manusia** sebelum dipakai matching.
- **Input:** `cvs.file_path` + `cv_extractions.raw_text` (sudah ada dari P2).
- **Output:** `cv_extractions.payload` (JSONB, skema Pydantic), `confirmed_at`/`confirmed_by` setelah review; status `needs_review`.
- **Dependensi:** basic_pdf (ada); Modul 2 meng-kanonikalisasi skills hasil parsing ini.
- **Backend:** `ai/extraction/segmenter.py` (heading ID/EN, 1–2 kolom), `entity_extractor.py` (regex kontak, rentang tanggal ID/EN "2023-01"/"sekarang"), `payload_schema.py`; endpoint `GET /cvs/{id}/extraction`, `PUT /cvs/{id}/extraction/confirm` (kandidat); migrasi 0006.
- **Frontend:** halaman **Review Ekstraksi** (`/app/cv/:id/review`, frame Figma 13): form per bagian + badge confidence + tombol "Konfirmasi & Gunakan" (+ opsional "Terapkan ke Profil"); chip status "Perlu review" di daftar CV.
- **Testing:** unit segmenter dengan fixture `raw_text` (ID, EN, dwibahasa, 2 kolom); integrasi API (konfirmasi mengubah state); E2E unggah→review→konfirmasi; sampel akurasi per-field manual.
- **Kriteria penerimaan:** 10 CV uji pertama hanya butuh koreksi minor; matching **menolak** CV tanpa konfirmasi; setiap field punya sumber (atau ditandai manual).
- **Risiko:** layout ekstotis & hasil pindai (fallback input manual sudah disepakati); waktu anotasi golden set.

## Modul 2 — Skill Extraction & Normalization

- **Tujuan:** taksonomi skill bilingual (ID/EN) + alias → nama kanonik; klasifikasi hard/soft; referensi ESCO.
- **Input:** payload Modul 1; teks lowongan (untuk kanonikalisasi `jobs.skills` + autocomplete HR).
- **Output:** `payload.skills = [{canonical, aliases, type: hard|soft, evidence}]`; endpoint autocomplete; opsional kolom `canonical` pada `jobs.skills` (non-breaking).
- **Dependensi:** Modul 1; embedder (Modul 3) untuk *linking* frasa tak dikenal (tahap 2 — dictionary-first dulu).
- **Backend:** `ai/extraction/taxonomy/*.json` (≥300 entri + alias + `related_to` edges + kategori), `skill_extractor.py`; `GET /skills/autocomplete?q=`.
- **Frontend:** autocomplete pada form "Buat Lowongan" (required/preferred); chips kanonik di halaman review.
- **Testing:** unit alias & dedupe; **F1 skill extraction vs golden CV teranotasi, target ≥ 0,80** (docs/03 §4.6); regresi taksonomi saat edit.
- **Kriteria penerimaan:** F1 tercapai pada golden set awal; tidak ada skill "makhluk asing" tanpa entri kanonik/alias di sampel audit.
- **Risiko:** jargon lokal tak tercakup → proses penambahan alias berkala; drift antara versi taksonomi (simpan `taxonomy_version`).

## Modul 3 — Semantic CV-Job Matching (Embedding)

- **Tujuan:** vektor semantik CV & lowongan + skor semantik terkalibrasi (faktor 40%).
- **Input:** payload terkonfirmasi + raw_text; lowongan aktif (title, skills, description).
- **Output:** baris `cv_embeddings`/`job_embeddings` (pgvector, 384-dim, `text_kind` berbeda) + konstanta kalibrasi cosine (anchor piecewise-linear, docs/03 §4.2 Tahap 1).
- **Dependensi:** Modul 1–2; pgvector aktif sejak migrasi 0001; `EMBEDDING_MODEL/EMBEDDING_DIM` (F2 — model configurable, swap = migrasi dim + re-embed script).
- **Backend:** `ai/matching/embedder.py` (interface + registry + chunking ±128 token + mean pooling), tugas embed saat konfirmasi CV / publikasi lowongan, skrip re-embed massal; `connect_args` sudah per-dialect.
- **Frontend:** tidak ada halaman baru (hasil terlihat lewat Modul 4/6).
- **Testing:** unit chunker/pooling (deterministik); benchmark **1 CV vs 500 lowongan < 5 dtk CPU**; distribusi cosine pasangan positif/negatif terdokumentasi (bahan anchor).
- **Kriteria penerimaan:** seluruh CV terkonfirmasi & lowongan aktif memiliki vektor versi model aktif; skrip swap model teruji sekali di staging; anchor kalibrasi tercetak di laporan.
- **Risiko:** memori model di mesin dev (muat malas); kualitas bahasa Indonesia (dimitigasi faktor skill 30% + evaluasi); swap model = re-embed penuh.

## Modul 4 — Explainable Compatibility Scoring

- **Tujuan:** skor komposit transparan **0,40·semantik + 0,30·skill + 0,20·pengalaman + 0,10·pendidikan** dengan artefak penjelasan penuh (anti black-box).
- **Input:** vektor (M3), payload (M1), `jobs.skills` wajib/tambahan (P2), taksonomi (M2).
- **Output:** baris `match_results` + respons API: `{overall, factors{semantic,skill_coverage,experience,education}, matched_skills[{name, match_type, evidence}], missing_skills[{name, importance, severity}], top_experiences, explanation (narasi template ID)}`.
- **Dependensi:** M1–M3; label golden set untuk kalibrasi bobot (docs/03 §4.2 Tahap 2 — grid search kelipatan 5, split 70/30, freeze per `model_version`).
- **Backend:** `ai/matching/{scorer,calibration,explainer}.py` (fungsi murni — mudah diuji), `match_service` (hitung + cache `match_results`, invalidasi saat CV/job berubah); `GET /jobs/{id}/compatibility` (kandidat).
- **Frontend:** halaman **Kompatibilitas** (`/app/jobs/:id/compatibility`, frame 16): ScoreRing, FactorBar, chips matched/missing, panel "Mengapa skor ini" + "pertanyaan wawancara" (template).
- **Testing:** unit scorer & explainer (murni); properti skor 0–100 & determinisme; skrip kalibrasi menghasilkan laporan; integrasi API; E2E buka halaman; **nDCG@10 & Spearman vs label manusia** (target awal 0,75/0,60 — laporkan apa adanya).
- **Kriteria penerimaan:** setiap skor disertai 4 sub-faktor + bukti + narasi; label bands sesuai desain (≥85 Sangat Cocok dst.); hasil kalibrasi terdokumentasi & dibekukan.
- **Risiko:** kualitas agreement rater (mitigasi sesi kalibrasi rubrik); overfit bobot (freeze validasi set); ekspektasi pemangku terhadap angka (laporkan proses, bukan janji).

## Modul 5 — Skill Gap Analysis

- **Tujuan:** matriks kompetensi target vs kandidat + severity + rekomendasi belajar (statis) — fitur diferensiasi utama.
- **Input:** `match_results.missing_skills`, kategori taksonomi, bobot wajib/tambahan.
- **Output:** API `GET /jobs/{id}/gap` (kandidat) & versi HR per kandidat (dipakai M9); UI kedua peran (frame 10/16) — **komponen shared** `GapMatrix`.
- **Dependensi:** Modul 4.
- **Backend:** `ai/matching/gap.py` (severity: kritis/menengah/minor dari bobot & besar gap; surplus juga dilaporkan); pemetaan statis taksonomi → sumber belajar (JSON).
- **Frontend:** matriks standar-vs-kandidat (bar + label surplus/gap), kartu gap dengan instruksi pewawancara; laporan gap dapat diekspor (PDF — boleh digabung dengan ekspor M8).
- **Testing:** unit severity & pemetaan; snapshot komponen; E2E buka gap kedua peran.
- **Kriteria penerimaan:** setiap missing skill memiliki severity + alasannya; HR & kandidat melihat data identik dari mesin yang sama (bukti dual-role); rekomendasi selalu tersedia untuk kategori ber-cakupan.
- **Risiko:** severity terasa sewenang-wenang → ambang eksplisit + dokumentasi rumus; scope creep ke marketplace kursi (dilarang — statis saja).

## Modul 6 — Job Recommendation Engine

- **Tujuan:** top-k lowongan aktif untuk kandidat dengan alasan per faktor.
- **Input:** CV utama (primary) terkonfirmasi; katalog aktif ber-vektor.
- **Output:** `GET /me/recommendations` (KNN top-100 via pgvector → re-rank faktor skill/pengalaman/pendidikan) + halaman **Rekomendasi** (`/app/recommendations`, frame 14: kartu + panel "Mengapa cocok" + mini factor bars) + ringkasan di dashboard.
- **Dependensi:** Modul 4.
- **Backend:** `recommendation_service` (kueri KNN + re-rank; cache hasil per CV), invalidasi saat CV/lowongan berubah.
- **Testing:** unit re-rank; integrasi; latensi **< 1 dtk saat cache hangat**; E2E buka rekomendasi + klik detail.
- **Kriteria penerimaan:** daftar terurut skor; setiap item menampilkan alasan (kriteria terpenuhi x/y); tanpa CV terkonfirmasi → empty state edukatif.
- **Risiko:** cold start (mitigasi: hitung saat konfirmasi); ekspektasi "rekomendasi = janji kerja" → copy jujur "berdasarkan kemiripan".

## Modul 7 — CV Diagnosis

- **Tujuan:** skor kualitas CV + kekuatan/hal-yang-perlu-ditingkatkan **deterministik** (tanpa LLM) — frame 13 bagian diagnosis.
- **Input:** payload terkonfirmasi + raw_text.
- **Output:** `GET /cvs/{id}/diagnosis` → `{quality_score, strengths[], improvements[], readability}`; kartu diagnosis di `/app/cv`.
- **Dependensi:** Modul 1–2.
- **Backend:** `ai/extraction/diagnosis.py` — aturan eksplisit (kontak lengkap, ringkasan ada, metrik kuantitatif di pengalaman, panjang section, kata kunci industri).
- **Frontend:** panel diagnosis (kekuatan hijau / perbaikan amber) + CTA ke Modul 8.
- **Testing:** unit tiap aturan; E2E tampil konsisten.
- **Kriteria penerimaan:** setiap poin diagnosis punya aturan sumber yang bisa disebut; skor stabil untuk input sama; tanpa panggilan LLM.
- **Risiko:** aturan terdengar menggurui → iterasi copywriting ID.

## Modul 8 — LLM-based CV Optimization

- **Tujuan:** saran per-edit yang **ter-grounding** pada isi CV untuk satu lowongan; persetujuan per-edit; hasil = versi CV baru; ekspor PDF.
- **Input:** payload/raw_text (M1), lowongan, gap analysis (M5), konteks profil.
- **Output:** baris `cv_optimizations` (suggestions JSONB + `grounding_report` + keputusan pengguna); CV versi n+1 (`parent_cv_id`) setelah apply; berkas PDF ekspor (ReportLab, gaya Harvard).
- **Dependensi:** M1–M5; **Groq API key (F1)**; kontrak JSON ketat: setiap edit wajib `source_ref` ke bullet CV asli, `change_type` terbatas, dilarang menyentuh tanggal/identitas.
- **Backend:** `ai/optimization/{llm_client.py (adapter agnostik), prompts.py (versi + hash), grounding_validator.py (allowlist entitas: perusahaan/institusi/sertifikasi harus ada di CV; referensi wajib resolvable)}`; `optimization_service`; endpoint: `POST /cvs/{id}/optimizations` (generate, async), `GET` daftar, `PATCH` keputusan per-edit, `POST apply` → versi baru → re-embed + re-match; `GET /cvs/{id}/export.pdf`.
- **Frontend:** halaman **Review Optimasi** (frame 17, versi ringkas): side-by-side original vs saran + rationale + badge validator + tombol Terapkan/Tolak per edit + "Terapkan yang dipilih" + unduh PDF.
- **Testing:** unit validator (fabrikasi wajib tertolak — tabel kasus); kontrak adapter (mock; 1 live call manual saat kunci aktif); integrasi apply→versi→re-embed→re-match; **audit groundedness ≥95% & 0 fabrikasi** pada 10 pasangan (docs/03 §4.6); E2E generate→review→apply→unduh (skip-with-reason bila kunci belum ada).
- **Kriteria penerimaan:** tidak ada perubahan CV tanpa persetujuan per-edit; CV asli immutable; setiap generasi tercatat (provider/model/prompt_version); validator menolak entitas asing.
- **Risiko:** kuota/rate-limit Groq (1 panggilan/generasi + cache + generate sebelum demo); JSON tidak valid (retry + schema validation); latensi (async + status); prompt injection dari isi CV (sanitasi + system prompt tegas).

## Modul 9 — HR Candidate Ranking

- **Tujuan:** peringkat pelamar per lowongan berdasarkan `match_results`, filter skor, bandingkan 2 kandidat — frame 8.
- **Input:** **Applications** (kandidat melamar dengan CV) — ⚠️ **dependensi keras**: fitur apply (P4-inti) harus ada lebih dulu; HR bulk upload tetap ditunda (F4).
- **Output:** `GET /hr/jobs/{id}/ranking` (terurut skor + faktor + chips), `GET /hr/jobs/{id}/compare?ids=a,b`; UI halaman **Ranking Kandidat** (frame 8: kartu terperingkat + filter + bottom compare bar) dan tautan ke detail/gap per kandidat.
- **Dependensi:** Modul 4 + **Applications inti** (submit/list/status dasar — bagian P4; direncanakan paralel oleh anggota backend di W3).
- **Backend:** kueri ranking (join applications×match_results, order overall desc), compare service (sisi-per-sisi faktor & skills).
- **Frontend:** halaman ranking + panel komparasi; aksi status aplikasi tetap milik P4.
- **Testing:** integrasi urutan & isolasi perusahaan (perusahaan lain 404); E2E HR buka ranking & bandingkan; seed aplikasi contoh untuk demo.
- **Kriteria penerimaan:** urutan sesuai skor `model_version` aktif; hanya pelamar perusahaan sendiri; compare ≤2 kandidat konsisten dengan halaman kompatibilitas.
- **Risiko:** demo tanpa pelamar terlihat kosong → seed harus membuat beberapa aplikasi; ekspektasi "auto-reject" (tidak ada di fase ini — ranking hanya membantu).

---

## Definition of Done — P3

1. Seluruh kriteria penerimaan modul terpenuhi dan teruji (unit + integrasi + E2E browser).
2. `EVALUATION.md` + laporan metrik nyata (F1 ekstraksi, nDCG/Spearman, groundedness, latensi) — menggantikan klaim marketing (F7).
3. docs/05 (skema & endpoint) + docs/04 (log) + README diperbarui; ADR baru untuk keputusan yang muncul.
4. Tidak ada penambahan scope di luar dokumen ini tanpa persetujuan.

## Pertanyaan Terbuka untuk Pemilik Proyek

1. Jadwal pendaftaran Groq & kepemilikan kunci (M8 tidak bisa mulai tanpa ini).
2. Apakah "Terapkan ke Profil" dari ekstraksi (M1) diinginkan di gelombang pertama atau menyusul?
3. Bahasa narasi explainability: ID saja (rekomendasi) atau ID+EN sejak awal?
