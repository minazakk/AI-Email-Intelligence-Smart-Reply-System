"""Authentication, profile and preference schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.enums import ReplyTone, UserRole
from app.core.security import validate_password_strength
from app.schemas.common import ErrorDetail


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    full_name: str = Field(default="", max_length=120)
    timezone: str = Field(default="UTC", max_length=64)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        problems = validate_password_strength(value)
        if problems:
            raise ValueError("; ".join(problems))
        return value

    @field_validator("full_name")
    @classmethod
    def _trim_name(cls, value: str) -> str:
        return (value or "").strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        problems = validate_password_strength(value)
        if problems:
            raise ValueError("; ".join(problems))
        return value


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)

    @field_validator("new_password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        problems = validate_password_strength(value)
        if problems:
            raise ValueError("; ".join(problems))
        return value


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)


class RequestVerifyEmailRequest(BaseModel):
    email: EmailStr | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16, max_length=512)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    is_verified: bool
    timezone: str
    created_at: datetime
    last_login_at: datetime | None = None
    email_verified_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("full_name")
    @classmethod
    def _trim(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class UserPreferencesOut(BaseModel):
    default_reply_tone: ReplyTone
    digest_enabled: bool
    timezone: str
    notification_channels: dict


class UserPreferencesUpdate(BaseModel):
    default_reply_tone: ReplyTone | None = None
    digest_enabled: bool | None = None
    timezone: str | None = Field(default=None, max_length=64)
    notification_channels: dict | None = None


class AuthMessage(BaseModel):
    message: str
    # Present only when DEV_MODE_ENABLE_TOKEN_LINKS=true and no SMTP exists.
    dev_link: str | None = None
    dev_token: str | None = None
    details: list[ErrorDetail] | None = None
