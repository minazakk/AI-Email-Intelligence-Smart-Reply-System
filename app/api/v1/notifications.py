"""Notification endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.core.enums import NotificationType
from app.core.errors import NotFoundError, ValidationFailedError
from app.models.notification import Notification
from app.schemas.common import Page, paginate
from app.schemas.notification import (
    BulkReadRequest,
    MarkReadRequest,
    NotificationOut,
    NotificationPreferencesOut,
    NotificationPreferencesUpdate,
)
from app.services.notification_service import (
    DEFAULT_ENABLED_TYPES,
    get_preferences,
    mark_all_read,
    mark_read,
)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=Page[NotificationOut], summary="List notifications")
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    unread_only: bool = False,
    ntype: str | None = Query(default=None, alias="type"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    if ntype:
        allowed = {t.value for t in NotificationType}
        if ntype not in allowed:
            raise ValidationFailedError(
                f"Invalid notification type: {ntype}. Allowed: {', '.join(sorted(allowed))}"
            )
        stmt = stmt.where(Notification.type == ntype)

    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(
        db.scalars(
            stmt.order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return paginate([NotificationOut.model_validate(r) for r in rows], total, page, page_size)


@router.get("/unread-count", summary="Unread notification count")
def unread_count(db: DbSession, user: CurrentUser) -> dict:
    count = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id, Notification.is_read.is_(False)
        )
    )
    return {"unread": int(count or 0)}


@router.post("/read-all", summary="Mark notifications as read")
def read_all(db: DbSession, user: CurrentUser, payload: BulkReadRequest | None = None) -> dict:
    ids = payload.ids if payload and payload.ids else None
    updated = mark_all_read(db, user.id, ids)
    db.commit()
    return {"updated": updated}


@router.post("/{notification_id}/read", response_model=NotificationOut, summary="Mark one as read")
def read_one(
    notification_id: int,
    payload: MarkReadRequest | None,
    db: DbSession,
    user: CurrentUser,
) -> NotificationOut:
    notification = mark_read(db, user.id, notification_id, payload.is_read if payload else True)
    if notification is None:
        raise NotFoundError(f"Notification {notification_id} was not found.")
    db.commit()
    return NotificationOut.model_validate(notification)


@router.delete("/{notification_id}", summary="Dismiss a notification")
def delete_notification(notification_id: int, db: DbSession, user: CurrentUser) -> dict:
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    )
    if notification is None:
        raise NotFoundError(f"Notification {notification_id} was not found.")
    db.delete(notification)
    db.commit()
    return {"ok": True}


@router.get(
    "/preferences/me",
    response_model=NotificationPreferencesOut,
    summary="Your notification preferences",
)
def get_prefs(db: DbSession, user: CurrentUser) -> NotificationPreferencesOut:
    pref = get_preferences(db, user.id)
    return NotificationPreferencesOut(
        in_app_enabled=pref.in_app_enabled,
        daily_digest=pref.daily_digest,
        enabled_types={**DEFAULT_ENABLED_TYPES, **(pref.enabled_types or {})},
    )


@router.put(
    "/preferences/me",
    response_model=NotificationPreferencesOut,
    summary="Update notification preferences",
)
def update_prefs(
    payload: NotificationPreferencesUpdate,
    db: DbSession,
    user: CurrentUser,
) -> NotificationPreferencesOut:
    pref = get_preferences(db, user.id)
    if payload.in_app_enabled is not None:
        pref.in_app_enabled = payload.in_app_enabled
    if payload.daily_digest is not None:
        pref.daily_digest = payload.daily_digest
    if payload.enabled_types is not None:
        allowed = {t.value for t in NotificationType}
        unknown = [k for k in payload.enabled_types if k not in allowed]
        if unknown:
            raise ValidationFailedError(
                f"Unknown notification types: {', '.join(sorted(unknown))}."
            )
        pref.enabled_types = {**(pref.enabled_types or {}), **payload.enabled_types}
    db.flush()
    db.commit()
    db.refresh(pref)
    return NotificationPreferencesOut(
        in_app_enabled=pref.in_app_enabled,
        daily_digest=pref.daily_digest,
        enabled_types={**DEFAULT_ENABLED_TYPES, **(pref.enabled_types or {})},
    )
