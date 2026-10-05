"""Authentication helpers: session issuance, verification and reset tokens."""

from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import TokenPurpose, UserRole
from app.core.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.core.utils import utcnow
from app.models.user import AuthToken, SessionToken, User, UserPreference


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str = "",
    timezone: str = "UTC",
    role: UserRole = UserRole.user,
    verified: bool = False,
) -> User:
    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        full_name=(full_name or "").strip(),
        role=role.value,
        timezone=timezone or "UTC",
        is_verified=verified,
        email_verified_at=utcnow() if verified else None,
    )
    db.add(user)
    db.flush()
    db.add(UserPreference(user_id=user.id, timezone=user.timezone))
    db.flush()
    return user


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = find_user_by_email(db, email)
    if user is None:
        # Constant-ish work factor so a missing account is not distinguishable.
        verify_password("$argon2id$v=19$m=65536,t=2,p=2$ZHVtbXk=$dummy", password)
        return None
    if not verify_password(user.password_hash, password):
        return None
    if not user.is_active:
        return None
    return user


def issue_tokens(db: Session, user: User, *, request=None) -> dict:
    """Create a JWT access token plus a server-side revocable refresh token."""
    refresh_raw = generate_token(48)
    session = SessionToken(
        user_id=user.id,
        token_hash=hash_token(refresh_raw),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
        user_agent=(request.headers.get("user-agent", "")[:256] if request else None),
    )
    db.add(session)
    db.flush()
    access_raw = create_access_token(
        subject=str(user.id), role=user.role, token_id=f"s{session.id}"
    )
    user.last_login_at = utcnow()
    return {
        "access_token": access_raw,
        "refresh_token": refresh_raw,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


def rotate_refresh_token(db: Session, refresh_token: str) -> tuple[SessionToken, str] | None:
    """Validate and rotate a refresh token.

    Returns ``(revoked_session, new_raw_refresh_token)`` or ``None`` when the
    token is unknown, expired or belongs to a deactivated account.
    """
    token_hash = hash_token(refresh_token)
    session = db.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash))
    if session is None or not session.is_active:
        return None
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None
    session.revoked_at = utcnow()
    new_raw = generate_token(48)
    new_session = SessionToken(
        user_id=user.id,
        token_hash=hash_token(new_raw),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
        user_agent=session.user_agent,
    )
    db.add(new_session)
    db.flush()
    return session, new_raw


def revoke_session(db: Session, refresh_token: str) -> bool:
    token_hash = hash_token(refresh_token)
    session = db.scalar(select(SessionToken).where(SessionToken.token_hash == token_hash))
    if session is None:
        return False
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        db.flush()
    return True


def revoke_all_sessions(db: Session, user_id: int) -> int:
    result = db.execute(
        update(SessionToken)
        .where(SessionToken.user_id == user_id, SessionToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.flush()
    return int(result.rowcount or 0)


def access_token_for_session(db: Session, user: User, session: SessionToken) -> str:
    return create_access_token(
        subject=str(user.id), role=user.role, token_id=f"s{session.id}"
    )


# --- verification / reset tokens ------------------------------------------

def mint_auth_token(db: Session, user: User, purpose: TokenPurpose) -> tuple[str, AuthToken]:
    raw = generate_token(32)
    minutes = (
        settings.verification_token_expire_minutes
        if purpose == TokenPurpose.email_verify
        else settings.reset_token_expire_minutes
    )
    token = AuthToken.new(
        user_id=user.id,
        token_hash=hash_token(raw),
        purpose=purpose,
        expires_at=utcnow() + timedelta(minutes=minutes),
    )
    db.add(token)
    db.flush()
    return raw, token


def consume_auth_token(db: Session, raw_token: str, purpose: TokenPurpose) -> User | None:
    """Single-use: the token is marked used inside the same transaction."""
    token_hash = hash_token(raw_token)
    token = db.scalar(select(AuthToken).where(AuthToken.token_hash == token_hash))
    if token is None or token.purpose != purpose.value or not token.is_usable():
        return None
    token.used_at = utcnow()
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        return None
    db.flush()
    return user


def reset_password(db: Session, user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    revoke_all_sessions(db, user.id)
    db.flush()


def get_or_create_preferences(db: Session, user: User) -> UserPreference:
    pref = user.preferences
    if pref is None:
        pref = UserPreference(user_id=user.id, timezone=user.timezone)
        db.add(pref)
        db.flush()
    return pref


def parse_channels(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def dump_channels(channels: dict) -> str:
    return json.dumps(channels, ensure_ascii=False)


__all__ = [
    "access_token_for_session",
    "authenticate",
    "consume_auth_token",
    "create_user",
    "dump_channels",
    "find_user_by_email",
    "get_or_create_preferences",
    "issue_tokens",
    "mint_auth_token",
    "parse_channels",
    "reset_password",
    "revoke_all_sessions",
    "revoke_session",
    "rotate_refresh_token",
]
