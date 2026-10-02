"""Action items, deadlines and suggested reply schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import ActionStatus, EmailPriority, ReplyStatus, ReplyTone


class ActionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email_id: int
    description: str
    owner: str | None = None
    due_text: str | None = None
    due_date: date | None = None
    due_at: datetime | None = None
    due_date_estimated: bool = False
    status: ActionStatus
    priority: EmailPriority = EmailPriority.medium
    completed_at: datetime | None = None
    created_at: datetime
    email_subject: str | None = None


class ActionItemUpdate(BaseModel):
    status: ActionStatus | None = None
    description: str | None = Field(default=None, max_length=2000)
    owner: str | None = Field(default=None, max_length=255)
    due_date: date | None = None
    due_text: str | None = Field(default=None, max_length=255)

    @field_validator("due_text")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class DeadlineOut(BaseModel):
    action_id: int
    email_id: int
    description: str
    due_date: date | None
    due_text: str | None = None
    status: ActionStatus
    days_until: int | None = None
    overdue: bool = False


class ReplyGenerateRequest(BaseModel):
    tone: ReplyTone = ReplyTone.professional
    regenerate: bool = False
    instructions: str | None = Field(default=None, max_length=1000)


class SuggestedReplyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email_id: int
    thread_id: int | None = None
    tone: ReplyTone
    body: str
    original_body: str | None = None
    is_edited: bool
    status: ReplyStatus
    provider: str
    model: str
    latency_ms: int | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SuggestedReplyUpdate(BaseModel):
    body: str | None = Field(default=None, max_length=100_000)
    status: ReplyStatus | None = None
    tone: ReplyTone | None = None

    @field_validator("body")
    @classmethod
    def _strip_body(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("Reply body cannot be empty.")
        return stripped
