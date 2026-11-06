"""Perender PDF CV hasil optimasi (M8) — ReportLab, tata letak sederhana.

Dokumen dirakit dari payload M1 (section yang terisi saja): header nama +
kontak, lalu RINGKASAN/PENGALAMAN/PENDIDIKAN/KEAHLIAN/SERTIFIKASI/BAHASA/
PROYEK. Tanpa gambar; font dasar (Helvetica) sehingga teks disanitasi ke
latin-1. UUID disematkan di metadata dokumen agar dua ekspor berisi identik
tetap menghasilkan byte berbeda — indeks unik dedupe CV (owner + sha256)
tidak pernah tabrakan antar penerapan optimasi.
"""

from __future__ import annotations

import io
import uuid

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen.canvas import Canvas

_MARGIN = 54.0
_BODY_FONT = "Helvetica"
_BOLD_FONT = "Helvetica-Bold"
_BODY_SIZE = 10.0
_LEADING = 13.0


def _clean(value: object) -> str:
    """Ke string aman-latin (font dasar PDF tidak mendukung seluruh unicode)."""
    if value is None:
        return ""
    text = str(value).strip()
    return text.encode("latin-1", "replace").decode("latin-1")


def _payload_sections(payload: dict) -> list[tuple[str, list[str]]]:
    """Rakit baris per section dari payload M1 (section kosong dilewati)."""
    sections: list[tuple[str, list[str]]] = []

    summary = _clean(payload.get("summary"))
    if summary:
        sections.append(("RINGKASAN", [summary]))

    experience_lines: list[str] = []
    for item in payload.get("experiences") or []:
        if not isinstance(item, dict):
            continue
        title = _clean(item.get("title"))
        company = _clean(item.get("company"))
        period = _clean(item.get("period"))
        head = " - ".join(part for part in (title, company) if part)
        if period:
            head = f"{head} ({period})" if head else period
        if head:
            experience_lines.append(head)
        for bullet in item.get("bullets") or []:
            text = _clean(bullet)
            if text:
                experience_lines.append(f"- {text}")
    if experience_lines:
        sections.append(("PENGALAMAN", experience_lines))

    education_lines: list[str] = []
    for item in payload.get("education") or []:
        if not isinstance(item, dict):
            continue
        degree_field = " ".join(
            part for part in (_clean(item.get("degree")), _clean(item.get("field"))) if part
        )
        parts = [
            part
            for part in (degree_field, _clean(item.get("institution")), _clean(item.get("years")))
            if part
        ]
        if item.get("gpa") is not None:
            parts.append(f"IPK {item.get('gpa')}")
        if parts:
            education_lines.append("- " + ", ".join(parts))
    if education_lines:
        sections.append(("PENDIDIKAN", education_lines))

    skill_names = [
        _clean(skill.get("name"))
        for skill in payload.get("skills") or []
        if isinstance(skill, dict)
    ]
    skill_names = [name for name in skill_names if name]
    if skill_names:
        sections.append(("KEAHLIAN", [", ".join(skill_names)]))

    certification_lines: list[str] = []
    for item in payload.get("certifications") or []:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        if not name:
            continue
        tail = ", ".join(
            part for part in (_clean(item.get("issuer")), str(item.get("year") or "")) if part
        )
        certification_lines.append(f"- {name}" + (f" ({tail})" if tail else ""))
    if certification_lines:
        sections.append(("SERTIFIKASI", certification_lines))

    language_lines: list[str] = []
    for item in payload.get("languages") or []:
        if not isinstance(item, dict):
            continue
        language = _clean(item.get("language"))
        level = _clean(item.get("level"))
        if language:
            language_lines.append(f"- {language}" + (f" ({level})" if level else ""))
    if language_lines:
        sections.append(("BAHASA", language_lines))

    project_lines: list[str] = []
    for item in payload.get("projects") or []:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        description = _clean(item.get("description"))
        if name:
            project_lines.append(f"- {name}" + (f": {description}" if description else ""))
    if project_lines:
        sections.append(("PROYEK", project_lines))

    return sections


def render_cv_pdf(payload: dict) -> bytes:
    """Render payload CV → byte PDF (A4, satu/lebih halaman, tanpa gambar)."""
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    # UUID pada metadata: byte dua ekspor identik tetap berbeda (aman dedupe).
    canvas.setTitle(f"TalentSync CV Optimasi {uuid.uuid4().hex}")
    canvas.setAuthor("TalentSync AI")

    width, height = A4
    y = height - _MARGIN

    def _ensure_space(needed: float) -> None:
        nonlocal y
        if y - needed < _MARGIN:
            canvas.showPage()
            y = height - _MARGIN

    def _write(
        text: str,
        *,
        font: str,
        size: float,
        leading: float | None = None,
        indent: float = 0.0,
    ) -> None:
        nonlocal y
        step = leading or (size + 3.0)
        usable = width - 2 * _MARGIN - indent
        for line in simpleSplit(text, font, size, usable) or [""]:
            _ensure_space(step)
            canvas.setFont(font, size)
            canvas.drawString(_MARGIN + indent, y, line)
            y -= step

    contact = payload.get("contact") or {}
    name = _clean(contact.get("name")) or "CV"
    _write(name, font=_BOLD_FONT, size=16, leading=20)

    contact_bits = [_clean(contact.get(key)) for key in ("email", "phone", "location")]
    links = [_clean(link) for link in contact.get("links") or []]
    contact_line = " | ".join(part for part in contact_bits + links if part)
    if contact_line:
        _write(contact_line, font=_BODY_FONT, size=9, leading=12)
    y -= 6

    for section_title, lines in _payload_sections(payload):
        _ensure_space(30)
        _write(section_title, font=_BOLD_FONT, size=11, leading=15)
        for line in lines:
            indent = 12.0 if line.startswith("- ") else 0.0
            _write(line, font=_BODY_FONT, size=_BODY_SIZE, leading=_LEADING, indent=indent)
        y -= 6

    canvas.showPage()
    canvas.save()
    return buffer.getvalue()
