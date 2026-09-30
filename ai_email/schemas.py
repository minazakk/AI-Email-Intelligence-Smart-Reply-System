"""Pydantic schemas: the validated contract of the AI module.

Every structured output produced by the module is validated against these
models before it is returned to a caller. The schemas are deliberately
database-agnostic so a future backend can persist them directly.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EmailCategory(StrEnum):
    SALES_INQUIRY = "sales_inquiry"
    CUSTOMER_COMPLAINT = "customer_complaint"
    SUPPORT_REQUEST = "support_request"
    MEETING_REQUEST = "meeting_request"
    INVOICE_PAYMENT = "invoice_payment"
    JOB_APPLICATION = "job_application"
    GENERAL_INFORMATION = "general_information"
    SPAM = "spam"
    URGENT = "urgent"
    OTHER = "other"


class PriorityLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    ANGRY = "angry"
    URGENT = "urgent"


class ActionStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


class ReplyTone(StrEnum):
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    SHORT = "short"
    DETAILED = "detailed"
    APOLOGETIC = "apologetic"
    FORMAL = "formal"


class ProcessingStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ResolutionKind(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NO_DATE = "no_date"


class ReadState(StrEnum):
    READ = "read"
    UNREAD = "unread"
    ANY = "any"


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_text(value: str | None, *, limit: int = 100_000) -> str:
    text = (value or "").replace("\x00", "").strip()
    if len(text) > limit:
        raise ValueError(f"text exceeds the maximum length of {limit} characters")
    return text


class EmailInput(BaseModel):
    """Minimal standalone email accepted by the module."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    subject: str | None = None
    sender: str = ""
    recipients: list[str] = Field(default_factory=list)
    body: str = ""
    received_at: datetime | None = None
    thread_id: str | None = None
    message_id: str | None = None
    is_read: bool | None = None
    is_starred: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("subject", "sender")
    @classmethod
    def _limit_short_text(cls, value: str | None) -> str | None:
        return _clean_text(value, limit=1_000) if value is not None else value

    @field_validator("body")
    @classmethod
    def _limit_body(cls, value: str) -> str:
        return _clean_text(value, limit=200_000)

    @field_validator("recipients")
    @classmethod
    def _clean_recipients(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if len(cleaned) > 50:
            raise ValueError("too many recipients (max 50)")
        return cleaned


class ThreadMessage(BaseModel):
    """One message of a conversation thread, oldest first."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    message_id: str | None = None
    sender: str = ""
    recipients: list[str] = Field(default_factory=list)
    body: str = ""
    subject: str | None = None
    sent_at: datetime | None = None
    direction: str | None = None  # "inbound" | "outbound" | None

    @field_validator("body")
    @classmethod
    def _limit_body(cls, value: str) -> str:
        return _clean_text(value, limit=200_000)


# ---------------------------------------------------------------------------
# Deadline handling
# ---------------------------------------------------------------------------


class NormalizedDeadline(BaseModel):
    """Result of deterministic deadline/date normalization."""

    model_config = ConfigDict(extra="ignore")

    raw_text: str
    normalized_date: date | None = None
    timezone: str = "UTC"
    resolution: ResolutionKind = ResolutionKind.NO_DATE
    reason: str | None = None

    @property
    def iso_date(self) -> str | None:
        return self.normalized_date.isoformat() if self.normalized_date else None


class DeadlineMention(BaseModel):
    """A deadline phrase found in an email (raw phrase always preserved)."""

    model_config = ConfigDict(extra="ignore")

    text: str
    normalized_date: date | None = None


# ---------------------------------------------------------------------------
# Analysis output
# ---------------------------------------------------------------------------


class ExtractedInformation(BaseModel):
    """Fields extracted verbatim from the email; ``None`` means 'not present'.

    The model must never invent values: unknown information stays ``None``
    or empty.
    """

    model_config = ConfigDict(extra="ignore")

    customer_name: str | None = None
    company: str | None = None
    phone_number: str | None = None
    email_address: str | None = None
    order_number: str | None = None
    invoice_number: str | None = None
    product: str | None = None
    amount: str | None = None
    currency: str | None = None
    dates: list[str] = Field(default_factory=list, max_length=20)
    deadlines: list[DeadlineMention] = Field(default_factory=list, max_length=10)
    meeting_date: str | None = None
    location: str | None = None
    requested_action: str | None = None

    @field_validator(
        "customer_name",
        "company",
        "phone_number",
        "email_address",
        "order_number",
        "invoice_number",
        "product",
        "amount",
        "currency",
        "meeting_date",
        "location",
        "requested_action",
    )
    @classmethod
    def _limit_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        return text[:500]

    @field_validator("email_address")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _EMAIL_RE.match(value):
            raise ValueError(f"invalid email address: {value!r}")
        return value


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = Field(min_length=1, max_length=500)
    owner: str | None = None
    deadline_text: str | None = None
    due_date: date | None = None
    status: ActionStatus = ActionStatus.PENDING
    source_email_id: str | None = None
    evidence: str | None = Field(default=None, max_length=500)

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str) -> str:
        return value.strip()

    @field_validator("owner", "deadline_text")
    @classmethod
    def _limit_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text[:300] or None


class ProcessingMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: str = "unknown"
    model: str | None = None
    prompt_version: str = "unknown"
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    latency_ms: float | None = None
    fallback_used: bool = False
    error: str | None = None
    usage: dict[str, Any] | None = None


class EmailAnalysis(BaseModel):
    """Validated analysis of a single email."""

    model_config = ConfigDict(extra="ignore")

    category: EmailCategory
    intent: str = Field(default="unknown", max_length=120)
    priority: PriorityLevel
    priority_reason: str = Field(default="", max_length=500)
    sentiment: Sentiment
    sentiment_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    reply_required: bool
    action_required: bool
    short_summary: str = Field(max_length=600)
    detailed_summary: str = Field(max_length=3_000)
    participants: list[str] = Field(default_factory=list, max_length=50)
    extracted_information: ExtractedInformation = Field(default_factory=ExtractedInformation)
    action_items: list[ActionItem] = Field(default_factory=list, max_length=25)
    key_points: list[str] = Field(default_factory=list, max_length=15)
    unresolved_issues: list[str] = Field(default_factory=list, max_length=15)
    processing_metadata: ProcessingMetadata = Field(default_factory=ProcessingMetadata)
    email_id: str | None = None

    @field_validator("intent")
    @classmethod
    def _clean_intent(cls, value: str) -> str:
        text = re.sub(r"\s+", " ", value or "").strip()
        return text.lower()[:120] or "unknown"

    @field_validator("short_summary", "detailed_summary")
    @classmethod
    def _clean_summary(cls, value: str) -> str:
        return re.sub(r"\s+", " ", value or "").strip()

    @field_validator("participants")
    @classmethod
    def _clean_participants(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for item in value:
            cleaned = (item or "").strip()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen

    @field_validator("key_points", "unresolved_issues")
    @classmethod
    def _clean_list(cls, value: list[str]) -> list[str]:
        cleaned = [(item or "").strip() for item in value]
        return [item for item in cleaned if item]

    @model_validator(mode="after")
    def _defaults(self) -> EmailAnalysis:
        if not self.short_summary:
            raise ValueError("short_summary must not be empty")
        if not self.detailed_summary:
            object.__setattr__(self, "detailed_summary", self.short_summary)
        return self


# ---------------------------------------------------------------------------
# Smart reply
# ---------------------------------------------------------------------------


class SmartReplyResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    draft: str = Field(min_length=1, max_length=8_000)
    tone: ReplyTone
    subject_line: str | None = None
    warnings: list[str] = Field(default_factory=list, max_length=20)
    thread_id: str | None = None
    reply_to_message_id: str | None = None
    status: str = "draft"
    requires_user_approval: bool = True
    sent: bool = False
    generated_at: datetime | None = None
    processing_metadata: ProcessingMetadata = Field(default_factory=ProcessingMetadata)

    @model_validator(mode="after")
    def _never_sent(self) -> SmartReplyResult:
        object.__setattr__(self, "sent", False)
        object.__setattr__(self, "requires_user_approval", True)
        if self.status == "sent":
            object.__setattr__(self, "status", "draft")
        return self


# ---------------------------------------------------------------------------
# Search intent / inbox assistant
# ---------------------------------------------------------------------------


class EmailSearchIntent(BaseModel):
    """Validated filter object produced from a natural-language question.

    The backend applies these filters with parameterized queries; the model
    never generates SQL.
    """

    model_config = ConfigDict(extra="ignore")

    categories: list[EmailCategory] = Field(default_factory=list)
    priorities: list[PriorityLevel] = Field(default_factory=list)
    sentiments: list[Sentiment] = Field(default_factory=list)
    reply_required: bool | None = None
    action_required: bool | None = None
    urgent: bool | None = None
    read_state: ReadState = ReadState.ANY
    keywords: list[str] = Field(default_factory=list, max_length=25)
    date_from: date | None = None
    date_to: date | None = None
    free_text: str | None = None
    matched_rules: list[str] = Field(default_factory=list)

    @field_validator("keywords")
    @classmethod
    def _clean_keywords(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            for token in re.split(r"[,\s]+", (item or "").strip().lower()):
                if token and token not in cleaned:
                    cleaned.append(token)
        return cleaned[:25]

    @model_validator(mode="after")
    def _date_order(self) -> EmailSearchIntent:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            self.date_from, self.date_to = self.date_to, self.date_from
        return self


class AssistantAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answer: str = Field(min_length=1, max_length=4_000)
    scope: str = "supplied_records"
    records_supplied: int = Field(ge=0, default=0)
    records_matched: int = Field(ge=0, default=0)
    referenced_email_ids: list[str] = Field(default_factory=list, max_length=100)
    out_of_scope: bool = False
    follow_up_questions: list[str] = Field(default_factory=list, max_length=5)
    processing_metadata: ProcessingMetadata = Field(default_factory=ProcessingMetadata)

    @model_validator(mode="after")
    def _scope_consistency(self) -> AssistantAnswer:
        if self.records_matched > self.records_supplied:
            raise ValueError("records_matched cannot exceed records_supplied")
        return self


__all__ = [
    "ActionItem",
    "ActionStatus",
    "AssistantAnswer",
    "DeadlineMention",
    "EmailAnalysis",
    "EmailCategory",
    "EmailInput",
    "EmailSearchIntent",
    "ExtractedInformation",
    "NormalizedDeadline",
    "PriorityLevel",
    "ProcessingMetadata",
    "ProcessingStatus",
    "ReadState",
    "ReplyTone",
    "ResolutionKind",
    "Sentiment",
    "SmartReplyResult",
    "ThreadMessage",
]
