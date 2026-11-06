"""Data taksonomi skill (skills_v1.json) — sumber kebenaran kanon + alias.

Berkas JSON di direktori ini di-seed ke tabel `canonical_skills`/`skill_aliases`
oleh `app.services.taxonomy_service.seed_from_json`. Normalizer (fase berikutnya)
membaca lewat DB, bukan berkas, agar versi taksonomi teraudit di database.
"""
