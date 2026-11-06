# ADR 0008 — Engine Embedding, Skor Kompatibilitas & Skill Gap (M3–M5)

**Status:** Diterima (Wave 3, 7 November 2026)

## 1. Konteks

M3–M5 membentuk inti matching: vektor semantik (M3), skor komposit
explainable (M4), dan skill gap (M5). Keputusan blueprint (bobot 40/30/20/10,
MiniLM, kalibrasi 3 tahap) tetap mengikat; ADR ini membekukan keputusan
implementasi yang muncul saat Wave 3 — termasuk temuan security review.

## 2. Keputusan

### 2.1 Embedding (M3)
- **Singleton lazy + thread-safe**: `get_embedder` memakai double-checked
  locking (thread pre-warm startup vs request pertama tidak boleh double-load
  torch — terverifikasi). **Pre-warm startup**: memuat model + SATU inferensi
  dummy (biaya ±30 dtk ada di lazy-init inferensi, bukan load) — thread di
  produksi; **sinkron** saat `EMBEDDING_PREWARM_SYNC=true` (dipakai E2E agar
  deterministic).
- **Teks berlabel Indonesia** (`build_cv_text`/`build_job_text` — RINGKASAN/
  PENGALAMAN/KEAHLIAN/…) agar sinyal section konsisten antar dokumen; chunk
  ≤480 char (word-boundary) → mean pool → L2.
- **Hanya CV terkonfirmasi** yang di-embed (hard gate); embed saat konfirmasi
  CV dan publikasi/update lowongan; upsert per (doc, model, text_kind);
  baris model lama dipertahankan (swap model = re-embed via
  `scripts/reembed_embeddings.py`, guard anti-tulis-Supabase tanpa `--yes`).
- **SAVEPOINT**: kegagalan tulis embedding di-roll-back sendiri — transaksi
  konfirmasi/publikasi utama tetap sehat.
- **Batas ukuran (security audit)**: `MAX_DOCUMENT_CHARS = 20_000` pada kedua
  build_text — payload hasil konfirmasi kandidat tidak berbatas.

### 2.2 Skor komposit (M4)
- Formula frozen (docs/03 §4.1): F_skill 0.6·Cov_req+0.4·Cov_pref (kelas
  kosong netral), kredit exact/alias 1.0 · related (edge taksonomi) 0.5 ·
  0.0; F_exp = 0.6·min(have,req)/req + 0.4·cosine(judul, judul-lowongan);
  F_edu ordinal 100/90/55/25; F_semantic via kalibrasi.
- **years_req**: regex deskripsi+requirements → fallback peta `seniority`
  (default 3). **education_req**: regex → fallback S1. (Lowongan belum punya
  kolom tersendiri — diangkat bila form HR membutuhkan field eksplisit.)
- **Kalibrasi Tahap 1 dibekukan (v1.1)**: anchor piecewise-linear
  0,4509→30 · 0,7327→85 — dari distribusi cosine golden set sintetis
  (median positif/negatif; `eval/reports/calibration.json`). **Grid search
  Tahap 2 report-only**: bobot prior [40,30,20,10] terbukti optimal pada set
  validasi → tidak diubah (anti-overfit sintetis).
- `model_version` = `m4v1|emb:minilm-l12-v2|w:40-30-20-10|cal:v1.1` (≤60
  char; nama model penuh tersimpan di kolom `model` tabel embedding).
- **Cache vektor judul** (`cv_title_vecs`): vektor judul pengalaman dihitung
  sekali per CV dan di-inject ke `score_pair` — benchmark 500 pasangan
  9,34 dtk → **0,81 dtk** (46×), hasil identik. Fallback encode per-item
  dipertahankan untuk panggilan langsung.
- Persist `match_results` per (cv, job, model_version) + invalidasi saat
  konfirmasi CV / update lowongan. M6 (rekomendasi) akan memakai KNN
  pgvector + re-rank faktor yang sama.

### 2.3 Skill gap (M5)
- Sumber: `missing` dari M4 — severity frozen: required tanpa kredit related
  = **kritis**; required hanya related = **menengah**; preferred = **minor**.
- Matrix per kategori taksonomi (target/candidate/delta/status met/gap/
  surplus); **saran belajar statis** dari `learning_resources.json` (12
  kategori × 3 sumber gratis terkemuka) — dilarang marketplace kursus dinamis
  (docs/08 M5 risiko scope creep).

### 2.4 Security (audit Wave 3)
- **HIGH ReDoS diperbaiki**: regex years_req dibatasi (`\d{1,4}`, whitespace
  ≤3) + scan cap 4.000 char → 34,6 dtk → 3,1 ms pada input adversarial.
- MEDIUM: batas ukuran dokumen (2.1); LOW tercatat: tanpa negative-cache
  kegagalan embed, tanpa rate limiting endpoint match — dirujuk ke M6+.

## 3. Konsekuensi & keterbatasan
- Evaluasi pada korpus **sintetis in-domain** (nDCG@10 0,9425, Spearman
  0,8663 — target 0,75/0,60): bukan performa produksi; kalibrasi final butuh
  golden set volunteer (docs/03 §4.2 Tahap 2 dengan label manusia).
- P@5 0,60 = plafon struktur golden set (3 relevan/7) — dilaporkan apa adanya.
- Encode inferensi sinkron di thread-pool request (MVP); rate limiting dan
  antrian tugas = keputusan fase berikutnya bila skala menuntut.
