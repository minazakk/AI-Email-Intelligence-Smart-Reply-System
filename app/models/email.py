"""Email threads, emails and category configuration."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import EmailDirection, EmailSource, ProcessingStatus
from app.core.utils import utcnow
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.analysis import EmailAnalysis


class EmailThread(Base, TimestampMixin):
    __tablename__ = "email_threads"
    __table_args__ = (
        UniqueConstraint("user_id", "thread_key", name="uq_email_threads_user_id_thread_key"),
        Index("ix_email_threads_user_id_last_message_at", "user_id", "last_message_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_key: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(998), nullable=False, default="")
    participant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    # Denormalised inbox flags so thread listing does not need N+1 scans.
    has_unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    emails: Mapped[list[Email]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", lazy="selectin"
    )


class Email(Base, TimestampMixin):
    """Original, user-owned email content. AI output lives elsewhere."""

    __tablename__ = "emails"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_hash", name="uq_emails_user_id_dedupe_hash"),
        Index("ix_emails_user_id_received_at", "user_id", "received_at"),
        Index("ix_emails_user_id_is_deleted_received_at", "user_id", "is_deleted", "received_at"),
        Index("ix_emails_user_id_is_archived", "user_id", "is_archived"),
        Index("ix_emails_user_id_direction", "user_id", "direction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[int | None] = mapped_column(
        ForeignKey("email_threads.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Headers -------------------------------------------------------------
    message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    from_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    from_address: Mapped[str] = mapped_column(String(320), nullable=False, default="", index=True)
    to: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    cc: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reply_to: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str] = mapped_column(String(998), nullable=False, default="", index=True)

    # Body ----------------------------------------------------------------
    body_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview: Mapped[str] = mapped_column(String(300), nullable=False, default="")

    # Timing / state ------------------------------------------------------
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    direction: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=EmailDirection.inbound.value,
        server_default=EmailDirection.inbound.value,
    )
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_starred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Provenance ----------------------------------------------------------
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EmailSource.manual.value, server_default=EmailSource.manual.value
    )
    has_attachments: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    attachment_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dedupe_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # AI processing -------------------------------------------------------
    processing_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ProcessingStatus.pending.value,
        server_default=ProcessingStatus.pending.value,
        index=True,
    )
    processing_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    thread: Mapped[EmailThread | None] = relationship(back_populates="emails")
    analysis: Mapped[EmailAnalysis | None] = relationship(
        "EmailAnalysis", back_populates="email", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )
