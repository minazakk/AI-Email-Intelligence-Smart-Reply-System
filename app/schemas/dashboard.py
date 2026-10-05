"""Dashboard and analytics response schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class DashboardCounters(BaseModel):
    total_emails: int = 0
    unread_emails: int = 0
    urgent_emails: int = 0
    reply_required: int = 0
    action_required: int = 0
    customer_emails: int = 0
    sales_emails: int = 0
    support_emails: int = 0
    complaint_emails: int = 0
    pending_actions: int = 0
    overdue_actions: int = 0
    unread_threads: int = 0
    processed_emails: int = 0
    failed_emails: int = 0
    pending_processing: int = 0


class CategoryCount(BaseModel):
    category: str
    count: int
    percentage: float = 0.0


class SentimentCount(BaseModel):
    sentiment: str
    count: int
    percentage: float = 0.0


class PriorityCount(BaseModel):
    priority: str
    count: int


class ActivityPoint(BaseModel):
    date: date
    received: int = 0
    read: int = 0
    replied: int = 0
    urgent: int = 0


class RecentEmail(BaseModel):
    id: int
    subject: str
    from_name: str
    from_address: str
    received_at: datetime
    category: str | None = None
    priority: str | None = None
    is_read: bool
    processing_status: str


class RecentActivity(BaseModel):
    id: int
    email_id: int | None = None
    kind: str
    label: str
    created_at: datetime


class DashboardSummary(BaseModel):
    counters: DashboardCounters
    category_distribution: list[CategoryCount] = Field(default_factory=list)
    sentiment_distribution: list[SentimentCount] = Field(default_factory=list)
    priority_distribution: list[PriorityCount] = Field(default_factory=list)
    upcoming_deadlines: list[dict] = Field(default_factory=list)
    recent_emails: list[RecentEmail] = Field(default_factory=list)
    recent_activity: list[RecentActivity] = Field(default_factory=list)


class AnalyticsReport(BaseModel):
    date_from: date
    date_to: date
    emails_received: int = 0
    emails_sent: int = 0
    emails_read: int = 0
    emails_replied: int = 0
    urgent_emails: int = 0
    customer_complaints: int = 0
    sales_inquiries: int = 0
    support_requests: int = 0
    meeting_requests: int = 0
    invoice_payment: int = 0
    job_applications: int = 0
    spam: int = 0
    by_category: list[CategoryCount] = Field(default_factory=list)
    by_priority: list[PriorityCount] = Field(default_factory=list)
    sentiment_trend: list[SentimentCount] = Field(default_factory=list)
    activity: list[ActivityPoint] = Field(default_factory=list)
    pending_actions: int = 0
    completed_actions: int = 0
    # Null when the stored data does not support a reliable computation.
    avg_response_time_seconds: float | None = None
    avg_response_time_sample_size: int = 0
