"""Ekstraksi entitas murni regex/heuristik per section (tanpa Pydantic, tanpa LLM).

Semua fungsi dirancang TOTAL: tidak pernah melempar exception pada input aneh —
kembalikan list kosong / None. Deterministik terhadap input yang sama; hasil
tiap fungsi berupa tipe Python polos (dict/list/str/float/None) dan hanya
dipetakan ke skema Pydantic oleh payload_schema di lapisan parser.
"""

import re

# ---------------------------------------------------------------- regex dasar
# Email divalidasi via pemindaian "@" manual (linear) + fullmatch regex;
# regex murni dengan char-class panjang di depan bersifat kuadratik pada
# baris panjang tanpa "@" (mesin regex mencoba mulai di setiap posisi).
_EMAIL_FULL_RE = re.compile(r"[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,255}\.[A-Za-z]{2,24}")
_EMAIL_LOCAL_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._%+-"
)
# Telepon Indonesia: +62… / 08…, spasi dan strip diperbolehkan; lookaround
# agar digit di dalam email/kata tidak ikut terhisap.
_PHONE_RE = re.compile(r"(?<![\w@])(?:\+62|0)[\d\s\-]{6,16}\d(?![\w@])")
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s|,;]+", re.IGNORECASE)
_PROFILE_URL_RE = re.compile(r"\b(?:linkedin\.com|github\.com|gitlab\.com)/[^\s|,;]+", re.I)
# Lokasi HANYA dipercaya bila baris header memuat awalan eksplisit ini.
_LOCATION_RE = re.compile(r"^(?:lokasi|location|alamat|address)\s*[:\-]?\s*(.+)$", re.IGNORECASE)

# Nama: kata-kata alfabetis (boleh titik), tanpa digit/@/http.
_NAME_WORDS_RE = re.compile(r"[A-Za-zÀ-ÿ.']+", re.UNICODE)
_NAME_LINE_RE = re.compile(r"^[A-Za-zÀ-ÿ]([A-Za-zÀ-ÿ.'\s]*[A-Za-zÀ-ÿ.])?$", re.UNICODE)
_NAME_CONTACT_MARKER_RE = re.compile(r"\d|@|https?://|www\.", re.IGNORECASE)
# Pola umum header CV: "Nama — Headline" / "Nama – Headline" / "Nama - Headline"
# / "Nama | Headline" (pemisah dengan spasi di sekelilingnya).
_NAME_SEPARATORS = (" — ", " – ", " - ", " | ")

# ---------------------------------------------------------------- rentang tanggal
_MONTHS: dict[str, int] = {
    "januari": 1,
    "jan": 1,
    "februari": 2,
    "feb": 2,
    "maret": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "mei": 5,
    "may": 5,
    "juni": 6,
    "jun": 6,
    "juli": 7,
    "jul": 7,
    "agustus": 8,
    "agu": 8,
    "agt": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "oktober": 10,
    "okt": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "desember": 12,
    "des": 12,
    "dec": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_CURRENT_RE = re.compile(r"^(?:sekarang|present|current|ongoing|kini)$", re.IGNORECASE)

# Anchor tanggal tunggal (urutan penting: bentuk spesifik sebelum tahun polos).
_A_YM = r"\b\d{4}-\d{1,2}\b"  # 2023-01
_A_MY = r"\b\d{1,2}/\d{4}\b"  # 01/2023
_A_MONYEAR = rf"\b(?:{_MONTH_ALT})\.?\s*,?\s*\d{{4}}\b"  # Jan 2023 / Januari 2023
_A_YEARMON = rf"\b\d{{4}}\s+(?:{_MONTH_ALT})\b"  # 2023 Jan
_A_YEAR = r"\b(?:19|20)\d{2}\b"  # 2023
# Pemisah rentang: -, –, —, to, s.d., sampai.
_RANGE_SEP = r"\s*(?:-|–|—|\bto\b|\bs\.d\.|\bsampai\b)\s*"

_RANGE_RE = re.compile(
    rf"(?P<start>(?:{_A_YM})|(?:{_A_MY})|(?:{_A_MONYEAR})|(?:{_A_YEARMON})|(?:{_A_YEAR}))"
    rf"(?P<sep>{_RANGE_SEP})"
    rf"(?P<end>(?:{_A_YM})|(?:{_A_MY})|(?:{_A_MONYEAR})|(?:{_A_YEARMON})|(?:{_A_YEAR})"
    rf"|\b(?:sekarang|present|current|ongoing|kini)\b)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------- pengalaman
_PAREN_RE = re.compile(r"\(([^()]*)\)")
# Pemisah judul-perusahaan: em/en dash (spasi opsional) atau strip ber-spasi.
_TITLE_COMPANY_SPLIT_RE = re.compile(r"\s*[—–]\s*|\s+-\s+")

# ---------------------------------------------------------------- pendidikan
_DEGREE_RE = re.compile(
    r"\b(S1|S2|S3|D3|D4|SMA|SMK|SLTA|SMP|Sarjana|Magister|Doktor|Diploma|BSc|B\.S\."
    r"|MSc|M\.S\.|B\.A\.|M\.A\.|B\.Eng|Bachelor|Master|PhD|Ph\.D|High School)(?!\w)",
    re.IGNORECASE,
)
_GPA_RE = re.compile(r"(?:IPK|GPA)\s*[:=]?\s*(\d[.,]\d{1,2})", re.IGNORECASE)
_EDU_SPLIT_RE = re.compile(r"\s*,\s*|\s*[—–]\s*|\s+di\s+|\s+at\s+", re.IGNORECASE)
_EDU_FIELD_PREFIX_RE = re.compile(r"^(?:jurusan|program studi|prodi|in|bidang)\s+", re.IGNORECASE)

# ---------------------------------------------------------------- bahasa
_LANGUAGES: tuple[str, ...] = (
    "bahasa indonesia",
    "indonesian",
    "inggris",
    "english",
    "arab",
    "arabic",
    "mandarin",
    "chinese",
    "jepang",
    "japanese",
    "korea",
    "jerman",
    "german",
    "perancis",
    "french",
    "spanyol",
    "spanish",
    "hokkien",
    "jawa",
    "sunda",
)
_LANGUAGE_LEVELS: tuple[str, ...] = (
    "native",
    "fluent",
    "advanced",
    "intermediate",
    "basic",
    "dasar",
    "mahir",
    "lancar",
)


def _strip_bullet(line: str) -> str:
    """Buang penanda bullet "• " hasil preprocess (verbatim teks item)."""
    text = line.strip()
    return text[1:].strip() if text.startswith("•") else text


# ================================================================ contact
def extract_contact(lines: list[str]) -> dict:
    """Ekstrak {name, email, phone, location, links} + confidence & evidence per
    field dari zona header (baris sebelum judul section pertama)."""
    name: str | None = None
    name_conf = 0.0
    name_evidence = ""
    email: str | None = None
    email_evidence = ""
    phone: str | None = None
    phone_evidence = ""
    location: str | None = None
    location_evidence = ""
    links: list[str] = []
    seen_links: set[str] = set()
    nonblank = 0

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        nonblank += 1

        if email is None and (found := _find_email(line)):
            email = found
            email_evidence = line
        if phone is None and (match := _PHONE_RE.search(line)):
            phone = match.group(0).strip()
            phone_evidence = line
        for match in _URL_RE.finditer(line):
            # Samakan host ber-"www." agar tidak dobel dengan _PROFILE_URL_RE.
            url = re.sub(r"^(https?://)www\.", r"\1", match.group(0), flags=re.IGNORECASE)
            _add_link(links, seen_links, url.rstrip(".,;"))
        for match in _PROFILE_URL_RE.finditer(line):
            _add_link(links, seen_links, "https://" + match.group(0).rstrip(".,;"))
        if location is None and (match := _LOCATION_RE.match(line)):
            location = match.group(1).strip() or None
            location_evidence = line

        # Nama hanya dicari di beberapa baris teratas zona header.
        if name is None and nonblank <= 5:
            candidate, confidence = _name_from_line(line)
            if candidate is not None:
                name, name_conf, name_evidence = candidate, confidence, line

    return {
        "name": name,
        "email": email,
        "phone": phone,
        "location": location,
        "links": links,
        "confidence": {
            "name": name_conf,
            "email": 0.95 if email else 0.0,
            "phone": 0.9 if phone else 0.0,
            "location": 0.9 if location else 0.0,
        },
        "evidence": {
            "name": name_evidence,
            "email": email_evidence,
            "phone": phone_evidence,
            "location": location_evidence,
        },
    }


def _add_link(links: list[str], seen: set[str], url: str) -> None:
    key = url.lower()
    if key not in seen:
        seen.add(key)
        links.append(url)


def _find_email(line: str) -> str | None:
    """Cari alamat email secara linear: kandang setiap "@", perluas local-part
    ke kiri dan domain ke kanan dengan batas panjang, lalu validasi. Teliti
    hingga "@" pertama yang valid; kembalikan None bila tidak ada."""
    start = 0
    while (at := line.find("@", start)) != -1:
        max_left = max(0, at - 64)
        left = at
        while left > max_left and line[left - 1] in _EMAIL_LOCAL_CHARS:
            left -= 1
        limit = min(len(line), at + 1 + 256)
        right = at + 1
        while right < limit and (line[right].isalnum() or line[right] in ".-"):
            right += 1
        candidate = line[left:right].rstrip(".-")
        if _EMAIL_FULL_RE.fullmatch(candidate):
            return candidate
        start = at + 1
    return None


def _name_from_line(line: str) -> tuple[str | None, float]:
    """Heuristik nama (M1 refinement):
    - baris mengandung pemisah " — " / " – " / " - " / " | " dan sisi kiri
      terdiri dari 1–4 kata alfabetis → nama = sisi kiri (confidence 0.8,
      pola umum "Nama — Headline");
    - tanpa pemisah yang memenuhi syarat → baris utuh 2–4 kata alfabetis
      tanpa digit/@/http (confidence 0.9);
    - tanpa kandidat valid → (None, 0.0)."""
    for sep in _NAME_SEPARATORS:
        if sep in line:
            left = line.split(sep, 1)[0].strip()
            if _is_name_candidate(left, min_words=1, max_words=4):
                return left, 0.8
    candidate = line.strip().strip(",|")
    if _is_name_candidate(candidate, min_words=2, max_words=4):
        return candidate, 0.9
    return None, 0.0


def _is_name_candidate(text: str, *, min_words: int, max_words: int) -> bool:
    text = text.strip()
    if not text or _NAME_CONTACT_MARKER_RE.search(text):
        return False
    if not _NAME_LINE_RE.match(text):
        return False
    return min_words <= len(_NAME_WORDS_RE.findall(text)) <= max_words


# ================================================================ tanggal
def _find_range_match(text: str) -> re.Match | None:
    return _RANGE_RE.search(text) if text else None


def parse_date_range(text: str) -> tuple[str, str | None, bool] | None:
    """Kenali rentang tanggal (ID/EN) → (mulai, selesai, sedang_berjalan).

    Format didukung: "2023-01 - sekarang", "2021-07 - 2022-12",
    "Jan 2023 – Present", "Januari 2023–Desember 2024", "2022 – 2024",
    "2023 - sekarang". Tahun-bulan dinormalisasi ke "YYYY-MM" bila dapat
    diurai, selain itu string mentah. Tidak dikenali → None.
    """
    match = _find_range_match(text)
    if match is None:
        return None
    start = _normalize_anchor(match.group("start"))
    end_raw = match.group("end")
    if _CURRENT_RE.match(end_raw):
        return (start, None, True)
    return (start, _normalize_anchor(end_raw), False)


def _normalize_anchor(raw: str) -> str:
    """Normalisasi anchor tanggal → "YYYY-MM" bila tahun+bulan dapat diurai,
    selain itu string mentah (mis. tahun polos "2022")."""
    s = raw.strip().rstrip(".")
    match = re.fullmatch(r"(\d{4})-(\d{1,2})", s)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    match = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if match:
        return f"{match.group(2)}-{int(match.group(1)):02d}"
    match = re.fullmatch(rf"({_MONTH_ALT})\s*,?\s*(\d{{4}})", s, re.IGNORECASE)
    if match:
        return f"{match.group(2)}-{_MONTHS[match.group(1).lower()]:02d}"
    match = re.fullmatch(rf"(\d{{4}})\s+({_MONTH_ALT})", s, re.IGNORECASE)
    if match:
        return f"{match.group(1)}-{_MONTHS[match.group(2).lower()]:02d}"
    return s


# ================================================================ pengalaman
def extract_experiences(lines: list[str]) -> list[dict]:
    """Pecah section pengalaman menjadi entri pada baris yang memuat rentang
    tanggal (header umum: "Title — Company (periode)" / "Company | Title").
    Baris bullet "•" setelah header menjadi bullet entri (verbatim, bullet
    dibuang) sampai header entri berikutnya."""
    entries: list[dict] = []
    current: dict | None = None
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        is_bullet = stripped.startswith("•")
        if is_bullet and current is not None:
            # Bullet milik entri berjalan — meski memuat angka tahun.
            current["bullets"].append(_strip_bullet(stripped))
            continue
        period = _find_period(stripped)
        if period is None:
            continue  # baris biasa tanpa rentang tanggal: bukan header entri
        matched, remainder = period
        title, company = _split_title_company(remainder)
        parsed = parse_date_range(matched)
        start, end, is_current = parsed if parsed else (None, None, False)
        if title and company:
            confidence = 0.9
        elif matched:
            confidence = 0.6
        else:
            confidence = 0.4
        current = {
            "title": title,
            "company": company,
            "period": matched.strip() or None,
            "start": start,
            "end": end,
            "current": is_current,
            "bullets": [],
            "evidence": stripped,
            "confidence": confidence,
        }
        entries.append(current)
    return entries


def _find_period(line: str) -> tuple[str, str] | None:
    """Cari rentang tanggal di baris header → (teks_periode, baris_tanpa_periode).
    Prioritas periode dalam tanda kurung, lalu rentang di mana pun di baris."""
    for paren in _PAREN_RE.finditer(line):
        if _find_range_match(paren.group(1)) is not None:
            without = (line[: paren.start()] + " " + line[paren.end() :]).strip()
            return paren.group(1).strip(), without
    match = _find_range_match(line)
    if match is None:
        return None
    return match.group(0).strip(), line.replace(match.group(0), " ").strip()


def _split_title_company(remainder: str) -> tuple[str | None, str | None]:
    """Pisahkan sisa header menjadi (title, company): "Title — Company" via
    dash, "Company | Title" via pipe; tanpa pemisah → title saja."""
    text = remainder.strip(" \t,;|")
    if not text:
        return None, None
    if "|" in text:
        left, right = (part.strip() for part in text.split("|", 1))
        return right or None, left or None  # pola umum: Company | Title
    parts = _TITLE_COMPANY_SPLIT_RE.split(text, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip() or None, parts[1].strip() or None
    return text or None, None


# ================================================================ pendidikan
def extract_education(lines: list[str]) -> list[dict]:
    """Satu entri per baris/bullet yang memuat kata kunci jenjang (S1, S2,
    Sarjana, BSc, ...). Institusi dari teks setelah koma/di/at/—, jurusan dari
    teks antara jenjang dan pemisah, IPK & tahun bila ada."""
    results: list[dict] = []
    for raw in lines:
        line = _strip_bullet(raw)
        if not line:
            continue
        match = _DEGREE_RE.search(line)
        if match is None:
            continue

        gpa_match = _GPA_RE.search(line)
        gpa: float | None = None
        if gpa_match:
            gpa = float(gpa_match.group(1).replace(",", "."))

        years = _extract_years(line)

        # Bersihkan potongan IPK/tahun (termasuk kurung pembungkusnya) agar
        # tidak mengotori institusi/jurusan.
        work = line
        if gpa_match:
            work = work.replace(gpa_match.group(0), " ")
        if years:
            work = work.replace(f"({years})", " ").replace(years, " ")
        segments = [seg for seg in _EDU_SPLIT_RE.split(work) if seg.strip()]

        degree = match.group(0)
        deg_seg_idx = next((i for i, seg in enumerate(segments) if _DEGREE_RE.search(seg)), None)
        if deg_seg_idx is None:
            continue

        seg = segments[deg_seg_idx]
        seg_match = _DEGREE_RE.search(seg)
        assert seg_match is not None  # dijamin oleh pemilihan deg_seg_idx
        field = seg[seg_match.end() :].strip(" ,;:-")
        field = _EDU_FIELD_PREFIX_RE.sub("", field) or None
        institution = next(
            (s.strip(" ,;—–") for s in segments[deg_seg_idx + 1 :] if s.strip()), None
        )
        if institution is None:
            institution = seg[: seg_match.start()].strip(" ,;—–-") or None

        results.append(
            {
                "degree": degree,
                "institution": institution,
                "field": field,
                "years": years,
                "gpa": gpa,
                "evidence": line,
                "confidence": 0.85 if institution else 0.5,
            }
        )
    return results


def _extract_years(line: str) -> str | None:
    """Tahun (atau rentang) pendidikan: rentang dulu, lalu tahun tunggal."""
    match = _find_range_match(line)
    if match is not None:
        return match.group(0).strip()
    match = re.search(r"\b(?:19|20)\d{2}\b", line)
    return match.group(0) if match else None


# ================================================================ keahlian
def extract_skills(lines: list[str]) -> list[dict]:
    """Pecah teks section pada koma/titik-koma/bullet/baris baru; buang item
    kosong & >40 karakter (kalimat); dedupe case-insensitive urut kemunculan."""
    seen: set[str] = set()
    results: list[dict] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        for part in re.split(r"[,;•]", line):
            name = part.strip()
            if not name or len(name) > 40:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            results.append({"name": name, "evidence": line, "confidence": 0.8})
    return results


# ================================================================ sertifikasi
_CERT_YEAR_PAREN_RE = re.compile(r"\(((?:19|20)\d{2})\)\s*$")
_CERT_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\s*$")
_CERT_ISSUER_SPLIT_RE = re.compile(r"\s+(?:—|–|-|by|dari)\s+", re.IGNORECASE)


def extract_certifications(lines: list[str]) -> list[dict]:
    """Per bullet/baris: nama = teks sebelum tahun di ekor (atau pemisah
    penerbit —/-/by/dari); tahun 4 digit rentang wajar 1990–2035."""
    results: list[dict] = []
    for raw in lines:
        line = _strip_bullet(raw)
        if not line:
            continue
        evidence = line
        year = _pop_trailing_year(line)
        work = line if year is None else line[: -len(_trailing_year_text(line))].strip()
        work = work.rstrip("(),;: ").strip()

        parts = _CERT_ISSUER_SPLIT_RE.split(work, maxsplit=1)
        name = parts[0].strip(" ,;—–-")
        if not name:
            continue
        issuer = parts[1].strip(" ,;—–-") if len(parts) == 2 else None
        results.append(
            {
                "name": name,
                "issuer": issuer or None,
                "year": year,
                "evidence": evidence,
                "confidence": 0.75,
            }
        )
    return results


def _pop_trailing_year(line: str) -> int | None:
    """Tahun di ekor baris (dalam kurung atau telanjang) bila rentang wajar."""
    match = _CERT_YEAR_PAREN_RE.search(line) or _CERT_YEAR_RE.search(line)
    if match is None:
        return None
    year = int(match.group(1))
    return year if 1990 <= year <= 2035 else None


def _trailing_year_text(line: str) -> str:
    """Potongan ekor baris yang menyimpan tahun (untuk dipangkas)."""
    match = _CERT_YEAR_PAREN_RE.search(line) or _CERT_YEAR_RE.search(line)
    return line[match.start() :] if match else ""


# ================================================================ bahasa
def extract_languages(lines: list[str]) -> list[dict]:
    """Kenali nama bahasa (ID/EN) + level opsional (native, fluent, mahir,
    lancar, ...). Level diikat ke bahasa terdekat di segmennya: baris
    "Bahasa Indonesia (native), Inggris (lancar)" → dua entri berbeda level."""
    results: list[dict] = []
    for raw in lines:
        line = _strip_bullet(raw)
        if not line:
            continue
        # Kumpulkan match bahasa, hindari span tumpang-tindih (alias panjang menang).
        matches: list[tuple[int, str]] = []
        spans: list[tuple[int, int]] = []
        for alias in sorted(_LANGUAGES, key=len, reverse=True):
            for match in re.finditer(rf"\b{re.escape(alias)}\b", line, re.IGNORECASE):
                if any(match.start() < end and match.end() > start for start, end in spans):
                    continue
                spans.append((match.start(), match.end()))
                matches.append((match.start(), match.group(0)))
        matches.sort()
        seen: set[str] = set()
        for idx, (pos, language) in enumerate(matches):
            key = language.casefold()
            if key in seen:
                continue
            seen.add(key)
            end = matches[idx + 1][0] if idx + 1 < len(matches) else len(line)
            level = _find_language_level(line[pos:end])
            results.append(
                {"language": language, "level": level, "evidence": line, "confidence": 0.8}
            )
    return results


def _find_language_level(line: str) -> str | None:
    for level in _LANGUAGE_LEVELS:
        match = re.search(rf"\b{re.escape(level)}\b", line, re.IGNORECASE)
        if match is not None:
            return match.group(0)
    return None


# ================================================================ proyek
_PROJECT_SPLIT_RE = re.compile(r":\s+|\s*[—–]\s*")


def extract_projects(lines: list[str]) -> list[dict]:
    """Entri bullet: nama = teks sebelum ":" atau "—", deskripsi = sisanya;
    tanpa pemisah → nama None, deskripsi satu baris."""
    results: list[dict] = []
    for raw in lines:
        line = _strip_bullet(raw)
        if not line:
            continue
        parts = _PROJECT_SPLIT_RE.split(line, maxsplit=1)
        if len(parts) == 2:
            name, description = parts[0].strip() or None, parts[1].strip() or None
        else:
            name, description = None, line
        results.append(
            {"name": name, "description": description, "evidence": line, "confidence": 0.7}
        )
    return results


# ================================================================ penghargaan
def extract_awards(lines: list[str]) -> list[dict]:
    """Per bullet/baris → teks apa adanya (verbatim) sebagai penghargaan."""
    results: list[dict] = []
    for raw in lines:
        line = _strip_bullet(raw)
        if not line:
            continue
        results.append({"text": line, "evidence": line, "confidence": 0.7})
    return results
