"""Exception hierarchy for the AI email module."""

from __future__ import annotations


class AIEmailError(Exception):
    """Base class for every error raised by the AI module."""


class InputValidationError(AIEmailError):
    """The caller supplied email/thread input that cannot be processed."""


class SchemaValidationError(AIEmailError):
    """The model output did not conform to the expected structured schema."""


class PromptTemplateError(AIEmailError):
    """A prompt template is missing or cannot be rendered."""


class ProviderError(AIEmailError):
    """Base class for AI provider failures."""

    def __init__(self, message: str, *, provider: str = "unknown", retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


class ProviderTimeoutError(ProviderError):
    def __init__(self, message: str = "Provider request timed out", *, provider: str = "unknown"):
        super().__init__(message, provider=provider, retryable=True)


class ProviderRateLimitError(ProviderError):
    def __init__(self, message: str = "Provider rate limit exceeded", *, provider: str = "unknown"):
        super().__init__(message, provider=provider, retryable=True)


class ProviderAuthError(ProviderError):
    def __init__(self, message: str = "Provider rejected the credentials", *, provider: str = "unknown"):
        super().__init__(message, provider=provider, retryable=False)


class ProviderUnavailableError(ProviderError):
    def __init__(self, message: str = "Provider is unavailable", *, provider: str = "unknown"):
        super().__init__(message, provider=provider, retryable=True)


class ProviderResponseError(ProviderError):
    """Malformed or unusable payload returned by the provider."""

    def __init__(self, message: str = "Provider returned a malformed response", *, provider: str = "unknown"):
        super().__init__(message, provider=provider, retryable=True)


class ConfigurationError(AIEmailError):
    """The module is not configured for the requested operation."""
