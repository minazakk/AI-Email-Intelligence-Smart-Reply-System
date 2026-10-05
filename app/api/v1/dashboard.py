"""Dashboard and analytics endpoints (user-scoped, computed from real rows)."""

from __future__ import annotations

from datetime import date as _date
from datetime import timedelta

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ValidationFailedError
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
from app.services import analytics_service

router = APIRouter(tags=["Dashboard and analytics"])


def _day(value: str | None, field: str) -> _date | None:
    if not value:
        return None
    try:
        return _date.fromisoformat(value)
    except ValueError:
        raise ValidationFailedError(
            "Dates must be formatted YYYY-MM-DD.",
            details=[{"field": field, "message": "Expected an ISO date (YYYY-MM-DD)."}],
        ) from None


@router.get("/dashboard/summary", response_model=DashboardSummary, summary="Dashboard summary")
def dashboard_summary(db: DbSession, user: CurrentUser) -> DashboardSummary:
    return analytics_service.dashboard_summary(db, user.id)


@router.get(
    "/dashboard/counters", response_model=DashboardCounters, summary="Dashboard counters only"
)
def dashboard_counters(db: DbSession, user: CurrentUser) -> DashboardCounters:
    return analytics_service.counters(db, user.id)


@router.get(
    "/dashboard/activity",
    response_model=list[ActivityPoint],
    summary="Email activity per day",
)
def dashboard_activity(
    db: DbSession,
    user: CurrentUser,
    days: int = Query(default=30, ge=1, le=365),
) -> list[ActivityPoint]:
    return analytics_service.activity_series(db, user.id, days=days)


@router.get(
    "/dashboard/categories",
    response_model=list[CategoryCount],
    summary="Category distribution",
)
def dashboard_categories(db: DbSession, user: CurrentUser) -> list[CategoryCount]:
    return analytics_service.category_distribution(db, user.id)


@router.get(
    "/dashboard/sentiments",
    response_model=list[SentimentCount],
    summary="Sentiment distribution",
)
def dashboard_sentiments(db: DbSession, user: CurrentUser) -> list[SentimentCount]:
    return analytics_service.sentiment_distribution(db, user.id)


@router.get(
    "/dashboard/priorities",
    response_model=list[PriorityCount],
    summary="Priority distribution",
)
def dashboard_priorities(db: DbSession, user: CurrentUser) -> list[PriorityCount]:
    return analytics_service.priority_distribution(db, user.id)


@router.get(
    "/dashboard/recent-emails",
    response_model=list[RecentEmail],
    summary="Most recent emails",
)
def dashboard_recent_emails(
    db: DbSession, user: CurrentUser, limit: int = Query(default=8, ge=1, le=50)
) -> list[RecentEmail]:
    return analytics_service.recent_emails(db, user.id, limit=limit)


@router.get(
    "/dashboard/recent-activity",
    response_model=list[RecentActivity],
    summary="Recent AI processing activity",
)
def dashboard_recent_activity(
    db: DbSession, user: CurrentUser, limit: int = Query(default=10, ge=1, le=50)
) -> list[RecentActivity]:
    return analytics_service.recent_activity(db, user.id, limit=limit)


@router.get(
    "/dashboard/deadlines",
    response_model=list[dict],
    summary="Upcoming and overdue deadlines",
)
def dashboard_deadlines(db: DbSession, user: CurrentUser) -> list[dict]:
    return analytics_service.upcoming_deadlines(db, user.id)


@router.get("/analytics", response_model=AnalyticsReport, summary="Analytics over a date range")
def analytics(
    db: DbSession,
    user: CurrentUser,
    date_from: str | None = None,
    date_to: str | None = None,
) -> AnalyticsReport:
    end = _day(date_to, "date_to") or _date.today()
    start = _day(date_from, "date_from") or (end - timedelta(days=29))
    if start > end:
        raise ValidationFailedError("date_from must be on or before date_to.")
    return analytics_service.analytics_report(db, user.id, start, end)
