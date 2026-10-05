"""Application settings loaded from environment variables / `.env`."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application ---------------------------------------------------------
    app_env: str = "development"
    app_name: str = "AI Email Intelligence API"
    app_version: str = "0.1.0"
    debug: bool = False
    secret_key: str = "insecure-dev-secret-change-me"
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:3000"
    trust_proxy_headers: bool = False

    # Database ------------------------------------------------------------
    database_url: str = "postgresql+psycopg://email_intel:change-me@127.0.0.1:5432/email_intelligence"
    test_database_url: str = "sqlite+pysqlite:///.test_tmp/test.db"

    # Auth ----------------------------------------------------------------
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    verification_token_expire_minutes: int = 1440
    reset_token_expire_minutes: int = 60
    password_min_length: int = 8
    dev_mode_enable_token_links: bool = True

    # Rate limiting -------------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_login_per_minute: int = 10
    rate_limit_signup_per_minute: int = 5
    rate_limit_sensitive_per_minute: int = 20

    # AI ------------------------------------------------------------------
    ai_provider: str = "mock"
    ai_model: str = "gemini-2.0-flash"
    ai_api_key: str = ""
    ai_timeout_seconds: float = 30.0
    ai_max_retries: int = 2
    ai_retry_backoff_seconds: float = 0.5
    ai_context_email_limit: int = 25

    # Uploads -------------------------------------------------------------
    upload_max_bytes: int = 2 * 1024 * 1024
    import_max_rows: int = 2000
    import_allowed_extensions: str = ".csv,.json,.eml"

    # Notifications -------------------------------------------------------
    deadline_reminder_days: int = 3

    # Logging -------------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    @field_validator("ai_provider")
    @classmethod
    def _normalise_provider(cls, value: str) -> str:
        allowed = {"mock", "gemini"}
        normalised = (value or "mock").strip().lower()
        if normalised not in allowed:
            raise ValueError(f"AI_PROVIDER must be one of {sorted(allowed)}")
        return normalised

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def allowed_upload_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.import_allowed_extensions.split(",") if e.strip()}

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
