"""Audit logging for sensitive actions.

Never pass passwords, tokens, API keys or full email bodies into ``context``.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import redact
from app.models.audit import AuditLog


def client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.client.host if request.client else None


def record(
    db: Session,
    *,
    action: str,
    user_id: int | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
    object_type: str | None = None,
    object_id: str | int | None = None,
    outcome: str = "success",
    request: Request | None = None,
    context: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        actor_email=actor_email,
        actor_role=actor_role,
        action=action,
        object_type=object_type,
        object_id=str(object_id) if object_id is not None else None,
        outcome=outcome,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent", "")[:256] if request else None),
        context=redact(context or {}),
    )
    db.add(entry)
    db.flush()
    return entry


def recent(db: Session, limit: int = 50) -> list[AuditLog]:
    return list(
        db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    )


__all__ = ["client_ip", "record", "recent"]
