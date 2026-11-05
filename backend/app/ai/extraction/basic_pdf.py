"""Basic PDF text extraction — boundary pertama modul AI.

P2 hanya mengekstrak teks mentah + jumlah halaman (PyMuPDF). Pipeline penuh
(segmentasi section, taksonomi skill, entity) adalah pekerjaan fase AI berikutnya;
struktur data `cv_extractions` sudah menyiapkan tempatnya.
"""

import logging

logger = logging.getLogger(__name__)

PARSER_VERSION = "pymupdf-basic-v1"
MAX_TEXT_CHARS = 200_000


class PdfExtractionError(Exception):
    """Gagal mengekstrak PDF (rusak, terproteksi, terlalu panjang, dst.)."""


def extract_text_from_pdf(path: str, *, max_pages: int) -> tuple[int, str]:
    try:
        import fitz  # pymupdf
    except ImportError as exc:  # pragma: no cover
        raise PdfExtractionError("Parser PDF tidak tersedia.") from exc

    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise PdfExtractionError("Berkas PDF tidak dapat dibaca.") from exc

    try:
        if doc.needs_pass:
            raise PdfExtractionError("PDF terproteksi kata sandi.")
        if doc.page_count == 0:
            raise PdfExtractionError("PDF tidak memiliki halaman yang dapat dibaca.")
        if doc.page_count > max_pages:
            raise PdfExtractionError(f"Jumlah halaman melebihi batas ({max_pages} halaman).")
        pages = doc.page_count
        text = "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()

    if not text.strip():
        raise PdfExtractionError("PDF tidak mengandung teks (kemungkinan hasil pindai).")

    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
    return pages, text
