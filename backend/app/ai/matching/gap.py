"""Skill gap (M5): matriks kategori, item gap, dan saran belajar (tanpa LLM).

Kontrak BEKU:
- matrix: per kategori yang muncul di skill lowongan → target 100, candidate =
  min(100, round(100·(#slug kandidat di kategori)/max(1, #slug lowongan))),
  status "met" bila == 100 else "gap". Kategori milik kandidat yang TIDAK
  diminta lowongan → baris terpisah: target 0, candidate 100, status "surplus".
- items: match["missing"] + alasan turunan severity (kritis/menengah/minor).
- learning_suggestions: kategori yang punya >=1 item gap → sumber belajar gratis
  dari `learning_resources.json` (honest generic entries).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

RESOURCES_PATH = Path(__file__).resolve().parent / "learning_resources.json"

# Alasan gap per severity (aturan beku M4).
REASONS: dict[str, str] = {
    "kritis": "Skill wajib belum dimiliki dan tidak ada skill terkait yang menutupi.",
    "menengah": "Skill wajib belum dikuasai penuh, tetapi ada skill terkait sebagai modal.",
    "minor": "Skill diutamakan yang belum dimiliki — penguatannya menjadi nilai tambah.",
}

_RESOURCES_CACHE: dict[str, list[dict]] | None = None


def load_learning_resources() -> dict[str, list[dict]]:
    """Muat peta kategori → daftar {title, provider, url} (cache per proses).

    Berkas hilang/korup → dict kosong (tanpa saran, tanpa exception). Salinan
    dikembalikan agar cache tidak termutasi pemanggil.
    """
    global _RESOURCES_CACHE
    if _RESOURCES_CACHE is None:
        try:
            data = json.loads(RESOURCES_PATH.read_text(encoding="utf-8"))
            cleaned: dict[str, list[dict]] = {}
            for category, items in data.items():
                rows = []
                for item in items or []:
                    if not isinstance(item, dict):
                        continue
                    rows.append(
                        {
                            "title": str(item.get("title", "")),
                            "provider": str(item.get("provider", "")),
                            "url": str(item.get("url", "")),
                        }
                    )
                if rows:
                    cleaned[str(category)] = rows
            _RESOURCES_CACHE = cleaned
        except (OSError, ValueError, json.JSONDecodeError):
            _RESOURCES_CACHE = {}
    return copy.deepcopy(_RESOURCES_CACHE)


def _ordered_categories(taxonomy_categories: list[str], present: set[str]) -> list[str]:
    """Kategori urut mengikuti taksonomi dulu, sisanya alfabet (deterministik)."""
    known = [category for category in taxonomy_categories or [] if category in present]
    known_set = set(known)
    extra = sorted(category for category in present if category not in known_set)
    return known + extra


def build_gap(
    match: dict,
    taxonomy_categories: list[str],
    candidate_category_slugs: dict[str, list[str]],
    job_category_slugs: dict[str, list[str]],
) -> dict:
    """Bangun kontrak gap dari hasil score_pair + peta kategori→slug.

    `candidate_category_slugs`/`job_category_slugs` berbentuk {kategori: [slug]}
    yang sudah dipetakan service dari CanonicalSkill. Fungsi murni — total
    terhadap input kosong.
    """
    candidate_map = {
        category: [slug for slug in slugs if slug]
        for category, slugs in (candidate_category_slugs or {}).items()
    }
    job_map = {
        category: [slug for slug in slugs if slug]
        for category, slugs in (job_category_slugs or {}).items()
    }

    matrix: list[dict] = []
    job_categories = {category for category, slugs in job_map.items() if slugs}
    for category in _ordered_categories(taxonomy_categories or [], job_categories):
        job_count = len(job_map.get(category) or [])
        candidate_count = len(candidate_map.get(category) or [])
        candidate_score = min(100, round(100 * candidate_count / max(1, job_count)))
        matrix.append(
            {
                "category": category,
                "target": 100,
                "candidate": candidate_score,
                "status": "met" if candidate_score >= 100 else "gap",
            }
        )

    # Surplus: kategori milik kandidat yang tidak diminta lowongan sama sekali.
    surplus_categories = {
        category
        for category, slugs in candidate_map.items()
        if slugs and category not in job_categories
    }
    for category in _ordered_categories(taxonomy_categories or [], surplus_categories):
        matrix.append({"category": category, "target": 0, "candidate": 100, "status": "surplus"})

    missing_items = [item for item in (match or {}).get("missing") or [] if isinstance(item, dict)]
    items = [
        {
            "name": str(item.get("name")),
            "display": str(item.get("display") or item.get("name")),
            "required": bool(item.get("required")),
            "severity": str(item.get("severity") or "minor"),
            "reason": REASONS.get(str(item.get("severity") or "minor"), REASONS["minor"]),
        }
        for item in missing_items
    ]

    # Kategori gap = kategori lowongan yang memuat slug yang missing.
    slug_to_category: dict[str, str] = {}
    for category, slugs in job_map.items():
        for slug in slugs:
            slug_to_category.setdefault(slug, category)
    gap_categories: list[str] = []
    for item in items:
        category = slug_to_category.get(item["name"])
        if category is not None and category not in gap_categories:
            gap_categories.append(category)
    gap_categories = _ordered_categories(taxonomy_categories or [], set(gap_categories))

    resources = load_learning_resources()
    learning_suggestions: list[dict] = []
    for category in gap_categories:
        for resource in resources.get(category) or []:
            learning_suggestions.append(
                {
                    "category": category,
                    "title": resource["title"],
                    "provider": resource["provider"],
                    "url": resource["url"],
                }
            )

    return {
        "matrix": matrix,
        "items": items,
        "learning_suggestions": learning_suggestions,
    }
