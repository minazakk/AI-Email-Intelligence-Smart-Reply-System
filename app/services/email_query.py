"""User-scoped email query builder.

Every helper in this module takes an explicit ``user_id`` and applies it
unconditionally. Callers never pass a user id that came from the request body.
"""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.enums import URGENT_PRIORITIES, EmailPriority
from app.core.utils import build_page
from app.models.analysis import EmailAnalysis, ExtractedEntity
from app.models.email import Email
from app.schemas.email import EmailFilterParams

_PRIORITY_ORDER = {
    EmailPriority.critical.value: 3,
    EmailPriority.high.value: 2,
    EmailPriority.medium.value: 1,
    EmailPriority.low.value: 0,
}


def _day_start(value: date) -> datetime:
    return datetime.combine(value, time.min)


def _day_end(value: date) -> datetime:
    return datetime.combine(value, time.max)


def base_query(user_id: int) -> Select:
    """Every email query starts here - owner scoping is not optional."""
    return select(Email).where(Email.user_id == user_id)


def apply_filters(query: Select, params: EmailFilterParams, *, user_id: int) -> Select:
    """Apply composable filters to a ``select(Email)`` statement."""

    # Soft-delete / archive defaults ------------------------------------
    if params.deleted is None:
        query = query.where(Email.is_deleted.is_(False))
    else:
        query = query.where(Email.is_deleted.is_(bool(params.deleted)))

    if params.archived is None:
        query = query.where(Email.is_archived.is_(False))
    else:
        query = query.where(Email.is_archived.is_(bool(params.archived)))

    # Text search -------------------------------------------------------
    if params.q:
        needle = f"%{params.q.lower()}%"
        query = query.where(
            or_(
                func.lower(Email.subject).like(needle),
                func.lower(Email.body_text).like(needle),
                func.lower(Email.from_name).like(needle),
                func.lower(Email.from_address).like(needle),
                func.lower(Email.preview).like(needle),
            )
        )
    if params.subject:
        query = query.where(func.lower(Email.subject).like(f"%{params.subject.lower()}%"))
    if params.from_address:
        query = query.where(
            or_(
                func.lower(Email.from_address).like(f"%{params.from_address.lower()}%"),
                func.lower(Email.from_name).like(f"%{params.from_address.lower()}%"),
            )
        )

    # Boolean flags -----------------------------------------------------
    if params.unread is not None:
        query = query.where(Email.is_read.is_(not params.unread))
    if params.starred is not None:
        query = query.where(Email.is_starred.is_(bool(params.starred)))
    if params.has_attachments is not None:
        query = query.where(Email.has_attachments.is_(bool(params.has_attachments)))
    if params.direction is not None:
        query = query.where(Email.direction == params.direction.value)
    if params.processing_status is not None:
        query = query.where(Email.processing_status == params.processing_status.value)

    # Date range (received_at, inclusive of both boundary days) ---------
    if params.date_from:
        query = query.where(Email.received_at >= _day_start(params.date_from))
    if params.date_to:
        query = query.where(Email.received_at <= _day_end(params.date_to))

    if params.thread_id is not None:
        query = query.where(Email.thread_id == params.thread_id)

    # AI-derived filters need the analysis row (outer join) -------------
    needs_analysis = bool(params.category or params.priority or params.sentiment) or any(
        flag is not None for flag in (params.urgent, params.reply_required, params.action_required)
    )
    if needs_analysis:
        query = query.outerjoin(EmailAnalysis, EmailAnalysis.email_id == Email.id)

    if params.category:
        query = query.where(EmailAnalysis.category.in_(params.category))
    if params.priority:
        query = query.where(EmailAnalysis.priority.in_(params.priority))
    if params.sentiment:
        query = query.where(EmailAnalysis.sentiment.in_(params.sentiment))
    if params.reply_required is not None:
        query = query.where(EmailAnalysis.reply_required.is_(bool(params.reply_required)))
    if params.action_required is not None:
        query = query.where(EmailAnalysis.action_required.is_(bool(params.action_required)))
    if params.urgent is not None:
        urgent_clause = or_(
            EmailAnalysis.priority.in_(URGENT_PRIORITIES),
            EmailAnalysis.sentiment == "urgent",
        )
        query = query.where(urgent_clause if params.urgent else ~urgent_clause)

    # Extracted-entity lookups ------------------------------------------
    if params.customer:
        needle = f"%{params.customer.lower()}%"
        query = query.where(
            select(ExtractedEntity.id)
            .where(
                ExtractedEntity.email_id == Email.id,
                ExtractedEntity.user_id == user_id,
                ExtractedEntity.field.in_(["customer_name", "company"]),
                func.lower(ExtractedEntity.value_text).like(needle),
            )
            .exists()
        )
    if params.order_number:
        needle = f"%{params.order_number.lower()}%"
        query = query.where(
            select(ExtractedEntity.id)
            .where(
                ExtractedEntity.email_id == Email.id,
                ExtractedEntity.user_id == user_id,
                ExtractedEntity.field.in_(["order_number", "invoice_number"]),
                func.lower(ExtractedEntity.value_text).like(needle),
            )
            .exists()
        )

    return query


def apply_sort(query: Select, params: EmailFilterParams) -> Select:
    direction = Email.received_at.desc() if params.sort_order == "desc" else Email.received_at.asc()
    if params.sort_by == "received_at":
        return query.order_by(direction, Email.id.desc())
    if params.sort_by == "created_at":
        order = Email.created_at.desc() if params.sort_order == "desc" else Email.created_at.asc()
        return query.order_by(order, Email.id.desc())
    if params.sort_by == "subject":
        order = func.lower(Email.subject).desc() if params.sort_order == "desc" else func.lower(Email.subject)
        return query.order_by(order, Email.id.desc())
    if params.sort_by == "size_bytes":
        order = Email.size_bytes.desc() if params.sort_order == "desc" else Email.size_bytes
        return query.order_by(order, Email.id.desc())
    if params.sort_by == "priority":
        expr = case(_PRIORITY_ORDER, value=EmailAnalysis.priority, else_=0)
        order = expr.desc() if params.sort_order == "desc" else expr
        return query.order_by(order, Email.received_at.desc())
    return query.order_by(direction, Email.id.desc())


def search_emails(db: Session, user_id: int, params: EmailFilterParams) -> tuple[list[Email], int]:
    query = apply_filters(base_query(user_id), params, user_id=user_id)

    count_query = select(func.count()).select_from(query.subquery())
    total = int(db.execute(count_query).scalar_one())

    page_query = apply_sort(query, params).offset((params.page - 1) * params.page_size).limit(
        params.page_size
    )
    items = list(db.scalars(page_query).unique().all())
    return items, total


def search_emails_page(db: Session, user_id: int, params: EmailFilterParams):
    items, total = search_emails(db, user_id, params)
    return build_page(items, total, params.page, params.page_size)


def urgent_clause():
    return or_(
        EmailAnalysis.priority.in_(URGENT_PRIORITIES),
        EmailAnalysis.sentiment == "urgent",
    )


__all__ = [
    "apply_filters",
    "apply_sort",
    "base_query",
    "build_page",
    "search_emails",
    "search_emails_page",
    "urgent_clause",
]
