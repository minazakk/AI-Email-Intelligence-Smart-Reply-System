"""Notifications and per-user notification preferences."""

from __future__ import annotations

from datetime import datetime

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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import NotificationType
from app.core.utils import utcnow
from app.db.base import Base, TimestampMixin


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_id_is_read_created_at", "user_id", "is_read", "created_at"),
        UniqueConstraint(
            "user_id",
            "dedupe_key",
            name="uq_notifications_user_id_dedupe_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email_id: Mapped[int | None] = mapped_column(
        ForeignKey("emails.id", ondelete="CASCADE"), nullable=True, index=True
    )
    action_id: Mapped[int | None] = mapped_column(
        ForeignKey("action_items.id", ondelete="CASCADE"), nullable=True
    )

    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    # Stable key that prevents duplicate notifications for the same event.
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )

    @staticmethod
    def make_dedupe_key(
        ntype: NotificationType | str,
        *,
        user_id: int,
        email_id: int | None = None,
        action_id: int | None = None,
        suffix: str = "",
    ) -> str:
        value = ntype.value if isinstance(ntype, NotificationType) else str(ntype)
        parts = [value, str(user_id)]
        if email_id is not None:
            parts.append(f"e{email_id}")
        if action_id is not None:
            parts.append(f"a{action_id}")
        if suffix:
            parts.append(suffix)
        return ":".join(parts)


class NotificationPreference(Base, TimestampMixin):
    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    # {"urgent_email": true, "customer_complaint": true, ...}
    enabled_types: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    daily_digest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
