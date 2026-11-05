# TalentSync AI — Decision Review & Scope Finalization

**Dokumen:** v0.1 — untuk review & persetujuan (bukan blueprint baru)
**Referensi:** `docs/01-technical-blueprint.md` (tidak diubah oleh dokumen ini)
**Status:** Menunggu persetujuan D1–D17 sebelum implementasi
**Tanggal:** 4 November 2026

---

## 1. Ringkasan Eksekutif Blueprint

TalentSync AI direncanakan sebagai **modular monolith** dengan tiga bagian yang berbagi satu kode dan satu database:

1. **API backend** — FastAPI + SQLAlchemy + PostgreSQL (+pgvector), melayani SPA React/Vite/TypeScript sesuai desain Figma.
2. **Mesin AI lokal** — (a) ekstraksi CV PDF secara deterministik (PyMuPDF + taksonomi skill bilingual ID/EN + regex) dengan **review koreksi oleh pengguna** sebelum dipakai matching; (b) **semantic matching multi-faktor yang transparan** (semantic 40% · skill coverage 30% · pengalaman 20% · pendidikan 10%) berbasis `paraphrase-multilingual-MiniLM-L12-v2` yang berjalan di CPU tanpa biaya; (c) **optimasi CV berbasis LLM yang ter-grounding** — setiap saran wajib merujuk konten CV asli (`source_ref`), divalidasi anti-fabrikasi, dan hanya diterapkan setelah persetujuan per-edit pengguna (CV asli tidak pernah diubah; hasil disimpan sebagai versi baru).
3. **Pipeline ingestion terjadwal** — konektor Python hanya ke sumber yang **diizinkan** (RemoteOK, Remotive, Arbeitnow, opsional Adzuna/Jooble; **tanpa scraping** Jobstreet/Glints/LinkedIn), dengan normalisasi, dedupe, upsert, siklus hidup lowongan (`posted_at/closing_at/last_seen_at`, aturan 3-kegagalan berturut, soft delete), logging per-run, dijalankan GitHub Actions cron + Windows Task Scheduler.

**Posisi inovasi akademik** (bukan algoritme baru, melainkan integrasi sistem yang terukur): (1) matching semantik + skill gap yang *explainable* untuk dua peran sekaligus, (2) LLM yang dipakai *aman* pada dokumen faktual dengan jejak audit, (3) data engineering siklus hidup end-to-end, (4) loop rekrutmen ganda peran yang utuh. Efektivitasnya diukur dengan rencana evaluasi (nDCG/Spearman terhadap penilaian manusia, F1 ekstraksi, audit groundedness, metrik pipeline) yang menggantikan angka marketing di desain dengan **metrik hasil pengukuran nyata**.

**Angka kunci:** tim 5 orang, target **±12 minggu**, anggaran **Rp0**, MVP terdefinisi tegas (§8.1 blueprint), 17 keputusan terbuka (D1–D17) yang direview di dokumen ini — **10 di antaranya harus dikunci sebelum baris kode pertama**.

---

## 2. Tabel Keputusan D1–D17

Kolom dampak menggunakan skala: Kompleksitas (rendah/sedang/tinggi) · Waktu (dampak terhadap jadwal ±12 minggu) · Biaya (Rp0 kecuali disebutkan).

| ID | Topik | Rekomendasi | Alternatif tersedia | Dampak (Kompleksitas · Waktu · Biaya) | Kapan harus diputuskan |
|---|---|---|---|---|---|
| **D1** | Bahasa UI | UI **Bahasa Indonesia** (sesuai Figma); kode & dokumen Inggris | i18n ID+EN sejak awal | i18n: kompleksitas **sedang** (seluruh string dibungkus) · +1–2 minggu · Rp0 | **Sekarang (Critical)** — menempel di semua layar sejak hari pertama; menunda = rework besar |
| **D2** | Format file CV | **PDF saja** di MVP (sesuai brief) | PDF+DOCX sekarang (desain Figma menampilkan DOCX/ZIP) | DOCX: parser modul baru (python-docx) · +1–2 minggu · Rp0 | **Sekarang (Critical)** — menentukan UI upload & arsitektur parser; DOCX tetap terbuka sebagai penambahan pasca-MVP |
| **D3** | Penyedia LLM (optimasi CV) | Adapter agnostik; default **free-tier** (Google Gemini Flash atau Groq) — tim mendaftarkan & memiliki kunci | OpenAI/Anthropic berbayar; Ollama lokal | Adapter: kompleksitas **rendah** · minimal · Rp0 (kuota free tier terbatas) | **Sekarang (Critical)** — registrasi kunci + desain prompt + kontrak JSON bergantung padanya; *pilihan penyedia bisa ditukar belakangan, keputusan "pakai adapter + free tier" tidak* |
| **D4** | Model embedding | `paraphrase-multilingual-MiniLM-L12-v2` lokal (384-dim, ID+EN, CPU) | mpnet-multilingual (lebih berat), LaBSE, IndoSBERT, embedding API | Lokal: **Rp0**, ±0,5 GB, CPU ok · dimensi **384 terkunci di skema DB**; API = biaya per-call + privasi data CV | **Sekarang (Critical)** — dimensi vektor tersimpan permanen di DB; model bisa dievaluasi ulang (P8) tanpa mengubah skema |
| **D5** | Whitelist sumber ingestion | RemoteOK + Remotive + Arbeitnow (+Adzuna/Jooble jika cakupan ID terverifikasi); **tanpa scraping** portal besar; dataset sintetis Indonesia berlabel jelas | Board perusahaan (Greenhouse/Lever) sebagai sumber ke-3; RSS-only | Kompleksitas **rendah–sedang** · ±2 minggu (P7) · Rp0 · **menghilangkan risiko hukum** | **Sekarang (Critical)** — menyangkut legalitas, kredibilitas akademik, dan desain konektor |
| **D6** | Penyimpanan vektor | **pgvector** via image Docker resmi | JSONB + numpy di memori aplikasi | pgvector: kompleksitas **rendah** (1 image) · ±0 · Rp0; JSONB cukup untuk ≤1rb job tapi logika filtering pindah ke Python | **Sekarang (Critical)** — tipe kolom DB; fallback JSONB tetap terbuka bila ada kendala |
| **D7** | Google OAuth | **Tunda pasca-MVP**; sembunyikan tombol di MVP | Bangun sekarang (perlu proyek Google Cloud) | Bangun: +±1 minggu + setup kredensial; tunda: Rp0 | **Konfirmasi penundaan: sekarang;** implementasi menyusul (Important) |
| **D8** | Unggah CV massal oleh HR (desain Figma ada) | **Tunda pasca-MVP**; MVP = pelamar mengunggah CV sendiri | Sertakan unggah CV tunggal per lowongan (versi mini) | Sertakan: +1,5–2 minggu + alur privasi (CV milik orang tanpa akun) · kompleksitas **sedang–tinggi** | **Sekarang (Critical)** — item scope terbesar setelah CV Builder |
| **D9** | Halaman pricing | Konten **statis**, tanpa pembayaran | Hilangkan dari MVP | Statis: kompleksitas **sangat rendah** · ±0,5 hari · Rp0 | **Bisa menunda** (Optional — saat polish P8) |
| **D10** | Format ekspor CV hasil optimasi | **PDF** via ReportLab (gaya Harvard sesuai desain) | + DOCX via python-docx | PDF: ±2–3 hari; DOCX tambahan: +2–3 hari · Rp0 | PDF = default sekarang; **keputusan DOCX bisa menunda** (saat P6) |
| **D11** | Dark mode | **Light-only** MVP; token CSS disiapkan untuk dark | Rilis dark (desain ada untuk ±6 halaman) | Dark: +1–2 minggu (token & pengujian komponen dobel) · Rp0 | **Konfirmasi penundaan: sekarang (sebelum P2 frontend)** |
| **D12** | Target deployment demo | **Docker Compose lokal** sebagai utama; opsional cloud free-tier (Neon + Render/Railway) bila waktu sisa | Cloud-only sejak awal | Cloud: setup 1–2 hari + risiko free tier (spin-down, kuota); lokal: Rp0 | **Bisa menunda** (paling lambat awal P8) |
| **D13** | Klaim marketing di UI (94.8%, "10 detik", dst.) | Ganti dengan **metrik hasil evaluasi riil**; label engine memakai versioning sendiri | Biarkan copy statis + disclaimer | Evaluasi memang deliverable akademik; eksekusi di P8 · ±1 hari penerapan | Prinsip: sekarang; **eksekusi bisa menunda** (P8) |
| **D14** | Cara melamar job eksternal | Job hasil ingestion **out-link** ke situs sumber; apply in-platform **hanya** untuk job yang diposting HR | "Intent-to-apply" untuk job eksternal (tercatat di platform) | Intent-to-apply: +alur & skema baru · kompleksitas **sedang**; out-link: rendah | **Sekarang (Critical)** — memengaruhi skema `applications` & UX kandidat |
| **D15** | Navigasi HR kanonik | Gabungkan 3 varian sidebar: Dashboard · Kelola Lowongan · Peringkat & Kecocokan · Analisis Skill Gap · Portal Pekerjaan · Pengaturan | Pertahankan varian B (PDF Fig. 1.7) | Kompleksitas **sangat rendah** · ±0,5 hari · Rp0 | **Sekarang** sebelum frontend P2 (Important) |
| **D16** | CV Builder dari nol (wizard 7 langkah) | **Tunda pasca-MVP**; MVP = unggah → ekstraksi → optimasi (memakai stack gap+LLM yang sama) | Bangun wizard sekarang | Wizard: +2–3 minggu · kompleksitas **tinggi** (editor + preview ATS + template) | **Sekarang (Critical)** — penundaan ini membebaskan ±3 minggu untuk kualitas matching & evaluasi |
| **D17** | Konfirmasi fitur di luar MVP | Messaging, penjadwalan interview, pusat notifikasi, market-gap analytics, talent-pool stats, kuota metering = **pasca-MVP** | Promosikan fitur tertentu ke MVP | Setiap fitur: +1–3 minggu | **Sekarang (Critical)** — penguncian scope, risiko jadwal #1 untuk tim mahasiswa |

---

## 3. Pengelompokan Prioritas

### 🔴 Critical — harus diputuskan sebelum implementasi (10)

Keputusan yang **mengunci skema database, arsitektur AI, posisi legal, atau batas scope**. Menundanya berarti rework.

| ID | Keputusan yang dikunci |
|---|---|
| D1 | UI Bahasa Indonesia |
| D2 | CV: PDF-only di MVP |
| D3 | LLM via adapter + free-tier (siapa pemegang kunci) |
| D4 | Model embedding lokal 384-dim (dipatriakan di DB) |
| D5 | Whitelist sumber ingestion & larangan scraping |
| D6 | pgvector |
| D8 | Tunda unggah CV massal HR |
| D14 | Apply eksternal = out-link |
| D16 | Tunda CV Builder wizard |
| D17 | Daftar fitur pasca-MVP disetujui (scope lock) |

### 🟡 Important — bisa diputuskan selama pengembangan (5, dengan tenggat)

| ID | Keputusan | Tenggat terlambat |
|---|---|---|
| D7 | Konfirmasi "Google OAuth ditunda" | Sebelum P1 (satu kalimat cukup) |
| D15 | Navigasi HR kanonik | Sebelum P2 (layar HR pertama) |
| D11 | Konfirmasi "light-only" | Sebelum P2 (fondasi token) |
| D10 | Tambah DOCX untuk ekspor atau tidak | Awal P6 |
| D12 | Deployment demo (lokal vs cloud free-tier) | Awal P8 |

### 🟢 Optional — bisa ditunda ke fase berikutnya (2)

| ID | Keputusan | Catatan |
|---|---|---|
| D9 | Pricing statis | Kosmetik; diputuskan saat polish P8 |
| D13 (eksekusi) | Penerapan metrik riil di UI | Prinsip sudah jelas; pelaksanaannya menyusul laporan evaluasi |

---

## 4. Scope MVP: Wajib vs Ditunda

Prinsip penyaringan: (a) apakah fitur **menopang klaim inovasi akademik** yang akan dievaluasi? (b) apakah fitur **prasyarat loop kerja** yang didemokan? (c) biaya vs sisa waktu tim 5 orang.

### ✅ Wajib masuk MVP

| # | Fitur | Alasan akademik/teknis | Fase |
|---|---|---|---|
| 1 | Auth + peran + akun demo (Dewi/Sarah) | Prasyarat semua demo & penilaian; ada di desain (login) | P1 |
| 2 | Profil kandidat + perusahaan | Entitas dasar sistem informasi | P1 |
| 3 | Upload CV PDF → ekstraksi → **review & koreksi pengguna** | Inti pipeline AI #1; human-in-the-loop adalah bagian dari cerita (desain Figma pun punya "Input Manual") | P3 |
| 4 | CRUD lowongan internal (skill berbobot 60/40, batas akhir, siklus hidup) | Basis data latihan matching + alur HR inti | P2 |
| 5 | Pencarian + detail lowongan (termasuk job eksternal ber-badge sumber) | Prasyarat rekomendasi & apply; layar baru (Figma hanya punya nav-nya) | P2 |
| 6 | **Matching multi-faktor + explainability** (faktor, matched/missing skills, bukti, narasi) | **Inovasi inti #1** — diuji dengan nDCG/Spearman | P4 |
| 7 | **Analisis skill gap** (matriks target vs kandidat, severity, rekomendasi belajar) | Diferensiasi utama vs ATS keyword; diminta eksplisit di proposal | P4 |
| 8 | Rekomendasi lowongan untuk kandidat (+ alasan kecocokan) | Nilai terlihat langsung bagi pengguna; turunan langsung matching | P4 |
| 9 | Peringkat kandidat untuk HR + perbandingan 2–3 kandidat + detail kandidat | Sisi ganda dari mesin yang sama — bukti integrasi sistem | P4–P5 |
| 10 | Applications + pelacakan status (kandidat) + pipeline status (HR) + catatan | Menutup loop rekrutmen end-to-end | P5 |
| 11 | **Optimasi CV ter-grounding LLM** + review per-edit + versioning + ekspor PDF | **Inovasi inti #2** — diuji dengan audit groundedness (target: 0 fabrikasi) | P6 |
| 12 | **Ingestion ≥2 konektor** + normalisasi/dedupe/upsert/expire + log + penjadwalan | **Inovasi inti #3** — data engineering siklus hidup; aturan 3-kegagalan wajib teruji | P7 |
| 13 | Dashboard HR dengan agregat **dihitung nyata** | Menggantikan angka mock di desain (D13) | P5 |
| 14 | Landing page statis + label provenance data | Wajah produk + kejujuran sumber data | P8 |
| 15 | Dataset seed + **skrip evaluasi** (golden set, laporan metrik) | Bukan pelengkap: ini deliverable akademik yang menghasilkan angka untuk laporan | P3–P8 |

### ⏸️ Sebaiknya ditunda (pasca-MVP)

| Fitur | Alasan penundaan |
|---|---|
| DOCX & ZIP + unggah CV massal HR (D2/D8) | PDF menutup loop inti; alur batch = pipeline kedua + isu privasi CV tanpa akun |
| CV Builder wizard 7 langkah (D16) | Tumpang tindih dengan alur optimasi; permukaan editor terbesar di desain |
| Google OAuth (D7) | Setup + review vs nilai demo yang kecil |
| Dark mode (D11) | Menggandakan pekerjaan token/komponen; tidak menopang klaim inovasi |
| Pembayaran/pricing fungsional (D9) | Di luar scope akademik |
| Simulasi interview AI, marketplace materi pelatihan, talent-pool stats, market-gap analytics, kuota metering (D17) | Mengesankan tetapi periferal; kandidat "future work" di laporan |
| Messaging, pusat notifikasi, admin UI monitoring | Infrastruktur/polish, bukan inovasi |
| Dedupe lintas-sumber fuzzy | Cukup log-only di MVP |
| i18n EN, deployment cloud produksi | Nilai akademik rendah per jam kerja |

**Path demo minimum (semua klaim inovasi terlihat ±10 menit):**
kandidat: login demo Sarah → upload CV → review ekstraksi → lihat rekomendasi → buka kompatibilitas & skill gap → generate optimasi → setujui per-edit → ekspor PDF → lamar → cek status. HR: login demo Dewi → lihat dashboard → buka peringkat kandidat → bandingkan 2 kandidat → ubah status. Pipeline: jalankan ingestion manual → tunjukkan log run + lowongan baru + satu kasus expire.

---

## 5. Risiko Teknis Terbesar (fokus 4 area)

### 5.1 CV Parsing — risiko harian yang paling mungkin terjadi

| Aspek | Penilaian |
|---|---|
| Risiko | Variasi layout (1–2 kolom, tabel, heading tak standar), PDF hasil scan tanpa teks, format tanggal/bulan Indonesia ("Jan 2023 – Sekarang"), CV dwibahasa campur |
| Kemungkinan × Dampak | **Tinggi × Sedang** — hampir pasti ada CV yang parse-nya jelek |
| Dampak domino | Ekstraksi buruk → matching buruk → kredibilitas fitur inti runtuh di depan penguji |
| Mitigasi | Deterministik-first + **confidence flag per field**; **review & koreksi wajib** sebelum matching (sudah selaras dengan desain Figma: "Input Manual Profil"); fallback input manual; golden set 20–30 CV teranotasi (ID+EN) untuk mengukur F1; mode terdegradasi (matching skill-only bila struktur gagal) |
| Risiko sisa | **Sedang** — diterima, karena review manusia menjadi jaring pengaman yang justru jadi cerita desain |

### 5.2 Semantic Matching

| Aspek | Penilaian |
|---|---|
| Risiko | Kualitas embedding multilingual pada jargon kerja ID; konteks model pendek (±128 token → wajib chunking); kalibrasi skor (cosine mentah 0.5–0.8 → harus jadi 0–100 yang bermakna); bobot faktor dituning manual, bukan dipelajari |
| Kemungkinan × Dampak | **Sedang × Sedang–Tinggi** |
| Mitigasi | Arsitektur multi-faktor membatasi blast radius (semantic hanya 40%; skill coverage membawa sinyal eksak); konstanta kalibrasi tersimpan per `model_version` dan di-tune dengan golden set; jalur ganti model (mpnet/IndoSBERT) terjaga; **laporan evaluasi jujur** (nDCG/Spearman) alih-alih klaim |
| Risiko terkait | **Tidak ada ground truth di awal** — pelabelan manusia (tim + mahasiswa lain, dengan izin) perlu di-time-box; mulai kumpulkan golden set di P3, jangan tunggu P8 |
| Risiko sisa | Sedang — dapat dikelola dan, yang penting, **dapat didemonstrasikan proses pengukurannya** (nilai akademik positif) |

### 5.3 Integrasi LLM (optimasi CV)

| Aspek | Penilaian |
|---|---|
| Risiko | **Fabrikasi kredensial** (garis merah — CV dokumen faktual); pelanggaran skema JSON; kuota/rate-limit free tier habis di tengah demo; latensi; deprecation penyedia |
| Kemungkinan × Dampak | Fabrikasi: **Sedang × Kritis** · Kuota: Sedang × Sedang |
| Mitigasi | Kontrak `source_ref` wajib + validator allowlist entitas (perusahaan/sertifikasi/gelar harus ada di CV); **persetujuan per-edit wajib**; CV asli immutable + versioning; 1 panggilan per generasi + cache; adapter agnostik (ganti penyedia = ganti config); timeout/retry + status "coba lagi nanti"; audit sampel berkala |
| Risiko sisa | **Rendah–Sedang** — fabrikasi yang lolos sampai ekspor harusnya 0 berkat lapisan persetujuan; risiko yang tersisa adalah UX saat kuota habis |

### 5.4 Automated Job Ingestion

| Aspek | Penilaian |
|---|---|
| Risiko | **Legal (ToS)** — risiko reputasi terbesar bila melakukan scraping; dedupe salah gabung/salah pisah; perubahan skema API sumber; sumber down memicu salah-expire; keterbatasan Actions (jadwal di-pause setelah 60 hari repo tidak aktif) |
| Kemungkinan × Dampak | Legal: **rendah (by design) × Kritis** · Dedupe/skema: **Sedang × Sedang** |
| Mitigasi | Hanya sumber berizin + dokumentasi kepatuhan di laporan (posisi defensibel); kunci dedupe konservatif + `duplicate_of` + audit sampel manual; **isolasi run gagal** (run gagal tidak pernah mengubah status lowongan); aturan 3-kegagalan; kontrak test konektor dengan fixture rekaman; dataset sintetis ID berlabel `seed` untuk konteks lokal; commit keep-alive + trigger manual |
| Risiko sisa | Rendah–Sedang; risiko legal **dihilangkan oleh desain**, konsekuensinya katalog kurang "lokal" — ditutup dengan seed data + model out-link |

### 5.5 Risiko lintas-area yang paling mengancam jadwal

**Scope creep (R9)** — desain Figma sengaja lengkap/ambisius (builder, pricing, simulasi interview, dark mode). Tanpa scope lock (D16, D17, D8), jadwal 12 minggu tidak realistis. Mitigasi: daftar §4 menjadi kontrak; fitur baru masuk lewat persetujuan Anda, bukan keputusan teknis harian.

---

## 6. Rekomendasi Final Arsitektur & Teknologi

Rekomendasi blueprint **dipertahankan** — dan setelah review ini, saya tegaskan sebagai pilihan yang **paling realistis** untuk konteks: tim 5 mahasiswa, ±12 minggu, Rp0, butuh hasil yang bisa didemokan dan diukur.

| Lapisan | Pilihan | Kenapa paling realistis |
|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind, TanStack Query | Sesuai desain Figma; satu bahasa untuk kedua peran; ecosystem terbesar untuk troubleshooting cepat |
| Backend | FastAPI + Pydantic v2 + SQLAlchemy + Alembic (modular monolith) | Satu deployable; kontrak OpenAPI otomatis untuk kerja paralel 5 orang; Python menyatu dengan stack AI |
| Database | PostgreSQL 16 + **pgvector** (image Docker) | Satu DB untuk data relasional + vektor; tanpa layanan baru; fallback JSONB tersedia |
| Embedding | `paraphrase-multilingual-MiniLM-L12-v2` lokal, CPU | Rp0, offline (demo aman), ID+EN satu model, ±0,5 GB; hanya 40% dari skor akhir sehingga kualitas "cukup baik" melebihi kebutuhan |
| Ekstraksi | PyMuPDF + taksonomi bilingual + regex (+review UI) | Deterministik, gratis, dapat diuji; LLM tidak dipakai untuk parsing di MVP |
| LLM | Adapter agnostik, default free-tier (Gemini Flash / Groq) | Biaya nol, tanpa lock-in; grounding + approval menutup risiko fabrikasi |
| Pipeline | Skrip Python (requests/BeautifulSoup/feedparser) + GitHub Actions cron + Task Scheduler | Tanpa Airflow/Kafka/Spark — tidak ada kebutuhan teknis nyata di skala ≤1rb lowongan |
| Ekspor | ReportLab (PDF, template Harvard-ish) | Lisensi permisif, murni Python |
| DevOps | Git, Docker Compose (web+api+db), GitHub Actions CI | `docker compose up` = demo portabel; CI gratis untuk repo publik |

### Yang secara sadar TIDAK direkomendasikan (anti-rekomendasi)

Microservices · Kubernetes · Airflow/Kafka/Spark · message broker (Celery+Redis) · vector DB terpisah (Qdrant/Milvus) · fine-tuning model · OCR cloud berbayar · WebSocket real-time · pembayaran — masing-masing menambah biaya operasional/koordinasi tanpa kebutuhan yang terbukti pada skala MVP.

### Dua saran proses (bukan perubahan blueprint)

1. **Kumpulkan golden set sejak P3** (bukan P8) — setiap kali ada CV uji, langsung masuk anotasi; evaluasi tidak menumpuk di akhir.
2. **Skrip evaluasi hidup sejak P4** — setiap perubahan `ai/` memicu laporan metrik, sehingga angka untuk laporan akhir terkumpul otomatis.

---

## 7. Checklist Persetujuan

Mohon isi kolom **Keputusan** (`Setuju` / `Ubah: …`) untuk tiap baris. Critical wajib lengkap sebelum implementasi dimulai.

| ID | Keputusan (ringkas) | Prioritas | Keputusan Anda | Catatan |
|---|---|---|---|---|
| D1 | UI Bahasa Indonesia | 🔴 Critical | | |
| D2 | CV PDF-only di MVP | 🔴 Critical | | |
| D3 | LLM adapter + free-tier (Gemini/Groq) | 🔴 Critical | | |
| D4 | Embedding lokal MiniLM 384-dim | 🔴 Critical | | |
| D5 | Whitelist sumber berizin, tanpa scraping | 🔴 Critical | | |
| D6 | pgvector | 🔴 Critical | | |
| D7 | Google OAuth ditunda | 🟡 Important | | |
| D8 | Unggah CV massal HR ditunda | 🔴 Critical | | |
| D9 | Pricing statis | 🟢 Optional | | |
| D10 | Ekspor PDF (DOCX opsional) | 🟡 Important | | |
| D11 | Light-only MVP | 🟡 Important | | |
| D12 | Deployment lokal utama | 🟡 Important | | |
| D13 | Metrik riil menggantikan klaim marketing | 🟢 Optional | | |
| D14 | Job eksternal = out-link apply | 🔴 Critical | | |
| D15 | Navigasi HR kanonik (gabungan varian) | 🟡 Important | | |
| D16 | CV Builder ditunda | 🔴 Critical | | |
| D17 | Daftar fitur pasca-MVP dikunci | 🔴 Critical | | |

**Setelah review ini disetujui:** langkah berikutnya adalah kick-off **P0** (scaffold repo, Docker Compose, CI, migrasi awal) + **P1** (auth & profil). Tidak ada kode yang ditulis sebelum persetujuan Anda.

---

*Dokumen review ini tidak mengubah `docs/01-technical-blueprint.md`; keduanya bersama-sama menjadi baseline untuk implementasi.*
