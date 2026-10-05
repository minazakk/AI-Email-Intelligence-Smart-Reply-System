"""Google Gemini generateContent adapter (server-side only).

Implemented with the standard library so no extra dependency is needed.
The adapter has never been exercised against the live API from this
repository - see docs/AI_MODULE.md for what was verified.
"""

from __future__ import annotations

import json
from urllib.parse import quote

from ..config import Settings
from ..exceptions import ConfigurationError, ProviderResponseError
from ._http import post_json
from .base import BaseProvider, ProviderRequest, ProviderResponse, extract_json_text

DEFAULT_MODEL = "gemini-1.5-flash"
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiProvider(BaseProvider):
    name = "gemini"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        if not settings.gemini_api_key:
            raise ConfigurationError("GEMINI_API_KEY is not configured")
        self.api_key = settings.gemini_api_key
        if not settings.model:
            self.model = DEFAULT_MODEL

    def _complete(self, request: ProviderRequest) -> ProviderResponse:
        temperature = request.temperature if request.temperature is not None else self.settings.temperature
        url = _ENDPOINT.format(model=quote(self.model, safe=""))
        body = {
            "systemInstruction": {"parts": [{"text": request.instructions}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": json.dumps(request.payload, ensure_ascii=False, default=str)}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
            },
        }
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        raw = post_json(url, body, headers=headers, timeout=self.settings.timeout_seconds, provider=self.name)

        try:
            parts = raw["candidates"][0]["content"]["parts"]
            content = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            snippet = str(raw)[:200]
            raise ProviderResponseError(f"gemini response missing candidates: {snippet}", provider=self.name) from exc

        usage = raw.get("usageMetadata") if isinstance(raw.get("usageMetadata"), dict) else {}
        return ProviderResponse(
            data=extract_json_text(content),
            text=content,
            provider=self.name,
            model=str(raw.get("modelVersion") or self.model),
            usage={
                "prompt_tokens": usage.get("promptTokenCount"),
                "completion_tokens": usage.get("candidatesTokenCount"),
                "total_tokens": usage.get("totalTokenCount"),
            },
        )
