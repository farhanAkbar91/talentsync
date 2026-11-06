"""Explainer (M4): narasi Bahasa Indonesia deterministik atas hasil matching.

Tanpa LLM — templat murni agar hasil selalu identik untuk input sama (mudah
diuji & murah). 2-4 kalimat: label band, faktor terkuat/terlemah, skill wajib,
dan pengalaman (years_have vs years_req).
"""

from __future__ import annotations

# Urutan faktor tetap → tie-break deterministik untuk terkuat/terlemah.
FACTOR_ORDER: tuple[str, ...] = ("semantic", "skill_coverage", "experience", "education")

FACTOR_LABELS: dict[str, str] = {
    "semantic": "kesesuaian semantik",
    "skill_coverage": "kecocokan skill",
    "experience": "pengalaman",
    "education": "pendidikan",
}


def label_for(overall: float) -> str:
    """Label band skor (BEKU): >=85 Sangat Cocok, 70-84 Cocok, 55-69 Cukup, <55 Kurang."""
    if overall >= 85:
        return "Sangat Cocok"
    if overall >= 70:
        return "Cocok"
    if overall >= 55:
        return "Cukup"
    return "Kurang"


def _strongest_weakest(factors: dict) -> tuple[tuple[str, float], tuple[str, float]]:
    """Faktor terkuat & terlemah berdasarkan FACTOR_ORDER (deterministik)."""
    ordered = [
        (key, float(factors.get(key, 0.0) or 0.0)) for key in FACTOR_ORDER if key in (factors or {})
    ]
    if not ordered:
        return ("skill_coverage", 0.0), ("skill_coverage", 0.0)
    strongest = max(ordered, key=lambda pair: pair[1])
    weakest = min(ordered, key=lambda pair: pair[1])
    return strongest, weakest


def build_explanation(
    *,
    overall: float,
    factors: dict,
    matched: list[dict],
    missing: list[dict],
    job_title: str,
    years_have: float,
    years_req: int | float,
) -> str:
    """Narasi deterministik 2-4 kalimat (Bahasa Indonesia) — tanpa LLM."""
    overall = float(overall or 0.0)
    band = label_for(overall)
    title = str(job_title or "").strip() or "lowongan ini"
    sentences: list[str] = [
        f'Skor kecocokan {overall:.1f} untuk lowongan "{title}" termasuk kategori {band}.'
    ]

    (strong_key, strong_value), (weak_key, weak_value) = _strongest_weakest(factors)
    sentences.append(
        f"Faktor terkuat: {FACTOR_LABELS.get(strong_key, strong_key)} ({strong_value:.1f}); "
        f"terlemah: {FACTOR_LABELS.get(weak_key, weak_key)} ({weak_value:.1f})."
    )

    matched_required = sum(1 for item in matched or [] if item.get("required"))
    missing_required = sum(1 for item in missing or [] if item.get("required"))
    total_required = matched_required + missing_required
    if total_required > 0:
        parts = [f"{matched_required} dari {total_required} skill wajib terpenuhi"]
        if missing_required:
            names = [
                str(item.get("display") or item.get("name"))
                for item in missing or []
                if item.get("required")
            ]
            shown = ", ".join(names[:3]) + (" dll." if len(names) > 3 else "")
            parts.append(f"belum: {shown}")
        sentences.append("; ".join(parts) + ".")
    else:
        sentences.append("Lowongan ini tidak mencantumkan skill wajib.")

    if years_have >= years_req:
        sentences.append(
            f"Pengalaman tercatat {years_have:.1f} tahun, sudah memenuhi kebutuhan "
            f"{years_req:g} tahun."
        )
    else:
        sentences.append(
            f"Pengalaman tercatat {years_have:.1f} tahun dari {years_req:g} tahun yang diminta."
        )

    return " ".join(sentences)
