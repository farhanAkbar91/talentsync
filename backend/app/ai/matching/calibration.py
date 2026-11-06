"""Kalibrasi skor semantik (M4): peta cosine → skor 0-100 piecewise-linear.

- Anchor dibaca dari `calibration.json` (berdampingan dengan modul ini) pada
  PANGGILAN PERTAMA, lalu di-cache per proses — Lead membekukan anchor hasil
  evaluasi dengan menulis ulang berkas JSON, tanpa perlu mengubah kode.
- Berkas hilang/rusak → jatuh ke default blueprint Tahap-0 (0.30→30, 0.62→85)
  agar scoring tidak pernah gagal karena konfigurasi.
- `map_cosine` menjepit nilai di luar anchor terluar ke skor anchor terluar
  (ekstrapolasi tidak pernah dilakukan).
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

# Default blueprint Tahap-0 — dipakai juga bila berkas JSON hilang/korup.
DEFAULT_CALIBRATION: dict = {
    "version": "v1",
    "anchors": [
        {"cos": 0.30, "score": 30},
        {"cos": 0.62, "score": 85},
    ],
}

_CALIBRATION_PATH = Path(__file__).resolve().parent / "calibration.json"

# Cache per proses: berkas hanya dibaca sekali (anchor dibekukan antar deploy).
_CACHE: dict | None = None


def _default_calibration() -> dict:
    """Salinan bersih default (pemanggil tidak boleh memutasi konstanta modul)."""
    return copy.deepcopy(DEFAULT_CALIBRATION)


def _parse_anchors(raw: object) -> list[dict]:
    """Validasi & rapikan daftar anchor: [{cos, score}] urut naik, angka valid."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("anchors kosong atau bukan list")
    anchors: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("anchor bukan objek")
        cos = float(item["cos"])
        score = float(item["score"])
        if math.isnan(cos) or math.isnan(score):
            raise ValueError("anchor mengandung NaN")
        anchors.append({"cos": cos, "score": score})
    anchors.sort(key=lambda a: a["cos"])
    return anchors


def reset_calibration_cache() -> None:
    """Kosongkan cache kalibrasi (untuk test — produksi tidak perlu memanggil)."""
    global _CACHE
    _CACHE = None


def load_calibration() -> dict:
    """Muat kalibrasi dari `calibration.json` (cache per proses).

    Berkas hilang/korup/struktur salah → default blueprint Tahap-0. Hasil
    selalu berbentuk {"version": str, "anchors": [{"cos": float, "score": float}]}
    dengan anchor urut naik berdasarkan cos.
    """
    global _CACHE
    if _CACHE is None:
        try:
            data = json.loads(_CALIBRATION_PATH.read_text(encoding="utf-8"))
            calibration = {
                "version": str(data.get("version", DEFAULT_CALIBRATION["version"])),
                "anchors": _parse_anchors(data.get("anchors")),
            }
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            calibration = _default_calibration()
        _CACHE = calibration
    return copy.deepcopy(_CACHE)


def map_cosine(cos: float, anchors: list[dict] | None = None) -> float:
    """Peta cosine similarity → skor 0-100 via interpolasi linear antar anchor.

    - `anchors` None → anchor dimuat dari `load_calibration()` (berkas JSON).
    - Di luar rentang anchor terluar → skor anchor terluar (clamped, tanpa
      ekstrapolasi). Anchor tanpa pasangan (satu anchor) → skor tunggal itu.
    - Anchor dengan cos identik → skor anchor berikutnya pada segmen itu
      (penjaga pembagian nol).
    """
    if anchors is None:
        anchors = load_calibration()["anchors"]
    if not anchors:
        return 0.0

    value = float(cos)
    if math.isnan(value):
        return 0.0
    ordered = sorted(anchors, key=lambda a: a["cos"])
    if value <= ordered[0]["cos"]:
        return float(ordered[0]["score"])
    if value >= ordered[-1]["cos"]:
        return float(ordered[-1]["score"])

    for left, right in zip(ordered, ordered[1:], strict=False):
        if left["cos"] <= value <= right["cos"]:
            span = right["cos"] - left["cos"]
            if span <= 0.0:
                return float(right["score"])
            t = (value - left["cos"]) / span
            return float(left["score"] + t * (right["score"] - left["score"]))
    return float(ordered[-1]["score"])
