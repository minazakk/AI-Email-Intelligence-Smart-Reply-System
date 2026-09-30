"""Minimal dependency-free HTTP helpers for live provider adapters."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..exceptions import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

_MAX_RESPONSE_BYTES = 4_000_000


def post_json(
    url: str,
    body: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout: float,
    provider: str,
) -> dict[str, Any]:
    """POST JSON and return the decoded response object.

    Maps transport and HTTP failures onto the module's provider exceptions
    so callers get one consistent error model.
    """
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(_MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        try:
            payload = exc.read(20_000).decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensive
            payload = ""
        raise _map_http_error(exc.code, payload, provider=provider) from exc
    except TimeoutError as exc:
        raise ProviderTimeoutError(f"{provider} request timed out after {timeout}s", provider=provider) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError):
            raise ProviderTimeoutError(f"{provider} request timed out after {timeout}s", provider=provider) from exc
        raise ProviderUnavailableError(f"{provider} unreachable: {reason}", provider=provider) from exc
    except OSError as exc:
        raise ProviderUnavailableError(f"{provider} connection failed: {exc}", provider=provider) from exc

    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderResponseError(f"{provider} returned a non-JSON response", provider=provider) from exc
    if not isinstance(decoded, dict):
        raise ProviderResponseError(f"{provider} returned an unexpected payload", provider=provider)
    return decoded


def _map_http_error(status: int, payload: str, *, provider: str):
    snippet = payload[:300].replace("\n", " ")
    if status in (401, 403):
        return ProviderAuthError(f"{provider} rejected the credentials (HTTP {status}): {snippet}", provider=provider)
    if status == 429:
        return ProviderRateLimitError(f"{provider} rate limit reached (HTTP 429)", provider=provider)
    if status in (408, 504):
        return ProviderTimeoutError(f"{provider} timed out (HTTP {status})", provider=provider)
    if status >= 500:
        return ProviderUnavailableError(f"{provider} server error (HTTP {status}): {snippet}", provider=provider)
    if status == 400 and "context" in payload.lower():
        return ProviderResponseError(f"{provider} context length error: {snippet}", provider=provider)
    return ProviderResponseError(f"{provider} error (HTTP {status}): {snippet}", provider=provider)
