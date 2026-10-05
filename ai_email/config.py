"""Environment driven configuration for the AI module.

Only environment variables (optionally loaded from a local ``.env`` file)
configure the module. No secrets are hard coded anywhere in the package.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

from .exceptions import ConfigurationError

VALID_PROVIDERS = ("mock", "openai", "gemini")

PROMPT_VERSION = "1.0"


def _load_dotenv(path: str | os.PathLike[str] = ".env") -> dict[str, str]:
    """Minimal dependency-free .env reader (KEY=VALUE lines only)."""
    file_path = Path(path)
    values: dict[str, str] = {}
    if not file_path.is_file():
        return values
    try:
        for line in file_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                values[key] = value
    except OSError:
        return {}
    return values


def _as_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _as_float(raw: str | None, default: float, *, name: str, minimum: float | None = None) -> float:
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}, got {value}")
    return value


def _as_int(raw: str | None, default: int, *, name: str, minimum: int = 0) -> int:
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}, got {value}")
    return value


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings for the AI module."""

    provider: str = "mock"
    model: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 2
    temperature: float = 0.2
    max_body_chars: int = 20_000
    max_eml_bytes: int = 2_000_000
    default_timezone: str = "UTC"
    allow_fallback: bool = False
    prompt_version: str = PROMPT_VERSION
    extra: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        provider = self.provider.lower().strip()
        if provider not in VALID_PROVIDERS:
            raise ConfigurationError(f"AI_PROVIDER must be one of {', '.join(VALID_PROVIDERS)} (got {self.provider!r})")
        object.__setattr__(self, "provider", provider)
        if provider in {"openai", "gemini"} and not self.api_key:
            raise ConfigurationError(
                f"AI_PROVIDER={provider} requires an API key; set "
                f"{'OPENAI_API_KEY' if provider == 'openai' else 'GEMINI_API_KEY'} in the environment"
            )

    @property
    def api_key(self) -> str | None:
        if self.provider == "openai":
            key = self.openai_api_key
        elif self.provider == "gemini":
            key = self.gemini_api_key
        else:
            return None
        key = (key or "").strip()
        return key or None

    @property
    def is_mock(self) -> bool:
        return self.provider == "mock"

    @property
    def effective_model(self) -> str:
        if self.model:
            return self.model
        if self.provider == "openai":
            return "gpt-4o-mini"
        if self.provider == "gemini":
            return "gemini-1.5-flash"
        return "mock-model"

    def replace(self, **changes: object) -> Settings:
        return replace(self, **changes)  # type: ignore[arg-type]

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        dotenv_path: str | os.PathLike[str] | None = ".env",
        load_dotenv: bool = True,
    ) -> Settings:
        """Build settings from the environment.

        A local ``.env`` file (if present) is read first and never overrides
        variables that are already set in the process environment.
        """
        environ: dict[str, str] = dict(env) if env is not None else dict(os.environ)
        if env is None and load_dotenv:
            for key, value in _load_dotenv(dotenv_path).items():
                environ.setdefault(key, value)

        return cls(
            provider=environ.get("AI_PROVIDER", "mock") or "mock",
            model=(environ.get("AI_MODEL") or "").strip() or None,
            openai_api_key=(environ.get("OPENAI_API_KEY") or "").strip() or None,
            gemini_api_key=(environ.get("GEMINI_API_KEY") or "").strip() or None,
            timeout_seconds=_as_float(environ.get("AI_TIMEOUT_SECONDS"), 30.0, name="AI_TIMEOUT_SECONDS", minimum=0.1),
            max_retries=_as_int(environ.get("AI_MAX_RETRIES"), 2, name="AI_MAX_RETRIES"),
            temperature=_as_float(environ.get("AI_TEMPERATURE"), 0.2, name="AI_TEMPERATURE", minimum=0.0),
            max_body_chars=_as_int(environ.get("AI_MAX_BODY_CHARS"), 20_000, name="AI_MAX_BODY_CHARS", minimum=200),
            max_eml_bytes=_as_int(environ.get("AI_MAX_EML_BYTES"), 2_000_000, name="AI_MAX_EML_BYTES", minimum=1024),
            default_timezone=(environ.get("AI_DEFAULT_TIMEZONE") or "UTC").strip() or "UTC",
            allow_fallback=_as_bool(environ.get("AI_ALLOW_FALLBACK"), False),
            extra={},
        )


_DEFAULT_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    """Return (and cache) settings resolved from the environment."""
    global _DEFAULT_SETTINGS
    if _DEFAULT_SETTINGS is None:
        _DEFAULT_SETTINGS = Settings.from_env()
    return _DEFAULT_SETTINGS


def set_settings(settings: Settings) -> None:
    """Replace the process-wide default settings (mainly for tests/CLI)."""
    global _DEFAULT_SETTINGS
    _DEFAULT_SETTINGS = settings


def reset_settings() -> None:
    """Forget cached settings so the environment is re-read."""
    global _DEFAULT_SETTINGS
    _DEFAULT_SETTINGS = None
