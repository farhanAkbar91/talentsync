"""Evaluasi M2 — Skill Extraction & Normalization pada golden set sintetis.

Metrik (keputusan pemilik proyek, target awal):
  1. Skill extraction F1 ≥ 0.85       : GT skills vs hasil ekstraksi payload
                                        (eksplisit + inferred, set-based P/R/F1)
  2. Canonicalization accuracy ≥ 0.90 : nama skill GT terpetakan ke canonical
                                        yang benar (nama canonical = GT)
  3. Adversarial false-mapping = 0    : pasangan yang SEMANTIK BERBEDA tidak
                                        boleh bergabung (java≠javascript dst.)
  4. Idempotency                      : normalisasi ulang input sama → hasil
                                        identik; seed ulang → jumlah baris sama
  5. Duplicate rate = 0               : tiap CV tidak boleh menghasilkan
                                        canonical duplikat

CATATAN JUJUR: korpus sintetis in-domain — angka bukan performa produksi;
evaluasi CV volunteer menyusul (docs/03 §4.4).

Jalankan dari backend/: .venv/Scripts/python scripts/evaluate_skills.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "eval" / "golden"
REPORT = REPO / "eval" / "reports" / "skills_evaluation.json"

# Pasangan yang TIDAK BOLEH bergabung (semantik berbeda) dan pasangan yang
# HARUS bergabung (alias resmi) — adversarial set manual.
MUST_NOT_MERGE = [
    ("java", "javascript"),
    ("sql", "postgresql"),
    ("machine-learning", "deep-learning"),
    ("data-analysis", "data-engineering"),
    ("react", "react-native"),
    ("power-bi", "tableau"),
]
MUST_MERGE = [
    ("bahasa pemrograman python", "python"),
    ("ml", "machine-learning"),
    ("reactjs", "react"),
    ("node.js", "nodejs"),
    ("bahasa inggris", "english-language"),
]


def _set_f1(pred: set[str], gt: set[str]) -> tuple[float, float, float]:
    if not gt and not pred:
        return 1.0, 1.0, 1.0
    if not gt or not pred:
        return 0.0, 0.0, 0.0
    overlap = len(pred & gt)
    precision = overlap / len(pred)
    recall = overlap / len(gt)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sqlalchemy.orm import sessionmaker

    from app.ai.extraction.parser import build_payload
    from app.db.session import build_engine
    from app.services import taxonomy_service

    # DB evaluasi: SQLite sementara + seed taxonomy (hermetik, bukan Supabase).
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = build_engine(f"sqlite:///{tmp.name}")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        from app.db.base import Base
        from app.services import skill_service

        Base.metadata.create_all(engine)
        stats = taxonomy_service.seed_from_json(db)
        db.commit()

        # --- 1+2: extraction F1 & canonicalization accuracy per CV ---
        cv_files = sorted(GOLDEN.glob("cvs/CV-*.json"))
        f1s, canon_ok, canon_total, dup_total = [], 0, 0, 0
        per_cv: dict[str, dict] = {}
        for path in cv_files:
            gt = json.loads(path.read_text(encoding="utf-8"))
            # GT memakai nama canonical: petakan tiap nama GT ke slug ekspektasi.
            gt_slugs: set[str] = set()
            for name in gt.get("skills", []):
                res = taxonomy_service.normalize_skill(db, name)
                gt_slugs.add(res["canonical"].slug if res["canonical"] else _norm(name))
                canon_total += 1
                if res["canonical"] and res["canonical"].name.lower() == name.lower():
                    canon_ok += 1
            payload = build_payload(gt["_text"])
            extracted = skill_service.extract_skills_from_payload(db, payload)
            pred_slugs, seen = set(), set()
            for item in extracted:
                slug = item["canonical"]["slug"] if item.get("canonical") else None
                if slug:
                    pred_slugs.add(slug)
                    if slug in seen:
                        dup_total += 1
                    seen.add(slug)
            p, r, f1 = _set_f1(pred_slugs, gt_slugs)
            f1s.append(f1)
            per_cv[gt["id"]] = {
                "precision": round(p, 3),
                "recall": round(r, 3),
                "f1": round(f1, 3),
                "gt": len(gt_slugs),
                "pred": len(pred_slugs),
            }

        extraction_f1 = sum(f1s) / len(f1s) if f1s else 0.0
        canon_acc = canon_ok / canon_total if canon_total else 0.0

        # --- 3: adversarial ---
        false_maps = []
        for a, b in MUST_NOT_MERGE:
            ra, rb = (
                taxonomy_service.normalize_skill(db, a),
                taxonomy_service.normalize_skill(db, b),
            )
            if ra["canonical"] and rb["canonical"] and ra["canonical"].slug == rb["canonical"].slug:
                false_maps.append(f"{a} == {b} → {ra['canonical'].slug}")
        failed_merges = []
        for raw, expected in MUST_MERGE:
            res = taxonomy_service.normalize_skill(db, raw)
            got = res["canonical"].slug if res["canonical"] else None
            if got != expected:
                failed_merges.append(f"{raw} → {got} (harus {expected})")

        # --- 4: idempotensi ---
        sample = "bahasa pemrograman python"
        r1, r2 = (
            taxonomy_service.normalize_skill(db, sample),
            taxonomy_service.normalize_skill(db, sample),
        )
        idempotent = (r1["canonical"].slug if r1["canonical"] else None) == (
            r2["canonical"].slug if r2["canonical"] else None
        ) and r1["method"] == r2["method"]
        stats2 = taxonomy_service.seed_from_json(db)
        db.commit()
        seed_stable = (
            stats["canonical"] == stats2["canonical"] and stats["aliases"] == stats2["aliases"]
        )

    engine.dispose()
    dup_rate = dup_total / canon_total if canon_total else 0.0

    def verdict(ok: bool, detail: str = "") -> str:
        return "LULUS" if ok else f"GAGAL{': ' + detail if detail else ''}"

    print("=== Evaluasi M2 — Skill Extraction & Normalization (sintetis) ===")
    f1_verdict = verdict(extraction_f1 >= 0.85)
    canon_verdict = verdict(canon_acc >= 0.90)
    print(f"  extraction F1 (macro) : {extraction_f1:.3f}  target >= 0.85 -> {f1_verdict}")
    print(f"  canonicalization acc  : {canon_acc:.3f}  target >= 0.90 -> {canon_verdict}")
    print(f"  adversarial false-map : {verdict(not false_maps, '; '.join(false_maps))}")
    print(f"  adversarial merges    : {verdict(not failed_merges, '; '.join(failed_merges))}")
    print(f"  idempotency           : {verdict(idempotent and seed_stable)}")
    print(f"  duplicate rate        : {dup_rate:.3f}  target 0 -> {verdict(dup_rate == 0)}")
    for cv_id, s in per_cv.items():
        print(
            f"    {cv_id}: P={s['precision']} R={s['recall']} F1={s['f1']}"
            f" (gt={s['gt']} pred={s['pred']})"
        )
    print("  Catatan: korpus sintetis in-domain — bukan performa produksi.")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(
            {
                "extraction_f1_macro": round(extraction_f1, 4),
                "canonicalization_accuracy": round(canon_acc, 4),
                "adversarial_false_maps": false_maps,
                "adversarial_failed_merges": failed_merges,
                "idempotent": idempotent and seed_stable,
                "duplicate_rate": round(dup_rate, 4),
                "per_cv": per_cv,
                "taxonomy": stats,
                "target": {
                    "extraction_f1": 0.85,
                    "canonicalization": 0.90,
                    "false_maps": 0,
                    "duplicates": 0,
                },
                "known_limitation": "korpus sintetis in-domain; evaluasi CV volunteer menyusul",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Laporan: {REPORT}")


def _norm(value: str) -> str:
    import re

    return re.sub(r"\s+", " ", (value or "")).strip().lower()


def gt_lookup(gt: dict, slug: str) -> str:
    """Nama GT yang memetakan ke slug — dipertahankan untuk kompatibilitas laporan."""
    return slug


if __name__ == "__main__":
    main()
