"""Klien LLM Groq (M8): satu adapter untuk generasi saran optimasi CV.

Perilaku beku (Wave 5):
- POST {base_url}/chat/completions, temperature 0.2.
- response_format json_schema strict=True lebih dulu; 400 (skema ditolak) →
  satu percobaan ulang dengan json_object pada model yang sama.
- 429/5xx → SATU percobaan ulang dengan menunggu Retry-After (dibatasi 10
  detik) → lalu model fallback → gagal lagi → LLMError (pesan aman pengguna,
  bahasa Indonesia). 400 setelah json_object juga dianggap gagal model tsb.
- Timeout 60 detik. Kunci API TIDAK PERNAH masuk log/pesan error.
- Pemakaian token (usage) terekam di `last_usage`; model yang benar-benar
  dipakai di `last_model`; gabungan keduanya di properti `last_meta`.

Unit test WAJIB memakai httpx.MockTransport lewat parameter konstruktor
`transport` (dan `sleep_fn` agar Retry-After tidak benar-benar menunggu) —
tidak ada panggilan jaringan nyata di test.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.ai.optimization.prompts import EDITS_JSON_SCHEMA
from app.core.config import Settings
from app.core.exceptions import DomainError

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_RETRY_WAIT_SECONDS = 10.0


class LLMError(DomainError):
    """Kegagalan LLM yang aman ditampilkan ke pengguna (pesan Indonesia).

    DomainError-style: dipetakan envelope core.errors → kode LLM_UNAVAILABLE.
    """

    status_code = 503
    code = "LLM_UNAVAILABLE"
    default_message = "Layanan AI sedang tidak tersedia. Silakan coba lagi nanti."


_FENCE_RE = re.compile(r"\A```(?:json)?\s*|\s*```\Z")


class GroqClient:
    """Adapter HTTP Groq (OpenAI-compatible /chat/completions)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        fallback_model: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._fallback_model = fallback_model
        self._sleep_fn = sleep_fn
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        # Jejak panggilan sukses terakhir (observability & audit M8).
        self.last_model: str | None = None
        self.last_usage: dict[str, Any] | None = None

    # --- lifecycle ---

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> GroqClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def last_meta(self) -> dict[str, Any]:
        """Meta panggilan sukses terakhir: model aktual + pemakaian token."""
        return {"model": self.last_model, "usage": self.last_usage}

    # --- factory ---

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: Any) -> GroqClient | None:
        """Bangun klien dari Settings; None bila fitur LLM nonaktif (kunci kosong)."""
        if not settings.groq_api_key:
            return None
        return cls(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            fallback_model=settings.groq_model_fallback,
            **kwargs,
        )

    # --- kontrak utama ---

    def generate_optimizations(self, system: str, user: str) -> dict[str, Any]:
        """Kirim prompt → dict JSON hasil parse (kontrak beku Wave 5).

        Coba model utama lalu model fallback (masing-masing dengan tangga
        json_schema → json_object dan satu retry 429/5xx); seluruh tangga gagal
        → LLMError dengan pesan generik yang aman untuk pengguna.
        """
        failures: list[str] = []
        for model in (self._model, self._fallback_model):
            try:
                return self._call_model(model, system, user)
            except LLMError as exc:
                failures.append(f"{model}: {exc.message}")
        # Detail teknis hanya ke log (nama model + status — tanpa kunci API);
        # pesan pengguna tetap generik.
        logger.warning("Semua model Groq gagal: %s", " | ".join(failures))
        raise LLMError(
            "Layanan AI gagal memproses permintaan setelah beberapa percobaan. "
            "Silakan coba lagi nanti."
        )

    # --- internal ---

    def _call_model(self, model: str, system: str, user: str) -> dict[str, Any]:
        """Satu model: json_schema → (400) json_object → (429/5xx) satu retry."""
        use_schema = True
        response = self._post(self._request_payload(model, system, user, use_schema))
        if response.status_code == 400:
            # Skema JSON ditolak provider → turunkan ke json_object (sekali).
            use_schema = False
            response = self._post(self._request_payload(model, system, user, use_schema))
        if self._is_retryable(response.status_code):
            self._wait_retry_after(response)
            response = self._post(self._request_payload(model, system, user, use_schema))
            if response.status_code == 400 and use_schema:
                use_schema = False
                response = self._post(self._request_payload(model, system, user, use_schema))
        if response.status_code != 200:
            raise LLMError("Layanan AI sedang sibuk atau tidak tersedia. Silakan coba lagi nanti.")
        content = self._extract_content(response)
        return self._parse(content, model)

    @staticmethod
    def _request_payload(
        model: str, system: str, user: str, use_json_schema: bool
    ) -> dict[str, Any]:
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": GroqClient._response_format(use_json_schema),
        }

    @staticmethod
    def _response_format(use_json_schema: bool) -> dict[str, Any]:
        if use_json_schema:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "cv_optimization_edits",
                    "strict": True,
                    "schema": EDITS_JSON_SCHEMA,
                },
            }
        return {"type": "json_object"}

    @staticmethod
    def _is_retryable(status_code: int) -> bool:
        return status_code == 429 or 500 <= status_code <= 599

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        try:
            return self._http.post(
                "/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as exc:
            # Hanya tipe exception yang dicatat — header/kunci tidak pernah masuk log.
            logger.warning("Panggilan Groq gagal (tanpa respons): %s", type(exc).__name__)
            raise LLMError("Layanan AI tidak dapat dihubungi. Silakan coba lagi nanti.") from exc

    def _extract_content(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("Respons AI tidak dapat dibaca. Silakan coba lagi nanti.") from exc
        usage = data.get("usage")
        self.last_usage = dict(usage) if isinstance(usage, dict) else None
        choices = data.get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
        content = (message or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMError("Respons AI kosong. Silakan coba lagi nanti.")
        return content

    def _parse(self, content: str, model: str) -> dict[str, Any]:
        text = _FENCE_RE.sub("", content.strip()).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Konten LLM bukan JSON valid: %s", exc)
            raise LLMError(
                "Respons AI tidak berformat JSON yang valid. Silakan coba lagi nanti."
            ) from exc
        if not isinstance(parsed, dict):
            raise LLMError("Respons AI tidak berformat yang diharapkan. Silakan coba lagi nanti.")
        self.last_model = model
        return parsed

    def _wait_retry_after(self, response: httpx.Response) -> None:
        """Tunggu Retry-After (detik, maks 10); tanpa header → langsung coba ulang."""
        raw = response.headers.get("retry-after")
        if not raw:
            return
        try:
            seconds = min(float(raw), MAX_RETRY_WAIT_SECONDS)
        except ValueError:
            return
        if seconds > 0:
            self._sleep_fn(seconds)


def build_client(settings: Settings) -> GroqClient | None:
    """Factory tingkat modul: None berarti fitur LLM nonaktif (kunci kosong)."""
    return GroqClient.from_settings(settings)
