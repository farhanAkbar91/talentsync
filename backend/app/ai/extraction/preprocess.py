"""Pra-pemrosesan teks CV mentah sebelum segmentasi (M1 — parsing lanjutan).

Menghasilkan BARIS bersih: struktur baris dipertahankan karena segmentasi
section dan heuristik entitas bekerja per baris. Langkah pembersihan:
- de-hifen kata yang terpotong antar baris (hanya bila baris berikut diawali
  huruf kecil, mis. "keuangan-\\nkerasan" → "keuangan-kerasan"),
- normalisasi bullet ke "• " (termasuk "-" dan "*" yang diikuti spasi),
- rapikan rangkaian spasi/tab internal, buang spasi di ujung,
- buang baris yang hanya berisi nomor halaman,
- padatkan baris kosong berurutan (maksimum satu).
"""

import re

MAX_TEXT_CHARS = 200_000

# Karakter bullet unicode yang dinormalisasi (em/en dash di awal baris pun
# lazim dipakai sebagai bullet oleh hasil render PDF).
_BULLET_UNICODE = "•●▪◦‣–—"

# Baris hanya berisi penomoran halaman: "2", "Halaman 2/5", "Page 3", "3 dari 5".
_PAGE_NUM_RE = re.compile(
    r"^(?:hal(?:aman)?\.?|page)?\s*\d{1,4}(?:\s*(?:/|dari|of)\s*\d{1,4})?$",
    re.IGNORECASE,
)
_MULTI_SPACE_RE = re.compile(r"[ \t]+")


def preprocess_text(raw: str) -> list[str]:
    """Bersihkan teks mentah menjadi daftar baris siap segmentasi. TOTAL: input
    kosong/aneh → list kosong; input dipotong defensif di MAX_TEXT_CHARS."""
    if not raw:
        return []
    lines = [line.rstrip() for line in raw[:MAX_TEXT_CHARS].splitlines()]
    lines = _dehyphenate(lines)

    cleaned: list[str] = []
    for line in lines:
        line = _MULTI_SPACE_RE.sub(" ", line).strip()
        line = _normalize_bullet(line)
        if not line:
            cleaned.append("")  # baris kosong dipertahankan, dipadatkan di akhir
            continue
        if _PAGE_NUM_RE.match(line):
            continue  # nomor halaman bukan konten
        cleaned.append(line)
    return _collapse_blank_runs(cleaned)


def _dehyphenate(lines: list[str]) -> list[str]:
    """Gabungkan kata terpotong di akhir baris ("-") bila baris berikutnya
    diawali huruf kecil; sisanya dibiarkan (bisa jadi judul/acronim)."""
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            len(line) > 1
            and line.endswith("-")
            and line[-2].isalnum()
            and i + 1 < len(lines)
            and lines[i + 1][:1].islower()
        ):
            result.append(line + lines[i + 1].strip())
            i += 2
            continue
        result.append(line)
        i += 1
    return result


def _normalize_bullet(line: str) -> str:
    """Samakan penanda daftar menjadi "• " supaya heuristik bullet downstream
    konsisten; baris kosong hasil normalisasi dikembalikan apa adanya."""
    if not line:
        return line
    first = line[0]
    if first in _BULLET_UNICODE or (first in "-*" and len(line) > 1 and line[1] == " "):
        rest = line[1:].lstrip()
        return f"• {rest}" if rest else ""
    return line


def _collapse_blank_runs(lines: list[str]) -> list[str]:
    """Maksimum satu baris kosong berurutan."""
    result: list[str] = []
    blank = False
    for line in lines:
        if line == "":
            if blank:
                continue
            blank = True
        else:
            blank = False
        result.append(line)
    return result
