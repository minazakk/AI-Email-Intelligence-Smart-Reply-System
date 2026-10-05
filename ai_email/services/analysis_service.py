"""Email analysis pipeline: parse -> prompt -> provider -> validate."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal

from ..config import Settings, get_settings
from ..date_normalizer import coerce_reference_datetime
from ..email_parser import normalize_email
from ..exceptions import (
    AIEmailError,
    ConfigurationError,
    ProviderError,
    SchemaValidationError,
)
from ..prompts import build_analysis_prompt
from ..providers import BaseProvider, ProviderRequest, build_provider
from ..schemas import (
    EmailAnalysis,
    EmailInput,
    ProcessingMetadata,
    ProcessingStatus,
)
from . import fallback

ErrorMode = Literal["raise", "status", "fallback"]


def _build_payload(
    normalized,  # type: ignore[no-untyped-def]
    reference: datetime,
    timezone: str,
) -> dict[str, Any]:
    return {
        "email": {
            "id": normalized.email_id,
            "subject": normalized.subject,
            "sender": normalized.sender,
            "recipients": normalized.recipients,
            "body": normalized.text_for_analysis,
            "received_at": normalized.received_at.isoformat() if normalized.received_at else None,
            "truncated": normalized.truncated,
        },
        "reference_datetime": reference.isoformat(),
        "timezone": timezone,
    }


def _failed_analysis(error: Exception, *, email_id: str | None, provider: str) -> EmailAnalysis:
    return EmailAnalysis(
        category="other",
        intent="analysis_failed",
        priority="medium",
        priority_reason="Analysis could not be completed; no classification was produced.",
        sentiment="neutral",
        sentiment_confidence=0.0,
        reply_required=False,
        action_required=False,
        short_summary="AI analysis failed for this email.",
        detailed_summary=f"AI analysis did not complete: {type(error).__name__}.",
        processing_metadata=ProcessingMetadata(
            provider=provider,
            prompt_version="1.0",
            processing_status=ProcessingStatus.FAILED,
            error=str(error)[:500],
        ),
        email_id=email_id,
    )


def analyze_email(
    email: EmailInput | dict[str, Any],
    reference_datetime: datetime | date | str | None = None,
    timezone: str = "UTC",
    *,
    settings: Settings | None = None,
    provider: BaseProvider | None = None,
    on_error: ErrorMode = "raise",
) -> EmailAnalysis:
    """Analyze one email and return a schema-validated :class:`EmailAnalysis`.

    ``on_error``:
      * ``"raise"`` (default) - provider/schema failures propagate.
      * ``"status"`` - failures return an analysis marked
        ``processing_status="failed"`` (never a fake success).
      * ``"fallback"`` - failures fall back to deterministic, input-derived
        rules marked ``processing_status="partial"`` and
        ``fallback_used=True``. Requires ``AI_ALLOW_FALLBACK=true``;
        requesting fallback without that opt-in raises
        :class:`ConfigurationError` instead of silently returning a
        different result.
    """
    settings = settings or get_settings()
    provider = provider or build_provider(settings)

    timezone = timezone or settings.default_timezone
    normalized = normalize_email(email, max_body_chars=settings.max_body_chars)

    reference_source = reference_datetime or normalized.received_at
    reference = coerce_reference_datetime(reference_source, timezone)

    payload = _build_payload(normalized, reference, timezone)
    instructions = build_analysis_prompt(
        {
            "analysis_schema": json.dumps(EmailAnalysis.model_json_schema(), indent=2, ensure_ascii=False),
            "reference_datetime": reference.isoformat(),
            "timezone": timezone,
        }
    )

    try:
        response = provider.generate_structured(
            ProviderRequest(
                task="analysis",
                payload=payload,
                instructions=instructions,
                response_schema=EmailAnalysis,
            )
        )
        analysis: EmailAnalysis = response.data
        analysis = analysis.model_copy(
            update={
                "processing_metadata": ProcessingMetadata(
                    provider=response.provider or provider.name,
                    model=response.model,
                    prompt_version=settings.prompt_version,
                    processing_status=ProcessingStatus.COMPLETED,
                    latency_ms=response.latency_ms,
                    fallback_used=False,
                    usage=response.usage or None,
                ),
                "email_id": normalized.email_id,
            }
        )
        return analysis
    except (ProviderError, SchemaValidationError, AIEmailError) as exc:
        if on_error == "raise":
            raise
        if on_error == "fallback":
            if not settings.allow_fallback:
                raise ConfigurationError(
                    "on_error='fallback' requires the explicit opt-in AI_ALLOW_FALLBACK=true; "
                    "use on_error='status' to return a failed analysis instead"
                ) from exc
            return fallback.deterministic_analysis(payload, provider_name=f"{provider.name}+fallback", error=exc)
        return _failed_analysis(exc, email_id=normalized.email_id, provider=provider.name)


def analyze_emails(
    emails: list[EmailInput | dict[str, Any]],
    reference_datetime: datetime | date | str | None = None,
    timezone: str = "UTC",
    *,
    settings: Settings | None = None,
    provider: BaseProvider | None = None,
    on_error: ErrorMode = "raise",
) -> list[EmailAnalysis]:
    """Batch convenience wrapper - one validated analysis per email."""
    return [
        analyze_email(
            email,
            reference_datetime=reference_datetime,
            timezone=timezone,
            settings=settings,
            provider=provider,
            on_error=on_error,
        )
        for email in emails
    ]


__all__ = ["analyze_email", "analyze_emails"]
