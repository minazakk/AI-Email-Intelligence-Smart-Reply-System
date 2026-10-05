"""Provider-neutral LLM interface."""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..config import Settings
from ..exceptions import ProviderError, SchemaValidationError

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


@dataclass
class ProviderRequest:
    """Everything a provider needs to answer one structured task."""

    task: str
    payload: dict[str, Any]
    instructions: str
    response_schema: type[BaseModel] | None = None
    temperature: float | None = None


@dataclass
class ProviderResponse:
    data: Any = None
    text: str | None = None
    provider: str = "unknown"
    model: str | None = None
    latency_ms: float | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw: str | None = None


def extract_json_text(text: str) -> str:
    """Return the first JSON object found in a model response."""
    if not text:
        return ""
    stripped = text.strip()
    fence = _FENCE.search(stripped)
    if fence:
        stripped = fence.group(1).strip()
    if stripped.startswith("{"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def parse_structured(text: str, *, provider: str = "unknown") -> dict[str, Any]:
    """Parse model text into a dict, raising a clear error when malformed."""
    candidate = extract_json_text(text)
    if not candidate:
        raise SchemaValidationError("provider returned an empty response")
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(f"provider returned malformed JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SchemaValidationError("provider returned JSON that is not an object")
    return data


def validate_output[T: BaseModel](data: dict[str, Any], schema: type[T], *, provider: str = "unknown") -> T:
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise SchemaValidationError(f"provider output failed schema validation: {exc}") from exc


class BaseProvider(ABC):
    """Abstract provider with bounded retries and structured output helpers."""

    name: str = "base"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model = settings.effective_model

    # -- interface ---------------------------------------------------------
    @abstractmethod
    def _complete(self, request: ProviderRequest) -> ProviderResponse:
        """Perform a single provider call (no retry logic here)."""

    # -- public ------------------------------------------------------------
    def generate_structured(self, request: ProviderRequest) -> ProviderResponse:
        if request.response_schema is None:
            raise SchemaValidationError("generate_structured requires a response_schema")
        response = self._with_retries(request)
        if not isinstance(response.data, dict):
            response.data = parse_structured(response.text or "", provider=self.name)
        try:
            response.data = validate_output(response.data, request.response_schema, provider=self.name)
        except SchemaValidationError:
            raise
        return response

    def generate_text(self, request: ProviderRequest) -> ProviderResponse:
        return self._with_retries(request)

    # -- retry -------------------------------------------------------------
    def _with_retries(self, request: ProviderRequest) -> ProviderResponse:
        attempts = self.settings.max_retries + 1
        last_error: ProviderError | None = None
        started = time.perf_counter()
        for attempt in range(attempts):
            try:
                response = self._complete(request)
                if response.latency_ms is None:
                    response.latency_ms = (time.perf_counter() - started) * 1000
                return response
            except ProviderError as exc:
                last_error = exc
                if not exc.retryable or attempt == attempts - 1:
                    raise
                delay = min(0.5 * (2**attempt), 4.0)
                _sleep(delay)
        raise last_error if last_error else ProviderError("provider failed", provider=self.name)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def set_sleep(func: Callable[[float], None]) -> None:
    """Allow tests to replace the retry backoff sleep."""
    global _sleep
    _sleep = func


__all__ = [
    "BaseProvider",
    "ProviderError",
    "ProviderRequest",
    "ProviderResponse",
    "extract_json_text",
    "parse_structured",
    "set_sleep",
    "validate_output",
]
