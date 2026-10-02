"""Password hashing, token minting and verification helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import UnauthorizedError

# Argon2id: memory hard, resistant to GPU cracking. One global hasher keeps the
# parameters consistent across the application.
_hasher = PasswordHasher(time_cost=2, memory_cost=64 * 1024, parallelism=2)

JWT_ALGORITHM = "HS256"


# --- passwords -------------------------------------------------------------

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception:  # pragma: no cover - defensive, never crash on a bad hash
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:  # pragma: no cover
        return False


def validate_password_strength(password: str) -> list[str]:
    """Return a list of human-readable problems; empty means acceptable."""
    problems: list[str] = []
    min_len = settings.password_min_length
    if len(password) < min_len:
        problems.append(f"Password must be at least {min_len} characters long.")
    if len(password) > 256:
        problems.append("Password must be at most 256 characters long.")
    if password.lower() in {"password", "12345678", "qwertyui", "letmein!"}:
        problems.append("Password is too common.")
    if password.isspace() or not password.strip():
        problems.append("Password must not be blank.")
    return problems


# --- opaque tokens (verification / reset / sessions) -----------------------

def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """One-way hash so a leaked database row cannot be replayed as a token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)


# --- JWT access tokens -----------------------------------------------------

def create_access_token(
    *,
    subject: str,
    role: str,
    token_id: str,
    expires_minutes: int | None = None,
) -> str:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=expires_minutes or settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "role": role,
        "jti": token_id,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Access token is invalid.", code="token_invalid") from exc
    if payload.get("type") != "access":
        raise UnauthorizedError("Access token is invalid.", code="token_invalid")
    return payload
