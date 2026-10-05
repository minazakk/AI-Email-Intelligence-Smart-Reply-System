"""Inbox assistant: deterministic data access plus optional AI interpretation.

The AI layer may *propose* a structured filter object. It never issues SQL and
never touches the database. All retrieval goes through the functions below,
which take an authenticated ``user_id`` and apply it unconditionally.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AIProviderError
from app.core.logging import get_logger, log_event
from app.models.action import ActionItem
from app.models.email import Email
from app.schemas.email import EmailFilterParams
from app.services.ai.base import AIProvider
from app.services.ai.prompts import (
    ASSISTANT_PROMPT_VERSION,
    build_assistant_answer_system_prompt,
    build_assistant_answer_user_prompt,
    build_query_system_prompt,
    build_query_user_prompt,
)
from app.services.ai.schemas import ASSISTANT_SCHEMA_VERSION, QueryFiltersModel
from app.services.email_query import search_emails

logger = get_logger("app.assistant")

# Whitelist of filter keys the assistant may propose. Anything else is dropped
# before validation, so a prompt-injected model cannot widen the query.
ALLOWED_FILTER_KEYS = frozenset(
    {
        "q",
        "from_address",
        "category",
        "priority",
        "sentiment",
        "date_from",
        "date_to",
        "unread",
        "urgent",
        "reply_required",
        "action_required",
        "order_number",
        "direction",
        "starred",
        "has_attachments",
        "sort_by",
        "sort_order",
        "page",
        "page_size",
    }
)


# --- data-access service interface (stable contract for the AI teammate) ---

def search_user_emails(
    db: Session,
    user_id: int,
    *,
    filters: dict[str, Any] | None = None,
    query: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    """Return a page of the authenticated user's emails plus the total count."""
    params = build_params(filters, query=query, page=page, page_size=page_size)
    items, total = search_emails(db, user_id, params)
    return items, total, params


def get_thread_context(db: Session, user_id: int, thread_id: int) -> list[Email]:
    return list(
        db.scalars(
            select(Email)
            .where(
                Email.thread_id == thread_id,
                Email.user_id == user_id,
                Email.is_deleted.is_(False),
            )
            .order_by(Email.received_at.asc(), Email.id.asc())
        ).all()
    )


def get_pending_actions(
    db: Session,
    user_id: int,
    *,
    date_from=None,
    date_to=None,
    include_completed: bool = False,
) -> list[ActionItem]:
    stmt = select(ActionItem).where(ActionItem.user_id == user_id)
    if not include_completed:
        stmt = stmt.where(ActionItem.status.in_(["pending", "in_progress"]))
    if date_from is not None:
        stmt = stmt.where(ActionItem.due_date.is_not(None), ActionItem.due_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(ActionItem.due_date.is_not(None), ActionItem.due_date <= date_to)
    return list(db.scalars(stmt.order_by(ActionItem.due_date.asc().nullslast())).all())


def get_email_context(db: Session, user_id: int, email_id: int) -> Email | None:
    return db.scalar(
        select(Email).where(Email.id == email_id, Email.user_id == user_id, Email.is_deleted.is_(False))
    )


def get_user_analytics(db: Session, user_id: int, *, date_from=None, date_to=None) -> dict[str, Any]:
    from app.services.analytics_service import analytics_report

    end = date_to or datetime.now(UTC).date()
    start = date_from or (end - timedelta(days=29))
    report = analytics_report(db, user_id, start, end)
    return report.model_dump(mode="json")


# --- query interpretation --------------------------------------------------

def heuristic_filters(question: str) -> dict[str, Any]:
    """Deterministic fallback used when the provider is unavailable."""
    text = (question or "").strip().lower()
    filters: dict[str, Any] = {
        "q": None,
        "from_address": None,
        "category": [],
        "priority": [],
        "sentiment": [],
        "date_from": None,
        "date_to": None,
        "unread": None,
        "urgent": None,
        "reply_required": None,
        "action_required": None,
        "order_number": None,
    }

    if "reply" in text and any(w in text for w in ("need", "awaiting", "waiting", "pending")):
        filters["reply_required"] = True
    if "action" in text or "to-do" in text or "todo" in text:
        filters["action_required"] = True
    if "unread" in text:
        filters["unread"] = True
    if any(w in text for w in ("urgent", "asap", "critical", "high priority")):
        filters["urgent"] = True
    if "angry" in text:
        filters["sentiment"] = ["angry"]
    elif "negative" in text:
        filters["sentiment"] = ["negative"]
    elif "positive" in text or "happy" in text:
        filters["sentiment"] = ["positive"]

    keyword_category = [
        ("complaint", "customer_complaint"),
        ("sales", "sales_inquiry"),
        ("quotation", "sales_inquiry"),
        ("quote", "sales_inquiry"),
        ("support", "support_request"),
        ("payment", "invoice_payment"),
        ("invoice", "invoice_payment"),
        ("meeting", "meeting_request"),
        ("job application", "job_application"),
        ("applicant", "job_application"),
        ("spam", "spam"),
    ]
    for needle, category in keyword_category:
        if needle in text and category not in filters["category"]:
            filters["category"] = [category]
            break

    order = re.search(r"order\s*(?:number|#|no\.?)?\s*([A-Z0-9][A-Z0-9\-_/]{2,})", question or "")
    if order:
        filters["order_number"] = order.group(1).upper()

    # Relative dates are only applied when no intent filter is active: a
    # question such as "which emails need my reply today" is about pending
    # work, and constraining it to a calendar window would return nothing.
    intent_active = any(
        filters[key] for key in ("urgent", "reply_required", "action_required", "unread")
    )
    today = datetime.now(UTC).date()
    if intent_active:
        pass
    elif "today" in text or "yesterday" in text:
        filters["date_from"] = today.isoformat()
        filters["date_to"] = today.isoformat()
    elif "this week" in text:
        start = today - timedelta(days=today.weekday())
        filters["date_from"] = start.isoformat()
        filters["date_to"] = today.isoformat()
    elif "this month" in text:
        filters["date_from"] = today.replace(day=1).isoformat()
        filters["date_to"] = today.isoformat()

    return filters


def _coerce_filters(raw: Any) -> dict[str, Any]:
    """Validate AI output and drop anything outside the allow-list."""
    if not isinstance(raw, dict):
        return {}
    allowed = {k: v for k, v in raw.items() if k in ALLOWED_FILTER_KEYS}
    try:
        model = QueryFiltersModel.model_validate(allowed)
    except ValidationError as exc:
        log_event(logger, 30, "Rejected assistant filters", errors=exc.errors()[:5])
        # Salvage individual fields that did validate.
        clean = {k: allowed.get(k) for k in allowed}
        try:
            model = QueryFiltersModel.model_validate(
                {k: v for k, v in clean.items() if k in QueryFiltersModel.model_fields}
            )
        except ValidationError:
            return {}
    data = model.model_dump()
    # Never let the model widen the result window beyond one page.
    data.pop("page", None)
    data.pop("page_size", None)
    return {k: v for k, v in data.items() if v is not None and v != []}


def interpret_question(provider: AIProvider, question: str) -> tuple[dict[str, Any], bool]:
    """Return ``(filters, used_fallback)``. The provider may fail; the
    deterministic heuristic then takes over so the endpoint still works."""
    try:
        response = provider.complete_json(
            system=build_query_system_prompt(),
            user=build_query_user_prompt(question),
        )
        raw_filters = response.parsed.get("filters", response.parsed)
        return _coerce_filters(raw_filters), False
    except AIProviderError as exc:
        log_event(logger, 30, "Assistant filter interpretation failed; using heuristic", code=exc.code)
        return heuristic_filters(question), True


def build_params(
    filters: dict[str, Any] | None,
    *,
    query: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> EmailFilterParams:
    data = dict(filters or {})
    if query:
        data["q"] = query
    # Drop keys EmailFilterParams does not accept, then validate.
    data = {k: v for k, v in data.items() if k in EmailFilterParams.model_fields}
    data["page"] = max(1, min(int(page), 10_000))
    data["page_size"] = max(1, min(int(page_size), 100))
    data.setdefault("deleted", False)
    return EmailFilterParams.model_validate(data)


def _record(email: Email) -> dict[str, Any]:
    analysis = email.analysis
    return {
        "id": email.id,
        "subject": email.subject,
        "sender": f"{email.from_name} <{email.from_address}>",
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "category": analysis.category if analysis else None,
        "priority": analysis.priority if analysis else None,
        "sentiment": analysis.sentiment if analysis else None,
        "reply_required": analysis.reply_required if analysis else None,
        "summary": analysis.summary_short if analysis else "",
        "is_read": email.is_read,
    }


def deterministic_answer(question: str, records: list[dict], total: int) -> str:
    if not records:
        return "I could not find any emails in your inbox matching that question."
    subjects = "; ".join(f"[#{r['id']}] {r['subject'] or '(no subject)'}" for r in records[:5])
    more = "" if total <= 5 else f" ({total - 5} more)"
    return (
        f"I found {total} matching email(s). Most relevant: {subjects}{more}."
    )


def answer_question(
    db: Session,
    user_id: int,
    provider: AIProvider,
    question: str,
    *,
    limit: int = 25,
) -> dict[str, Any]:
    """Interpret, retrieve and answer - all strictly user-scoped."""
    filters, used_fallback = interpret_question(provider, question)
    params = build_params(filters, page=1, page_size=min(limit, 100))
    matches, total = search_emails(db, user_id, params)
    records = [_record(email) for email in matches[:limit]]

    answer = None
    deterministic = used_fallback
    if records:
        try:
            response = provider.complete_json(
                system=build_assistant_answer_system_prompt(),
                user=build_assistant_answer_user_prompt(question, records),
            )
            answer = str(response.parsed.get("answer") or "").strip() or None
        except AIProviderError as exc:
            log_event(logger, 30, "Assistant answer generation failed", code=exc.code)
            deterministic = True
    if not answer:
        answer = deterministic_answer(question, records, total)
        deterministic = True

    return {
        "applied_filters": filters,
        "total_matches": total,
        "results": records,
        "answer": answer[:6000],
        "deterministic": deterministic,
        "provider": getattr(provider, "name", "unknown"),
        "prompt_version": ASSISTANT_PROMPT_VERSION,
        "schema_version": ASSISTANT_SCHEMA_VERSION,
    }


__all__ = [
    "ALLOWED_FILTER_KEYS",
    "answer_question",
    "build_params",
    "deterministic_answer",
    "get_email_context",
    "get_pending_actions",
    "get_thread_context",
    "get_user_analytics",
    "heuristic_filters",
    "interpret_question",
    "search_user_emails",
]
