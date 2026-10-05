"""AI provider abstraction.

Every provider implements :class:`AIProvider`. The rest of the codebase only
depends on this interface, so tests can swap in :class:`MockAIProvider`
without credentials and the AI teammate can rely on stable behaviour.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.core.errors import AIProviderError, AIResponseInvalidError


@dataclass(slots=True)
class AIProviderResponse:
    raw_text: str
    parsed: dict[str, Any]
    provider: str
    model: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AIProvider(Protocol):
    name: str
    model: str

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema_hint: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> AIProviderResponse:
        """Run one structured completion and return parsed JSON."""
        ...


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model response.

    Providers sometimes wrap output in markdown fences or add a sentence
    around it. Anything that cannot be parsed raises
    :class:`AIResponseInvalidError` so a malformed reply is never stored as a
    successful analysis.
    """
    if not text or not text.strip():
        raise AIResponseInvalidError("AI provider returned an empty response.")

    candidate = text.strip()
    fence = _FENCE_RE.match(candidate)
    if fence:
        candidate = fence.group(1).strip()

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fall back to the first balanced {...} span.
    start = candidate.find("{")
    if start == -1:
        raise AIResponseInvalidError("AI provider response did not contain a JSON object.")
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(candidate)):
        char = candidate[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                fragment = candidate[start : index + 1]
                try:
                    parsed = json.loads(fragment)
                except json.JSONDecodeError as exc:
                    raise AIResponseInvalidError(
                        "AI provider returned malformed JSON."
                    ) from exc
                if isinstance(parsed, dict):
                    return parsed
                raise AIResponseInvalidError("AI provider returned a non-object JSON value.")
    raise AIResponseInvalidError("AI provider returned malformed JSON.")


class BaseProvider:
    """Shared bookkeeping for concrete providers."""

    name: str = "base"
    model: str = "unknown"

    def _measure(self, started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    @staticmethod
    def _fail(message: str, *, code: str, retryable: bool, status: int | None = None) -> AIProviderError:
        return AIProviderError(
            message,
            code=code,
            retryable=retryable,
            details={"provider_status": status} if status else None,
        )


__all__ = [
    "AIProvider",
    "AIProviderResponse",
    "BaseProvider",
    "AIProviderError",
    "AIResponseInvalidError",
    "extract_json",
]
