"""Provider factory. Live adapters are imported only when selected."""

from __future__ import annotations

from ..config import Settings, get_settings
from ..exceptions import ConfigurationError
from .base import (
    BaseProvider,
    ProviderRequest,
    ProviderResponse,
    parse_structured,
    validate_output,
)
from .mock_provider import MockProvider

__all__ = [
    "BaseProvider",
    "ProviderRequest",
    "ProviderResponse",
    "build_provider",
    "parse_structured",
    "validate_output",
]


def build_provider(settings: Settings | None = None) -> BaseProvider:
    """Create the provider configured by ``AI_PROVIDER``."""
    settings = settings or get_settings()
    if settings.provider == "mock":
        return MockProvider(settings)
    if settings.provider == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(settings)
    if settings.provider == "gemini":
        from .gemini_provider import GeminiProvider

        return GeminiProvider(settings)
    raise ConfigurationError(f"unknown AI provider: {settings.provider!r}")
