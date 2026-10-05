"""Inbox assistant Q&A over caller-supplied records only.

The AI module never queries a database: a future backend retrieves the
authenticated user's records and passes them in. Counts and id validation
are enforced deterministically here, so a model cannot invent records.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from ..config import Settings, get_settings
from ..date_normalizer import coerce_reference_datetime
from ..exceptions import (
    AIEmailError,
    InputValidationError,
    ProviderError,
    SchemaValidationError,
)
from ..prompts import render_template
from ..providers import BaseProvider, ProviderRequest, build_provider
from ..schemas import (
    AssistantAnswer,
    EmailAnalysis,
    EmailInput,
    ProcessingMetadata,
    ProcessingStatus,
    ThreadMessage,
)

_RECORD_FIELDS = (
    "id",
    "subject",
    "sender",
    "received_at",
    "category",
    "priority",
    "sentiment",
    "reply_required",
    "action_required",
    "short_summary",
    "is_read",
)


def _record_view(item: EmailInput | EmailAnalysis | ThreadMessage | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, EmailAnalysis):
        data = item.model_dump(mode="json")
        return {
            "id": data.get("email_id"),
            "subject": None,
            "sender": None,
            "received_at": None,
            "category": data.get("category"),
            "priority": data.get("priority"),
            "sentiment": data.get("sentiment"),
            "reply_required": data.get("reply_required"),
            "action_required": data.get("action_required"),
            "short_summary": data.get("short_summary"),
            "is_read": None,
        }
    if isinstance(item, EmailInput) or isinstance(item, ThreadMessage):
        data = item.model_dump(mode="json")
    elif isinstance(item, dict):
        data = dict(item)
    else:
        raise InputValidationError(f"unsupported record type: {type(item).__name__}")

    record_id = data.get("id") or data.get("message_id") or data.get("email_id")
    analysis = data.get("analysis") if isinstance(data.get("analysis"), dict) else {}
    view = {
        "id": record_id,
        "subject": data.get("subject"),
        "sender": data.get("sender"),
        "received_at": data.get("received_at"),
        "category": data.get("category") or analysis.get("category"),
        "priority": data.get("priority") or analysis.get("priority"),
        "sentiment": data.get("sentiment") or analysis.get("sentiment"),
        "reply_required": data.get("reply_required")
        if data.get("reply_required") is not None
        else analysis.get("reply_required"),
        "action_required": data.get("action_required")
        if data.get("action_required") is not None
        else analysis.get("action_required"),
        "short_summary": data.get("short_summary") or analysis.get("short_summary"),
        "is_read": data.get("is_read"),
    }
    return {key: value for key, value in view.items() if key in _RECORD_FIELDS or value is not None}


def _record_id(record: dict[str, Any]) -> str | None:
    value = record.get("id")
    return str(value) if value else None


def _deterministic_empty_answer(question: str, supplied: int) -> AssistantAnswer:
    return AssistantAnswer(
        answer=(
            "No records were supplied for this question, so I cannot answer it from the inbox. "
            "Ask the backend to run a search first, or widen the filters."
        ),
        scope="supplied_records",
        records_supplied=supplied,
        records_matched=0,
        referenced_email_ids=[],
        out_of_scope=True,
        follow_up_questions=["Which category or date range should I search?"],
        processing_metadata=ProcessingMetadata(
            provider="deterministic",
            prompt_version="n/a",
            processing_status=ProcessingStatus.COMPLETED,
        ),
    )


def answer_inbox_question(
    question: str,
    retrieved_emails: Iterable[EmailInput | EmailAnalysis | dict[str, Any]] | None,
    pending_actions: Iterable[dict[str, Any]] | None = None,
    reference_datetime: datetime | date | str | None = None,
    timezone: str = "UTC",
    *,
    matched_count: int | None = None,
    settings: Settings | None = None,
    provider: BaseProvider | None = None,
) -> AssistantAnswer:
    """Answer a question using ONLY the records supplied by the caller."""
    settings = settings or get_settings()
    provider = provider or build_provider(settings)
    timezone = timezone or settings.default_timezone

    if not question or not str(question).strip():
        raise InputValidationError("question must not be empty")

    records = [_record_view(item) for item in (retrieved_emails or [])]
    actions = [dict(item) for item in (pending_actions or [])]
    supplied = len(records)
    matched = supplied if matched_count is None else max(0, min(int(matched_count), supplied))

    if supplied == 0 or matched == 0:
        return _deterministic_empty_answer(str(question).strip(), supplied)

    known_ids = {identifier for identifier in (_record_id(record) for record in records) if identifier}
    reference = coerce_reference_datetime(reference_datetime, timezone)

    payload = {
        "question": str(question).strip(),
        "records": records,
        "pending_actions": actions,
        "records_supplied": supplied,
        "records_matched": matched,
        "reference_datetime": reference.isoformat(),
        "timezone": timezone,
    }

    instructions = render_template(
        "inbox_assistant.txt",
        {
            "question": payload["question"],
            "records_json": json.dumps(records, ensure_ascii=False, default=str),
            "actions_json": json.dumps(actions, ensure_ascii=False, default=str) if actions else "[]",
            "reference_datetime": reference.isoformat(),
            "assistant_schema": json.dumps(AssistantAnswer.model_json_schema(), indent=2, ensure_ascii=False),
            "records_supplied": supplied,
        },
    )

    try:
        response = provider.generate_structured(
            ProviderRequest(
                task="assistant",
                payload=payload,
                instructions=instructions,
                response_schema=AssistantAnswer,
            )
        )
        answer: AssistantAnswer = response.data
    except (ProviderError, SchemaValidationError, AIEmailError) as exc:
        fallback_answer = AssistantAnswer(
            answer=(
                f"I could not complete the answer ({type(exc).__name__}). "
                f"{matched} record(s) were supplied; please retry."
            ),
            scope="supplied_records",
            records_supplied=supplied,
            records_matched=matched,
            referenced_email_ids=[],
            out_of_scope=True,
            processing_metadata=ProcessingMetadata(
                provider=provider.name,
                prompt_version=settings.prompt_version,
                processing_status=ProcessingStatus.FAILED,
                error=str(exc)[:500],
            ),
        )
        return fallback_answer

    # Enforce deterministic facts after model validation.
    safe_ids = [identifier for identifier in answer.referenced_email_ids if identifier in known_ids]
    updates: dict[str, Any] = {
        "records_supplied": supplied,
        "records_matched": matched,
        "referenced_email_ids": safe_ids,
        "scope": "supplied_records",
        "processing_metadata": ProcessingMetadata(
            provider=response.provider or provider.name,
            model=response.model,
            prompt_version=settings.prompt_version,
            processing_status=ProcessingStatus.COMPLETED,
            latency_ms=response.latency_ms,
            usage=response.usage or None,
        ),
    }
    dropped_any = len(safe_ids) < len(answer.referenced_email_ids)
    if dropped_any:
        updates["answer"] = (answer.answer + "\n(Some referenced ids were not in the supplied set and were dropped.)")[
            :3900
        ]
        updates["out_of_scope"] = True
    return answer.model_copy(update=updates)


__all__ = ["answer_inbox_question"]
