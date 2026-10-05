"""Shared FastAPI dependencies: authentication, authorization, AI provider."""

from __future__ import annotations

import re
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import UserRole
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import SessionToken, User
from app.services.ai.base import AIProvider
from app.services.ai.factory import get_ai_provider

bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]

# Access tokens are minted with ``jti = "s<session id>"`` so a revoked session
# kills every access token issued for it, not just the refresh token.
_SESSION_JTI = re.compile(r"^s(\d+)$")


def _require_live_session(db: Session, payload: dict, user_id: int) -> None:
    match = _SESSION_JTI.match(str(payload.get("jti") or ""))
    if match is None:
        raise UnauthorizedError("Access token is invalid.", code="token_invalid")
    session = db.get(SessionToken, int(match.group(1)))
    if session is None or session.user_id != user_id:
        raise UnauthorizedError("Session is no longer valid.", code="session_revoked")
    if not session.is_active:
        raise UnauthorizedError("Session has been revoked.", code="session_revoked")


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Authentication credentials were not provided.")
    payload = decode_access_token(credentials.credentials)
    user_id_raw = payload.get("sub")
    if not user_id_raw:
        raise UnauthorizedError("Access token is invalid.", code="token_invalid")
    try:
        user_id = int(user_id_raw)
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("Access token is invalid.", code="token_invalid") from exc

    user = db.get(User, user_id)
    if user is None:
        raise UnauthorizedError("Account no longer exists.", code="user_not_found")
    if not user.is_active:
        raise ForbiddenError("Account is deactivated.", code="account_inactive")
    _require_live_session(db, payload, user_id)
    return user


def get_current_user_optional(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User | None:
    if credentials is None or not credentials.credentials:
        return None
    try:
        return get_current_user(db, credentials)
    except (UnauthorizedError, ForbiddenError):
        return None


def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.admin.value:
        raise ForbiddenError("Administrator role is required.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
AIProviderDep = Annotated[AIProvider, Depends(get_ai_provider)]


def client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def user_agent(request: Request) -> str | None:
    value = request.headers.get("user-agent")
    return value[:256] if value else None


__all__ = [
    "AIProviderDep",
    "CurrentAdmin",
    "CurrentUser",
    "DbSession",
    "OptionalUser",
    "bearer_scheme",
    "client_ip",
    "get_current_admin",
    "get_current_user",
    "get_current_user_optional",
    "get_db",
    "user_agent",
    "Generator",
]
