"""Notification schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import NotificationType


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: NotificationType
    title: str
    body: str
    severity: str
    email_id: int | None = None
    action_id: int | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class NotificationPreferencesOut(BaseModel):
    in_app_enabled: bool
    daily_digest: bool
    enabled_types: dict[str, bool]


class NotificationPreferencesUpdate(BaseModel):
    in_app_enabled: bool | None = None
    daily_digest: bool | None = None
    enabled_types: dict[str, bool] | None = None


class MarkReadRequest(BaseModel):
    is_read: bool = True


class BulkReadRequest(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=500)
    all: bool = False
