"""OpenAI chat-completions adapter (server-side only).

Implemented with the standard library so no extra dependency is needed.
The adapter has never been exercised against the live API from this
repository - see docs/AI_MODULE.md for what was verified.
"""

from __future__ import annotations

import json

from ..config import Settings
from ..exceptions import ConfigurationError, ProviderResponseError
from ._http import post_json
from .base import BaseProvider, ProviderRequest, ProviderResponse, extract_json_text

DEFAULT_MODEL = "gpt-4o-mini"
_ENDPOINT = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(BaseProvider):
    name = "openai"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        if not settings.openai_api_key:
            raise ConfigurationError("OPENAI_API_KEY is not configured")
        self.api_key = settings.openai_api_key
        if not settings.model:
            self.model = DEFAULT_MODEL

    def _complete(self, request: ProviderRequest) -> ProviderResponse:
        temperature = request.temperature if request.temperature is not None else self.settings.temperature
        body = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": request.instructions
                    + "\nRespond with a single JSON object only. No prose, no code fences.",
                },
                {"role": "user", "content": json.dumps(request.payload, ensure_ascii=False, default=str)},
            ],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        raw = post_json(_ENDPOINT, body, headers=headers, timeout=self.settings.timeout_seconds, provider=self.name)

        try:
            content = raw["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            snippet = str(raw)[:200]
            raise ProviderResponseError(f"openai response missing choices: {snippet}", provider=self.name) from exc

        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        return ProviderResponse(
            data=extract_json_text(content),
            text=content,
            provider=self.name,
            model=str(raw.get("model") or self.model),
            usage={
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            },
            raw=None,
        )
