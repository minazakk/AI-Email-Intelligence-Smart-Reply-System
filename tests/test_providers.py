import json

import pytest

from ai_email import Settings, set_settings
from ai_email.exceptions import (
    ConfigurationError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    SchemaValidationError,
)
from ai_email.providers import (
    BaseProvider,
    ProviderRequest,
    ProviderResponse,
    build_provider,
    parse_structured,
)
from ai_email.providers.base import set_sleep, validate_output
from ai_email.schemas import EmailAnalysis


def _analysis_payload():
    return {
        "category": "sales_inquiry",
        "intent": "requesting_quote",
        "priority": "medium",
        "priority_reason": "Standard quote request.",
        "sentiment": "neutral",
        "sentiment_confidence": 0.7,
        "reply_required": True,
        "action_required": True,
        "short_summary": "A buyer asks for a quotation.",
        "detailed_summary": "A buyer asked for a quotation for several units and lead time.",
    }


def test_mock_provider_is_default():
    provider = build_provider(Settings(provider="mock"))
    assert provider.name == "mock"
    assert provider.model == "mock-model"


def test_openai_provider_requires_key():
    with pytest.raises(ConfigurationError):
        Settings(provider="openai")
    with pytest.raises(ConfigurationError):
        Settings(provider="openai", openai_api_key="   ")


def test_unknown_provider_rejected():
    with pytest.raises(ConfigurationError):
        Settings(provider="llama")


def test_mock_structured_call_is_schema_valid():
    provider = build_provider(Settings(provider="mock"))
    request = ProviderRequest(
        task="analysis",
        payload={"email": {"subject": "Quote please", "body": "Please send a quote."}},
        instructions="unused",
        response_schema=EmailAnalysis,
    )
    response = provider.generate_structured(request)
    assert isinstance(response.data, EmailAnalysis)
    assert response.provider == "mock"


def test_structured_call_requires_schema():
    provider = build_provider(Settings(provider="mock"))
    with pytest.raises(SchemaValidationError):
        provider.generate_structured(ProviderRequest(task="analysis", payload={}, instructions="x"))


def test_parse_structured_handles_code_fences():
    data = parse_structured('```json\n{"a": 1}\n```')
    assert data == {"a": 1}


def test_parse_structured_rejects_non_object():
    with pytest.raises(SchemaValidationError):
        parse_structured("[1, 2, 3]")
    with pytest.raises(SchemaValidationError):
        parse_structured("")
    with pytest.raises(SchemaValidationError):
        parse_structured("{not json")


def test_validate_output_rejects_wrong_shape():
    with pytest.raises(SchemaValidationError):
        validate_output({"category": "nope"}, EmailAnalysis)


class _FlakyProvider(BaseProvider):
    name = "flaky"

    def __init__(self, settings, *, error, fail_times):  # type: ignore[no-untyped-def]
        super().__init__(settings)
        self.error = error
        self.fail_times = fail_times
        self.calls = 0

    def _complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error
        return ProviderResponse(text=json.dumps(_analysis_payload()), provider=self.name, model="m")


@pytest.fixture(autouse=True)
def no_sleep():
    calls = []
    set_sleep(lambda seconds: calls.append(seconds))
    yield calls
    set_sleep(lambda seconds: None)


def test_retry_recovers_from_transient_error(no_sleep):
    settings = Settings(provider="mock", max_retries=2)
    provider = _FlakyProvider(settings, error=ProviderTimeoutError("slow", provider="flaky"), fail_times=1)
    request = ProviderRequest(task="analysis", payload={}, instructions="x", response_schema=EmailAnalysis)
    response = provider.generate_structured(request)
    assert provider.calls == 2
    assert isinstance(response.data, EmailAnalysis)
    assert len(no_sleep) == 1


def test_retry_exhaustion_raises(no_sleep):
    settings = Settings(provider="mock", max_retries=1)
    provider = _FlakyProvider(
        settings,
        error=ProviderRateLimitError("limited", provider="flaky"),
        fail_times=5,
    )
    request = ProviderRequest(task="analysis", payload={}, instructions="x", response_schema=EmailAnalysis)
    with pytest.raises(ProviderRateLimitError):
        provider.generate_structured(request)
    assert provider.calls == 2  # 1 attempt + 1 retry


def test_non_retryable_error_does_not_retry(no_sleep):
    settings = Settings(provider="mock", max_retries=3)
    provider = _FlakyProvider(
        settings,
        error=ProviderAuthError("bad key", provider="flaky"),
        fail_times=5,
    )
    request = ProviderRequest(task="analysis", payload={}, instructions="x", response_schema=EmailAnalysis)
    with pytest.raises(ProviderAuthError):
        provider.generate_structured(request)
    assert provider.calls == 1
    assert no_sleep == []


def test_malformed_json_from_provider(no_sleep):
    settings = Settings(provider="mock", max_retries=1)
    provider = _FlakyProvider(
        settings,
        error=ProviderResponseError("bad gateway", provider="flaky"),
        fail_times=0,
    )
    provider._complete = lambda request: ProviderResponse(text="<<<not-json>>>", provider="flaky")  # type: ignore[method-assign]
    request = ProviderRequest(task="analysis", payload={}, instructions="x", response_schema=EmailAnalysis)
    with pytest.raises(SchemaValidationError):
        provider.generate_structured(request)


def test_mock_provider_needs_no_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    set_settings(Settings(provider="mock"))
    provider = build_provider()
    assert provider.name == "mock"
