"""Matching engine (M3 embedding + M4 scoring + M5 skill gap).

- `embedder`: TextEmbedder (SentenceTransformer lazy singleton), chunking, dan
  perakitan teks CV/lowongan berlabel Indonesia.
- `similarity`: cosine murni Python (tanpa numpy) untuk skor cepat per pasangan.
- `calibration`: peta cosine → skor 0-100 piecewise-linear (anchor berkas JSON,
  cache per proses).
- `scorer`: fungsi murni skor kompatibilitas (semantic/skill/experience/education)
  — rumus BEKU kontrak M4, tanpa DB.
- `explainer`: narasi deterministik Bahasa Indonesia + label band skor.
- `gap`: matriks kategori skill, item gap, dan saran belajar (M5).
"""
