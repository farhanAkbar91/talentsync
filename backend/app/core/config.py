"""Application settings — satu sumber konfigurasi via environment variables."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

APP_VERSION = "0.1.0"

# .env aplikasi di-anchor ke direktori backend/ (bukan CWD) supaya uvicorn,
# alembic, dan scripts membaca konfigurasi yang sama dari working directory mana
# pun (ADR 0005).
BACKEND_DIR = Path(__file__).resolve().parents[2]


def _split_list(value: object) -> object:
    """Terima list Python, JSON string, atau string comma-separated (env format)."""
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in text.split(",") if item.strip()]
    return value


def _parse_weights(value: object) -> object:
    """MATCH_WEIGHTS: terima tuple/list atau "0.40,0.30,0.20,0.10" dari env."""
    if isinstance(value, str):
        return tuple(float(part) for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(float(item) for item in value)
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "TalentSync AI"
    app_env: str = "dev"  # dev | test | prod
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+psycopg://talentsync:talentsync_dev_only@localhost:5432/talentsync"
    )
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    # P1 (JWT): kunci signing. Kosong di P0; wajib diisi di lingkungan non-lokal.
    secret_key: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # CV upload (P2)
    uploads_dir: str = "uploads"
    max_cv_size_bytes: int = 10 * 1024 * 1024  # 10 MB, sesuai desain Figma
    max_cv_pages: int = 20

    # P3 — AI Engine (keputusan pemilik proyek 6 Nov 2026; ADR 0006)
    groq_api_key: str = ""  # adapter LLM (M8); kosong = fitur LLM nonaktif + test mock
    groq_model: str = "openai/gpt-oss-120b"  # hasil benchmark live 6 Nov 2026
    groq_model_fallback: str = "openai/gpt-oss-20b"
    # Model embedding masih sifatnya kandidat — dibekukan setelah benchmark
    # e5-small vs MiniLM pada golden set sintetis (keputusan #5 pemilik proyek).
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = 384
    match_weights: Annotated[tuple[float, float, float, float], NoDecode] = (
        0.40,
        0.30,
        0.20,
        0.10,
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        return _split_list(value)

    @field_validator("match_weights", mode="before")
    @classmethod
    def _weights_from_env(cls, value: object) -> object:
        return _parse_weights(value)

    @field_validator("match_weights")
    @classmethod
    def _validate_weights(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        if len(value) != 4:
            raise ValueError("match_weights harus 4 nilai (semantic, skill, experience, education)")
        if any(weight < 0.0 or weight > 1.0 for weight in value):
            raise ValueError("setiap bobot match_weights harus di [0.0, 1.0]")
        if abs(sum(value) - 1.0) > 0.001:
            raise ValueError("total match_weights harus = 1.0")
        return value

    def jwt_secret(self) -> str:
        """Kunci signing JWT.

        Dev/test tanpa SECRET_KEY memakai kunci sementara yang jelas ditandai tidak
        aman (lihat ADR 0002). Lingkungan prod WAJIB menyediakan SECRET_KEY.
        """
        if self.secret_key:
            return self.secret_key
        if self.app_env == "prod":
            raise RuntimeError("SECRET_KEY wajib diisi pada lingkungan prod.")
        return f"dev-insecure-secret::{self.app_env}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
