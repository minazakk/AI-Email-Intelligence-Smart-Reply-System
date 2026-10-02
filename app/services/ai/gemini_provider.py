"""Google Gemini provider adapter (JSON mode, bounded timeouts, retries)."""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import AIProviderError
from app.services.ai.base import AIProviderResponse, BaseProvider, extract_json

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        backoff: float | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else settings.ai_api_key) or ""
        self.model = model or settings.ai_model
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.ai_timeout_seconds
        self.max_retries = (
            max_retries if max_retries is not None else max(0, settings.ai_max_retries)
        )
        self.backoff = backoff if backoff is not None else settings.ai_retry_backoff_seconds

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema_hint: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> AIProviderResponse:
        if not self.api_key:
            raise AIProviderError(
                "AI provider is not configured (missing API key).",
                code="ai_not_configured",
                retryable=False,
            )

        body: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
                "maxOutputTokens": 4096,
            },
        }
        if schema_hint:
            body["generationConfig"]["responseSchema"] = schema_hint

        attempt = 0
        last_error: AIProviderError | None = None
        started_all = time.monotonic()
        while attempt <= self.max_retries:
            attempt += 1
            try:
                return self._request(body, timeout or self.timeout, attempt)
            except AIProviderError as exc:
                last_error = exc
                if not exc.retryable or attempt > self.max_retries:
                    break
                time.sleep(self.backoff * attempt)

        assert last_error is not None
        last_error.details = {
            **(last_error.details or {}),
            "attempts": attempt,
            "total_latency_ms": int((time.monotonic() - started_all) * 1000),
        }
        raise last_error

    def _request(self, body: dict[str, Any], timeout: float, attempt: int) -> AIProviderResponse:
        url = f"{self.base_url}/models/{self.model}:generateContent"
        started = time.monotonic()
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, json=body, headers={"x-goog-api-key": self.api_key})
        except httpx.TimeoutException as exc:
            raise AIProviderError(
                "AI provider request timed out.", code="ai_timeout", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(
                "AI provider could not be reached.", code="ai_unreachable", retryable=True
            ) from exc

        latency = int((time.monotonic() - started) * 1000)

        if response.status_code in _RETRYABLE_STATUS:
            raise AIProviderError(
                "AI provider returned a transient error.",
                code="ai_rate_limited" if response.status_code == 429 else "ai_server_error",
                retryable=True,
                details={"provider_status": response.status_code},
            )
        if response.status_code == 401 or response.status_code == 403:
            raise AIProviderError(
                "AI provider rejected the configured credentials.",
                code="ai_auth_error",
                retryable=False,
                details={"provider_status": response.status_code},
            )
        if response.status_code >= 400:
            raise AIProviderError(
                "AI provider returned an error response.",
                code="ai_provider_error",
                retryable=False,
                details={"provider_status": response.status_code},
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise AIProviderError(
                "AI provider returned a non-JSON response.",
                code="ai_response_invalid",
                retryable=False,
            ) from exc

        try:
            candidates = payload.get("candidates") or []
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
        except (IndexError, AttributeError, TypeError) as exc:
            raise AIProviderError(
                "AI provider response was missing candidates.",
                code="ai_response_invalid",
                retryable=False,
            ) from exc

        parsed = extract_json(text)
        usage = payload.get("usageMetadata") or {}
        return AIProviderResponse(
            raw_text=text,
            parsed=parsed,
            provider=self.name,
            model=self.model,
            latency_ms=latency,
            prompt_tokens=int(usage.get("promptTokenCount") or 0),
            completion_tokens=int(usage.get("candidatesTokenCount") or 0),
            total_tokens=int(usage.get("totalTokenCount") or 0),
            meta={"attempt": attempt},
        )


__all__ = ["GeminiProvider"]
