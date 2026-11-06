# EVALUATION — TalentSync AI (AI Engine M1–M9)

> Semua angka di bawah adalah hasil pengukuran nyata pada korpus **sintetis
> in-domain** (`eval/golden/`, 12 CV + 30 job + 84 pasangan berlabel rubrik
> 0–3) kecuali yang ditandai live. **Bukan performa produksi** — evaluasi CV
> volunteer menyusul (docs/03 §4.4). Dataset version: golden-manifest
> 2026-11-06; taxonomy v1.1.0; model_version `m4v1|emb:minilm-l12-v2|w:40-30-20-10|cal:v1.1`.

## 1. Ekstraksi CV (M1) — target F1 ≥ 0,80

| Field | F1 |
|---|---|
| nama / email / telepon | 1,000 |
| skills (set-F1) | 1,000 |
| pengalaman / pendidikan / sertifikasi (recall) | 1,000 |
| **Macro F1** | **1,000** — LULUS |

Keterbatasan: korpus dari template yang sama dengan target parser.
Skrip: `backend/scripts/evaluate_extraction.py` → `eval/reports/extraction_evaluation.json`.

## 2. Skill Extraction & Normalization (M2) — target F1 ≥ 0,85; canon ≥ 0,90

| Metrik | Hasil | Target |
|---|---|---|
| Extraction F1 (macro) | **0,980** | ≥ 0,85 ✅ |
| Canonicalization accuracy | **0,923** | ≥ 0,90 ✅ |
| Adversarial false-map (java≠javascript, react≠react-native, dst.) | **0** | 0 ✅ |
| Idempotensi normalisasi + seed | **lulus** | — |
| Duplicate rate | **0,000** | 0 ✅ |

Taksonomi: 352 canonical, 610 alias, 21 kategori (v1.1.0).
Skrip: `backend/scripts/evaluate_skills.py` → `eval/reports/skills_evaluation.json`.

## 3. Matching & Rekomendasi (M3–M4, M6) — target nDCG@10 ≥ 0,75; ρ ≥ 0,60

| Metrik | Hasil |
|---|---|
| nDCG@10 (macro, 12 CV) | **0,9425** ✅ |
| Spearman ρ (84 pasangan) | **0,8663** ✅ |
| Precision@5 | 0,600 — **plafon dataset** (3 relevan/7 per CV) |
| Grid search Tahap 2 (report-only) | prior [40,30,20,10] optimal pada validasi |
| Anchor kalibrasi dibekukan (v1.1) | 0,4509→30 · 0,7327→85 |

**Benchmark throughput (M3)**: 1 CV vs 500 lowongan = **0,81 dtk scoring**
(1,62 ms/pair) — target < 5 dtk ✅. Cache vektor judul = 46× speedup.
Skrip: `evaluate_matching.py`, `benchmark_matching.py` → `eval/reports/matching_evaluation.json`.

## 4. LLM CV Optimization (M8) — target groundedness ≥ 95% pada sampel diterima; 0 fabrikasi

Live audit (Groq, gpt-oss-120b, 3 pasangan sintetis × 3 run, n=48 edits):

| Lapisan | Hasil |
|---|---|
| First-pass LLM groundedness (raw) | **91,7%** (44/48; rentang 87,5–94,4 antar-run — LLM non-deterministik) |
| **Groundedness edits yang DITERAPKAN** | **100% by construction** — `apply` me-revalidasi; pelanggaran validator ditolak (400) dan di-UI ditandai "Ditolak validator" default-unchecked |
| Fabrikasi kredensial yang mencapai CV | **0** |

Contoh pelanggaran tertangkap validator: "API RESTful" (varian frasa dari
"REST API" di CV) — strict by design. Skrip: `audit` inline
(`eval/reports/groundedness_audit.json`).

## 5. Diagnosis CV (M7) & Lainnya

- Diagnosis: 8 aturan deterministik teruji (32 test); tanpa LLM; skor stabil
  untuk input sama (properti teruji).
- E2E browser: **3/3 Playwright** (HR, kandidat full-chain, applications-loop
  dengan ranking) — ADR 0003.
- CI GitHub Actions: backend (PG16+pgvector asli, 354 test) / frontend /
  compose — **semua lulus** di HEAD.

## 6. Known Limitations

1. Korpus sintetis in-domain — angka bukan performa produksi; CV volunteer
   + rubrik manusia menyusul (docs/03 §4.4–4.5).
2. P@5 terikat plafon dataset; kalibrasi Tahap 2 final menunggu label manusia.
3. First-pass LLM groundedness ~92% (fluktuatif) — mitigasi berlapis:
   validator menolak pelanggaran, UI default-unchecked, apply me-revalidasi.
4. Ranking aplikasi menghitung skor on-demand (tanpa antrean) — cukup untuk
   skala MVP; antrean = keputusan fase berikutnya.
