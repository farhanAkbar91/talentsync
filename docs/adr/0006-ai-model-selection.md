# ADR 0006 — Pemilihan Model AI (LLM Groq & Embedding Multilingual)

**Status:** Diterima (P3.0, 6 November 2026; keputusan pemilik proyek #3 & #5)

## 1. Konteks

M8 (CV Optimization) adalah satu-satunya modul P3 yang memakai LLM (blueprint §6,
"deterministik-first"; parsing/diagnosis/scoring tetap Python murni). Kebutuhan:
JSON ketat, grounded generation (anti-fabrikasi), kualitas ID/EN, biaya rendah,
rate-limit friendly (desain: 1 panggilan per generasi + cache). Model embedding
(M3) harus multilingual ID/EN dan muat di laptop CPU.

Katalog Groq diverifikasi live (GET /models, kunci akun) dan dibenchmark nyata
(`backend/scripts/benchmark_groq_models.py`, CV sintetis ID + jebakan fabrikasi;
`benchmark_results.json`).

## 2. LLM — Keputusan

| Peran | Model | Alasan |
|---|---|---|
| **Utama** (`GROQ_MODEL`) | `openai/gpt-oss-120b` | Benchmark live terbaik: json_schema penuh (strict:false & strict:true), ekstraksi lengkap (5 skills), **0 fabrikasi**, ±2,3 dtk; Production tier; termurah ($0.15/$0.60 per 1M) |
| **Fallback** (`GROQ_MODEL_FALLBACK`) | `openai/gpt-oss-20b` | Keluarga sama, strict:true juga, tercepat (±1,2 dtk), 0 fabrikasi; berbeda kuota dari 120b |

Ditolak / tidak dipilih:
- `qwen/qwen3.8-27b` (kandidat awal di .env): berfungsi tapi benchmark paling
  lemah — melewatkan bagian KEAHLIAN (skills=0) pada ekstraksi, sempat 429 pada
  panggilan ke-2 dalam ~1 menit, dan berstatus **Preview** (risiko deprecation).
- `allam-2-7b`: **fabrikasi terdeteksi** (menambah 'Tableau' yang tidak ada di CV)
  + halusinasi jumlah pengalaman → diskualifikasi untuk M8.
- `llama-3.3-70b-versatile` / `llama-3.1-8b-instant`: **tidak tersedia di akun**
  (kelas Llama kini enterprise-only di Groq) — fallback awal yang direkomendasikan
  berbasis docs direvisi sesuai katalog aktual.

Batas aktual akun (header `x-ratelimit-*`): **RPD 1.000, TPM 8.000** — aman untuk
desain 1 panggilan/generasi; 131k context jauh melebihi kebutuhan (CV ±2–4k token).

Adapter LLM (M8) wajib: strict json_schema di model utama; fallback otomatis ke
`GROQ_MODEL_FALLBACK` pada 429/5xx + validasi Pydantic + retry sesuai
`retry-after`; key kosong = fitur LLM nonaktif (test memakai mock).

## 3. Embedding — Keputusan

Kandidat dibenchmark empiris pada golden set sintetis berlabel
(`scripts/benchmark_embedding_models.py`, pasangan CV-job ID/EN):

1. `intfloat/multilingual-e5-small` — 384 dim, konteks **512 token**, kualitas
   retrieval multilingual umumnya di atas baseline; wajib prefix `query:`/`passage:`.
2. `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` — 384 dim,
   konteks 128 token (baseline blueprint).

**Kriteria pembekuan:** gap cosine positif-vs-negatif, akurasi threshold,
overlap distribusi, latensi per teks pada CPU.

**Hasil benchmark (6 Nov 2026, 12 CV × 30 jobs, 84 pasangan berlabel,
cosine pasangan positif label≥2 vs negatif label≤1):**

| Model | cos pos | cos neg | Gap | Overlap (pos_min vs neg_max) | Acc @mid | Latensi (ms/teks) |
|---|---|---|---|---|---|---|
| **paraphrase-multilingual-MiniLM-L12-v2** ⭐ | 0,759 ±0,001 | 0,453 ±0,074 | **0,306** | 0,757 vs 0,561 (bersih) | 1,00 | 55–58 |
| multilingual-e5-small | 0,916 ±0,012 | 0,854 ±0,015 | 0,062 | 0,902 vs 0,874 (tipis) | 1,00 | 60–98 |

Kedua model akurat sempurna pada corpus sintetis, tetapi **MiniLM memberikan
margin separasi ±5× lebih lebar** dan sedikit lebih cepat — lebih aman untuk
anchor kalibrasi Tahap 1 (docs/03 §4.2). e5 menunjukkan kompresi skor
(anisotropi) yang membuat threshold kalibrasi rapuh bila data berubah.

**Keputusan: `EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
(dibekukan).** Catatan jujur: corpus sintetis relatif mudah; e5 (512-token ctx)
boleh diuji ulang saat kalibrasi dengan CV volunteer yang lebih panjang/berat —
`EMBEDDING_MODEL` bersifat configurable, keduanya 384-dim sehingga swap tidak
menuntut migrasi. Detail: `eval/reports/embedding_benchmark.json`.

## 4. Konfigurasi env (tanpa secret)

```
GROQ_MODEL=openai/gpt-oss-120b
GROQ_MODEL_FALLBACK=openai/gpt-oss-20b
EMBEDDING_MODEL=<pemenang benchmark §3>
EMBEDDING_DIM=384
MATCH_WEIGHTS=0.40,0.30,0.20,0.10   # prior Tahap 0 (docs/03 §4.2), kalibrasi menyusul
```
