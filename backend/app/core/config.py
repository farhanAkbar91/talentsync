"""Application settings — satu sumber konfigurasi via environment variables."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TalentSync AI"
    app_env: str = "dev"  # dev | test | prod
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+psycopg://talentsync:talentsync_dev_only@localhost:5432/talentsync"
    )
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    # P1 (JWT): kunci signing. Kosong di P0; wajib diisi di lingkungan non-lokal.
    secret_key: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # CV upload (P2)
    uploads_dir: str = "uploads"
    max_cv_size_bytes: int = 10 * 1024 * 1024  # 10 MB, sesuai desain Figma
    max_cv_pages: int = 20

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # Terima format env "a,b,c" (bukan hanya JSON array).
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
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
