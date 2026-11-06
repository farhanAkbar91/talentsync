"""Similarity (M3): cosine murni Python untuk satu pasangan vektor.

Sengaja tanpa numpy: skor dihitung per pasangan (CV x lowongan) saat matching
M4 dengan dimensi 384 — overhead list comprehension dapat diterima, dan modul
ini tetap ringan diimpor dari mana pun (termasuk skrip evaluasi).
"""

from __future__ import annotations

import math


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity dua vektor (hasil dijepit ke [-1, 1]).

    Salah satu vektor ber-norma 0 (mis. teks kosong) → 0.0, bukan NaN.
    """
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    # Jepit hasil: penjumlahan float bisa menghasilkan 1.0000000000000002.
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))
