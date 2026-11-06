"""Pipeline ingestion lowongan eksternal (fase Data Engineering).

Alur: `sources` (konektor API publik, read-only) → `normalizer` (payload
insert) → `ingest_service` (dedupe + insert + normalisasi skill + embed).
Dijalankan via `scripts/ingest_jobs.py`.
"""
