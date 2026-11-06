"""Validator grounding saran optimasi CV (M8) — pertahanan kedua sisi server.

Aturan beku (R1-R4), diperiksa per edit terhadap teks CV (build_cv_text) dan
judul lowongan:
- R1 `source_not_found`: `source_ref` (awalan literal dari original_text) harus
  dapat dilokalisasi sebagai awalan salah satu baris teks CV — perbandingan
  case-insensitive + whitespace dinormalisasi; penanda poin ("-") di awal baris
  ditoleransi agar LLM yang mengutip tanpa marker tetap lolos.
- R2 `change_type_invalid`: change_type harus anggota CHANGE_TYPES.
- R3 `fabricated_entity` / `fabricated_number`: proper noun (frasa kapital
  multi-kata, atau kata kapital tunggal di tengah kalimat) yang tidak ada di
  leksikon CV maupun judul lowongan ditolak; angka baru (untuk quantify maupun
  change_type lain — aturan beku melarang angka baru) hanya boleh bila sudah
  ada di original_text atau di CV.
- R4 `date_modified`: token tanggal/tahun di suggested_text tidak boleh baru
  (harus sudah ada di original_text).

Semua fungsi murni dan total terhadap input kosong; hasil deterministik.
"""

from __future__ import annotations

import re
from typing import Any

from app.ai.matching.embedder import build_cv_text
from app.ai.optimization.prompts import CHANGE_TYPES

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9&./+#-]*")
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")
_SLASH_DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/(?:19|20)\d{2}\b")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_SENTENCE_GAP_RE = re.compile(r"[.!?]\s*$|\n\s*$")


# --- Normalisasi dasar ---


def _normalize(text: str) -> str:
    """Casefold + collapse whitespace (perbandingan toleran R1)."""
    return " ".join(str(text or "").split()).casefold()


def _strip_line_markers(line: str) -> str:
    """Lepas penanda poin di awal baris ("- ", "*", "•") sebelum dibandingkan."""
    stripped = line.strip()
    for marker in ("-", "*", "\u2022"):
        if stripped.startswith(marker):
            return stripped[1:].lstrip()
    return stripped


# --- Leksikon CV ---


def _payload_lexicon(payload: dict) -> tuple[set[str], set[str]]:
    """(kata, frasa) dari seluruh nilai string payload — leksikon CV.

    Frasa dinormalisasi utuh (mis. "pt teknologi cerdas"); kata dipecah per
    token sehingga skill/perusahaan satu kata ikut terlindungi.
    """
    words: set[str] = set()
    phrases: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            if value.strip():
                phrases.add(_normalize(value))
            for word in _WORD_RE.findall(value):
                words.add(word.casefold())

    walk(payload)
    return words, phrases


def _word_known(word: str, allowed: set[str]) -> bool:
    """Kata dikenal bila utuh, atau seluruh sub-bagian pemisah /&+ dikenal.

    Sub-pemecahan menjaga reword wajar seperti "SQL/Python" (di CV: "SQL" dan
    "Python" terpisah) agar tidak dianggap entitas fabrikasi.
    """
    if word in allowed:
        return True
    parts = [part for part in re.split(r"[/&+]", word) if part]
    return bool(parts) and all(part in allowed for part in parts)


# --- Deteksi proper noun ---


def _tokenize(text: str) -> list[tuple[str, bool]]:
    """[(token, sentence_initial)] — token awal kalimat tidak dianggap proper
    noun tunggal (kapital di awal kalimat adalah konvensi, bukan entitas)."""
    tokens: list[tuple[str, bool]] = []
    previous_end = 0
    for index, match in enumerate(_WORD_RE.finditer(text)):
        gap = text[previous_end : match.start()]
        initial = index == 0 or bool(_SENTENCE_GAP_RE.search(gap))
        tokens.append((match.group(0), initial))
        previous_end = match.end()
    return tokens


def _proper_noun_candidates(text: str) -> list[tuple[str, list[str], bool]]:
    """Kandidat proper noun dari suggested_text.

    Mengembalikan [(frasa_lowercase, [kata], tunggal)]:
    - frasa kapital >= 2 kata berurutan (tunggal=False);
    - kata kapital tunggal di tengah kalimat, panjang >= 3, bukan akronim
      all-caps (tunggal=True).
    """
    candidates: list[tuple[str, list[str], bool]] = []
    run: list[tuple[str, bool]] = []

    def flush() -> None:
        nonlocal run
        if not run:
            return
        if len(run) >= 2:
            words = [token for token, _flag in run]
            candidates.append((" ".join(words).casefold(), words, False))
        else:
            token, initial = run[0]
            if not initial and len(token) >= 3 and not token.isupper():
                candidates.append((token.casefold(), [token], True))
        run = []

    for token, initial in _tokenize(text):
        if token[0].isupper():
            run.append((token, initial))
        else:
            flush()
    flush()
    return candidates


# --- Angka & tanggal ---


def _numbers(text: str) -> list[str]:
    return [match.group(0) for match in _NUMBER_RE.finditer(text or "")]


def _date_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for regex in (_SLASH_DATE_RE, _ISO_DATE_RE, _YEAR_RE):
        tokens.extend(match.group(0) for match in regex.finditer(text or ""))
    return tokens


# --- Pemeriksa per aturan ---


def _source_resolves(source_ref: str, lines: list[str]) -> bool:
    """R1: source_ref (dinormalisasi) adalah awalan salah satu baris CV."""
    ref = _normalize(source_ref)
    if not ref:
        return False
    for line in lines:
        for candidate in (_normalize(line), _normalize(_strip_line_markers(line))):
            if candidate and candidate.startswith(ref):
                return True
    return False


def _check_entities(
    suggested: str, lexicon_words: set[str], lexicon_phrases: set[str], title_words: set[str]
) -> str | None:
    """R3 (entitas): None bila bersih, else detail pelanggaran pertama."""
    allowed = lexicon_words | title_words
    for phrase, words, single in _proper_noun_candidates(suggested):
        if single:
            if not _word_known(words[0].casefold(), allowed):
                return f"Entitas '{words[0]}' tidak ada di CV maupun judul lowongan."
            continue
        if phrase in lexicon_phrases:
            continue
        unknown = [
            word for word in words if len(word) >= 3 and not _word_known(word.casefold(), allowed)
        ]
        if unknown:
            return f'Entitas "{" ".join(words)}" tidak ada di CV maupun judul lowongan.'
    return None


def _check_numbers(suggested: str, allowed_numbers: set[str]) -> str | None:
    """R3 (angka): angka di suggested harus sudah ada di original_text/CV."""
    for number in _numbers(suggested):
        if number not in allowed_numbers:
            return f"Angka {number} tidak ada di teks asli maupun CV."
    return None


# --- Kontrak publik ---


def validate_edits(edits: list[Any], cv_payload: dict, job_title: str) -> dict[str, Any]:
    """Validasi grounding seluruh edit (R1-R4).

    Mengembalikan {"passed": bool, "violations": [{"suggestion_id", "rule",
    "detail"}], "checked": n} — total & deterministik. `passed` True hanya bila
    tidak ada pelanggaran sama sekali.
    """
    lines = (build_cv_text(cv_payload) or "").splitlines()
    lexicon_words, lexicon_phrases = _payload_lexicon(cv_payload or {})
    title_words = {word.casefold() for word in _WORD_RE.findall(job_title or "")}
    cv_numbers = set(_numbers(build_cv_text(cv_payload) or ""))

    violations: list[dict[str, str]] = []
    checked = 0
    for index, edit in enumerate(edits or []):
        if not isinstance(edit, dict):
            continue
        checked += 1
        suggestion_id = str(edit.get("suggestion_id") or f"edit-{index}")
        source_ref = str(edit.get("source_ref") or "")
        original = str(edit.get("original_text") or "")
        suggested = str(edit.get("suggested_text") or "")
        change_type = str(edit.get("change_type") or "")

        # R1 — source_ref harus merujuk baris teks CV yang benar-benar ada.
        if not _source_resolves(source_ref, lines):
            violations.append(
                {
                    "suggestion_id": suggestion_id,
                    "rule": "source_not_found",
                    "detail": "source_ref tidak ditemukan sebagai awalan baris teks CV.",
                }
            )

        # R2 — change_type harus dari daftar beku.
        if change_type not in CHANGE_TYPES:
            violations.append(
                {
                    "suggestion_id": suggestion_id,
                    "rule": "change_type_invalid",
                    "detail": (
                        f"change_type '{change_type}' bukan salah satu dari: "
                        + ", ".join(CHANGE_TYPES)
                    ),
                }
            )

        # R3a — proper noun tidak boleh difabrikasi.
        entity_detail = _check_entities(suggested, lexicon_words, lexicon_phrases, title_words)
        if entity_detail:
            violations.append(
                {
                    "suggestion_id": suggestion_id,
                    "rule": "fabricated_entity",
                    "detail": entity_detail,
                }
            )

        # R3b — angka baru dilarang (quantify pun hanya boleh memakai angka yang
        # sudah ada di original_text atau di CV; aturan beku prompt senada).
        allowed_numbers = cv_numbers | set(_numbers(original))
        number_detail = _check_numbers(suggested, allowed_numbers)
        if number_detail:
            violations.append(
                {
                    "suggestion_id": suggestion_id,
                    "rule": "fabricated_number",
                    "detail": number_detail,
                }
            )

        # R4 — tanggal/tahun tidak boleh baru relatif terhadap original_text.
        allowed_dates = set(_date_tokens(original))
        for token in _date_tokens(suggested):
            if token not in allowed_dates:
                violations.append(
                    {
                        "suggestion_id": suggestion_id,
                        "rule": "date_modified",
                        "detail": f"Tanggal/tahun {token} tidak ada di teks asli.",
                    }
                )
                break

    return {"passed": not violations, "violations": violations, "checked": checked}


def ensure_suggestion_ids(edits: list[Any]) -> list[dict]:
    """Pastikan tiap edit punya `suggestion_id` stabil & unik (kontrak decisions).

    ID hilang/kosong/duplikat diganti `edit-{index}` (dengan suffix bila masih
    bentrok). Mengembalikan list edit yang valid (dict) — bukan dict lain.
    """
    seen: set[str] = set()
    normalized: list[dict] = []
    for index, edit in enumerate(edits or []):
        if not isinstance(edit, dict):
            continue
        suggestion_id = edit.get("suggestion_id")
        if not isinstance(suggestion_id, str) or not suggestion_id or suggestion_id in seen:
            suggestion_id = f"edit-{index}"
            suffix = 1
            while suggestion_id in seen:
                suggestion_id = f"edit-{index}-{suffix}"
                suffix += 1
        edit["suggestion_id"] = suggestion_id
        seen.add(suggestion_id)
        normalized.append(edit)
    return normalized
