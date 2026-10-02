"""Admin panel schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import UserRole


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    is_verified: bool
    created_at: datetime
    last_login_at: datetime | None = None
    email_count: int = 0


class AdminUserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    is_verified: bool | None = None


class AdminUserList(BaseModel):
    items: list[AdminUserOut]
    total: int
    page: int
    page_size: int
    pages: int


class AdminStats(BaseModel):
    users_total: int = 0
    users_active: int = 0
    emails_total: int = 0
    emails_processed: int = 0
    emails_failed: int = 0
    analysis_total: int = 0
    replies_total: int = 0
    action_items_total: int = 0
    ai_calls_total: int = 0
    ai_calls_failed: int = 0
    ai_tokens_total: int = 0
    ai_errors_last_24h: int = 0


class AIUsageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    email_id: int | None = None
    purpose: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: int | None
    status: str
    created_at: datetime


class AIErrorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    email_id: int | None = None
    purpose: str
    provider: str
    model: str
    error_code: str
    error_message: str
    attempts: int
    retryable: bool
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    action: str
    object_type: str | None = None
    object_id: str | None = None
    outcome: str
    ip_address: str | None = None
    context: dict = Field(default_factory=dict)
    created_at: datetime


class CategoryConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    label: str
    description: str
    is_active: bool
    sort_order: int


class CategoryConfigUpsert(BaseModel):
    key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    is_active: bool = True
    sort_order: int = 0


class CategoryConfigUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    sort_order: int | None = None


class SystemConfigOut(BaseModel):
    key: str
    value: object
    description: str
    updated_at: datetime
    updated_by: int | None = None


class SystemConfigUpdate(BaseModel):
    value: object
    description: str = Field(default="", max_length=2000)
