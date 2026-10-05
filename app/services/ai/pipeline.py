"""AI processing pipeline: analysis, smart reply and provider bookkeeping.

Guarantees enforced here:

* Provider output is schema-validated before it touches the database.
* A provider failure is recorded as a failure - never as a successful analysis.
* Original email content is never modified by AI processing.
* Every call writes an AI usage record, and failures also write an error log.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.enums import (
    ActionStatus,
    AiPurpose,
    NotificationType,
    ProcessingStatus,
    ReplyTone,
)
from app.core.errors import AIProviderError, AIResponseInvalidError
from app.core.logging import get_logger, log_event
from app.models.action import ActionItem, SuggestedReply
from app.models.ai import AIErrorLog, AIUsageRecord
from app.models.analysis import EmailAnalysis, ExtractedEntity
from app.models.email import Email
from app.services.ai.base import AIProvider
from app.services.ai.prompts import (
    ANALYSIS_PROMPT_VERSION,
    REPLY_PROMPT_VERSION,
    build_analysis_system_prompt,
    build_analysis_user_prompt,
    build_reply_system_prompt,
    build_reply_user_prompt,
)
from app.services.ai.schemas import (
    ANALYSIS_SCHEMA_VERSION,
    REPLY_SCHEMA_VERSION,
    EmailAnalysisModel,
    ReplyModel,
)

logger = get_logger("app.ai.pipeline")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _email_payload(email: Email) -> dict[str, Any]:
    return {
        "from_name": email.from_name,
        "from_address": email.from_address,
        "to": list(email.to or []),
        "cc": list(email.cc or []),
        "subject": email.subject,
        "received_at_iso": email.received_at.isoformat() if email.received_at else None,
        "body_text": email.body_text,
    }


def _record_usage(
    db: Session,
    *,
    user_id: int | None,
    email_id: int | None,
    purpose: AiPurpose,
    provider: str,
    model: str,
    response,
    status: str,
) -> None:
    db.add(
        AIUsageRecord(
            user_id=user_id,
            email_id=email_id,
            purpose=purpose.value,
            provider=provider,
            model=model,
            prompt_tokens=response.prompt_tokens if response else 0,
            completion_tokens=response.completion_tokens if response else 0,
            total_tokens=response.total_tokens if response else 0,
            latency_ms=response.latency_ms if response else None,
            status=status,
        )
    )


def _record_error(
    db: Session,
    *,
    user_id: int | None,
    email_id: int | None,
    purpose: AiPurpose,
    provider: str,
    model: str,
    exc: AIProviderError,
    attempts: int = 1,
) -> None:
    db.add(
        AIErrorLog(
            user_id=user_id,
            email_id=email_id,
            purpose=purpose.value,
            provider=provider,
            model=model,
            error_code=exc.code,
            error_message=str(exc.message)[:2000],
            attempts=attempts,
            retryable=exc.retryable,
        )
    )


def _persist_failure(
    db: Session,
    *,
    email: Email | None,
    user_id: int | None,
    purpose: AiPurpose,
    provider: str,
    model: str,
    exc: AIProviderError,
) -> None:
    """Commit the failure state independently of the caller's transaction."""
    db.rollback()
    try:
        if email is not None:
            pending = db.get(Email, email.id)
            if pending is not None:
                pending.processing_status = ProcessingStatus.failed.value
                pending.processing_error = exc.code
        _record_usage(
            db,
            user_id=user_id,
            email_id=email.id if email else None,
            purpose=purpose,
            provider=provider,
            model=model,
            response=None,
            status="error",
        )
        _record_error(
            db,
            user_id=user_id,
            email_id=email.id if email else None,
            purpose=purpose,
            provider=provider,
            model=model,
            exc=exc,
        )
        db.commit()
    except Exception:  # pragma: no cover - last-resort guard
        db.rollback()
        log_event(logger, 40, "Failed to persist AI error record", code=exc.code)


def analyze_email(
    db: Session,
    email: Email,
    provider: AIProvider,
    *,
    user_timezone: str = "UTC",
) -> EmailAnalysis:
    """Run the full analysis pipeline for one email.

    On success the previous analysis (if any) is replaced, action items and
    extracted entities are refreshed, and the email is marked ``completed``.
    On failure the email is marked ``failed`` and the error is recorded.
    """
    email.processing_status = ProcessingStatus.processing.value
    email.processing_error = None
    db.flush()

    response = None
    try:
        response = provider.complete_json(
            system=build_analysis_system_prompt(),
            user=build_analysis_user_prompt(_email_payload(email)),
        )
        payload = EmailAnalysisModel.model_validate(response.parsed)
    except AIProviderError as exc:
        _persist_failure(
            db,
            email=email,
            user_id=email.user_id,
            purpose=AiPurpose.analysis,
            provider=getattr(provider, "name", "unknown"),
            model=getattr(provider, "model", "unknown"),
            exc=exc,
        )
        raise
    except ValidationError as exc:
        wrapped = AIResponseInvalidError("AI analysis failed schema validation.")
        wrapped.details = {"errors": exc.errors()[:10]}
        _persist_failure(
            db,
            email=email,
            user_id=email.user_id,
            purpose=AiPurpose.analysis,
            provider=getattr(provider, "name", "unknown"),
            model=getattr(provider, "model", "unknown"),
            exc=wrapped,
        )
        raise wrapped from exc

    analysis = _persist_analysis(db, email=email, payload=payload, response=response)
    _record_usage(
        db,
        user_id=email.user_id,
        email_id=email.id,
        purpose=AiPurpose.analysis,
        provider=response.provider,
        model=response.model,
        response=response,
        status="success",
    )
    _notify_analysis(db, email=email, analysis=analysis)
    db.flush()
    return analysis


def _persist_analysis(
    db: Session,
    *,
    email: Email,
    payload: EmailAnalysisModel,
    response,
) -> EmailAnalysis:
    existing = db.scalar(select(EmailAnalysis).where(EmailAnalysis.email_id == email.id))
    if existing is not None:
        # ORM-level deletes keep the identity map in sync with the database.
        for entity in list(existing.entities):
            db.delete(entity)
        db.delete(existing)
        db.flush()

    analysis = EmailAnalysis(
        email_id=email.id,
        user_id=email.user_id,
        category=payload.category.value,
        category_confidence=payload.category_confidence,
        intent=payload.intent,
        priority=payload.priority.value,
        priority_reason=payload.priority_reason,
        sentiment=payload.sentiment.value,
        sentiment_confidence=payload.sentiment_confidence,
        reply_required=payload.reply_required,
        action_required=payload.action_required,
        summary_short=payload.summary_short,
        summary_detailed=payload.summary_detailed,
        key_points=list(payload.key_points),
        unresolved_issues=list(payload.unresolved_issues),
        provider=response.provider,
        model=response.model,
        prompt_version=ANALYSIS_PROMPT_VERSION,
        schema_version=ANALYSIS_SCHEMA_VERSION,
        processing_status=ProcessingStatus.completed.value,
        latency_ms=response.latency_ms,
        analyzed_at=datetime.now(UTC),
    )
    db.add(analysis)
    db.flush()

    for item in payload.extracted:
        db.add(
            ExtractedEntity(
                analysis_id=analysis.id,
                email_id=email.id,
                user_id=email.user_id,
                field=ExtractedEntity.coerce_field(item.field),
                value_text=(item.value or "")[:4000],
                value_normalized=item.normalized_value,
                raw_phrase=(item.raw_phrase or item.value or "")[:255],
                confidence=item.confidence,
                evidence=(item.evidence or None),
            )
        )

    # Refresh action items derived from this email.
    db.execute(delete(ActionItem).where(ActionItem.email_id == email.id, ActionItem.status == "pending"))
    for item in payload.action_items:
        due_date = None
        if item.due_date:
            try:
                due_date = datetime.strptime(item.due_date, "%Y-%m-%d").date()
            except ValueError:
                due_date = None
        db.add(
            ActionItem(
                user_id=email.user_id,
                email_id=email.id,
                description=item.description,
                owner=item.owner,
                due_text=item.due_text,
                due_date=due_date,
                due_date_estimated=due_date is not None,
                status=ActionStatus.pending.value,
                priority=item.priority.value,
            )
        )

    email.processing_status = ProcessingStatus.completed.value
    email.processing_error = None
    email.processed_at = datetime.now(UTC)
    db.flush()
    return analysis


def _notify_analysis(db: Session, *, email: Email, analysis: EmailAnalysis) -> None:
    """Create in-app notifications driven by the analysis result."""
    from app.services.notification_service import notify

    if analysis.priority in {"high", "critical"} or analysis.sentiment == "urgent":
        notify(
            db,
            user_id=email.user_id,
            ntype=NotificationType.urgent_email,
            title=f"Urgent email: {email.subject[:120] or '(no subject)'}",
            body=f"Priority {analysis.priority}: {analysis.priority_reason[:200]}",
            severity="warning",
            email_id=email.id,
        )
    if analysis.category == "customer_complaint":
        notify(
            db,
            user_id=email.user_id,
            ntype=NotificationType.customer_complaint,
            title=f"Customer complaint: {email.subject[:120] or '(no subject)'}",
            body=analysis.summary_short[:200],
            severity="warning",
            email_id=email.id,
        )
    if analysis.reply_required:
        notify(
            db,
            user_id=email.user_id,
            ntype=NotificationType.reply_required,
            title=f"Reply requested: {email.subject[:120] or '(no subject)'}",
            body=analysis.summary_short[:200],
            severity="info",
            email_id=email.id,
        )
    notify(
        db,
        user_id=email.user_id,
        ntype=NotificationType.ai_processing_completed,
        title="AI analysis completed",
        body=f"{email.subject[:100] or '(no subject)'} classified as {analysis.category}.",
        severity="info",
        email_id=email.id,
    )


# --- smart reply -----------------------------------------------------------

def _thread_messages(db: Session, email: Email, limit: int = 8) -> list[Email]:
    if email.thread_id is None:
        return [email]
    rows = list(
        db.scalars(
            select(Email)
            .where(Email.thread_id == email.thread_id, Email.is_deleted.is_(False))
            .order_by(Email.received_at.asc(), Email.id.asc())
        ).all()
    )
    # Ensure the message being answered is last.
    rows = [r for r in rows if r.id != email.id] + [email]
    return rows[-limit:]


def build_thread_summary(messages: list[Email], *, max_chars: int = 12000) -> str:
    chunks: list[str] = []
    for message in messages:
        role = "LATEST MESSAGE" if message is messages[-1] else "earlier message"
        chunks.append(
            f"[{role}] from={message.from_name} <{message.from_address}> "
            f"at={message.received_at.isoformat() if message.received_at else 'unknown'}\n"
            f"subject={message.subject}\n"
            f"{message.body_text[:3000]}"
        )
    return "\n\n---\n\n".join(chunks)[:max_chars]


def generate_reply(
    db: Session,
    email: Email,
    provider: AIProvider,
    *,
    tone: ReplyTone = ReplyTone.professional,
    instructions: str | None = None,
) -> SuggestedReply:
    """Draft a thread-aware reply. Nothing is ever sent automatically."""
    messages = _thread_messages(db, email)
    thread_summary = build_thread_summary(messages[:-1]) if len(messages) > 1 else "(no earlier messages)"

    response = None
    try:
        response = provider.complete_json(
            system=build_reply_system_prompt(tone.value, thread_summary),
            user=build_reply_user_prompt(_email_payload(email), instructions),
        )
        payload = ReplyModel.model_validate(response.parsed)
    except AIProviderError as exc:
        _persist_failure(
            db,
            email=email,
            user_id=email.user_id,
            purpose=AiPurpose.reply,
            provider=getattr(provider, "name", "unknown"),
            model=getattr(provider, "model", "unknown"),
            exc=exc,
        )
        raise
    except ValidationError as exc:
        wrapped = AIResponseInvalidError("AI reply failed schema validation.")
        wrapped.details = {"errors": exc.errors()[:10]}
        _persist_failure(
            db,
            email=email,
            user_id=email.user_id,
            purpose=AiPurpose.reply,
            provider=getattr(provider, "name", "unknown"),
            model=getattr(provider, "model", "unknown"),
            exc=wrapped,
        )
        raise wrapped from exc

    reply = SuggestedReply(
        user_id=email.user_id,
        email_id=email.id,
        thread_id=email.thread_id,
        tone=(payload.tone or tone).value,
        body=payload.body,
        original_body=payload.body,
        provider=response.provider,
        model=response.model,
        prompt_version=REPLY_PROMPT_VERSION,
        latency_ms=response.latency_ms,
        generation_metadata={
            "schema_version": REPLY_SCHEMA_VERSION,
            "requested_tone": tone.value,
            "thread_size": len(messages),
        },
    )
    db.add(reply)
    _record_usage(
        db,
        user_id=email.user_id,
        email_id=email.id,
        purpose=AiPurpose.reply,
        provider=response.provider,
        model=response.model,
        response=response,
        status="success",
    )
    db.flush()
    log_event(
        logger,
        20,
        "Smart reply drafted",
        email_id=email.id,
        tone=reply.tone,
        provider=response.provider,
        latency_ms=response.latency_ms,
    )
    return reply


__all__ = [
    "analyze_email",
    "build_thread_summary",
    "generate_reply",
    "_email_payload",
]
