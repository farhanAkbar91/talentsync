"""Benchmark performa matching M4 (Wave 3 T5) — gate blueprint M3:

  1 CV vs 500 lowongan < 5 dtk CPU (waktu SCORING murni, vektor sudah ada).

Metode:
- 500 lowongan disintesis dari 30 lowongan golden (siklus + jitter
  deterministik ber-seed: senioritas judul, angka tahun pengalaman, subset
  skill opsional) — skor realistis tanpa jaringan.
- Embedding MiniLM ASLI untuk 500 teks lowongan + 1 teks CV — waktu EMBED
  dihitung TERPISAH (di produksi vektor disimpan saat publish, bukan dihitung
  ulang per query; gate 5 dtk hanya untuk score_pair murni).
- 500x score_pair murni dijumlahkan -> PASS/FAIL vs 5 dtk.

CATATAN JUJUR: korpus SINTETIS; gate mengukur throughput pemakaian nyata
(1 CV x 500 lowongan), bukan latensi end-to-end API.

Hasil ditulis ke eval/reports/matching_evaluation.json di bawah kunci
"benchmark" (merge dengan laporan evaluasi bila sudah ada).

Jalankan dari backend/: .venv/Scripts/python scripts/benchmark_matching.py
Jalankan BERURUTAN (tidak paralel dgn evaluate_matching.py) — batasan CPU i5/16GB.
"""

from __future__ import annotations

import json
import random
import re
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

sys.path.insert(0, str(BACKEND))

N_JOBS = 500
GATE_SECONDS = 5.0
SEED = 20261106
# Ukuran blok encode (progres + RAM stabil; hasil identik dgn satu panggilan
# karena pooling dilakukan per teks).
EMBED_BLOCK = 100

_LEVEL_CYCLE = ["junior", "mid", "senior"]
_LEVEL_TAG = {"junior": "(Junior)", "mid": "(Menengah)", "senior": "(Senior)"}
_LEVEL_TAG_RE = re.compile(r"\s*\((?:Junior|Menengah|Senior)\)\s*")


def synthesize_jobs(golden_jobs: list[dict]) -> list[dict]:
    """500 varian deterministik dari 30 lowongan golden (siklus + jitter).

    Jitter per varian k (random.Random(SEED), urutan iterasi tetap):
    - senioritas: siklus junior/mid/senior -> sufiks judul diganti.
    - tahun pengalaman: angka pada "±N tahun" / "N+ tahun" diganti 1..6.
    - skill opsional: sebagian dibuang (required selalu dipertahankan).
    """
    random.Random(SEED)
    variants: list[dict] = []
    for k in range(N_JOBS):
        base = golden_jobs[k % len(golden_jobs)]
        level = _LEVEL_CYCLE[k % 3]
        title = _LEVEL_TAG_RE.sub(" ", base["title"]).strip()
        title = f"{title} {_LEVEL_TAG[level]}"

        years = 1 + (k * 7 + k // 30) % 6
        description = re.sub(
            r"(±|\+)\s*\d+\s*tahun", rf"\g<1>{years} tahun", base.get("deskripsi") or ""
        )
        requirements = [
            re.sub(r"\b\d+\s*(\+)?\s*tahun", f"{years} tahun", r)
            for r in base.get("requirements", [])
        ]

        skills = []
        for idx, skill in enumerate(base.get("skills", [])):
            required = bool(skill.get("required"))
            if not required and (k + idx) % 3 == 0:
                continue  # buang sebagian skill opsional secara deterministik
            skills.append(skill)

        variants.append(
            {
                "id": f"{base['id']}-V{k:03d}",
                "base": base["id"],
                "title": title,
                "level": level,
                "description": description,
                "requirements": requirements,
                "skills": skills,
                "responsibilities": base.get("responsibilities", []),
            }
        )
    return variants


def main() -> None:
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401 — daftarkan seluruh model ke Base.metadata
    from app.core.config import Settings
    from app.db.base import Base
    from app.db.session import build_engine

    settings = Settings()
    weights = tuple(settings.match_weights)
    print(f"=== Benchmark Matching M4: 1 CV vs {N_JOBS} lowongan (SINTETIS) ===")
    print(f"  Bobot: {weights} | gate: scoring < {GATE_SECONDS} dtk (CPU)")

    tmp_dir = Path(tempfile.mkdtemp(prefix="talentsync_bench_matching_"))
    engine = None
    try:
        engine = build_engine(f"sqlite:///{(tmp_dir / 'bench_matching.db').as_posix()}")
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(engine)
        with factory() as db:
            from app.ai.extraction.parser import build_payload
            from app.ai.matching.embedder import build_cv_text, build_job_text, get_embedder
            from app.ai.matching.scorer import score_pair
            from app.services import skill_service, taxonomy_service

            taxonomy_service.seed_from_json(db)
            db.commit()

            # --- lowongan golden -> slug (sekali; varian hanya subset/mutasi teks) ---
            golden_jobs = [
                json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(GOLDEN.glob("jobs/JOB-*.json"))
            ]
            golden_slugs: dict[str, list[dict]] = {}
            for gt in golden_jobs:
                skills = []
                for skill in gt.get("skills", []):
                    raw = str(skill.get("name") or "").strip()
                    if not raw:
                        continue
                    canon = taxonomy_service.normalize_skill(db, raw)["canonical"]
                    skills.append(
                        {
                            "name": raw,
                            "slug": canon.slug if canon else None,
                            "display": canon.name if canon else raw,
                            "required": bool(skill.get("required")),
                        }
                    )
                golden_slugs[gt["id"]] = skills

            variants = synthesize_jobs(golden_jobs)
            job_dicts: list[dict] = []
            job_texts: list[str] = []
            for var in variants:
                skills = []
                for skill in var["skills"]:
                    raw = str(skill.get("name") or "").strip()
                    matched = next((s for s in golden_slugs[var["base"]] if s["name"] == raw), None)
                    skills.append(
                        matched
                        if matched
                        else {
                            "name": raw,
                            "slug": None,
                            "display": raw,
                            "required": bool(skill.get("required")),
                        }
                    )
                requirements = "\n".join(f"- {r}" for r in var["requirements"])
                responsibilities = "\n".join(f"- {r}" for r in var["responsibilities"])
                job = {
                    "title": var["title"],
                    "skills": skills,
                    "description": var["description"],
                    "requirements": requirements,
                    "responsibilities": responsibilities,
                    "seniority": var["level"],
                }
                job_dicts.append(job)
                job_texts.append(
                    build_job_text(
                        title=job["title"],
                        skill_names=[s["display"] for s in skills],
                        description=job["description"],
                        requirements=job["requirements"],
                        responsibilities=job["responsibilities"],
                    )
                )

            # --- 1 CV ---
            cv_gt = json.loads((GOLDEN / "cvs" / "CV-001.json").read_text(encoding="utf-8"))
            cv_payload = build_payload(cv_gt["_text"])
            cv_text = build_cv_text(cv_payload)
            items = skill_service.extract_skills_from_payload(db, cv_payload)
            cand, expl = set(), set()
            for item in items:
                canon = item.get("canonical")
                if not canon:
                    continue
                cand.add(canon["slug"])
                if item.get("extraction_method") == "explicit":
                    expl.add(canon["slug"])

            tax_path = BACKEND / "app" / "ai" / "extraction" / "taxonomy" / "skills_v1.json"
            tax = json.loads(tax_path.read_text(encoding="utf-8"))
            taxonomy_related = {it["slug"]: set(it.get("related") or []) for it in tax["skills"]}

            # --- embedding ASLI (waktu terpisah dari gate scoring) ---
            embedder = get_embedder(settings.embedding_model)
            print("  Memuat model embedding (warm-up ±30 dtk di CPU) ...")
            t_load = time.perf_counter()
            embedder.encode([cv_text])  # warm-up: model load + first pass
            load_seconds = time.perf_counter() - t_load

            print(
                f"  Embedding {len(job_texts)} teks lowongan + "
                f"{len(job_dicts)} judul + 1 CV + judul pengalaman CV ..."
            )
            t_embed = time.perf_counter()
            cv_vec = embedder.encode([cv_text])[0]
            job_vecs: list[list[float]] = []
            title_vecs: list[list[float]] = []
            for start in range(0, len(job_texts), EMBED_BLOCK):
                block = job_texts[start : start + EMBED_BLOCK]
                job_vecs.extend(embedder.encode(block))
                print(
                    f"    {min(start + EMBED_BLOCK, len(job_texts))}/{len(job_texts)} di-embed ..."
                )
            title_vecs = embedder.encode([job["title"] for job in job_dicts])
            # Pola produksi (amandemen Wave 3): vektor judul pengalaman CV
            # dihitung SEKALI per CV dan di-inject ke score_pair.
            exp_titles = [
                e.get("judul") or e.get("title") or "" for e in cv_payload.get("experiences", [])
            ]
            cv_title_vecs = embedder.encode(exp_titles) if exp_titles else []
            embed_seconds = time.perf_counter() - t_embed

            # --- scoring murni 500x (GATE) ---
            print(f"  Scoring {N_JOBS} pasangan (score_pair murni) ...")
            t_score = time.perf_counter()
            for idx, (job, job_vec, title_vec) in enumerate(
                zip(job_dicts, job_vecs, title_vecs, strict=False), start=1
            ):
                score_pair(
                    cv_payload=cv_payload,
                    job=job,
                    cv_vec=cv_vec,
                    job_vec=job_vec,
                    job_title_vec=title_vec,
                    candidate_slugs=cand,
                    explicit_slugs=expl,
                    weights=weights,
                    taxonomy_related=taxonomy_related,
                    calibration_version="v1.1",
                    cv_title_vecs=cv_title_vecs,
                )
                if idx % 100 == 0:
                    print(f"    {idx}/{N_JOBS} pasangan di-skor ...")
            score_seconds = time.perf_counter() - t_score

            total_seconds = load_seconds + embed_seconds + score_seconds
            passed = score_seconds < GATE_SECONDS

            # Diagnostik: score_pair meng-embed judul pengalaman CV DI DALAM
            # panggilan (fallback _encode_titles — produksi mem-bind encoder yang
            # sama via set_title_encoder). Ukur porsi itu terpisah: CV-001 punya
            # 1 judul pengalaman, jadi biaya per panggilan identik.
            exp_titles = [
                str(item.get("title") or "").strip()
                for item in (cv_payload.get("experiences") or [])
                if str(item.get("title") or "").strip()
            ]
            title_share_seconds = 0.0
            if exp_titles:
                title_text = exp_titles[0]
                t_title = time.perf_counter()
                for _ in range(N_JOBS):
                    embedder.encode([title_text])
                title_share_seconds = time.perf_counter() - t_title

            # Varian B (diagnostik, TIDAK mengubah gate utama): encoder judul
            # ber-cache — mensimulasikan optimasi "vektor judul pengalaman dihitung
            # sekali per CV" yang BELUM ada di scorer/service saat ini.
            from app.ai.matching.scorer import set_title_encoder

            score_seconds_cached = None
            if exp_titles:
                precomputed = dict(zip(exp_titles, embedder.encode(exp_titles), strict=False))

                def cached_encoder(texts, _pre=precomputed):
                    return [_pre.get(t) or embedder.encode([t])[0] for t in texts]

                set_title_encoder(cached_encoder)
                try:
                    t_cached = time.perf_counter()
                    for job, job_vec, title_vec in zip(
                        job_dicts, job_vecs, title_vecs, strict=False
                    ):
                        score_pair(
                            cv_payload=cv_payload,
                            job=job,
                            cv_vec=cv_vec,
                            job_vec=job_vec,
                            job_title_vec=title_vec,
                            candidate_slugs=cand,
                            explicit_slugs=expl,
                            weights=weights,
                            taxonomy_related=taxonomy_related,
                            calibration_version="v1",
                        )
                    score_seconds_cached = time.perf_counter() - t_cached
                finally:
                    set_title_encoder(None)  # pulihkan fallback — tidak bocor ke proses lain

            print("\n--- Hasil benchmark ---")
            print(f"  muat model + warm-up : {load_seconds:.2f} dtk")
            print(
                f"  embed 500+1 teks     : {embed_seconds:.2f} dtk "
                f"(di luar gate; produksi: vektor tersimpan saat publish)"
            )
            print(
                f"  scoring 500x         : {score_seconds:.3f} dtk  "
                f"-> {'LULUS' if passed else 'GAGAL'} (gate < {GATE_SECONDS} dtk)"
            )
            print(f"  rata-rata per pasangan: {score_seconds / N_JOBS * 1000:.2f} ms")
            if title_share_seconds:
                print(
                    f"  diagnostik           : ±{title_share_seconds:.2f} dtk dari "
                    f"waktu skor adalah embed judul pengalaman CV per panggilan "
                    f"(di dalam score_pair)"
                )
            if score_seconds_cached is not None:
                print(
                    f"  varian B (diagnostik): scoring 500x dgn encoder judul "
                    f"ber-cache = {score_seconds_cached:.3f} dtk "
                    f"({'< 5 dtk' if score_seconds_cached < GATE_SECONDS else '>= 5 dtk'}) "
                    f"— optimasi yang belum ada di kode saat ini"
                )
            print(f"  total proses         : {total_seconds:.2f} dtk")
            print("  Catatan: korpus SINTETIS — gate throughput, bukan latensi API.")

            REPORTS.mkdir(parents=True, exist_ok=True)
            report = {}
            if REPORT.exists():
                try:
                    report = json.loads(REPORT.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    report = {}
            report["benchmark"] = {
                "scenario": f"1 CV vs {N_JOBS} lowongan (sintesis deterministik "
                f"dari 30 lowongan golden, seed={SEED})",
                "n_jobs": N_JOBS,
                "model": settings.embedding_model,
                "model_load_warmup_seconds": round(load_seconds, 2),
                "embed_seconds": round(embed_seconds, 2),
                "score_seconds": round(score_seconds, 3),
                "total_seconds": round(total_seconds, 2),
                "avg_ms_per_pair": round(score_seconds / N_JOBS * 1000, 2),
                "title_embed_share_seconds": round(title_share_seconds, 2)
                if title_share_seconds
                else None,
                "title_embed_note": "score_pair meng-embed judul pengalaman CV per "
                "panggilan (_encode_titles fallback / encoder "
                "ter-inject dgn model sama di produksi)",
                "score_seconds_with_cached_title_encoder": (
                    round(score_seconds_cached, 3) if score_seconds_cached is not None else None
                ),
                "cached_encoder_note": "diagnostik optimasi hipotetis (cache vektor "
                "judul per CV) — gate utama tetap diukur tanpa cache",
                "gate_seconds": GATE_SECONDS,
                "gate_scope": "score_pair murni (vektor sudah tersedia), tanpa I/O DB",
                "pass": bool(passed),
                "corpus": "synthetic",
                "known_limitation": "korpus SINTETIS; gate throughput scoring, "
                "bukan latensi end-to-end API",
            }
            REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Laporan: {REPORT}")
    finally:
        if engine is not None:
            engine.dispose()
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
