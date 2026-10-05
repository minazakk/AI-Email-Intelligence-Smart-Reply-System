"""Small shared helpers (pagination envelopes, time, hashing)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20
    pages: int = 0
    has_next: bool = False
    has_previous: bool = False


def build_page(items: list[T], total: int, page: int, page_size: int) -> Page[T]:
    pages = (total + page_size - 1) // page_size if page_size else 0
    return Page[T](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
        has_previous=page > 1,
    )


class OkResponse(BaseModel):
    ok: bool = Field(default=True)
    message: str | None = None


def dedupe_fingerprint(
    *,
    user_id: int,
    from_address: str,
    subject: str,
    received_at: datetime | None,
    body_text: str,
) -> str:
    stamp = received_at.isoformat() if received_at else ""
    raw = "|".join(
        [
            str(user_id),
            (from_address or "").strip().lower(),
            (subject or "").strip().lower(),
            stamp,
            (body_text or "").strip()[:2000],
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clamp(value: str | None, allowed: list[str] | tuple[str, ...], default: str | None = None):
    if value is None:
        return default
    normalised = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if normalised in allowed:
        return normalised
    return default


def payload_size(data: Any) -> int:
    try:
        import json

        return len(json.dumps(data, default=str).encode("utf-8"))
    except Exception:  # pragma: no cover
        return 0
