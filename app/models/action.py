"""Action items / deadlines and suggested reply drafts."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ActionStatus, ReplyStatus, ReplyTone
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.email import Email


class ActionItem(Base, TimestampMixin):
    __tablename__ = "action_items"
    __table_args__ = (
        Index("ix_action_items_user_id_status_due_date", "user_id", "status", "due_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_id: Mapped[int] = mapped_column(
        ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True
    )

    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Original phrase (e.g. "by Friday") preserved even when not normalisable.
    due_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # True only when the source context was strong enough to normalise.
    due_date_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ActionStatus.pending.value, server_default=ActionStatus.pending.value
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")

    email: Mapped[Email] = relationship(lazy="joined")


class SuggestedReply(Base, TimestampMixin):
    __tablename__ = "suggested_replies"
    __table_args__ = (
        Index("ix_suggested_replies_user_id_email_id", "user_id", "email_id"),
        Index("ix_suggested_replies_user_id_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_id: Mapped[int] = mapped_column(
        ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_threads.id", ondelete="SET NULL"), nullable=True
    )

    tone: Mapped[str] = mapped_column(String(32), nullable=False, default=ReplyTone.professional.value)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Preserved so an edited draft can still show what the model produced.
    original_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReplyStatus.draft.value, server_default=ReplyStatus.draft.value
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown")
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    email: Mapped[Email] = relationship(lazy="joined")
