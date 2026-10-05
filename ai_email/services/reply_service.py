"""Context-aware smart reply drafting (draft only - never sends)."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from ..config import Settings, get_settings
from ..date_normalizer import coerce_reference_datetime
from ..email_parser import normalize_email, normalize_thread
from ..exceptions import (
    AIEmailError,
    InputValidationError,
    ProviderError,
    SchemaValidationError,
)
from ..prompts import render_template
from ..providers import BaseProvider, ProviderRequest, build_provider
from ..schemas import (
    EmailInput,
    ProcessingMetadata,
    ProcessingStatus,
    ReplyTone,
    SmartReplyResult,
    ThreadMessage,
)

DEFAULT_TONE = ReplyTone.PROFESSIONAL


def _thread_text(messages: list[ThreadMessage], limit: int) -> str:
    chunks: list[str] = []
    for index, message in enumerate(messages, start=1):
        direction = message.direction or ("inbound" if index == len(messages) else "outbound")
        body = (message.body or "")[:limit]
        chunks.append(f"[{index}] {direction} from {message.sender or 'unknown'}: {body}")
    return "\n\n".join(chunks)


def generate_smart_reply(
    email: EmailInput | dict[str, Any],
    thread_messages: list[ThreadMessage | dict[str, Any]] | None = None,
    tone: ReplyTone | str = DEFAULT_TONE,
    business_context: str | None = None,
    *,
    length_preference: str | None = None,
    reference_datetime: datetime | date | str | None = None,
    timezone: str = "UTC",
    settings: Settings | None = None,
    provider: BaseProvider | None = None,
) -> SmartReplyResult:
    """Generate an editable draft for the latest email in a thread.

    The result is always ``status="draft"`` with
    ``requires_user_approval=True``. Nothing is ever sent.
    """
    settings = settings or get_settings()
    provider = provider or build_provider(settings)
    timezone = timezone or settings.default_timezone

    try:
        selected_tone = tone if isinstance(tone, ReplyTone) else ReplyTone(str(tone).lower().strip())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ReplyTone)
        raise InputValidationError(f"unknown tone {tone!r}; allowed: {allowed}") from exc

    normalized = normalize_email(email, max_body_chars=settings.max_body_chars)
    thread = normalize_thread(thread_messages, max_body_chars=settings.max_body_chars)

    # The latest message must be part of the thread context.
    if not any(
        (message.message_id and message.message_id == normalized.original.message_id)
        or (message.body.strip() == normalized.body_clean.strip())
        for message in thread
    ):
        thread = thread + [
            ThreadMessage(
                message_id=normalized.original.message_id,
                sender=normalized.sender,
                recipients=normalized.recipients,
                body=normalized.text_for_analysis,
                subject=normalized.subject,
                sent_at=normalized.received_at,
                direction="inbound",
            )
        ]

    reference = coerce_reference_datetime(reference_datetime or normalized.received_at, timezone)

    payload: dict[str, Any] = {
        "email": {
            "id": normalized.email_id,
            "subject": normalized.subject,
            "sender": normalized.sender,
            "body": normalized.text_for_analysis,
            "received_at": normalized.received_at.isoformat() if normalized.received_at else None,
        },
        "thread": [
            {
                "message_id": message.message_id,
                "sender": message.sender,
                "body": (message.body or "")[: settings.max_body_chars],
                "sent_at": message.sent_at.isoformat() if message.sent_at else None,
                "direction": message.direction,
            }
            for message in thread
        ],
        "tone": selected_tone.value,
        "length_preference": length_preference,
        "business_context": business_context,
        "reference_datetime": reference.isoformat(),
        "timezone": timezone,
    }

    instructions = render_template(
        "smart_reply.txt",
        {
            "reply_schema": json.dumps(SmartReplyResult.model_json_schema(), indent=2, ensure_ascii=False),
            "tone": selected_tone.value,
            "length_preference": length_preference or "medium",
            "business_context": business_context or "(none supplied)",
            "thread_text": _thread_text(thread, settings.max_body_chars),
        },
    )

    try:
        response = provider.generate_structured(
            ProviderRequest(
                task="smart_reply",
                payload=payload,
                instructions=instructions,
                response_schema=SmartReplyResult,
            )
        )
        result: SmartReplyResult = response.data
        result = result.model_copy(
            update={
                "tone": selected_tone,
                "thread_id": normalized.original.thread_id,
                "reply_to_message_id": normalized.original.message_id,
                "status": "draft",
                "requires_user_approval": True,
                "sent": False,
                "processing_metadata": ProcessingMetadata(
                    provider=response.provider or provider.name,
                    model=response.model,
                    prompt_version=settings.prompt_version,
                    processing_status=ProcessingStatus.COMPLETED,
                    latency_ms=response.latency_ms,
                    usage=response.usage or None,
                ),
            }
        )
        return result
    except (ProviderError, SchemaValidationError, AIEmailError) as exc:
        if settings.is_mock:
            raise
        return SmartReplyResult(
            draft="Unable to generate a draft right now. Please try again.",
            tone=selected_tone,
            warnings=[f"Draft generation failed: {type(exc).__name__}: {exc}"],
            thread_id=normalized.original.thread_id,
            reply_to_message_id=normalized.original.message_id,
            processing_metadata=ProcessingMetadata(
                provider=provider.name,
                prompt_version=settings.prompt_version,
                processing_status=ProcessingStatus.FAILED,
                error=str(exc)[:500],
            ),
        )


__all__ = ["generate_smart_reply"]
