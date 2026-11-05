# ADR 0004 — Strategi Kolom Vector Embedding (pgvector + SQLite Variant)

**Status:** Diterima (P3.0, 6 November 2026)

## 1. Konteks

P3 membutuhkan kolom embedding vektor (`cv_embeddings`, `job_embeddings`) untuk
semantic matching (docs/08 M3–M4). Blueprint mengikat PostgreSQL 16 + pgvector.
Kendala lingkungan: seluruh test lokal (pytest, Playwright E2E) berjalan di
**SQLite** (ADR 0002), sementara Docker tidak terpasang; database dev/prod kini
**Supabase PostgreSQL 17** (ADR 0005) dengan pgvector aktif.

Kolom `vector(384)` tidak ada di SQLite — tanpa strategi, seluruh suite lokal
(create_all) akan rusak.

## 2. Keputusan

Tipe kolom embedding memakai **variant pattern yang sudah menjadi konvensi proyek**:

```python
from pgvector.sqlalchemy import Vector
embedding: Mapped[list[float]] = mapped_column(
    Vector(384).with_variant(JSON(), "sqlite"), nullable=False
)
```

- **PostgreSQL/Supabase (dev, migrasi, CI):** `VECTOR(384)` asli. KNN memakai
  operator pgvector (`<=>`) di SQL.
- **SQLite (pytest lokal + E2E):** `JSON` — vektor disimpan sebagai list float;
  **cosine similarity dihitung di Python** (NumPy/skalar) oleh layer service.

Tidak ada TypeDecorator kustom — variant `with_variant` identik dengan pola
`JSONB().with_variant(JSON(), "sqlite")` yang sudah dipakai semua tabel.

## 3. Implikasi

1. Semua operasi mirip/KNN **harus melewati lapisan service**, bukan SQL mentah
   di endpoint, agar jalur SQLite (Python cosine) dan PostgreSQL (KNN SQL)
   tertangani di satu tempat.
2. **Tidak ada index ivfflat/hnsw di migrasi 0007** — skala MVP (≤500 lowongan)
   sequential scan < 5 dtk (target benchmark docs/08 M3). Index ditambahkan di
   migrasi terpisah saat skala menuntut.
3. Dimensi embedding (384) dibekukan lewat `EMBEDDING_DIM` (configurable per F2);
   ganti model dengan dimensi berbeda = migrasi + re-embed massal (docs/08 M3).
4. Konsistensi schema model⇄migrasi wajib (aturan audit P1+P2): nullability dan
   tipe paralel antara `app/models/ai.py` dan migrasi 0006–0009.

## 4. Alternatif yang ditolak

- **PostgreSQL-only untuk semua test** — menggugurkan 51 test lokal + E2E;
  menuntut Docker yang tidak tersedia; koneksi Supabase per-test lambat & berisiko
  (conftest melakukan drop_all — tidak boleh diarahkan ke database bersama).
- **Simpan vektor sebagai JSON di PostgreSQL juga** — kehilangan KNN SQL dan
  tipe dimensi pgvector; mengabaikan alasan utama memilih pgvector.
