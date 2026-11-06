"""Embedding engine (M3): chunking, perakitan teks, dan embedder singleton.

Desain (Windows CPU-only, i5/16GB):
- Model SentenceTransformer dimuat SEKALI per proses via `get_embedder`
  (singleton malas per model_name) — hook confirm/publish dan skrip re-embed
  berbagi instance yang sama, tanpa duplikasi load.
- `TextEmbedder.encode`: tiap teks dipecah `chunk_text` → seluruh chunk dari
  SEMUA teks dikirim ke model dalam SATU batch → vektor chunk per teks di-
  MEAN POOL → L2-normalize. Impor `sentence_transformers` (berat) ditunda ke
  saat model benar-benar dimuat agar test suite tidak memikul biaya impor.
- Teks CV/lowongan dirakit berlabel Indonesia (RINGKASAN/PENGALAMAN/...) agar
  model multilingual memakai sinyal section yang konsisten antar dokumen.
"""

from __future__ import annotations

import re
import threading

# Panjang chunk maksimum (karakter). MiniLM-L12 menerima 512 token (~≈500
# karakter teks Indonesia); 480 memberi margin aman untuk word-boundary wrap.
DEFAULT_MAX_CHARS = 480
# SECURITY (audit Wave 3): batas ukuran teks gabungan & jumlah judul — payload
# hasil konfirmasi kandidat tidak berbatas, tanpa ini encode bisa mem-bengkak.
MAX_DOCUMENT_CHARS = 20_000
MAX_TITLES = 50

# Ukuran batch inference model (CPU: kecil agar RAM stabil).
ENCODE_BATCH_SIZE = 16

# Pemecah paragraf: satu baris kosong (boleh berisi spasi) antar blok teks.
_BLANK_LINE_RE = re.compile(r"\n\s*\n")


def chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    """Pecah teks menjadi chunk ≤ `max_chars` karakter.

    Urutan strategi: split baris kosong dulu (paragraf utuh tidak pernah
    terpotong), lalu paragraf yang masih kepanjangan di-hard-wrap pada batas
    kata. Tidak pernah mengembalikan list kosong — teks kosong → [""].
    """
    if not text or not text.strip():
        return [""]

    paragraphs = [para.strip() for para in _BLANK_LINE_RE.split(text)]
    chunks: list[str] = []
    for para in paragraphs:
        if not para:
            continue
        if len(para) <= max_chars:
            chunks.append(para)
            continue
        current = ""
        for word in para.split():
            candidate = f"{current} {word}".strip()
            if len(candidate) > max_chars and current:
                chunks.append(current)
                current = word
            else:
                current = candidate
        if current:
            chunks.append(current)
    return chunks if chunks else [""]


def _clean(value: object) -> str:
    """Normalisasi field payload opsional → string bersih (None-safe)."""
    if value is None:
        return ""
    return str(value).strip()


def build_cv_text(payload: dict) -> str:
    """Rakit teks CV terstruktur berlabel Indonesia dari payload M1.

    Hanya section yang terisi yang disertakan (urutan tetap: identitas →
    ringkasan → pengalaman → pendidikan → keahlian → sertifikasi → bahasa →
    proyek) supaya distribusi token konsisten antar CV.
    """
    contact = payload.get("contact") or {}
    lines: list[str] = []

    name = _clean(contact.get("name"))
    contact_bits = [
        _clean(contact.get(key))
        for key in ("email", "phone", "location")
        if _clean(contact.get(key))
    ]
    links = [_clean(link) for link in (contact.get("links") or []) if _clean(link)]
    if name:
        lines.append(f"NAMA: {name}")
    if contact_bits or links:
        lines.append("KONTAK: " + " | ".join(contact_bits + links))

    summary = _clean(payload.get("summary"))
    if summary:
        lines.append("RINGKASAN")
        lines.append(summary)

    experiences = payload.get("experiences") or []
    if experiences:
        lines.append("PENGALAMAN")
        for item in experiences:
            title = _clean(item.get("title")) or "Tanpa jabatan"
            company = _clean(item.get("company"))
            period = _clean(item.get("period"))
            role_bits = f"{title} — {company}" if company else title
            if period:
                role_bits += f" ({period})"
            lines.append(f"- {role_bits}")
            for bullet in item.get("bullets") or []:
                bullet_text = _clean(bullet)
                if bullet_text:
                    lines.append(f"  - {bullet_text}")

    education = payload.get("education") or []
    if education:
        lines.append("PENDIDIKAN")
        for item in education:
            degree = _clean(item.get("degree"))
            field = _clean(item.get("field"))
            head = f"{degree} {field}".strip()
            institution = _clean(item.get("institution"))
            edu_bits = [part for part in (head, institution) if part]
            years = _clean(item.get("years"))
            if years:
                edu_bits.append(f"({years})")
            gpa = item.get("gpa")
            if gpa is not None:
                edu_bits.append(f"IPK {gpa}")
            if edu_bits:
                lines.append("- " + ", ".join(edu_bits))

    skills = payload.get("skills") or []
    if skills:
        lines.append("KEAHLIAN")
        names = [_clean(skill.get("name")) for skill in skills]
        lines.append(", ".join(name for name in names if name))

    certifications = payload.get("certifications") or []
    if certifications:
        lines.append("SERTIFIKASI")
        for item in certifications:
            cert = _clean(item.get("name"))
            issuer = _clean(item.get("issuer"))
            year = item.get("year")
            tail = ", ".join(part for part in (issuer, str(year) if year else "") if part)
            lines.append(f"- {cert}" + (f" ({tail})" if tail else ""))

    languages = payload.get("languages") or []
    if languages:
        lines.append("BAHASA")
        for item in languages:
            language = _clean(item.get("language"))
            level = _clean(item.get("level"))
            lines.append(f"- {language}" + (f" ({level})" if level else ""))

    projects = payload.get("projects") or []
    if projects:
        lines.append("PROYEK")
        for item in projects:
            project = _clean(item.get("name"))
            description = _clean(item.get("description"))
            lines.append(f"- {project}" + (f": {description}" if description else ""))

    # Cap anti-bengkak (audit Wave 3): payload konfirmasi tidak berbatas.
    return "\n".join(lines).strip()[:MAX_DOCUMENT_CHARS]


def build_job_text(
    *,
    title: str,
    skill_names: list[str],
    description: str,
    requirements: str | None = None,
    responsibilities: str | None = None,
) -> str:
    """Rakit teks lowongan berlabel Indonesia (POSISI/KUALIFIKASI/KEAHLIAN/
    TANGGUNG JAWAB). Section opsional hanya disertakan bila terisi."""
    lines = ["POSISI", title.strip()]
    if description and description.strip():
        lines.append(description.strip())

    if requirements and requirements.strip():
        lines.append("KUALIFIKASI")
        lines.append(requirements.strip())

    names = [name.strip() for name in skill_names if name and name.strip()]
    if names:
        lines.append("KEAHLIAN")
        lines.append(", ".join(names))

    if responsibilities and responsibilities.strip():
        lines.append("TANGGUNG JAWAB")
        lines.append(responsibilities.strip())

    return "\n".join(lines).strip()[:MAX_DOCUMENT_CHARS]  # cap anti-bengkak


class TextEmbedder:
    """Pembungkus SentenceTransformer: encode teks → chunk → batch → mean pool
    → L2-normalize. Model dimuat malas pada `encode` pertama (sekali per
    instance; instance-nya sendiri disingleton oleh `get_embedder`)."""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None  # dimuat malas — impor berat torch/ST ditunda juga

    def _load_model(self):
        """Muat model embedding (dipanggil sekali; monkeypatch-able di test)."""
        # Impor di dalam fungsi: mengimpor sentence_transformers menarik torch
        # (puluhan detik di Windows) — jangan biarkan terjadi saat impor modul.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode daftar teks → daftar vektor L2-normalized (dim model).

        Seluruh chunk dari semua teks di-encode dalam satu panggilan batch,
        lalu vektor chunk tiap teks dirata-rata (mean pooling) dan dinormalkan.
        """
        if not texts:
            return []
        model = self._model if self._model is not None else self._load_model()

        all_chunks: list[str] = []
        spans: list[tuple[int, int]] = []
        for text in texts:
            start = len(all_chunks)
            all_chunks.extend(chunk_text(text))
            spans.append((start, len(all_chunks)))

        # Impor numpy dijalankan malas (ikut terpakai saat model dipakai).
        import numpy as np

        matrix = np.asarray(
            model.encode(
                all_chunks,
                batch_size=ENCODE_BATCH_SIZE,
                convert_to_numpy=True,
                normalize_embeddings=False,
                show_progress_bar=False,
            ),
            dtype=float,
        )

        vectors: list[list[float]] = []
        for start, end in spans:
            mean = matrix[start:end].mean(axis=0)
            norm = float(np.linalg.norm(mean))
            if norm > 0.0:
                mean = mean / norm
            vectors.append([float(value) for value in mean])
        return vectors


# Singleton malas per model_name: hook confirm/publish dan skrip re-embed dalam
# satu proses berbagi instance yang sama — model tidak pernah dimuat ganda.
_EMBEDDER_CACHE: dict[str, TextEmbedder] = {}
# Lock muat model: thread pre-warm startup & thread request pertama tidak boleh
# saling memuat model secara bersamaan (double-load torch = ±60 dtk, Wave 3).
_EMBEDDER_LOCK = threading.Lock()


def get_embedder(model_name: str) -> TextEmbedder:
    """Ambil TextEmbedder singleton untuk `model_name` (muat sekali per proses).

    Double-checked locking: pre-warm startup dan request pertama berbagi satu
    pemuatan model — pemenit kedua memastikan tidak ada double-load."""
    embedder = _EMBEDDER_CACHE.get(model_name)
    if embedder is None:
        with _EMBEDDER_LOCK:
            embedder = _EMBEDDER_CACHE.get(model_name)
            if embedder is None:
                embedder = TextEmbedder(model_name)
                _EMBEDDER_CACHE[model_name] = embedder
    return embedder
