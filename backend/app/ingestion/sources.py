"""Konektor sumber lowongan publik — read-only API, TANPA kunci & TANPA scraping.

Aturan atribusi (docs/03-final-scope-and-feasibility.md §3):
- RemoteOK (`remoteok.com/api`): elemen pertama respons adalah notice legal —
  WAJIB dilewati; setiap item WAJIB menyimpan `url` balik ke remoteok.com
  (follow-link) sebagai atribusi → disimpan ke jobs.source_url (badge
  provenance di UI memakainya).
- Remotive (`remotive.com/api/remote-jobs`): API publik tanpa kunci; volume
  terobservasi kecil — jangan diandalkan sebagai sumber volume utama.
- Arbeitnow (`arbeitnow.com/api/job-board-api`): 300 lowongan/halaman; ToS
  melarang abuse — interval run panjang (8 jam) tetap jauh di bawah batas.

Ketatnya: semua konektor memakai httpx (timeout 20 dtk, User-Agent jelas
"proyek akademik"), sanity ukuran respons < 5 MB, dan tidak pernah melempar
exception jaringan ke pemanggil — kegagalan satu sumber → list kosong +
log warning, agar run multi-sumber tidak mati di tengah jalan.

Bentuk antara per item (di-normalize lagi oleh normalizer.to_job_payloads):
{external_id, title, company, location, description, url, tags, posted_at?,
remote} — `remote` menandai sumber/item remote utk pemetaan work_mode.

Transport dapat disuntik (`transport=httpx.MockTransport(...)`) untuk test —
pola yang sama dengan GroqClient (app/ai/optimization/llm_client.py).
"""

import logging
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)

# Kontrak HTTP bersama (docs/03 §3: API publik gratis, tanpa autentikasi).
USER_AGENT = "TalentSyncAI/1.0 (academic project)"
TIMEOUT_SECONDS = 20.0
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # sanity: 5 MB

REMOTEOK_API_URL = "https://remoteok.com/api"
REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs"
ARBEITNOW_API_URL = "https://www.arbeitnow.com/api/job-board-api"

SOURCES: tuple[str, ...] = ("remoteok", "remotive", "arbeitnow")


def _fetch_json(url: str, *, transport: httpx.BaseTransport | None = None) -> list | dict | None:
    """GET satu API publik → JSON terparse, atau None bila gagal (tidak raise).

    Kegagalan yang ditangani: error jaringan/timeout (httpx.HTTPError), status
    non-200, respons > MAX_RESPONSE_BYTES, dan body bukan JSON valid.
    """
    try:
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
            follow_redirects=True,
        ) as client:
            response = client.get(url)
        if response.status_code != 200:
            logger.warning("Ingestion %s: HTTP %d — sumber diabaikan.", url, response.status_code)
            return None
        if len(response.content) > MAX_RESPONSE_BYTES:
            logger.warning(
                "Ingestion %s: respons %.1f MB melebihi batas sanity — diabaikan.",
                url,
                len(response.content) / (1024 * 1024),
            )
            return None
        return response.json()
    except httpx.HTTPError as exc:
        logger.warning("Ingestion %s gagal (jaringan): %s — sumber diabaikan.", url, exc)
        return None
    except ValueError as exc:  # json.JSONDecodeError (subclass ValueError)
        logger.warning("Ingestion %s gagal (JSON tidak valid): %s — sumber diabaikan.", url, exc)
        return None


def _cap(items: list[dict], limit: int | None) -> list[dict]:
    """Batasi jumlah item per sumber (RemoteOK/Arbeitnow tidak punya param limit)."""
    if limit is not None and limit >= 0:
        return items[:limit]
    return items


def _epoch_to_iso(epoch: object) -> str | None:
    """Detik unix → ISO 8601 UTC (fallback posted_at RemoteOK)."""
    try:
        return datetime.fromtimestamp(int(epoch), tz=UTC).isoformat()  # type: ignore[call-arg]
    except (TypeError, ValueError, OSError):
        return None


def _clean_str(value: object) -> object:
    """Pertahankan str apa adanya, None untuk selain itu (guard API liar)."""
    return value if isinstance(value, str) else None


def fetch_remoteok(
    *, transport: httpx.BaseTransport | None = None, limit: int | None = None
) -> list[dict]:
    """RemoteOK → bentuk antara. Elemen 'legal' pertama dilewati (atribusi tetap
    dipenuhi via `url` yang dipertahankan). Seluruh katalog RemoteOK = remote."""
    payload = _fetch_json(REMOTEOK_API_URL, transport=transport)
    items: list[dict] = []
    if isinstance(payload, list):
        for raw in payload:
            if not isinstance(raw, dict) or "legal" in raw:
                continue  # notice legal / objek asing — bukan lowongan
            external_id = raw.get("slug") or raw.get("id")
            items.append(
                {
                    "external_id": str(external_id) if external_id is not None else None,
                    "title": _clean_str(raw.get("position")),
                    "company": _clean_str(raw.get("company")),
                    "location": _clean_str(raw.get("location")),
                    "description": _clean_str(raw.get("description")),
                    # Atribusi wajib (docs/03 §3): tautan balik remoteok.com dipertahankan.
                    "url": _clean_str(raw.get("url")) or _clean_str(raw.get("apply_url")),
                    "tags": raw.get("tags") if isinstance(raw.get("tags"), list) else [],
                    "posted_at": _clean_str(raw.get("date")) or _epoch_to_iso(raw.get("epoch")),
                    "remote": True,  # seluruh lowongan RemoteOK bersifat remote
                }
            )
    return _cap(items, limit)


def fetch_remotive(
    *, transport: httpx.BaseTransport | None = None, limit: int | None = None
) -> list[dict]:
    """Remotive → bentuk antara. API mendukung `?limit=`; papan 100% remote."""
    url = REMOTIVE_API_URL
    if limit is not None and limit > 0:
        url = f"{url}?limit={int(limit)}"
    payload = _fetch_json(url, transport=transport)
    items: list[dict] = []
    if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
        for raw in payload["jobs"]:
            if not isinstance(raw, dict):
                continue
            external_id = raw.get("id")
            items.append(
                {
                    "external_id": str(external_id) if external_id is not None else None,
                    "title": _clean_str(raw.get("title")),
                    "company": _clean_str(raw.get("company_name")),
                    "location": _clean_str(raw.get("candidate_required_location")),
                    "description": _clean_str(raw.get("description")),
                    "url": _clean_str(raw.get("url")),
                    "tags": raw.get("tags") if isinstance(raw.get("tags"), list) else [],
                    "posted_at": _clean_str(raw.get("publication_date")),
                    "remote": True,  # Remotive = papan lowongan remote penuh
                }
            )
    return _cap(items, limit)


def fetch_arbeitnow(
    *, transport: httpx.BaseTransport | None = None, limit: int | None = None
) -> list[dict]:
    """Arbeitnow → bentuk antara. 300 lowongan/halaman; flag `remote` per item."""
    payload = _fetch_json(ARBEITNOW_API_URL, transport=transport)
    items: list[dict] = []
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        for raw in payload["data"]:
            if not isinstance(raw, dict):
                continue
            external_id = raw.get("slug")
            items.append(
                {
                    "external_id": str(external_id) if external_id is not None else None,
                    "title": _clean_str(raw.get("title")),
                    "company": _clean_str(raw.get("company_name")),
                    "location": _clean_str(raw.get("location")),
                    "description": _clean_str(raw.get("description")),
                    "url": _clean_str(raw.get("url")),
                    "tags": raw.get("tags") if isinstance(raw.get("tags"), list) else [],
                    "posted_at": _clean_str(raw.get("created_at")),
                    "remote": bool(raw.get("remote")),
                }
            )
    return _cap(items, limit)
