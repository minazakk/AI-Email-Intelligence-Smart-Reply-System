"""In-app notification creation and preference handling."""

from __future__ import annotations

import json

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.enums import NotificationType
from app.core.utils import utcnow
from app.models.notification import Notification, NotificationPreference

DEFAULT_ENABLED_TYPES: dict[str, bool] = {
    NotificationType.urgent_email.value: True,
    NotificationType.customer_complaint.value: True,
    NotificationType.reply_required.value: True,
    NotificationType.deadline_upcoming.value: True,
    NotificationType.action_item.value: True,
    NotificationType.ai_processing_completed.value: False,
    NotificationType.ai_processing_failed.value: True,
}


def get_preferences(db: Session, user_id: int) -> NotificationPreference:
    pref = db.scalar(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )
    if pref is None:
        pref = NotificationPreference(user_id=user_id, enabled_types=dict(DEFAULT_ENABLED_TYPES))
        db.add(pref)
        db.flush()
    return pref


def _is_enabled(pref: NotificationPreference, ntype: NotificationType) -> bool:
    if not pref.in_app_enabled:
        return False
    enabled = pref.enabled_types or {}
    return bool(enabled.get(ntype.value, DEFAULT_ENABLED_TYPES.get(ntype.value, True)))


def notify(
    db: Session,
    *,
    user_id: int,
    ntype: NotificationType,
    title: str,
    body: str = "",
    severity: str = "info",
    email_id: int | None = None,
    action_id: int | None = None,
    dedupe_suffix: str = "",
) -> Notification | None:
    """Create a notification unless the user disabled that type.

    Returns ``None`` when the notification is suppressed or already exists.
    Never raises on a duplicate dedupe key.
    """
    pref = get_preferences(db, user_id)
    if not _is_enabled(pref, ntype):
        return None

    dedupe_key = Notification.make_dedupe_key(
        ntype, user_id=user_id, email_id=email_id, action_id=action_id, suffix=dedupe_suffix
    )
    if dedupe_key:
        existing = db.scalar(
            select(Notification.id).where(
                Notification.user_id == user_id, Notification.dedupe_key == dedupe_key
            )
        )
        if existing is not None:
            return None

    notification = Notification(
        user_id=user_id,
        email_id=email_id,
        action_id=action_id,
        type=ntype.value,
        title=title[:255],
        body=body[:4000],
        severity=severity,
        dedupe_key=dedupe_key or None,
    )
    db.add(notification)
    db.flush()
    return notification


def mark_read(db: Session, user_id: int, notification_id: int, is_read: bool = True) -> Notification | None:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
    )
    if notification is None:
        return None
    notification.is_read = is_read
    notification.read_at = utcnow() if is_read else None
    db.flush()
    return notification


def mark_all_read(db: Session, user_id: int, ids: list[int] | None = None) -> int:
    stmt = update(Notification).where(
        Notification.user_id == user_id, Notification.is_read.is_(False)
    )
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))
    result = db.execute(stmt.values(is_read=True, read_at=utcnow()))
    db.flush()
    return int(result.rowcount or 0)


def parse_channels(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


__all__ = [
    "DEFAULT_ENABLED_TYPES",
    "get_preferences",
    "mark_all_read",
    "mark_read",
    "notify",
    "parse_channels",
]
