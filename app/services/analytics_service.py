"""Dashboard and analytics aggregation.

Every number here is computed from rows the authenticated user owns. No value
is hardcoded and no mock figure is ever returned from a production route.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.enums import ActionStatus, EmailCategory, ProcessingStatus
from app.models.action import ActionItem
from app.models.analysis import EmailAnalysis
from app.models.email import Email, EmailThread
from app.schemas.dashboard import (
    ActivityPoint,
    AnalyticsReport,
    CategoryCount,
    DashboardCounters,
    DashboardSummary,
    PriorityCount,
    RecentActivity,
    RecentEmail,
    SentimentCount,
)
from app.services.email_query import urgent_clause


def _day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, tzinfo=UTC),
        datetime.combine(end, time.max, tzinfo=UTC),
    )


def _scoped(db: Session, user_id: int):
    """Active (non-deleted, non-archived) emails joined to their analysis."""
    return (
        select(Email, EmailAnalysis)
        .outerjoin(EmailAnalysis, EmailAnalysis.email_id == Email.id)
        .where(
            Email.user_id == user_id,
            Email.is_deleted.is_(False),
            Email.is_archived.is_(False),
        )
    )


def counters(db: Session, user_id: int) -> DashboardCounters:
    base = _scoped(db, user_id)
    row = db.execute(
        base.with_only_columns(
            func.count(Email.id),
            func.sum(case((Email.is_read.is_(False), 1), else_=0)),
            func.sum(case((urgent_clause(), 1), else_=0)),
            func.sum(case((EmailAnalysis.reply_required.is_(True), 1), else_=0)),
            func.sum(case((EmailAnalysis.action_required.is_(True), 1), else_=0)),
            func.sum(case((EmailAnalysis.category == EmailCategory.sales_inquiry.value, 1), else_=0)),
            func.sum(case((EmailAnalysis.category == EmailCategory.support_request.value, 1), else_=0)),
            func.sum(case((EmailAnalysis.category == EmailCategory.customer_complaint.value, 1), else_=0)),
            func.sum(case((EmailAnalysis.category == EmailCategory.general_information.value, 1), else_=0)),
            func.sum(case((EmailAnalysis.category == EmailCategory.spam.value, 1), else_=0)),
            func.sum(case((Email.processing_status == ProcessingStatus.completed.value, 1), else_=0)),
            func.sum(case((Email.processing_status == ProcessingStatus.failed.value, 1), else_=0)),
            func.sum(case((Email.processing_status == ProcessingStatus.pending.value, 1), else_=0)),
        )
    ).one()

    pending_actions = db.scalar(
        select(func.count(ActionItem.id)).where(
            ActionItem.user_id == user_id,
            ActionItem.status.in_([ActionStatus.pending.value, ActionStatus.in_progress.value]),
        )
    )
    overdue = db.scalar(
        select(func.count(ActionItem.id)).where(
            ActionItem.user_id == user_id,
            ActionItem.status.in_([ActionStatus.pending.value, ActionStatus.in_progress.value]),
            ActionItem.due_date.is_not(None),
            ActionItem.due_date < datetime.now(UTC).date(),
        )
    )
    unread_threads = db.scalar(
        select(func.count(EmailThread.id)).where(
            EmailThread.user_id == user_id, EmailThread.has_unread.is_(True)
        )
    )

    def n(value) -> int:
        return int(value or 0)

    (
        total,
        unread,
        urgent,
        reply_required,
        action_required,
        sales,
        support,
        complaint,
        general,
        spam,
        processed,
        failed,
        pending,
    ) = row
    return DashboardCounters(
        total_emails=n(total),
        unread_emails=n(unread),
        urgent_emails=n(urgent),
        reply_required=n(reply_required),
        action_required=n(action_required),
        sales_emails=n(sales),
        support_emails=n(support),
        complaint_emails=n(complaint),
        pending_actions=int(pending_actions or 0),
        overdue_actions=int(overdue or 0),
        unread_threads=int(unread_threads or 0),
        processed_emails=n(processed),
        failed_emails=n(failed),
        pending_processing=n(pending),
    )


def category_distribution(db: Session, user_id: int) -> list[CategoryCount]:
    rows = db.execute(
        select(EmailAnalysis.category, func.count(EmailAnalysis.id))
        .join(Email, Email.id == EmailAnalysis.email_id)
        .where(
            Email.user_id == user_id,
            Email.is_deleted.is_(False),
            Email.is_archived.is_(False),
        )
        .group_by(EmailAnalysis.category)
        .order_by(func.count(EmailAnalysis.id).desc())
    ).all()
    total = sum(int(r[1]) for r in rows) or 1
    return [
        CategoryCount(category=r[0], count=int(r[1]), percentage=round(100 * int(r[1]) / total, 2))
        for r in rows
    ]


def sentiment_distribution(db: Session, user_id: int) -> list[SentimentCount]:
    rows = db.execute(
        select(EmailAnalysis.sentiment, func.count(EmailAnalysis.id))
        .join(Email, Email.id == EmailAnalysis.email_id)
        .where(
            Email.user_id == user_id,
            Email.is_deleted.is_(False),
            Email.is_archived.is_(False),
        )
        .group_by(EmailAnalysis.sentiment)
        .order_by(func.count(EmailAnalysis.id).desc())
    ).all()
    total = sum(int(r[1]) for r in rows) or 1
    return [
        SentimentCount(sentiment=r[0], count=int(r[1]), percentage=round(100 * int(r[1]) / total, 2))
        for r in rows
    ]


def priority_distribution(db: Session, user_id: int) -> list[PriorityCount]:
    rows = db.execute(
        select(EmailAnalysis.priority, func.count(EmailAnalysis.id))
        .join(Email, Email.id == EmailAnalysis.email_id)
        .where(
            Email.user_id == user_id,
            Email.is_deleted.is_(False),
            Email.is_archived.is_(False),
        )
        .group_by(EmailAnalysis.priority)
    ).all()
    return [PriorityCount(priority=r[0], count=int(r[1])) for r in rows]


def activity_series(db: Session, user_id: int, days: int = 30) -> list[ActivityPoint]:
    end = datetime.now(UTC).date()
    start = end - timedelta(days=days - 1)
    lo, hi = _day_bounds(start, end)

    rows = db.execute(
        select(
            func.date(Email.received_at),
            func.count(Email.id),
            func.sum(case((Email.is_read.is_(True), 1), else_=0)),
            func.sum(case((urgent_clause(), 1), else_=0)),
        )
        .outerjoin(EmailAnalysis, EmailAnalysis.email_id == Email.id)
        .where(
            Email.user_id == user_id,
            Email.is_deleted.is_(False),
            Email.received_at >= lo,
            Email.received_at <= hi,
        )
        .group_by(func.date(Email.received_at))
    ).all()
    by_day = {str(r[0]): r for r in rows}

    series: list[ActivityPoint] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        key = day.isoformat()
        row = by_day.get(key)
        series.append(
            ActivityPoint(
                date=day,
                received=int(row[1]) if row else 0,
                read=int(row[2] or 0) if row else 0,
                urgent=int(row[3] or 0) if row else 0,
            )
        )

    replied = db.execute(
        select(func.date(Email.received_at), func.count(Email.id)).where(
            Email.user_id == user_id,
            Email.direction == "outbound",
            Email.is_deleted.is_(False),
            Email.received_at >= lo,
            Email.received_at <= hi,
        )
        .group_by(func.date(Email.received_at))
    ).all()
    for day, count in replied:
        for point in series:
            if point.date.isoformat() == str(day):
                point.replied = int(count)
    return series


def recent_emails(db: Session, user_id: int, limit: int = 8) -> list[RecentEmail]:
    rows = db.execute(
        select(Email, EmailAnalysis.category, EmailAnalysis.priority)
        .outerjoin(EmailAnalysis, EmailAnalysis.email_id == Email.id)
        .where(
            Email.user_id == user_id,
            Email.is_deleted.is_(False),
            Email.is_archived.is_(False),
        )
        .order_by(Email.received_at.desc())
        .limit(limit)
    ).all()
    return [
        RecentEmail(
            id=email.id,
            subject=email.subject,
            from_name=email.from_name,
            from_address=email.from_address,
            received_at=email.received_at,
            category=category,
            priority=priority,
            is_read=email.is_read,
            processing_status=email.processing_status,
        )
        for email, category, priority in rows
    ]


def recent_activity(db: Session, user_id: int, limit: int = 10) -> list[RecentActivity]:
    """Recent AI processing events derived from stored analysis rows."""
    rows = db.execute(
        select(EmailAnalysis, Email.subject)
        .join(Email, Email.id == EmailAnalysis.email_id)
        .where(Email.user_id == user_id, Email.is_deleted.is_(False))
        .order_by(EmailAnalysis.analyzed_at.desc())
        .limit(limit)
    ).all()
    return [
        RecentActivity(
            id=analysis.id,
            email_id=analysis.email_id,
            kind="ai_analysis",
            label=f"{subject or '(no subject)'} -> {analysis.category}",
            created_at=analysis.analyzed_at,
        )
        for analysis, subject in rows
    ]


def upcoming_deadlines(db: Session, user_id: int, horizon_days: int = 14) -> list[dict]:
    today = datetime.now(UTC).date()
    horizon = today + timedelta(days=horizon_days)
    rows = db.execute(
        select(ActionItem, Email.subject)
        .join(Email, Email.id == ActionItem.email_id)
        .where(
            ActionItem.user_id == user_id,
            ActionItem.status.in_([ActionStatus.pending.value, ActionStatus.in_progress.value]),
            ActionItem.due_date.is_not(None),
            ActionItem.due_date <= horizon,
        )
        .order_by(ActionItem.due_date.asc())
        .limit(25)
    ).all()
    return [
        {
            "action_id": action.id,
            "email_id": action.email_id,
            "description": action.description,
            "due_date": action.due_date.isoformat() if action.due_date else None,
            "due_text": action.due_text,
            "status": action.status,
            "subject": subject,
            "days_until": (action.due_date - today).days if action.due_date else None,
            "overdue": bool(action.due_date and action.due_date < today),
        }
        for action, subject in rows
    ]


def dashboard_summary(db: Session, user_id: int) -> DashboardSummary:
    return DashboardSummary(
        counters=counters(db, user_id),
        category_distribution=category_distribution(db, user_id),
        sentiment_distribution=sentiment_distribution(db, user_id),
        priority_distribution=priority_distribution(db, user_id),
        upcoming_deadlines=upcoming_deadlines(db, user_id),
        recent_emails=recent_emails(db, user_id),
        recent_activity=recent_activity(db, user_id),
    )


# --- analytics -------------------------------------------------------------

def _count_where(db: Session, user_id: int, start: datetime, end: datetime, *clauses) -> int:
    stmt = (
        select(func.count(Email.id))
        .outerjoin(EmailAnalysis, EmailAnalysis.email_id == Email.id)
        .where(Email.user_id == user_id, Email.received_at >= start, Email.received_at <= end)
    )
    for clause in clauses:
        stmt = stmt.where(clause)
    return int(db.scalar(stmt) or 0)


def average_response_time(db: Session, user_id: int, start: datetime, end: datetime) -> tuple[float | None, int]:
    """Mean time between an inbound email and the first later outbound reply
    in the same thread.

    Computed in Python so the result is identical on PostgreSQL and SQLite.
    Returns ``(None, 0)`` when the stored data does not support a reliable
    sample - the API then reports ``null`` instead of an invented figure.
    """
    inbound = list(
        db.scalars(
            select(Email).where(
                Email.user_id == user_id,
                Email.direction == "inbound",
                Email.is_deleted.is_(False),
                Email.received_at >= start,
                Email.received_at <= end,
            )
        ).all()
    )
    if not inbound:
        return None, 0

    thread_ids = {mail.thread_id for mail in inbound if mail.thread_id is not None}
    if not thread_ids:
        return None, 0

    outbound = list(
        db.scalars(
            select(Email).where(
                Email.user_id == user_id,
                Email.direction == "outbound",
                Email.is_deleted.is_(False),
                Email.thread_id.in_(thread_ids),
            ).order_by(Email.thread_id, Email.sent_at.asc())
        ).all()
    )
    first_reply: dict[int, Email] = {}
    for mail in outbound:
        if mail.thread_id is not None and mail.sent_at is not None:
            first_reply.setdefault(mail.thread_id, mail)

    deltas: list[float] = []
    for mail in inbound:
        reply = first_reply.get(mail.thread_id) if mail.thread_id else None
        if reply is None or reply.sent_at is None:
            continue
        seconds = (reply.sent_at - mail.received_at).total_seconds()
        if seconds >= 0:
            deltas.append(seconds)

    if not deltas:
        return None, 0
    return sum(deltas) / len(deltas), len(deltas)


def analytics_report(db: Session, user_id: int, start: date, end: date) -> AnalyticsReport:
    lo, hi = _day_bounds(start, end)

    received = _count_where(db, user_id, lo, hi)
    sent = _count_where(db, user_id, lo, hi, Email.direction == "outbound")
    read = _count_where(db, user_id, lo, hi, Email.is_read.is_(True))
    urgent = _count_where(db, user_id, lo, hi, urgent_clause())
    complaint = _count_where(
        db, user_id, lo, hi, EmailAnalysis.category == EmailCategory.customer_complaint.value
    )
    sales = _count_where(
        db, user_id, lo, hi, EmailAnalysis.category == EmailCategory.sales_inquiry.value
    )
    support = _count_where(
        db, user_id, lo, hi, EmailAnalysis.category == EmailCategory.support_request.value
    )
    meeting = _count_where(
        db, user_id, lo, hi, EmailAnalysis.category == EmailCategory.meeting_request.value
    )
    invoice = _count_where(
        db, user_id, lo, hi, EmailAnalysis.category == EmailCategory.invoice_payment.value
    )
    jobs = _count_where(
        db, user_id, lo, hi, EmailAnalysis.category == EmailCategory.job_application.value
    )
    spam = _count_where(db, user_id, lo, hi, EmailAnalysis.category == EmailCategory.spam.value)

    inbound_in_replied = db.execute(
        select(func.count(func.distinct(Email.id)))
        .where(
            Email.user_id == user_id,
            Email.direction == "inbound",
            Email.is_deleted.is_(False),
            Email.received_at >= lo,
            Email.received_at <= hi,
            Email.thread_id.in_(
                select(Email.thread_id).where(
                    Email.user_id == user_id,
                    Email.direction == "outbound",
                    Email.is_deleted.is_(False),
                )
            ),
        )
    ).scalar_one()

    avg_seconds, sample = average_response_time(db, user_id, lo, hi)

    pending_actions = db.scalar(
        select(func.count(ActionItem.id)).where(
            ActionItem.user_id == user_id,
            ActionItem.status.in_([ActionStatus.pending.value, ActionStatus.in_progress.value]),
        )
    )
    completed_actions = db.scalar(
        select(func.count(ActionItem.id)).where(
            ActionItem.user_id == user_id, ActionItem.status == ActionStatus.completed.value
        )
    )

    return AnalyticsReport(
        date_from=start,
        date_to=end,
        emails_received=received,
        emails_sent=sent,
        emails_read=read,
        emails_replied=int(inbound_in_replied or 0),
        urgent_emails=urgent,
        customer_complaints=complaint,
        sales_inquiries=sales,
        support_requests=support,
        meeting_requests=meeting,
        invoice_payment=invoice,
        job_applications=jobs,
        spam=spam,
        by_category=category_distribution(db, user_id),
        by_priority=priority_distribution(db, user_id),
        sentiment_trend=sentiment_distribution(db, user_id),
        activity=activity_series(db, user_id, days=(end - start).days + 1),
        pending_actions=int(pending_actions or 0),
        completed_actions=int(completed_actions or 0),
        avg_response_time_seconds=round(avg_seconds, 2) if avg_seconds is not None else None,
        avg_response_time_sample_size=sample,
    )


__all__ = [
    "activity_series",
    "analytics_report",
    "average_response_time",
    "category_distribution",
    "counters",
    "dashboard_summary",
    "priority_distribution",
    "recent_activity",
    "recent_emails",
    "sentiment_distribution",
    "upcoming_deadlines",
]
