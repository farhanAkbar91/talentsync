"""Benchmark model embedding kandidat P3 pada golden set sintetis.

Mengukur pada pasangan CV-job berlabel (rubrik 0-3):
  - distribusi cosine pasangan POSITIF (label >= 2) vs NEGATIF (label <= 1)
  - gap separasi + akurasi threshold titik tengah (bahan anchor kalibrasi
    Tahap 1, docs/03 §4.2)
  - subset per bahasa/job-domain
  - latensi embedding per teks (CPU)

Kandidat (keputusan #5 pemilik proyek):
  1. sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (baseline blueprint)
  2. intfloat/multilingual-e5-small (kandidat utama; wajib prefix query:/passage:)

Hasil: eval/reports/embedding_benchmark.json + tabel terminal.
Jalankan dari backend/: .venv/Scripts/python scripts/benchmark_embedding_models.py
(skalanya kecil — ~1-2 menit CPU setelah model terunduh ±1 GB ke cache HF).
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "eval" / "golden"
REPORT_DIR = REPO / "eval" / "reports"

CANDIDATES = [
    {"id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "prefix": None},
    {
        "id": "intfloat/multilingual-e5-small",
        "prefix_query": "query: ",
        "prefix_passage": "passage: ",
    },
]

EN_HINTS = (
    "react",
    "typescript",
    "flutter",
    "figma",
    "docker",
    "kubernetes",
    "power bi",
    "tableau",
)


def _load(domain: str) -> list[dict]:
    folder = GOLDEN / domain
    items = []
    for path in sorted(folder.glob("*.json")):
        items.append(json.loads(path.read_text(encoding="utf-8")))
    return items


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def main() -> None:
    import numpy as np  # noqa: F401 — dipakai transitive oleh sentence-transformers
    from sentence_transformers import SentenceTransformer

    cvs = _load("cvs")
    jobs = _load("jobs")
    pairs = []
    with (GOLDEN / "pairs_labels.csv").open(encoding="utf-8") as f:
        import csv

        for row in csv.DictReader(f):
            pairs.append((row["cv_id"], row["job_id"], int(row["label"])))
    {c["id"]: c for c in cvs}
    job_by_id = {j["id"]: j for j in jobs}
    print(f"corpus: {len(cvs)} CV, {len(jobs)} jobs, {len(pairs)} pasangan berlabel")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    for cand in CANDIDATES:
        model_id = cand["id"]
        print(f"\n== {model_id} (unduhan pertama ±0,5 GB bila cache kosong) ==")
        t0 = time.perf_counter()
        model = SentenceTransformer(model_id)
        # sentence-transformers 6.x: get_sentence_embedding_dimension diganti nama.
        _dim_fn = getattr(model, "get_embedding_dimension", None)
        dim = _dim_fn() if _dim_fn else model.get_sentence_embedding_dimension()
        print(f"   dimensi: {dim} | muat: {time.perf_counter() - t0:.1f}s")
        pref_q = cand.get("prefix_query", "")
        pref_p = cand.get("prefix_passage", "")

        def embed(
            texts: list[str],
            kind: str,
            _pref_q: str = pref_q,
            _pref_p: str = pref_p,
            _model: SentenceTransformer = model,
        ) -> tuple[list[list[float]], float]:
            prefix = _pref_q if kind == "query" else _pref_p
            t0 = time.perf_counter()
            vecs = _model.encode([prefix + t for t in texts], normalize_embeddings=True)
            per_text = (time.perf_counter() - t0) / len(texts) * 1000
            return vecs.tolist(), per_text

        cv_vecs, cv_ms = embed([c["_text"] for c in cvs], "query")
        job_vecs, job_ms = embed([j["_text"] for j in jobs], "passage")
        cv_map = {c["id"]: v for c, v in zip(cvs, cv_vecs, strict=False)}
        job_map = {j["id"]: v for j, v in zip(jobs, job_vecs, strict=False)}

        pos, neg, pos_en, neg_en = [], [], [], []
        for cv_id, job_id, label in pairs:
            cos = _cosine(cv_map[cv_id], job_map[job_id])
            job_text = job_by_id[job_id]["_text"].lower()
            is_en = any(h in job_text for h in EN_HINTS)
            bucket_pos, bucket_neg = (pos_en, neg_en) if is_en else (pos, neg)
            (bucket_pos if label >= 2 else bucket_neg).append(cos)

        thr = (statistics.mean(pos) + statistics.mean(neg)) / 2
        acc = (
            sum(1 for x in pos if x >= thr) / len(pos) * 0.5
            + sum(1 for x in neg if x < thr) / len(neg) * 0.5
        )
        results[model_id] = {
            "dim": dim,
            "cos_pos_mean": round(statistics.mean(pos), 4),
            "cos_pos_std": round(statistics.stdev(pos), 4),
            "cos_neg_mean": round(statistics.mean(neg), 4),
            "cos_neg_std": round(statistics.stdev(neg), 4),
            "gap": round(statistics.mean(pos) - statistics.mean(neg), 4),
            "accuracy_midpoint": round(acc, 4),
            "threshold_anchor": round(thr, 4),
            "n_pos": len(pos),
            "n_neg": len(neg),
            "subset_en": {
                "n_pos": len(pos_en),
                "n_neg": len(neg_en),
                "gap": round(statistics.mean(pos_en) - statistics.mean(neg_en), 4),
            }
            if pos_en and neg_en
            else None,
            "latency_ms_per_text": {"cv": round(cv_ms, 1), "job": round(job_ms, 1)},
            "cos_pos_min": round(min(pos), 4),
            "cos_neg_max": round(max(neg), 4),
        }
        r = results[model_id]
        print(
            f"   pos {r['cos_pos_mean']}±{r['cos_pos_std']}"
            f" | neg {r['cos_neg_mean']}±{r['cos_neg_std']}"
            f" | gap {r['gap']} | acc@mid {r['accuracy_midpoint']}"
            f" | overlap: pos_min {r['cos_pos_min']} vs neg_max {r['cos_neg_max']}"
            f" | {r['latency_ms_per_text']}"
        )

    out = REPORT_DIR / "embedding_benchmark.json"
    out.write_text(
        json.dumps(
            {
                "corpus": {"cvs": len(cvs), "jobs": len(jobs), "pairs": len(pairs)},
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nLaporan: {out}")


if __name__ == "__main__":
    main()
