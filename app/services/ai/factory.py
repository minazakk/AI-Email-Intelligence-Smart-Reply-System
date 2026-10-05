"""AI provider selection.

``AI_PROVIDER=mock`` needs no credentials and is what the test-suite and
local development use by default. ``AI_PROVIDER=gemini`` requires
``AI_API_KEY``; if the key is missing the factory logs a warning and falls
back to the mock provider so the application still starts.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger, log_event
from app.services.ai.base import AIProvider
from app.services.ai.gemini_provider import GeminiProvider
from app.services.ai.mock_provider import MockAIProvider

logger = get_logger("app.ai")

_ACTIVE_OVERRIDE: AIProvider | None = None


def set_provider_override(provider: AIProvider | None) -> None:
    """Used by tests and dependency overrides to install a stub provider."""
    global _ACTIVE_OVERRIDE
    _ACTIVE_OVERRIDE = provider


@lru_cache(maxsize=1)
def _cached_default_provider() -> AIProvider:
    name = settings.ai_provider
    if name == "gemini":
        if settings.ai_api_key:
            log_event(logger, 20, "Using AI provider", provider="gemini", model=settings.ai_model)
            return GeminiProvider()
        log_event(
            logger,
            30,
            "AI_PROVIDER=gemini but AI_API_KEY is empty; falling back to the mock provider.",
            provider="mock",
        )
    return MockAIProvider()


def get_ai_provider() -> AIProvider:
    """FastAPI dependency returning the active provider."""
    if _ACTIVE_OVERRIDE is not None:
        return _ACTIVE_OVERRIDE
    return _cached_default_provider()


def reset_provider_cache() -> None:
    _cached_default_provider.cache_clear()


__all__ = [
    "AIProvider",
    "GeminiProvider",
    "MockAIProvider",
    "get_ai_provider",
    "reset_provider_cache",
    "set_provider_override",
]
