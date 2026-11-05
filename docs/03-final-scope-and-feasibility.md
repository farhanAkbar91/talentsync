# TalentSync AI — Final Scope & Feasibility Check

**Dokumen:** v1.0 — addendum final; menunggu persetujuan implementasi
**Baseline:** `docs/01-technical-blueprint.md` + `docs/02-decision-review.md` (tidak diubah; dokumen ini menjadi lapisan keputusan final)
**Status kode:** **Tidak ada implementasi.** Satu-satunya aktivitas teknis yang dilakukan adalah *probe read-only* terhadap API publik sumber lowongan (bagian B) — sesuai permintaan verifikasi.
**Tanggal:** 4 November 2026

---

## 1. Keputusan Final (F1–F7)

Tujuh penyesuaian hasil review Anda dicatat sebagai keputusan final berikut. Semuanya konsisten dengan rekomendasi blueprint — yang berubah hanya parameternya.

| ID | Keputusan Final | Merinci | Konsekuensi teknis |
|---|---|---|---|
| **F1** | **Groq API = default LLM provider**, melalui adapter agnostik | D3 | Adapter tetap wajib (penyedia dapat ditukar via config). Pemilihan model instruksi (keluarga Llama terbaru yang tersedia di Groq saat implementasi) dikonfigurasi, bukan hard-coded. Anggaran: 1 panggilan per generasi + cache hasil + status "coba lagi" saat rate-limit. Tim mendaftarkan akun & kunci Groq sendiri. |
| **F2** | **Model embedding wajib configurable** — dapat diganti tanpa merombak sistem | D4 | Pola: interface `Embedder` + registry via config (`EMBEDDING_MODEL`, `EMBEDDING_DIM`); setiap vektor menyimpan nama modelnya. **Batas jujur:** dimensi kolom pgvector tetap perlu satu migrasi Alembik + skrip *re-embed* satu perintah saat ganti model — kodenya tidak berubah, datanya di-recompute. MiniLM multilingual (384-dim) tetap default MVP. |
| **F3** | **Sumber ingestion divalidasi lebih dulu**, khususnya relevansi Indonesia | D5 | Probe live dilakukan (hasil di §3). Konektor MVP = **RemoteOK + Remotive** (terverifikasi dapat diakses). Arbeitnow = kandidat ke-3. Adzuna/Jooble **ditunda** sampai kunci terdaftar dan cakupan Indonesia terverifikasi. Dataset seed Indonesia berlabel tetap dalam scope. |
| **F4** | CV Builder Wizard & HR Bulk Upload **ditunda ke post-MVP** (bukan dibatalkan) | D8, D16 | Masuk backlog terstruktur sebagai P9/P10 dengan estimasi tersimpan; tidak ada pekerjaan MVP. |
| **F5** | Pricing page **bukan prioritas MVP** | D9 | Landing MVP tanpa section pricing; konten pricing masuk backlog. |
| **F6** | **Deployment awal = Docker Compose lokal** | D12 | Cloud free-tier hanya opsi eksperimen pasca-MVP. Demo akademik berjalan dari laptop. |
| **F7** | **Seluruh klaim marketing diganti metrik terukur** | D13 | Hero landing menampilkan angka nyata dari DB (jumlah lowongan aktif, CV terproses, dst.) dan metrik evaluasi (nDCG/F1) begitu laporan evaluasi tersedia. Sebelum itu: angka disembunyikan atau diberi label "diukur saat evaluasi akhir". Label engine memakai versioning sendiri ("Match Engine v1"), bukan branding fiktif. |

---

## 2. A. Feasibility — 15 Kelompok Fitur MVP dalam 12 Minggu

### 2.1 Asumsi kapasitas

| Parameter | Nilai | Catatan |
|---|---|---|
| Tim | 5 orang | A Backend Core · B AI/NLP · C Frontend Kandidat · D Frontend HR + Design System · E Pipeline + QA + Evaluasi |
| Durasi | 12 minggu | Termasuk 1 minggu hardening + 1 minggu penyiapan submission |
| Hari efektif | **3,5 hari/orang/minggu** (konservatif; mahasiswa punya kuliah lain) | Kapasitas kotor ≈ **210 person-day (pd)** |
| Overhead integrasi (standup, merge, demo internal) | ±15% | Kapasitas rekayasa efektif ≈ **178 pd** |

### 2.2 Estimasi ulang 15 kelompok fitur

| # | Kelompok fitur | Baseline (pd) | Setelah penyederhanaan (pd) | PIC utama |
|---|---|---|---|---|
| 1 | Setup P0: repo, Docker Compose, CI, migrasi awal | 5 | 4 | A + E |
| 2 | Auth, peran, profil kandidat & perusahaan, akun demo | 16 | 14 | A (BE) + C (FE) |
| 3 | CRUD lowongan internal + siklus hidup (weighted skills, closing date) | 14 | 12 | A + D |
| 4 | Pencarian + detail lowongan + katalog eksternal ber-badge | 10 | 8 | C + A |
| 5 | Upload CV → ekstraksi → review & koreksi | 20 | 17 | B + C |
| 6 | Matching multi-faktor + explainability | 18 | 16 | B + A |
| 7 | Analisis skill gap (1 komponen, 2 peran) | 9 | 8 | B + D |
| 8 | Rekomendasi lowongan (+ alasan) | 5 | 4 | C |
| 9 | Peringkat kandidat + komparasi + detail kandidat (HR) | 13 | 11 | D |
| 10 | Applications + status + catatan (2 peran) | 13 | 11 | A + C |
| 11 | Optimasi CV (Groq) + review per-edit + versioning + ekspor PDF | 15 | 13 | B + C |
| 12 | Ingestion 2 konektor + lifecycle + scheduling + log | 14 | 12 | E |
| 13 | Dashboard HR (agregat dihitung nyata) | 4 | 3 | D |
| 14 | Landing + label provenance | 3 | 2 | C + D |
| 15 | Seed data + golden set + skrip evaluasi | 14 | 12 | E + B |
| — | *Design system komponen bersama (lintas fitur)* | 12 | 10 | D |
| — | *Hardening, empty states, security pass, docs, rehearsal* | 10 | 8 | Semua |
| | **Total** | **195** | **165** | |

**Kesimpulan kuantitatif:** baseline 195 pd **melebihi** kapasitas efektif 178 pd. Dengan paket penyederhanaan §2.3, total turun ke **165 pd → muat dengan buffer ±13 pd (±7%)**. Artinya: **layak, tetapi penyederhanaan bersifat wajib, bukan opsional.**

### 2.3 Penyederhanaan yang tidak mengurangi kontribusi akademik

Semua inovasi yang dievaluasi (matching explainable, skill gap, optimasi grounded, ingestion lifecycle) **tetap utuh**. Yang dipangkas adalah perapihannya:

| Fitur | Bentuk sederhana (MVP) | Yang ditunda |
|---|---|---|
| Pencarian lowongan | ILIKE/pg_trgm + 4 filter (kata kunci, lokasi, tipe, work mode) | Full-text ranking tsvector berbobot, filter lanjutan, saved-search |
| Komparasi kandidat | Side-by-side **2 kandidat** | 3 kandidat + diff granular |
| Rekomendasi | Top-10 tanpa filter lanjutan; panel "mengapa" memakai data kompatibilitas yang sama | Filter skor/gaji/tipe, paginasi besar |
| Optimasi CV | 1 template PDF (Harvard-ish), tanpa pemilih template/preview mobile | Multi-template, A4/mobile toggle |
| Skill gap | Severity 3 level; rekomendasi belajar = tabel statis taksonomi→sumber belajar | Marketplace materi, estimasi jam belajar dinamis |
| Review ekstraksi | Form edit per field + badge confidence | Drag-drop reorder section, rich-text inline |
| Ingestion | 2 konektor; trigger manual + GH Actions; dedupe intra-sumber | Konektor ke-3/4, dedupe lintas-sumber fuzzy |
| Dashboard | 4 stat card + daftar aktivitas terbaru | Tabel "kandidat terbaik minggu ini", panel market-gap |
| Auth | Email+password, tanpa verifikasi email (dicatat sebagai keterbatasan) | Verifikasi email, OAuth |
| Landing | Halaman statis dari desain, angka riil/tersembunyi sesuai F7 | Animasi, section pricing (F5) |
| Jobs tersimpan (bookmark) | **Dihilangkan dari MVP** (chip UI disiapkan, endpoint tidak) | — |
| Ekstraksi→matching | Matching berjalan setelah konfirmasi ekstraksi; job baru tidak memicu re-match massal semua CV (dilakukan on-demand + cache) | Rekomputasi massal terjadwal |

### 2.4 Urutan *cut lever* bila terjadi kegeseran jadwal

Jika di tengah jalan kapasitas riil < asumsi, potong berurutan dari atas (total ~16 pd):
1. Bookmark/save job (−2, sudah di luar) → 2. Konektor Arbeitnow (−2) → 3. Komparasi tetap 2 arah (−1) → 4. Tabel kandidat terbaik di dashboard (−2) → 5. Filter rekomendasi (−2) → 6. Golden set 30→20 CV (−3) → 7. Landing mode ringkas (−1) → 8. Export DOCX tidak pernah masuk (0).

**Aturan:** pemotongan hanya via persetujuan Anda; tidak ada pemotongan diam-diam pada item berlabel inovasi inti (fitur #5, #6, #7, #11, #12, #15).

---

## 3. B. Data Ingestion — Hasil Verifikasi Langsung (4 Nov 2026)

**Metode probe:** `curl` read-only tanpa kredensial, dari mesin kerja, dengan User-Agent khusus. **Probe ≠ konektor siap.** Sebuah konektor hanya dinyatakan siap setelah: implementasi + contract test dengan fixture rekaman + **3 run terjadwal berturut-turut sukses** + verifikasi upsert/dedupe/expire.

### 3.1 Status per sumber

| Sumber | Hasil probe | Struktur data | Catatan kepatuhan | Status |
|---|---|---|---|---|
| **RemoteOK** — `remoteok.com/api` | **HTTP 200**, 651 KB, **99 lowongan** di jendela terkini | `position, company, location, tags, description, salary_min/max, date/epoch, url, apply_url` | Objek pertama respons berisi **`legal`**: wajib menautkan balik ke remoteok.com dengan tautan *follow* + menyebut sebagai sumber — **wajib diimplementasikan di UI (badge provenance)** | ✅ Terverifikasi dapat diakses → konektor #1 |
| **Remotive** — `remotive.com/api/remote-jobs` | **HTTP 200**, 166 KB, **11 lowongan** (dengan dan tanpa `limit`; `job-count: 11`) | `title, company_name, category, job_type, candidate_required_location, salary, publication_date, url, description` | API publik, tanpa kunci | ✅ Terverifikasi dapat diakses → konektor #2. ⚠️ **Volume terobservasi kecil** (11 lowongan, rentang terbit 4 Okt–2 Nov 2026) — perlu investigasi param di P7; jangan mengandalkan sebagai sumber volume |
| **Arbeitnow** — `arbeitnow.com/api/job-board-api` | **HTTP 200**, 3,9 MB, **300 lowongan/halaman** + meta paginasi | `slug, company_name, title, description, remote, url, tags, job_types, location, created_at` | Meta berisi ToS eksplisit: API publik gratis, larangan abuse, apresiasi link-back | ✅ Terverifikasi → **kandidat ke-3 (opsional, lever #2)** |
| **Adzuna** | **HTTP 400** tanpa kredensial (endpoint hidup, kunci wajib) | — | Free tier berbasis kunci | ⏸️ Ditunda (F3): validasi kunci + **cakupan `country=id`** baru dilakukan setelah registrasi |
| **Jooble** | Belum diuji (butuh kunci hasil persetujuan) | — | — | ⏸️ Ditunda |

### 3.2 Temuan kunci: cakupan Indonesia

| Sumber | Lowongan dianalisis | Hit kata kunci ID (indonesia/jakarta/surabaya/bandung) | Worldwide/remote |
|---|---|---|---|
| RemoteOK | 99 | **2** | 94 |
| Remotive | 11 | **1** | 11 (9 = "Worldwide") |
| Arbeitnow | 300 | **0** | 22 remote eksplisit |

**Interpretasi jujur:** sumber berizin yang tersedia adalah portal *remote global berbahasa Inggris* — **bukan pasar kerja Indonesia**. Dampak & mitigasi:
1. Ekspektasi demo disetel benar: katalog eksternal = lowongan remote global yang relevan bagi talenta ID (banyak perusahaan menerima remote worldwide); lowongan lokal datang dari (a) lowongan yang dibuat HR di platform dan (b) **dataset seed Indonesia berlabel `source='seed'`** yang jelas ditandai.
2. Filter `candidate_required_location`/`location` memuat "Worldwide/Anywhere" ditampilkan; lowongan terbatas wilayah tertentu tetap masuk katalog dengan badge sumber.
3. Jalur perbaikan relevansi (post-probe): registrasi Adzuna/Jooble → cek cakupan `id` → jika lolos, jadi konektor #3/#4 di P7 atau pasca-MVP.
4. Gaji eksternal dalam mata uang asing → normalisasi tampilan (simbol mata uang asli disimpan; konversi IDR opsional, informatif saja).
5. **Klaim yang boleh dibuat di laporan/demo:** "endpoint X terverifikasi dapat diakses pada 4 Nov 2026" — **bukan** "pipeline berjalan" atau "konektor siap", sampai kriteria §3.0 terpenuhi di P7.

### 3.3 Keputusan konektor MVP

**RemoteOK + Remotive** (keduanya terverifikasi hari ini, tanpa kunci, tanpa scraping). Arbeitnow opsional bila kapasitas memungkinkan. Interval run 8 jam (jauh di bawah batas abuse semua sumber). Semua sumber mencantumkan atribusi sesuai ketentuan masing-masing.

---

## 4. C. Matching Evaluation

### 4.1 Arsitektur skor dan normalisasi

Setiap faktor dinormalisasi ke 0–100 **sebelum** digabung:

```
F_semantic   = mapping(cosine(cv_vec, job_vec))              # 40%
F_skill      = 0.6·Cov_required + 0.4·Cov_preferred          # 30%
F_experience = 0.6·min(tahun, tahun_req)/tahun_req
             + 0.4·sim(title_history, job_title_req)          # 20%
F_education  = ordinal (lebih tinggi=100, pas=90, −1=55, tak terkait=25)  # 10%

Overall = 0.40·F_semantic + 0.30·F_skill + 0.20·F_experience + 0.10·F_education
Label: ≥85 Sangat Cocok · 70–84 Cocok · 55–69 Cukup · <55 Kurang
```

### 4.2 Protokol kalibrasi (3 tahap, tanpa model gelap)

**Tahap 0 — Prior (sebelum data):** bobot 40/30/20/10 diambil sebagai prior berdasar desain Figma (faktor teknikal dominan) dan dianggap hipotesis, bukan kebenaran.

**Tahap 1 — Kalibrasi pemetaan cosine (sebelum golden set penuh):** distribusi cosine pasangan positif (CV–job yang jelas relevan) dan negatif dikumpulkan dari golden set awal; pemetaan piecewise-linear ditetapkan dari **anchor**: median pasangan relevan ≈ 85, median tidak relevan ≈ 30, linear di antara, clamp di luar. Konstanta disimpan per `model_version`.

**Tahap 2 — Kalibrasi bobot (dengan golden set):** grid search bobot kelipatan 5, masing-masing dibatasi [10, 60] dan total = 100; tujuan memaksimalkan **nDCG@10** dan **Spearman ρ** terhadap label manusia; split 70/30 (kalibrasi/validasi); hasil dibekukan sebagai `model_version` baru dan **tidak boleh di-tune lagi terhadap set validasi** (mencegah overfitting ke test set). Interpretabilitas dijaga: tidak dipakai model pembelajaran gelap — bobot akhir tetap 4 angka yang bisa dijelaskan ke penguji.

### 4.3 Hubungan 60/40 (form lowongan) dengan skor skill coverage

Angka 60/40 yang diisi HR di form "Buat Lowongan" adalah **bobot di dalam faktor skill (F_skill)**, bukan bobot skor keseluruhan. Rumus lengkap:

```
Cov_required = (Σ skor matching skill required) / (jumlah skill required)
Cov_preferred = (Σ skor matching skill preferred) / (jumlah skill preferred)
skor per skill: 1.0 exact/alias · 0.5 related (relasi taksonomi) · 0.0 tidak ada
F_skill = 0.6·Cov_required + 0.4·Cov_preferred          # lalu × 100
Overall = 0.40·F_semantic + 0.30·F_skill + 0.20·F_exp + 0.10·F_edu
```

**Contoh numerik:** lowongan punya 3 skill required (kandidat match 2 exact) dan 4 preferred (match 2 exact, 1 related):
`Cov_required = (1+1+0)/3 = 0.667` · `Cov_preferred = (1+1+0.5+0)/4 = 0.625`
`F_skill = 0.6·0.667 + 0.4·0.625 = 0.400 + 0.250 = 0.650 → 65`
`Kontribusi ke Overall = 0.30 × 65 = 19.5 poin` (dari 30 maksimal).

Implikasi desain yang dijamin: lowongan **tanpa preferred skills** tetap adil (`Cov_preferred` kosong = faktor hanya dari required, tanpa penalti); lowongan tanpa required skills (jarang) diblokir oleh validasi form.

### 4.4 Rancangan golden set

| Aspek | Keputusan |
|---|---|
| Komposisi CV | 20–30: **12 sintetis berlabel** (dibuat tim, realistis, dwibahasa) + **8–15 CV volunteer** (mahasiswa lain, **dengan formulir persetujuan tertulis**, dianonimkan menjadi `CV-001…`) |
| Komposisi job | 30–50: campuran lowongan seed internal + lowongan hasil probe ingestion |
| Pasangan dinilai | **±200 pasangan**, disampling stratified: untuk tiap CV ambil 5–8 job yang mencakup desil skor model (tinggi→rendah) + beberapa acak — menghindari bias hanya-mengukur-ujung |
| Penyimpanan | `eval/golden/` (label CSV + manifest), **tanpa PII** (nama/telepon/alamat dihapus; hanya struktur CV) |
| Pisah data | 70% kalibrasi · 30% validasi (dibekukan) |

### 4.5 Protokol penilaian manusia

1. **Rater:** 3 orang (anggota tim yang tidak menulis modul matching + 1–2 volunteer eksternal bila ada); tiap pasangan dinilai **min. 2 rater**, rater ke-3 untuk kasus selisih ≥2.
2. **Buta (blind):** rater **tidak melihat skor model**; hanya ringkasan terstruktur CV + deskripsi job.
3. **Rubrik 0–3** dengan definisi perilaku: `3` = akan masuk shortlist · `2` = relevan, layak dipertimbangkan · `1` = relevan lemah/sebagian · `0` = tidak relevan.
4. **Sesi kalibrasi rater** di awal: 10 pasangan bersama-sama, bahas perbedaan, revisi panduan.
5. **Agreement:** target Cohen's κ ≥ 0.6 (atau Krippendorff's α ≥ 0.6). Di bawah target → perbaiki rubrik, ulangi, **laporkan angka agreement apa adanya** di laporan.
6. **Label final:** mean rater (atau majority untuk 0–3).
7. **Metrik dilaporkan:** nDCG@10, Spearman ρ, Precision@5 (label ≥2), MAE skor vs label ternormalisasi. Target awal yang dinyatakan jujur di proposal: nDCG@10 ≥ 0.75, ρ ≥ 0.6 — **target, bukan janji**; hasil apa adanya yang dilaporkan.

### 4.6 Evaluasi dua kapabilitas lain

- **Ekstraksi:** 20 CV dianotasi skill ground-truth → Precision/Recall/F1 (target F1 ≥ 0.80) + catatan jenis kegagalan (layout, dwibahasa).
- **Optimasi LLM:** untuk 10 pasangan (CV, job), tiap saran edit dinilai rater: *grounded / tidak grounded*, *akurat secara faktual*, *berguna*. Target: ≥95% grounded pada sampel yang diterima, **0 fabrikasi kredensial**, acceptance rate dilaporkan.

---

## 5. D. Privacy & Security

### 5.1 Siklus hidup file CV

```
Upload (multipart, auth wajib)
 └─ validasi (§5.2) → simpan ke volume server: uploads/cvs/{tahun}/{uuid4}.pdf
     (DI LUAR root statis; nama acak 128-bit; nama asli hanya metadata tampilan)
 └─ proses parse (background) → payload ekstraksi JSON (draft)
 └─ konfirmasi pengguna → dipakai matching
 └─ akses: HANYA via GET /api/v1/cvs/{id}/file (streaming, otorisasi per-request, diaudit)
 └─ hapus: soft delete; hard delete atas permintaan pemilik / sweep retensi
```

### 5.2 Validasi file

| Pemeriksaan | Aturan |
|---|---|
| Ekstensi + MIME | `application/pdf` (ekstensi tidak dipercaya; magic bytes `%PDF-` wajib) |
| Ukuran | ≤ 10 MB (sesuai desain Figma) |
| Struktur | Dibuka dengan parser; gagal parse/telah terenkripsi-password → ditolak dengan pesan jelas |
| Halaman | ≤ 20 halaman |
| Duplikat | `sha256` per pemilik → tolak duplikat persis |
| Rate limit | ≤ 10 upload/jam/pengguna |
| Nama file | Disanitasi untuk tampilan; tidak pernah dipakai sebagai path |

### 5.3 Matriks RBAC (endpoint × peran)

| Resource | Anonim | Kandidat | HR |
|---|---|---|---|
| Landing, katalog job `active` (tanpa data pribadi) | ✔ | ✔ | ✔ |
| Detail job + kompatibilitas | ✖ | ✔ (CV miliknya) | ✔ |
| File CV | ✖ | ✔ **milik sendiri** | ✔ **hanya CV yang terikat aplikasi ke lowongan perusahaannya** |
| Payload ekstraksi | ✖ | ✔ sendiri | ✔ (applicant perusahaannya) |
| `match_results` | ✖ | ✔ (CV sendiri × job aktif) | ✔ (applicant perusahaannya) |
| Applications & status | ✖ | ✔ milik sendiri (boleh withdraw) | ✔ perusahaannya (transisi status) |
| **Draft optimasi CV** | ✖ | ✔ sendiri | **✖ — HR tidak pernah melihat draft optimasi; hanya versi CV final yang dilampirkan kandidat saat melamar** |
| Catatan HR internal | ✖ | ✖ | ✔ perusahaannya |
| Ingestion (trigger, run log) | ✖ | ✖ | ✖ (CLI/admin saja di MVP) |

Aturan object-level ditegakkan **server-side di setiap route**; pelanggaran mengembalikan **404 (bukan 403)** untuk menghindari kebocoran keberadaan resource. Semua perubahan status & unduhan CV masuk `audit_logs`.

### 5.4 Pembatasan akses dokumen — checklist "tidak ada CV terekspos publik"

1. Direktori `uploads/` **tidak** dimount sebagai static file oleh web server/API.
2. Tidak ada URL file yang dapat ditebak: nama `uuid4`, tanpa listing direktori.
3. Tidak ada *presigned/public URL* di MVP; setiap unduhan melewati otorisasi + audit log (siapa, kapan, CV mana).
4. CORS dibatasi origin frontend sendiri; *security headers* standar (`X-Content-Type-Options`, `frame-ancestors 'none'`, dsb.).
5. JWT: access 15 menit + refresh rotasi; refresh dicabut saat ganti password.
6. Rate limit pada login, register, upload.
7. Log aplikasi **bebas PII CV** (email/nama dimasking; isi CV tidak pernah dicetak ke log).
8. Uji keamanan minimum di P8: percobaan akses lintas-peran (kandidat A → CV kandidat B; HR perusahaan X → aplikasi perusahaan Y) sebagai *integration test* permanen.

### 5.5 Privasi terhadap LLM (Groq)

- Sebelum payload dikirim ke Groq: **PII kontak dihapus** (email, telepon, alamat) — yang dikirim hanya bagian skills/pengalaman/pendidikan yang relevan untuk optimasi.
- Log menyimpan versi prompt + hash konten, bukan isi.
- Saat registrasi Groq: tinjau kebijakan retensi/data-use mereka; pilih endpoint/opsi tanpa retensi pelatihan bila tersedia (diverifikasi waktu implementasi, dicatat di ADR).

### 5.6 Keselarasan UU PDP

Persetujuan eksplisit saat upload (tujuan jelas: analisis kecocokan & rekrutmen) · minimisasi data · batas retensi (CV aplikasi ditolak dihapus otomatis 6 bulan pasca-keputusan — konfigurasi) · hak akses & penghapusan data pribadi (endpoint delete akun) · jejak audit — selaras dengan prinsip yang sudah dinyatakan di landing/desain ("Kepatuhan UU PDP").

---

## 6. E. Roadmap 12 Minggu — Pembagian Paralel

### 6.1 Kunci kerja paralel (prasyarat)

- **Kontrak API dibekukan akhir Minggu 2**: spec OpenAPI untuk modul auth/job/CV/matching → C & D memakai mock server, tidak menunggu backend.
- **Design tokens dibekukan Minggu 1** → D membangun komponen bersama tanpa menunggu layar.
- **Taksonomi skill v1 tutup Minggu 3** → dipakai ekstraksi (P3) dan form lowongan (P2).
- **Harness evaluasi berdiri Minggu 4** → setiap perubahan `ai/` memicu laporan metrik (bukan menumpuk di akhir).
- Konektor berjalan di balik *feature flag* sampai lulus kriteria §3.0.

### 6.2 Tabel mingguan (A Backend Core · B AI/NLP · C FE Kandidat · D FE HR+DS · E Pipeline/QA/Evaluasi)

| Minggu | A | B | C | D | E | Milestone |
|---|---|---|---|---|---|---|
| **1** | Scaffold API, config, migrasi, health | Spike embedder + taksonomi v0 | Tokens + landing statis | Shells 3 peran + DS komponen inti | Docker Compose, CI, formulir consent + rekrut volunteer | |
| **2** | Auth + JWT + RBAC dasar | Parser PDF v0 (teks+segmentasi) | Auth UI (login/register + demo persona) | DS lanjutan (table, chips, score ring) | **Freeze kontrak OpenAPI**; fixture framework | |
| **3** | CRUD lowongan + lifecycle states | Taksonomi v1 + ekstraksi entitas v1 | Profil + upload CV UI | Form buat lowongan (60/40) + tabel kelola | Seed data v0; golden set v0 (10 CV sintetis) | **M1: platform dapat dijelajahi end-to-end (data seed)** |
| **4** | Pencarian + katalog eksternal (baca) | Embedder + scorer v1 + chunking | Search + detail job | Search/detail UI (layar baru) + review ekstraksi UI | Harness evaluasi; probe→implementasi RemoteOK v0 | |
| **5** | Applications core + status machine | Matching API + cache + kalibrasi cosine (Tahap 1) | Kompatibilitas + rekomendasi UI | Peringkat kandidat UI | Remotive v0 + normalisasi/dedupe + upsert | |
| **6** | Status transisi + catatan + komparasi API | Explainer (evidence, narasi template) + gap engine | Lamaran Saya + apply flow | Detail kandidat + komparasi 2 arah | Lifecycle tests (deadline, 3-miss, failed-run) | **M2: matching tampil di kedua peran** |
| **7** | Versioning CV + endpoint optimasi | Adapter Groq + prompt + validator grounding | Review optimasi UI (diff per-edit) | Skill gap UI (2 peran, 1 komponen) | Golden set: sprint anotasi #1 | |
| **8** | Dashboard agregat + audit log | Kalibrasi bobot (Tahap 2) + re-embed | Ekspor PDF + polish optimasi | Dashboard UI | GH Actions live (staging) + run monitor | **M3: optimasi + ingestion berjalan, evaluasi v1** |
| **9** | Security pass (RBAC audit, file streaming) | Grounding audit + perbaikan + eval ekstraksi | Empty/error states | Responsive + empty states | Dedupe audit + laporan kualitas run | |
| **10** | Bugfix + perf pass (NFR-1..4) | **Evaluasi penuh #1** (nDCG, ρ, F1, groundedness) | UAT peran kandidat + bugfix | UAT peran HR + bugfix | EVALUATION.md draft + demo script | |
| **11** | Hardening akhir + freeze | Perbaikan dari evaluasi; freeze `model_version` | Polish akhir | Polish akhir | Golden set run #2 + laporan final metrik | **M4: feature freeze** |
| **12** | Dukungan demo | Dukungan demo | Rehearsal demo | Rehearsal demo | Rehearsal + submission package (docs, laporan) | **Submission** |

### 6.3 Milestone & kriteria kelulusan

| Milestone | Akhir | Kriteria |
|---|---|---|
| M1 | M3 | Register/login kedua peran; lowongan seed bisa dilihat & dicari; CI hijau |
| M2 | M6 | Kandidat: upload→review→rekomendasi→kompatibilitas; HR: peringkat + detail + status; kompatibilitas terhadap golden set v0 diukur pertama kali |
| M3 | M8 | Optimasi LLM end-to-end dengan approval; ingestion 2 konektor berjalan terjadwal; metrik evaluasi v1 tercetak |
| M4 | W11 | Feature freeze; security pass lulus; laporan evaluasi final; demo script teruji 2× |

### 6.4 Risiko yang diperbarui oleh pemeriksaan ini

| Risiko baru/terkonfirmasi | Dampak | Mitigasi |
|---|---|---|
| Volume Remotive kecil (11/job-bulan terobservasi) | Katalog eksternal tipis | RemoteOK (99/jendela) + Arbeitnow (300/hal) sebagai volume; seed ID untuk konteks lokal; investigasi param Remotive di P7 |
| Cakupan Indonesia dari sumber global ≈ 0–2% | Relevansi lokal rendah | Sudah diantisipasi F3/F7: provenance badge + seed berlabel + Adzuna/Jooble sebagai jalur perbaikan |
| Kuota/rate-limit Groq free tier di tengah demo | Fitur optimasi tak tersedia saat demo | 1 panggilan/generasi + cache + mode "coba lagi"; generate sebelum demo (hasil tersimpan di `cv_optimizations`) |
| Kapasitas tim riil < 3,5 hari/minggu | Jadwal geser | Cut lever §2.4 (urutan disetujui); minggu 10–12 berisi buffer fungsi |
| Agreement rater rendah (κ < 0.6) | Metrik matching lemah kredibilitas | Sesi kalibrasi rubrik; laporkan apa adanya; perbaiki rubrik lalu ulang — prosesnya sendiri bernilai akademik |

---

## 7. Checklist Persetujuan Final

| # | Butir | Status |
|---|---|---|
| 1 | F1–F7 (Groq, embedding configurable, validasi sumber, deferral builder/bulk, pricing tidak diprioritaskan, deployment lokal, metrik riil) | ☐ Disetujui |
| 2 | Penyederhanaan wajib §2.3 + total 165 pd | ☐ Disetujui |
| 3 | Konektor MVP = RemoteOK + Remotive; Arbeitnow opsional; Adzuna/Jooble tertunda | ☐ Disetujui |
| 4 | Protokol kalibrasi + golden set + rubrik 0–3 (§4) | ☐ Disetujui |
| 5 | Mekanisme privasi & RBAC (§5), termasuk "HR tidak melihat draft optimasi" | ☐ Disetujui |
| 6 | Roadmap 12 minggu + pembagian 5 workstream (§6) | ☐ Disetujui |
| 7 | **Mulai P0 (scaffold + Docker Compose + CI) dan P1 (auth)** | ☐ Setujui mulai / ☐ Tunda |

---

*Setelah butir 7 disetujui, langkah pertama implementasi adalah P0 sesuai §6.2 Minggu 1. Semua klaim kemampuan pipeline/konektor akan tetap dirilis mengikuti kriteria pengujian §3.0, bukan rencana.*
