"""Authentication, profile and preference endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.enums import TokenPurpose, UserRole
from app.core.errors import ConflictError, NotFoundError, UnauthorizedError, ValidationFailedError
from app.core.logging import get_logger, log_event
from app.core.rate_limit import enforce_rate_limit
from app.core.security import create_access_token, hash_password, hash_token, verify_password
from app.core.utils import utcnow
from app.models.user import SessionToken, User
from app.schemas.auth import (
    AuthMessage,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    RequestVerifyEmailRequest,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UserOut,
    UserPreferencesOut,
    UserPreferencesUpdate,
    VerifyEmailRequest,
)
from app.schemas.common import OkResponse
from app.services import auth_service
from app.services.audit_service import record as audit_record

logger = get_logger("app.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _token_response(db: DbSession, user: User, request: Request) -> TokenResponse:
    tokens = auth_service.issue_tokens(db, user, request=request)
    return TokenResponse(**tokens, user=UserOut.model_validate(user))


def _dev_link(kind: str, token: str) -> str:
    return f"/{kind}?token={token}"


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    enforce_rate_limit(request, "auth:signup", settings.rate_limit_signup_per_minute)
    if auth_service.find_user_by_email(db, payload.email):
        raise ConflictError("An account with this email already exists.", code="email_taken")

    user = auth_service.create_user(
        db,
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
        timezone=payload.timezone,
    )
    auth_service.mint_auth_token(db, user, TokenPurpose.email_verify)
    audit_record(
        db,
        action="auth.signup",
        user_id=user.id,
        actor_email=user.email,
        actor_role=user.role,
        object_type="user",
        object_id=user.id,
        request=request,
    )
    # Issue the session inside the same transaction so a successful signup and
    # its refresh token are always persisted together.
    result = _token_response(db, user, request)
    db.commit()

    response.set_cookie(
        "refresh_token",
        result.refresh_token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",
    )
    log_event(logger, 20, "Account created", user_id=user.id, verified=False)
    return result


@router.post("/login", response_model=TokenResponse, summary="Exchange credentials for tokens")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    enforce_rate_limit(request, "auth:login", settings.rate_limit_login_per_minute)
    user = auth_service.authenticate(db, str(payload.email), payload.password)
    if user is None:
        audit_record(
            db,
            action="auth.login_failed",
            actor_email=str(payload.email),
            outcome="failure",
            request=request,
            context={"reason": "invalid_credentials"},
        )
        db.commit()
        raise UnauthorizedError("Invalid email or password.", code="invalid_credentials")

    audit_record(
        db,
        action="auth.login",
        user_id=user.id,
        actor_email=user.email,
        actor_role=user.role,
        object_type="user",
        object_id=user.id,
        request=request,
    )
    result = _token_response(db, user, request)
    db.commit()
    response.set_cookie(
        "refresh_token",
        result.refresh_token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",
    )
    return result


@router.post("/refresh", response_model=TokenResponse, summary="Rotate the refresh token")
def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> TokenResponse:
    enforce_rate_limit(request, "auth:refresh", settings.rate_limit_sensitive_per_minute)
    rotated = auth_service.rotate_refresh_token(db, payload.refresh_token)
    if rotated is None:
        raise UnauthorizedError("Refresh token is invalid or expired.", code="refresh_invalid")
    _old_session, new_refresh_raw = rotated
    new_session = db.scalar(
        select(SessionToken).where(SessionToken.token_hash == hash_token(new_refresh_raw))
    )
    user = db.get(User, new_session.user_id)
    if user is None:  # pragma: no cover - cascade guarantees the user exists
        raise UnauthorizedError("Account no longer exists.", code="user_not_found")

    access = create_access_token(
        subject=str(user.id), role=user.role, token_id=f"s{new_session.id}"
    )
    audit_record(
        db,
        action="auth.refresh",
        user_id=user.id,
        actor_email=user.email,
        actor_role=user.role,
        object_type="user",
        object_id=user.id,
        request=request,
    )
    result = TokenResponse(
        access_token=access,
        refresh_token=new_refresh_raw,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )
    db.commit()
    response.set_cookie(
        "refresh_token",
        result.refresh_token,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth",
    )
    return result


@router.post("/logout", response_model=OkResponse, summary="Revoke the current session")
def logout(
    payload: RefreshRequest,
    db: DbSession,
    user: CurrentUser,
) -> OkResponse:
    auth_service.revoke_session(db, payload.refresh_token)
    db.commit()
    return OkResponse(message="Signed out.")


@router.post("/logout-all", response_model=OkResponse, summary="Revoke every session")
def logout_all(db: DbSession, user: CurrentUser) -> OkResponse:
    count = auth_service.revoke_all_sessions(db, user.id)
    db.commit()
    return OkResponse(message=f"Revoked {count} session(s).")


@router.post(
    "/verify-email/request",
    response_model=AuthMessage,
    summary="Request an email verification token",
)
def request_verification(
    payload: RequestVerifyEmailRequest,
    request: Request,
    db: DbSession,
) -> AuthMessage:
    enforce_rate_limit(request, "auth:sensitive", settings.rate_limit_sensitive_per_minute)
    email = str(payload.email) if payload.email else None
    user = auth_service.find_user_by_email(db, email) if email else None
    message = AuthMessage(
        message="If that account exists, a verification link has been issued."
    )
    if user is None or user.is_verified:
        # Never reveal whether an address exists.
        return message

    raw, _token = auth_service.mint_auth_token(db, user, TokenPurpose.email_verify)
    audit_record(
        db,
        action="auth.verification_requested",
        user_id=user.id,
        actor_email=user.email,
        object_type="user",
        object_id=user.id,
        request=request,
    )
    db.commit()
    if settings.dev_mode_enable_token_links:
        message.dev_link = _dev_link("verify-email", raw)
        message.dev_token = raw
    log_event(
        logger,
        20,
        "Email verification token issued",
        user_id=user.id,
        delivery="dev-mode" if settings.dev_mode_enable_token_links else "unset",
    )
    return message


@router.post("/verify-email/confirm", response_model=AuthMessage, summary="Confirm an email address")
def confirm_verification(payload: VerifyEmailRequest, db: DbSession) -> AuthMessage:
    user = auth_service.consume_auth_token(db, payload.token, TokenPurpose.email_verify)
    if user is None:
        raise ValidationFailedError(
            "Verification link is invalid, already used or expired.",
            code="token_invalid",
        )
    user.is_verified = True
    user.email_verified_at = utcnow()
    db.commit()
    return AuthMessage(message="Email address verified.")


@router.post(
    "/password/forgot",
    response_model=AuthMessage,
    summary="Start the password reset flow",
)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: DbSession) -> AuthMessage:
    enforce_rate_limit(request, "auth:sensitive", settings.rate_limit_sensitive_per_minute)
    message = AuthMessage(
        message="If that account exists, a password reset link has been issued."
    )
    user = auth_service.find_user_by_email(db, str(payload.email))
    if user is None:
        return message

    raw, _token = auth_service.mint_auth_token(db, user, TokenPurpose.password_reset)
    audit_record(
        db,
        action="auth.password_reset_requested",
        user_id=user.id,
        actor_email=user.email,
        object_type="user",
        object_id=user.id,
        request=request,
    )
    db.commit()
    if settings.dev_mode_enable_token_links:
        message.dev_link = _dev_link("reset-password", raw)
        message.dev_token = raw
    log_event(logger, 20, "Password reset token issued", user_id=user.id)
    return message


@router.post("/password/reset", response_model=AuthMessage, summary="Complete a password reset")
def reset_password(payload: ResetPasswordRequest, db: DbSession) -> AuthMessage:
    user = auth_service.consume_auth_token(db, payload.token, TokenPurpose.password_reset)
    if user is None:
        raise ValidationFailedError(
            "Reset link is invalid, already used or expired.", code="token_invalid"
        )
    auth_service.reset_password(db, user, payload.new_password)
    db.commit()
    return AuthMessage(message="Password updated. All sessions were signed out.")


@router.post("/password/change", response_model=AuthMessage, summary="Change your password")
def change_password(
    payload: ChangePasswordRequest,
    db: DbSession,
    user: CurrentUser,
) -> AuthMessage:
    if not verify_password(user.password_hash, payload.current_password):
        raise ValidationFailedError("Current password is incorrect.", code="invalid_password")
    user.password_hash = hash_password(payload.new_password)
    auth_service.revoke_all_sessions(db, user.id)
    db.commit()
    return AuthMessage(message="Password updated. All sessions were signed out.")


@router.get("/me", response_model=UserOut, summary="Current profile")
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut, summary="Update your profile")
def update_me(
    payload: ProfileUpdateRequest,
    db: DbSession,
    user: CurrentUser,
) -> User:
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.timezone is not None:
        # users.timezone and user_preferences.timezone are one value, two homes.
        user.timezone = payload.timezone
        auth_service.get_or_create_preferences(db, user).timezone = payload.timezone
    db.flush()
    db.commit()
    db.refresh(user)
    return user


@router.get("/me/preferences", response_model=UserPreferencesOut, summary="Your preferences")
def get_preferences(db: DbSession, user: CurrentUser) -> UserPreferencesOut:
    pref = auth_service.get_or_create_preferences(db, user)
    return UserPreferencesOut(
        default_reply_tone=pref.default_reply_tone,
        digest_enabled=pref.digest_enabled,
        timezone=pref.timezone,
        notification_channels=auth_service.parse_channels(pref.notification_channels),
    )


@router.put("/me/preferences", response_model=UserPreferencesOut, summary="Update preferences")
def update_preferences(
    payload: UserPreferencesUpdate,
    db: DbSession,
    user: CurrentUser,
) -> UserPreferencesOut:
    pref = auth_service.get_or_create_preferences(db, user)
    if payload.default_reply_tone is not None:
        pref.default_reply_tone = payload.default_reply_tone.value
    if payload.digest_enabled is not None:
        pref.digest_enabled = payload.digest_enabled
    if payload.timezone is not None:
        pref.timezone = payload.timezone
        user.timezone = payload.timezone
    if payload.notification_channels is not None:
        pref.notification_channels = auth_service.dump_channels(payload.notification_channels)
    db.flush()
    db.commit()
    return UserPreferencesOut(
        default_reply_tone=pref.default_reply_tone,
        digest_enabled=pref.digest_enabled,
        timezone=pref.timezone,
        notification_channels=auth_service.parse_channels(pref.notification_channels),
    )


@router.post("/dev/promote", response_model=UserOut, summary="Development-only role switch")
def dev_promote(db: DbSession, user: CurrentUser) -> User:
    """Only available when ``DEBUG=true`` and not in production.

    Lets a single developer account reach the admin surface without hand-editing
    the database. Always returns 404 outside development.
    """
    if settings.is_production or not settings.debug:
        raise NotFoundError("Endpoint not found.")
    user.role = UserRole.admin.value
    db.flush()
    db.commit()
    db.refresh(user)
    return user
