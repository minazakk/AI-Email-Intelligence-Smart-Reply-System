"""Deterministic offline provider - no credentials, no network."""

from __future__ import annotations

import time
from typing import Any

from ..exceptions import SchemaValidationError
from .base import BaseProvider, ProviderRequest, ProviderResponse
from .mock_heuristics import mock_analysis, mock_assistant, mock_smart_reply

_TASKS = {
    "analysis": mock_analysis,
    "smart_reply": mock_smart_reply,
    "assistant": mock_assistant,
}


class MockProvider(BaseProvider):
    """Rule-based provider used for tests, demos and offline evaluation.

    Its output is always marked ``provider="mock"`` so downstream UIs can
    label it honestly as non-LLM analysis.
    """

    name = "mock"

    def __init__(self, settings):  # type: ignore[no-untyped-def]
        super().__init__(settings)
        self.model = "mock-model"

    def _complete(self, request: ProviderRequest) -> ProviderResponse:
        started = time.perf_counter()
        handler = _TASKS.get(request.task)
        if handler is None:
            raise SchemaValidationError(f"mock provider does not implement task {request.task!r}")
        data: dict[str, Any] = handler(request.payload)
        return ProviderResponse(
            data=data,
            text=None,
            provider=self.name,
            model=self.model,
            latency_ms=(time.perf_counter() - started) * 1000,
            usage={"prompt_tokens": 0, "completion_tokens": 0},
        )
