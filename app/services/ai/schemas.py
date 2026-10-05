"""Validated structured-output contracts for every AI call.

The provider returns JSON; it is parsed into these models before anything is
written to the database. Missing or out-of-range values are normalised rather
than trusted.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.enums import (
    CATEGORIES,
    PRIORITIES,
    SENTIMENTS,
    EmailCategory,
    EmailPriority,
    EmailSentiment,
    ReplyTone,
)

ANALYSIS_SCHEMA_VERSION = "1.0"
REPLY_SCHEMA_VERSION = "1.0"
ASSISTANT_SCHEMA_VERSION = "1.0"


class ExtractedFieldModel(BaseModel):
    field: str = Field(description="One of the supported extracted-field keys.")
    value: str = Field(default="", max_length=2000)
    raw_phrase: str | None = Field(default=None, max_length=255, description="Verbatim source phrase.")
    normalized_value: str | None = Field(
        default=None,
        max_length=64,
        description="ISO-8601 date/datetime or machine value; null when not derivable.",
    )
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: str | None = Field(default=None, max_length=500)

    @field_validator("value", mode="before")
    @classmethod
    def _value_str(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()


class ActionItemModel(BaseModel):
    description: str = Field(max_length=1000)
    owner: str | None = Field(default=None, max_length=255)
    due_text: str | None = Field(default=None, max_length=255, description="Original deadline phrase.")
    due_date: str | None = Field(
        default=None,
        max_length=32,
        description="YYYY-MM-DD only when the source text unambiguously supports it; else null.",
    )
    priority: EmailPriority = EmailPriority.medium

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Action item description cannot be empty.")
        return stripped

    @field_validator("due_date")
    @classmethod
    def _check_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from datetime import date as _date

        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = _date.fromisoformat(text[:10])
        except ValueError:
            # Ambiguous or unparseable: keep only the raw phrase upstream.
            return None
        return parsed.isoformat()


class EmailAnalysisModel(BaseModel):
    """Full analysis payload requested from the provider."""

    category: EmailCategory
    category_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    intent: str = Field(default="", max_length=255)
    priority: EmailPriority
    priority_reason: str = Field(default="", max_length=500)
    sentiment: EmailSentiment
    sentiment_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reply_required: bool = False
    action_required: bool = False
    summary_short: str = Field(default="", max_length=600)
    summary_detailed: str = Field(default="", max_length=4000)
    key_points: list[str] = Field(default_factory=list, max_length=20)
    unresolved_issues: list[str] = Field(default_factory=list, max_length=20)
    extracted: list[ExtractedFieldModel] = Field(default_factory=list, max_length=40)
    action_items: list[ActionItemModel] = Field(default_factory=list, max_length=20)

    @field_validator("summary_short", "summary_detailed", "intent", "priority_reason")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("key_points", "unresolved_issues", mode="before")
    @classmethod
    def _clean_list(cls, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(v).strip() for v in value if str(v).strip()][:20]

    @field_validator("extracted", "action_items", mode="before")
    @classmethod
    def _clean_objs(cls, value: object) -> list:
        if not isinstance(value, list):
            return []
        return value[:40]


class ReplyModel(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    tone: ReplyTone = ReplyTone.professional

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Reply body cannot be empty.")
        return stripped


class QueryFiltersModel(BaseModel):
    """Validated filter object the assistant may propose. The backend applies
    these itself; no model-generated SQL is ever executed."""

    q: str | None = Field(default=None, max_length=255)
    from_address: str | None = Field(default=None, max_length=320)
    category: list[str] = Field(default_factory=list)
    priority: list[str] = Field(default_factory=list)
    sentiment: list[str] = Field(default_factory=list)
    date_from: str | None = Field(default=None, max_length=32)
    date_to: str | None = Field(default=None, max_length=32)
    unread: bool | None = None
    urgent: bool | None = None
    reply_required: bool | None = None
    action_required: bool | None = None
    order_number: str | None = Field(default=None, max_length=64)

    @field_validator("category", "priority", "sentiment", mode="before")
    @classmethod
    def _lower_list(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [v.strip().lower() for v in value.split(",") if v.strip()]
        if isinstance(value, (list, tuple)):
            return [str(v).strip().lower() for v in value if str(v).strip()]
        return []

    @field_validator("category")
    @classmethod
    def _check_category(cls, value: list[str]) -> list[str]:
        return [v for v in value if v in CATEGORIES]

    @field_validator("priority")
    @classmethod
    def _check_priority(cls, value: list[str]) -> list[str]:
        return [v for v in value if v in PRIORITIES]

    @field_validator("sentiment")
    @classmethod
    def _check_sentiment(cls, value: list[str]) -> list[str]:
        return [v for v in value if v in SENTIMENTS]

    @field_validator("q", "from_address", "date_from", "date_to", "order_number")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None


class AssistantAnswerModel(BaseModel):
    answer: str = Field(min_length=1, max_length=6000)
    requires_data: bool = True


SUPPORTED_EXTRACTED_FIELDS = (
    "customer_name",
    "company",
    "phone",
    "email",
    "order_number",
    "invoice_number",
    "product",
    "amount",
    "currency",
    "date",
    "deadline",
    "meeting_date",
    "location",
    "requested_action",
)

__all__ = [
    "ANALYSIS_SCHEMA_VERSION",
    "REPLY_SCHEMA_VERSION",
    "ASSISTANT_SCHEMA_VERSION",
    "ActionItemModel",
    "AssistantAnswerModel",
    "EmailAnalysisModel",
    "ExtractedFieldModel",
    "QueryFiltersModel",
    "ReplyModel",
    "SUPPORTED_EXTRACTED_FIELDS",
    "EmailCategory",
    "EmailPriority",
    "EmailSentiment",
    "ReplyTone",
]
