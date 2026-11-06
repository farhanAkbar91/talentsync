"""Evaluasi matching M4 (Wave 3 T5) pada golden set sintetis.

Pipeline hermetik di SQLite sementara (seed taxonomy; TANPA Supabase, TANPA
jaringan):

  0. Distribusi cosine mentah (positif label>=2 vs negatif label<=1) ->
     usulan anchor kalibrasi -> eval/reports/calibration.json (hanya butuh
     T1: embedder + similarity + parser + taxonomy).
  1. 12 CV  -> build_payload -> build_cv_text -> embedding MiniLM ASLI.
  2. 30 lowongan -> slug via normalize_skill -> job dict kontrak score_pair
     -> embedding teks lowongan + teks JUDUL (job_title_vec).
  3. slug kandidat per CV via skill_service.extract_skills_from_payload
     (murni baca; explicit = extraction_method 'explicit' + canonical).
  4. 84 pasangan -> score_pair (bobot dari Settings.match_weights,
     taxonomy_related dari skills_v1.json).
  5. Metrik vs label 0-3: nDCG@10 per CV (>=2 lowongan berlabel), macro
     nDCG@10, Spearman rho seluruh pasangan, Precision@5 (label>=2 di top-5,
     per CV dengan >=5 pasangan, makro).
  6. Grid search Tahap 2 (LAPORAN SAJA — tidak diterapkan ke config): bobot
     kelipatan 5 di [10,60] berjumlah 100; split kalibrasi/validasi 70/30
     deterministik per hash pasangan; dipilih nDCG@10 makro terbaik pada
     split kalibrasi, dilaporkan nDCG-nya pada split validasi vs bobot lama.

Target awal (dilaporkan jujur): nDCG@10 >= 0.75, rho >= 0.60.
CATATAN JUJUR: korpus ini SINTETIS in-domain (template yang sama dengan
generator golden set) — angka TIDAK boleh diklaim sebagai kinerja produksi
pada CV/lowongan nyata.

Jalankan dari backend/:
  .venv/Scripts/python scripts/evaluate_matching.py            # evaluasi penuh
  .venv/Scripts/python scripts/evaluate_matching.py --part0-only
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "eval" / "golden"
REPORTS = REPO / "eval" / "reports"
REPORT = REPORTS / "matching_evaluation.json"
CALIBRATION_REPORT = REPORTS / "calibration.json"

sys.path.insert(0, str(BACKEND))

# Skor anchor usulan (keputusan tugas T5): median cosine negatif -> 30,
# median cosine positif -> 85.
ANCHOR_NEG_SCORE = 30
ANCHOR_POS_SCORE = 85

# Kunci faktor AKTUAL score_pair (app/ai/matching/scorer.py), urut sesuai
# tuple match_weights (semantic, skill, experience, education) — config.py.
FACTOR_KEYS = ("semantic", "skill_coverage", "experience", "education")


# ---------------------------------------------------------------- utilitas


def percentile(values: list[float], q: float) -> float:
    """Persentil q (0-100) dengan interpolasi linear (konvensi numpy)."""
    if not values:
        return 0.0
    vals = sorted(values)
    if len(vals) == 1:
        return float(vals[0])
    pos = (len(vals) - 1) * (q / 100.0)
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return float(vals[lo])
    return float(vals[lo] + (vals[hi] - vals[lo]) * (pos - lo))


def _average_ranks(values: list[float]) -> list[float]:
    """Peringkat rata-rata (tie-handling) untuk Spearman."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman_rho(x: list[float], y: list[float]) -> float:
    """Korelasi rank Spearman dengan penanganan tie (rata-rata peringkat)."""
    n = len(x)
    if n < 2:
        return 0.0
    rx, ry = _average_ranks(x), _average_ranks(y)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=False))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0.0 or dy == 0.0:
        return 0.0
    return num / (dx * dy)


def dcg(labels: list[float], k: int = 10) -> float:
    return sum(
        (2.0**rel - 1.0) / math.log2(rank + 1) for rank, rel in enumerate(labels[:k], start=1)
    )


def ndcg_at_k(scored: list[tuple[float, float]], k: int = 10) -> float | None:
    """nDCG@k dari [(skor, label)] — ideal diurut label desc.

    None bila IDCG = 0 (semua label 0 — urutan tak bermakna) atau < 2 item.
    """
    if len(scored) < 2:
        return None
    by_score = [label for _score, label in sorted(scored, key=lambda p: (-p[0], p[1]))]
    ideal = sorted((label for _s, label in scored), reverse=True)
    idcg = dcg(ideal, k)
    if idcg <= 0.0:
        return None
    return dcg(by_score, k) / idcg


def derive_seniority(title: str) -> str | None:
    """Senioritas dari kata kunci judul lowongan (junior/menengah/senior)."""
    t = (title or "").lower()
    if "junior" in t:
        return "junior"
    if "senior" in t:
        return "senior"
    if "menengah" in t or " mid " in f" {t} " or "(mid)" in t:
        return "mid"
    return None


def load_pairs() -> list[dict]:
    with (GOLDEN / "pairs_labels.csv").open(encoding="utf-8") as fh:
        return [
            {"cv_id": r["cv_id"], "job_id": r["job_id"], "label": int(r["label"])}
            for r in csv.DictReader(fh)
        ]


def taxonomy_related_from_json() -> dict[str, set[str]]:
    """Peta slug -> set(slug terkait) dari app/ai/extraction/taxonomy/skills_v1.json."""
    path = BACKEND / "app" / "ai" / "extraction" / "taxonomy" / "skills_v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["slug"]: set(item.get("related") or []) for item in data["skills"]}


def grid_weight_percentages() -> list[tuple[int, int, int, int]]:
    """Semua kombinasi bobot kelipatan 5 di [10,60] berjumlah 100 (persen)."""
    out: list[tuple[int, int, int, int]] = []
    for a in range(10, 61, 5):
        for b in range(10, 61, 5):
            for c in range(10, 61, 5):
                d = 100 - a - b - c
                if 10 <= d <= 60:
                    out.append((a, b, c, d))
    return out


# --------------------------------------------------------- setup hermetik


def setup_db(tmp_dir: Path):
    """SQLite sementara + seed taxonomy (idempoten). Kembalikan (engine, factory)."""
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401 — daftarkan seluruh model ke Base.metadata
    from app.db.base import Base
    from app.db.session import build_engine

    engine = build_engine(f"sqlite:///{(tmp_dir / 'eval_matching.db').as_posix()}")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        from app.services import taxonomy_service

        stats = taxonomy_service.seed_from_json(db)
        db.commit()
    print(
        f"  DB sementara siap (taxonomy: {stats['canonical']} kanon / "
        f"{stats['aliases']} alias, v{stats['version']})"
    )
    return engine, factory


def build_corpus(db, embedder) -> dict:
    """Muat golden set, bangun payload/teks/vektor/slug — TANPA tulis DB."""
    from app.ai.extraction.parser import build_payload
    from app.ai.matching.embedder import build_cv_text, build_job_text
    from app.services import skill_service, taxonomy_service

    # --- CV ---
    cv_ids: list[str] = []
    cv_payloads: dict[str, dict] = {}
    cv_texts: dict[str, str] = {}
    candidate_slugs: dict[str, set[str]] = {}
    explicit_slugs: dict[str, set[str]] = {}
    for path in sorted(GOLDEN.glob("cvs/CV-*.json")):
        gt = json.loads(path.read_text(encoding="utf-8"))
        payload = build_payload(gt["_text"])
        cv_ids.append(gt["id"])
        cv_payloads[gt["id"]] = payload
        cv_texts[gt["id"]] = build_cv_text(payload)
        items = skill_service.extract_skills_from_payload(db, payload)
        cand, expl = set(), set()
        for item in items:
            canon = item.get("canonical")
            if not canon:
                continue
            cand.add(canon["slug"])
            if item.get("extraction_method") == "explicit":
                expl.add(canon["slug"])
        candidate_slugs[gt["id"]] = cand
        explicit_slugs[gt["id"]] = expl

    # --- lowongan ---
    job_ids: list[str] = []
    job_dicts: dict[str, dict] = {}
    job_texts: dict[str, str] = {}
    unmatched_job_skills: list[str] = []
    for path in sorted(GOLDEN.glob("jobs/JOB-*.json")):
        gt = json.loads(path.read_text(encoding="utf-8"))
        skills = []
        for skill in gt.get("skills", []):
            raw = str(skill.get("name") or "").strip()
            if not raw:
                continue
            res = taxonomy_service.normalize_skill(db, raw)
            canon = res["canonical"]
            if canon is None:
                unmatched_job_skills.append(f"{gt['id']}:{raw}")
            skills.append(
                {
                    "name": raw,
                    "slug": canon.slug if canon else None,
                    "display": canon.name if canon else raw,
                    "required": bool(skill.get("required")),
                }
            )
        requirements = "\n".join(f"- {r}" for r in gt.get("requirements", []))
        responsibilities = "\n".join(f"- {r}" for r in gt.get("responsibilities", []))
        job = {
            "title": gt["title"],
            "skills": skills,
            "description": gt.get("deskripsi") or "",
            "requirements": requirements,
            "responsibilities": responsibilities,
            "seniority": derive_seniority(gt["title"]),
        }
        job_ids.append(gt["id"])
        job_dicts[gt["id"]] = job
        job_texts[gt["id"]] = build_job_text(
            title=job["title"],
            skill_names=[s["display"] for s in skills],
            description=job["description"],
            requirements=job["requirements"],
            responsibilities=job["responsibilities"],
        )

    # --- embedding ASLI: satu batch gabungan (12 CV + 30 lowongan + 30 judul) ---
    print("  Embedding MiniLM ASLI: 12 teks CV + 30 teks lowongan + 30 judul ...")
    t0 = time.perf_counter()
    texts = (
        [cv_texts[cid] for cid in cv_ids]
        + [job_texts[jid] for jid in job_ids]
        + [job_dicts[jid]["title"] for jid in job_ids]
    )
    vecs = embedder.encode(texts)
    n_cv, n_job = len(cv_ids), len(job_ids)
    cv_vecs = {cid: vecs[i] for i, cid in enumerate(cv_ids)}
    job_vecs = {jid: vecs[n_cv + i] for i, jid in enumerate(job_ids)}
    title_vecs = {jid: vecs[n_cv + n_job + i] for i, jid in enumerate(job_ids)}
    print(f"  Embedding selesai dalam {time.perf_counter() - t0:.1f} dtk ({len(texts)} teks)")

    return {
        "cv_ids": cv_ids,
        "cv_payloads": cv_payloads,
        "cv_vecs": cv_vecs,
        "candidate_slugs": candidate_slugs,
        "explicit_slugs": explicit_slugs,
        "job_ids": job_ids,
        "job_dicts": job_dicts,
        "job_vecs": job_vecs,
        "title_vecs": title_vecs,
        "unmatched_job_skills": unmatched_job_skills,
    }


# --------------------------------------------- bagian 0: kalibrasi (T1 saja)


def cosine_distribution(corpus: dict, pairs: list[dict]) -> dict:
    """Distribusi cosine mentah positif (label>=2) vs negatif (label<=1)."""
    from app.ai.matching.similarity import cosine

    pos, neg, all_cos = [], [], []
    for pair in pairs:
        cos = cosine(corpus["cv_vecs"][pair["cv_id"]], corpus["job_vecs"][pair["job_id"]])
        all_cos.append(cos)
        (pos if pair["label"] >= 2 else neg).append(cos)
    return {
        "positive": {
            "median": percentile(pos, 50),
            "p25": percentile(pos, 25),
            "p75": percentile(pos, 75),
            "n": len(pos),
        },
        "negative": {
            "median": percentile(neg, 50),
            "p25": percentile(neg, 25),
            "p75": percentile(neg, 75),
            "n": len(neg),
        },
        "pos_median": percentile(pos, 50),
        "neg_median": percentile(neg, 50),
        "p25": {
            "positive": percentile(pos, 25),
            "negative": percentile(neg, 25),
            "all": percentile(all_cos, 25),
        },
        "p75": {
            "positive": percentile(pos, 75),
            "negative": percentile(neg, 75),
            "all": percentile(all_cos, 75),
        },
        "all_median": percentile(all_cos, 50),
        "n_pos": len(pos),
        "n_neg": len(neg),
        "proposed_anchors": [
            {
                "score": ANCHOR_NEG_SCORE,
                "cosine": round(percentile(neg, 50), 4),
                "source": "neg_median",
            },
            {
                "score": ANCHOR_POS_SCORE,
                "cosine": round(percentile(pos, 50), 4),
                "source": "pos_median",
            },
        ],
    }


def write_calibration_report(dist: dict) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    CALIBRATION_REPORT.write_text(
        json.dumps(
            {
                "corpus": "eval/golden (12 CV x 30 lowongan SINTETIS, 84 pasangan berlabel)",
                "n_pos": dist["n_pos"],
                "n_neg": dist["n_neg"],
                "pos_median": round(dist["pos_median"], 4),
                "neg_median": round(dist["neg_median"], 4),
                "p25": {k: round(v, 4) for k, v in dist["p25"].items()},
                "p75": {k: round(v, 4) for k, v in dist["p75"].items()},
                "positive": {
                    k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in dist["positive"].items()
                },
                "negative": {
                    k: (round(v, 4) if isinstance(v, float) else v)
                    for k, v in dist["negative"].items()
                },
                "proposed_anchors": dist["proposed_anchors"],
                "anchor_rule": f"neg_median -> {ANCHOR_NEG_SCORE}, "
                f"pos_median -> {ANCHOR_POS_SCORE}",
                "note": "Usulan anchor v1 (laporan saja, belum diterapkan ke config); "
                "korpus sintetis in-domain — bukan distribusi produksi.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Laporan kalibrasi: {CALIBRATION_REPORT}")


# --------------------------------------------------------- evaluasi penuh


def score_all_pairs(corpus: dict, pairs: list[dict], weights, taxonomy_related) -> list[dict]:
    """Panggil score_pair untuk 84 pasangan; kembalikan hasil + skor + waktu."""
    from app.ai.matching.scorer import score_pair

    results = []
    t0 = time.perf_counter()
    for idx, pair in enumerate(pairs, start=1):
        cv_id, job_id = pair["cv_id"], pair["job_id"]
        res = score_pair(
            cv_payload=corpus["cv_payloads"][cv_id],
            job=corpus["job_dicts"][job_id],
            cv_vec=corpus["cv_vecs"][cv_id],
            job_vec=corpus["job_vecs"][job_id],
            job_title_vec=corpus["title_vecs"][job_id],
            candidate_slugs=corpus["candidate_slugs"][cv_id],
            explicit_slugs=corpus["explicit_slugs"][cv_id],
            weights=tuple(weights),
            taxonomy_related=taxonomy_related,
            calibration_version="v1",
        )
        results.append({**pair, "result": res})
        if idx % 20 == 0:
            print(f"  {idx}/{len(pairs)} pasangan diproses ...")
    print(f"  84 pasangan di-skor dalam {time.perf_counter() - t0:.1f} dtk (score_pair murni)")
    return results


def _combine_overall(factors: dict[str, float], weights) -> float:
    """Gabungkan faktor 0-100 dengan bobot (urut semantic/skill/experience/education)."""
    keys = [k for k in FACTOR_KEYS if k in factors] or list(factors.keys())
    total_w = sum(weights[: len(keys)])
    return sum(weights[i] * factors[keys[i]] for i in range(len(keys))) / (total_w or 1.0)


def metrics(results: list[dict], weights) -> dict:
    """nDCG@10 makro, Spearman, P@5, per-CV; + verifikasi kombinasi faktor."""
    by_cv: dict[str, list[dict]] = {}
    for r in results:
        by_cv.setdefault(r["cv_id"], []).append(r)

    per_cv: dict[str, dict] = {}
    ndcgs: list[float] = []
    p5s: list[float] = []
    for cv_id in sorted(by_cv):
        rows = by_cv[cv_id]
        scored = [(r["result"]["overall"], float(r["label"])) for r in rows]
        ndcg = ndcg_at_k(scored, k=10)
        entry: dict = {"n_pairs": len(rows)}
        if ndcg is not None:
            entry["ndcg10"] = round(ndcg, 4)
            ndcgs.append(ndcg)
        if len(rows) >= 5:
            ranked = sorted(rows, key=lambda r: (-r["result"]["overall"], r["job_id"]))[:5]
            p5 = sum(1 for r in ranked if r["label"] >= 2) / 5.0
            entry["precision_at5"] = round(p5, 4)
            p5s.append(p5)
        per_cv[cv_id] = entry

    spearman = spearman_rho(
        [r["result"]["overall"] for r in results],
        [float(r["label"]) for r in results],
    )

    # Verifikasi jalur cepat grid search: overall == gabungan berbobot faktor?
    combine_err = 0.0
    for r in results:
        factors = r["result"].get("factors") or {}
        combine_err = max(
            combine_err, abs(_combine_overall(factors, weights) - r["result"]["overall"])
        )

    return {
        "ndcg10_macro": sum(ndcgs) / len(ndcgs) if ndcgs else None,
        "n_cv_ndcg": len(ndcgs),
        "precision_at5": sum(p5s) / len(p5s) if p5s else None,
        "n_cv_p5": len(p5s),
        "spearman": spearman,
        "per_cv": per_cv,
        "combine_max_error": combine_err,
        "by_cv_rows": by_cv,
    }


def ndcg_macro_for_weights(rows_by_cv: dict[str, list[dict]], weights) -> float:
    """nDCG@10 makro utk satu kombinasi bobot via jalur cepat faktor tetap."""
    vals: list[float] = []
    for _cv_id, rows in rows_by_cv.items():
        if len(rows) < 2:
            continue
        scored = [
            (_combine_overall(r["result"].get("factors") or {}, weights), float(r["label"]))
            for r in rows
        ]
        ndcg = ndcg_at_k(scored, k=10)
        if ndcg is not None:
            vals.append(ndcg)
    return sum(vals) / len(vals) if vals else 0.0


def grid_search(results: list[dict], weights) -> dict:
    """Tahap 2 (LAPORAN SAJA): grid bobot kelipatan 5, split 70/30 per hash."""
    by_cv: dict[str, list[dict]] = {}
    for r in results:
        by_cv.setdefault(r["cv_id"], []).append(r)

    calib: dict[str, list[dict]] = {}
    val: dict[str, list[dict]] = {}
    for cv_id, rows in by_cv.items():
        for r in rows:
            digest = hashlib.md5(f"{r['cv_id']}|{r['job_id']}".encode()).hexdigest()
            bucket = calib if int(digest[:8], 16) % 100 < 70 else val
            bucket.setdefault(cv_id, []).append(r)

    prior_pct = tuple(round(w * 100) for w in weights)
    combos = grid_weight_percentages()
    scored_combos: list[tuple[float, float, tuple[int, int, int, int]]] = []
    for combo in combos:
        calib_ndcg = ndcg_macro_for_weights(calib, tuple(w / 100.0 for w in combo))
        scored_combos.append(
            (calib_ndcg, sum(abs(c - p) for c, p in zip(combo, prior_pct, strict=False)), combo)
        )
    # Utamakan nDCG kalibrasi tertinggi; tie-break: terdekat ke bobot lama, lalu urutan enumerasi.
    scored_combos.sort(key=lambda t: (-round(t[0], 6), t[1], combos.index(t[2])))
    best_calib, _dist, best_combo = scored_combos[0]
    best_val = ndcg_macro_for_weights(val, tuple(w / 100.0 for w in best_combo))
    prior_calib = ndcg_macro_for_weights(calib, weights)
    prior_val = ndcg_macro_for_weights(val, weights)

    top = [
        {
            "weights_pct": list(combo),
            "ndcg10_calibration": round(c, 4),
            "ndcg10_validation": round(
                ndcg_macro_for_weights(val, tuple(w / 100.0 for w in combo)), 4
            ),
        }
        for c, _d, combo in scored_combos[:5]
    ]
    return {
        "n_combinations": len(combos),
        "split": "70% kalibrasi / 30% validasi, deterministik per hash pasangan (md5)",
        "n_pairs_calibration": sum(len(v) for v in calib.values()),
        "n_pairs_validation": sum(len(v) for v in val.values()),
        "best_weights_pct": list(best_combo),
        "best_ndcg10_calibration": round(best_calib, 4),
        "best_ndcg10_validation": round(best_val, 4),
        "prior_weights_pct": list(prior_pct),
        "prior_ndcg10_calibration": round(prior_calib, 4),
        "prior_ndcg10_validation": round(prior_val, 4),
        "top5": top,
        "applied_to_config": False,
        "note": "LAPORAN SAJA — bobot di config (.env MATCH_WEIGHTS) tidak diubah.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluasi matching M4 (golden set sintetis)")
    ap.add_argument(
        "--part0-only",
        action="store_true",
        help="hanya distribusi cosine + calibration.json (butuh T1 saja)",
    )
    args = ap.parse_args()

    from app.core.config import Settings

    weights = tuple(Settings().match_weights)
    print("=== Evaluasi Matching M4 (golden set SINTETIS) ===")
    print(f"  Bobot config: {weights} (semantic, skill, experience, education)")

    # --- T2 tersedia? ---
    t2_error: str | None = None
    try:
        from app.ai.matching import calibration as calibration_mod
        from app.ai.matching import scorer as scorer_mod

        if not hasattr(scorer_mod, "score_pair") or not hasattr(calibration_mod, "map_cosine"):
            raise ImportError("score_pair/map_cosine belum ditemukan di modul T2")
    except Exception as exc:  # noqa: BLE001 — probe ketersediaan T2
        t2_error = f"{type(exc).__name__}: {exc}"
        if not args.part0_only:
            print(f"  [T2] scorer/calibration belum tersedia ({t2_error})")
            print(
                "       -> jalankan bagian 0 (kalibrasi) saja; jalankan ulang nanti "
                "untuk evaluasi penuh."
            )
    if t2_error and args.part0_only:
        pass  # bagian 0 memang tidak butuh T2

    # --- setup hermetik ---
    tmp_dir = Path(tempfile.mkdtemp(prefix="talentsync_eval_matching_"))
    engine = None
    try:
        engine, factory = setup_db(tmp_dir)
        with factory() as db:
            from app.ai.matching.embedder import get_embedder

            embedder = get_embedder(Settings().embedding_model)
            print("  Memuat model embedding (warm-up ±30 dtk di CPU) ...")
            corpus = build_corpus(db, embedder)
            if corpus["unmatched_job_skills"]:
                print(
                    f"  Catatan: {len(corpus['unmatched_job_skills'])} skill lowongan "
                    f"tanpa slug kanon: {corpus['unmatched_job_skills'][:8]}"
                )

            pairs = load_pairs()
            dist = cosine_distribution(corpus, pairs)
            write_calibration_report(dist)
            print(
                f"  Distribusi cosine: positif median={dist['pos_median']:.4f} "
                f"[{dist['positive']['p25']:.4f}, {dist['positive']['p75']:.4f}] "
                f"(n={dist['n_pos']}) | negatif median={dist['neg_median']:.4f} "
                f"[{dist['negative']['p25']:.4f}, {dist['negative']['p75']:.4f}] "
                f"(n={dist['n_neg']})"
            )
            print(
                f"  Usulan anchor: neg_median({dist['neg_median']:.4f})->"
                f"{ANCHOR_NEG_SCORE}, pos_median({dist['pos_median']:.4f})->"
                f"{ANCHOR_POS_SCORE}"
            )

            if t2_error:
                print("  Selesai bagian 0 — T2 belum tersedia untuk evaluasi penuh.")
                sys.exit(2)
            if args.part0_only:
                print("  --part0-only: berhenti setelah kalibrasi.")
                sys.exit(0)

            # --- evaluasi penuh (butuh T2) ---
            from app.ai.matching.calibration import load_calibration

            taxonomy_related = taxonomy_related_from_json()
            results = score_all_pairs(corpus, pairs, weights, taxonomy_related)
            m = metrics(results, weights)

            grid = grid_search(results, weights)
            calibration_info = load_calibration()

            print("\n--- Hasil metrik (korpus SINTETIS in-domain) ---")
            ndcg = m["ndcg10_macro"]
            print(
                f"  nDCG@10 makro : {ndcg:.4f}  (target >= 0.75 -> "
                f"{'LULUS' if ndcg >= 0.75 else 'BELUM'}; {m['n_cv_ndcg']} CV)"
            )
            print(
                f"  Spearman rho  : {m['spearman']:.4f}  (target >= 0.60 -> "
                f"{'LULUS' if m['spearman'] >= 0.60 else 'BELUM'})"
            )
            print(
                f"  Precision@5   : {m['precision_at5']:.4f}  (makro, "
                f"{m['n_cv_p5']} CV dengan >=5 pasangan; PLAFON dataset 3/5=0.6 — "
                f"tiap CV hanya punya 3 lowongan relevan label>=2)"
            )
            for cv_id, entry in m["per_cv"].items():
                print(
                    f"    {cv_id}: nDCG@10={entry.get('ndcg10')} "
                    f"P@5={entry.get('precision_at5')} (n={entry['n_pairs']})"
                )
            print("\n--- Grid search Tahap 2 (LAPORAN SAJA) ---")
            print(
                f"  kombinasi bobot : {grid['n_combinations']} (kelipatan 5 di [10,60], jumlah 100)"
            )
            print(
                f"  split           : {grid['n_pairs_calibration']} kalibrasi / "
                f"{grid['n_pairs_validation']} validasi"
            )
            print(
                f"  bobot lama {grid['prior_weights_pct']}: nDCG kalibrasi="
                f"{grid['prior_ndcg10_calibration']}, validasi="
                f"{grid['prior_ndcg10_validation']}"
            )
            print(
                f"  bobot terbaik {grid['best_weights_pct']}: nDCG kalibrasi="
                f"{grid['best_ndcg10_calibration']}, validasi="
                f"{grid['best_ndcg10_validation']} (tidak diterapkan ke config)"
            )
            for row in grid["top5"]:
                print(
                    f"    {row['weights_pct']}: kal={row['ndcg10_calibration']} "
                    f"val={row['ndcg10_validation']}"
                )

            REPORTS.mkdir(parents=True, exist_ok=True)
            REPORT.write_text(
                json.dumps(
                    {
                        "corpus": "eval/golden (12 CV + 30 lowongan SINTETIS, "
                        "84 pasangan berlabel)",
                        "dataset": "synthetic",
                        "model": Settings().embedding_model,
                        "calibration_version": calibration_info.get("version"),
                        "weights_used": list(weights),
                        "ndcg10_macro": round(ndcg, 4),
                        "spearman": round(m["spearman"], 4),
                        "precision_at5": round(m["precision_at5"], 4),
                        "per_cv": m["per_cv"],
                        "cosine_distribution": {
                            "pos_median": round(dist["pos_median"], 4),
                            "neg_median": round(dist["neg_median"], 4),
                            "positive": {
                                k: (round(v, 4) if isinstance(v, float) else v)
                                for k, v in dist["positive"].items()
                            },
                            "negative": {
                                k: (round(v, 4) if isinstance(v, float) else v)
                                for k, v in dist["negative"].items()
                            },
                            "proposed_anchors": dist["proposed_anchors"],
                        },
                        "grid_search_tahap2": grid,
                        "targets": {"ndcg10": 0.75, "spearman": 0.60},
                        "precision_at5_ceiling": 0.6,
                        "targets_met": {
                            "ndcg10": bool(ndcg >= 0.75),
                            "spearman": bool(m["spearman"] >= 0.60),
                        },
                        "factors_combine_max_error": round(m["combine_max_error"], 8),
                        "known_limitation": "korpus SINTETIS in-domain (template sama "
                        "dgn generator golden) — angka bukan kinerja "
                        "produksi; evaluasi CV/lowongan nyata menyusul",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"\nLaporan: {REPORT}")
    finally:
        if engine is not None:
            engine.dispose()
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
