"""Email, thread, import and search/filter schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import (
    ACTION_STATUSES,
    CATEGORIES,
    PRIORITIES,
    PROCESSING_STATUSES,
    SENTIMENTS,
    EmailCategory,
    EmailDirection,
    EmailPriority,
    EmailSentiment,
    EmailSource,
    ProcessingStatus,
)


def _split_addresses(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for chunk in value.split(",") for p in chunk.split(";")]
        return [p for p in parts if p]
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


class EmailCreate(BaseModel):
    """Manual / pasted email creation."""

    subject: str = Field(default="", max_length=998)
    from_name: str = Field(default="", max_length=255)
    from_address: str = Field(default="", max_length=320)
    to: list[str] = Field(default_factory=list, max_length=50)
    cc: list[str] = Field(default_factory=list, max_length=50)
    reply_to: str | None = Field(default=None, max_length=320)
    body_text: str = Field(default="", max_length=500_000)
    body_html: str | None = Field(default=None, max_length=1_000_000)
    received_at: datetime | None = None
    direction: EmailDirection = EmailDirection.inbound
    message_id: str | None = Field(default=None, max_length=255)
    has_attachments: bool = False
    attachment_names: list[str] = Field(default_factory=list, max_length=50)
    process_with_ai: bool = True

    @field_validator("to", "cc", "attachment_names", mode="before")
    @classmethod
    def _coerce_list(cls, value: object) -> list[str]:
        return _split_addresses(value)

    @model_validator(mode="after")
    def _require_content(self) -> EmailCreate:
        if not self.body_text.strip() and not self.body_html:
            raise ValueError("Either body_text or body_html must be provided.")
        if not self.from_address.strip() and not self.subject.strip():
            raise ValueError("At least one of from_address or subject is required.")
        return self


class EmailAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: EmailCategory
    category_confidence: float | None = None
    intent: str
    priority: EmailPriority
    priority_reason: str
    sentiment: EmailSentiment
    sentiment_confidence: float | None = None
    reply_required: bool
    action_required: bool
    summary_short: str
    summary_detailed: str
    key_points: list[str] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    latency_ms: int | None = None
    analyzed_at: datetime


class ExtractedEntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    field: str
    value_text: str
    value_normalized: str | None = None
    raw_phrase: str | None = None
    confidence: float | None = None
    evidence: str | None = None


class EmailListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int | None = None
    subject: str
    preview: str
    from_name: str
    from_address: str
    to: list[str] = Field(default_factory=list)
    received_at: datetime
    direction: EmailDirection
    is_read: bool
    is_starred: bool
    is_archived: bool
    is_deleted: bool = False
    has_attachments: bool
    source: EmailSource
    processing_status: ProcessingStatus
    category: str | None = None
    priority: str | None = None
    sentiment: str | None = None
    reply_required: bool | None = None
    action_required: bool | None = None
    is_urgent: bool = False


class EmailDetail(EmailListItem):
    body_text: str
    body_html: str | None = None
    cc: list[str] = Field(default_factory=list)
    reply_to: str | None = None
    message_id: str | None = None
    in_reply_to: str | None = None
    attachment_names: list[str] = Field(default_factory=list)
    size_bytes: int = 0
    created_at: datetime
    processed_at: datetime | None = None
    processing_error: str | None = None
    analysis: EmailAnalysisOut | None = None
    extracted: list[ExtractedEntityOut] = Field(default_factory=list)


class ThreadMessage(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str
    from_name: str
    from_address: str
    to: list[str] = Field(default_factory=list)
    received_at: datetime
    direction: EmailDirection
    body_text: str
    is_read: bool
    processing_status: ProcessingStatus
    category: str | None = None
    summary_short: str | None = None


class ThreadListItem(BaseModel):
    id: int
    thread_key: str
    subject: str
    message_count: int
    participant_count: int
    last_message_at: datetime
    has_unread: bool
    is_starred: bool
    preview: str = ""


class ThreadDetail(BaseModel):
    id: int
    thread_key: str
    subject: str
    last_message_at: datetime
    message_count: int
    messages: list[ThreadMessage] = Field(default_factory=list)


class StateUpdateRequest(BaseModel):
    is_read: bool | None = None
    is_starred: bool | None = None
    is_archived: bool | None = None


class EmailUpdateRequest(BaseModel):
    subject: str | None = Field(default=None, max_length=998)
    from_name: str | None = Field(default=None, max_length=255)
    body_text: str | None = Field(default=None, max_length=500_000)


# --- imports ---------------------------------------------------------------

class ImportRowError(BaseModel):
    row: int
    field: str | None = None
    message: str


class ImportSummary(BaseModel):
    source: EmailSource
    filename: str | None = None
    received: int = 0
    created: int = 0
    duplicates: int = 0
    failed: int = 0
    errors: list[ImportRowError] = Field(default_factory=list)
    email_ids: list[int] = Field(default_factory=list)


# --- search / filters ------------------------------------------------------

def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip().lower() for v in value.split(",") if v.strip()]


class EmailFilterParams(BaseModel):
    """Composable query filters. Every field is optional."""

    q: str | None = Field(default=None, max_length=255)
    from_address: str | None = Field(default=None, max_length=320)
    subject: str | None = Field(default=None, max_length=255)
    category: list[str] = Field(default_factory=list)
    priority: list[str] = Field(default_factory=list)
    sentiment: list[str] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None
    unread: bool | None = None
    starred: bool | None = None
    archived: bool | None = None
    deleted: bool | None = None
    urgent: bool | None = None
    reply_required: bool | None = None
    action_required: bool | None = None
    direction: EmailDirection | None = None
    processing_status: ProcessingStatus | None = None
    customer: str | None = Field(default=None, max_length=255)
    order_number: str | None = Field(default=None, max_length=255)
    has_attachments: bool | None = None
    thread_id: int | None = None
    sort_by: str = "received_at"
    sort_order: str = "desc"
    page: int = Field(default=1, ge=1)
    # The listing endpoint caps this at 100 via its own Query parameter; the
    # CSV export raises the ceiling to 1000, so the model allows that much.
    page_size: int = Field(default=20, ge=1, le=1000)

    @field_validator("category", "priority", "sentiment", mode="before")
    @classmethod
    def _from_csv(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return _csv(value)
        if isinstance(value, (list, tuple)):
            return [str(v).strip().lower() for v in value if str(v).strip()]
        return []

    @field_validator("q", "from_address", "subject")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("sort_by")
    @classmethod
    def _check_sort(cls, value: str) -> str:
        allowed = {"received_at", "created_at", "subject", "priority", "size_bytes"}
        if value not in allowed:
            raise ValueError(f"sort_by must be one of {sorted(allowed)}")
        return value

    @field_validator("sort_order")
    @classmethod
    def _check_order(cls, value: str) -> str:
        normalised = value.strip().lower()
        if normalised not in {"asc", "desc"}:
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return normalised

    @model_validator(mode="after")
    def _check_enums(self) -> EmailFilterParams:
        checks = (
            (self.category, CATEGORIES, "category"),
            (self.priority, PRIORITIES, "priority"),
            (self.sentiment, SENTIMENTS, "sentiment"),
        )
        for values, allowed, label in checks:
            bad = [v for v in values if v not in allowed]
            if bad:
                raise ValueError(f"Invalid {label}: {', '.join(bad)}. Allowed: {', '.join(allowed)}")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self


class EmailSearchResult(BaseModel):
    items: list[EmailListItem]
    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_previous: bool


__all__ = [
    "ACTION_STATUSES",
    "PROCESSING_STATUSES",
    "EmailAnalysisOut",
    "EmailCreate",
    "EmailDetail",
    "EmailFilterParams",
    "EmailListItem",
    "EmailSearchResult",
    "EmailUpdateRequest",
    "ExtractedEntityOut",
    "ImportRowError",
    "ImportSummary",
    "StateUpdateRequest",
    "ThreadDetail",
    "ThreadListItem",
    "ThreadMessage",
    "EmailCategory",
    "EmailPriority",
    "EmailSentiment",
    "EmailSource",
]
