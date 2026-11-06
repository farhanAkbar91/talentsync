"""Evaluasi ekstraksi M1 pada golden set sintetis (docs/03 §4.6).

Perbandingan hasil `build_payload` terhadap ground truth terstruktur
`eval/golden/cvs/CV-XXX.json` — metrik per tipe field:

  - nama/email/telepon : binary exact-match (telepon dinormalisasi digit)
  - skills             : set-based Precision / Recall / F1 (case-insensitive)
  - pengalaman         : recall perusahaan (GT company ditemukan di hasil)
  - pendidikan         : recall institusi
  - sertifikasi        : recall nama (tanpa tahun)

Target awal (keputusan pemilik proyek): macro F1 gabungan ≥ 0.80 pada golden set.
CATATAN JUJUR: korpus ini SINTETIS dan dibangun dari template yang sama dengan
data uji parser — angka tidak boleh diklaim sebagai kinerja pada CV nyata.
Evaluasi CV volunteer menyusul (docs/03 §4.4).

Jalankan dari backend/: .venv/Scripts/python scripts/evaluate_extraction.py
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "eval" / "golden"
REPORT = REPO / "eval" / "reports" / "extraction_evaluation.json"


def _norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "")).strip().lower()


def _norm_phone(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("62"):
        digits = digits[2:]
    return digits.lstrip("0")


def _strip_year(value: str) -> str:
    return _norm_text(re.sub(r"\(\d{4}\)", "", value)).strip(" -—")


def evaluate_cv(gt: dict, payload: dict) -> dict[str, float]:
    """Skor 0..1 per tipe field untuk satu CV."""
    scores: dict[str, float] = {}
    contact = payload.get("contact") or {}

    # --- nama / email / telepon: exact match ternormalisasi ---
    scores["nama"] = 1.0 if _norm_text(contact.get("name")) == _norm_text(gt.get("nama")) else 0.0
    email_gt = (gt.get("email") or "").lower()
    scores["email"] = 1.0 if (contact.get("email") or "").lower() == email_gt else 0.0
    gt_phone = _norm_phone(gt.get("telepon"))
    scores["telepon"] = 1.0 if _norm_phone(contact.get("phone")) == gt_phone else 0.0

    # --- skills: set P/R/F1 ---
    gt_skills = {_norm_text(s) for s in gt.get("skills", [])}
    pred_skills = {_norm_text(s.get("name")) for s in payload.get("skills", [])}
    scores["skills"] = _set_f1(pred_skills, gt_skills)

    # --- pengalaman: recall perusahaan ---
    gt_companies = {_norm_text(e.get("perusahaan")) for e in gt.get("pengalaman", [])}
    pred_companies = {_norm_text(e.get("company")) for e in payload.get("experiences", [])}
    scores["pengalaman"] = _recall(gt_companies, pred_companies)

    # --- pendidikan: recall institusi ---
    gt_inst = {_norm_text(e.get("institusi")) for e in gt.get("pendidikan", [])}
    pred_inst = {_norm_text(e.get("institution")) for e in payload.get("education", [])}
    scores["pendidikan"] = _recall(gt_inst, pred_inst)

    # --- sertifikasi: recall nama (tanpa tahun) ---
    gt_cert = {_strip_year(c) for c in gt.get("sertifikasi", [])}
    pred_cert = {_strip_year(c.get("name") or "") for c in payload.get("certifications", [])}
    scores["sertifikasi"] = _recall(gt_cert, pred_cert)

    return scores


def _set_f1(pred: set[str], gt: set[str]) -> float:
    if not gt and not pred:
        return 1.0
    if not gt or not pred:
        return 0.0
    overlap = len(pred & gt)
    precision = overlap / len(pred)
    recall = overlap / len(gt)
    return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def _recall(gt: set[str], pred: set[str]) -> float:
    if not gt:
        return 1.0
    if not pred:
        return 0.0
    return len(gt & pred) / len(gt)


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.ai.extraction.parser import build_payload

    cv_files = sorted(GOLDEN.glob("cvs/CV-*.json"))
    if not cv_files:
        print("eval/golden/cvs tidak ditemukan — jalankan generate_golden_synthetic.py dulu.")
        sys.exit(1)

    per_field: dict[str, list[float]] = {}
    failures: list[dict] = []
    for path in cv_files:
        gt = json.loads(path.read_text(encoding="utf-8"))
        payload = build_payload(gt["_text"])
        scores = evaluate_cv(gt, payload)
        for field, value in scores.items():
            per_field.setdefault(field, []).append(value)
        if scores["nama"] == 0.0 or scores["email"] == 0.0:
            failures.append(
                {
                    "cv": gt["id"],
                    "name_pred": payload.get("contact", {}).get("name"),
                    "email_pred": payload.get("contact", {}).get("email"),
                }
            )

    macro = {field: sum(vals) / len(vals) for field, vals in per_field.items()}
    overall = sum(macro.values()) / len(macro)

    print("=== Evaluasi Ekstraksi M1 (golden set sintetis) ===")
    for field, value in sorted(macro.items()):
        marker = "✓" if value >= 0.80 else "✗"
        print(f"  {marker} {field:<14} {value:.3f}  (n={len(per_field[field])})")
    verdict = "LULUS" if overall >= 0.80 else "BELUM"
    print(f"  MACRO F1 GABUNGAN: {overall:.3f}  (target ≥ 0.80: {verdict})")
    if failures:
        print("  kasus gagal identitas:", json.dumps(failures, ensure_ascii=False))
    print("  Catatan: korpus sintetis (template sama dgn parser) — bukan kinerja CV nyata.")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(
            {
                "corpus": "eval/golden/cvs (12 CV sintetis)",
                "parser_version": payload.get("parser_version"),
                "per_field_macro": {k: round(v, 4) for k, v in macro.items()},
                "overall_macro_f1": round(overall, 4),
                "target": 0.80,
                "identity_failures": failures,
                "known_limitation": "korpus sintetis in-domain; evaluasi CV volunteer menyusul",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Laporan: {REPORT}")


if __name__ == "__main__":
    main()
