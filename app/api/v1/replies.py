"""Smart reply draft endpoints.

The system only ever stores drafts. Nothing is transmitted to the recipient.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import select

from app.api.deps import AIProviderDep, CurrentUser, DbSession
from app.api.v1.emails import get_owned_email
from app.core.enums import ReplyStatus, ReplyTone
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.logging import get_logger, log_event
from app.models.action import SuggestedReply
from app.schemas.action import (
    ReplyGenerateRequest,
    SuggestedReplyOut,
    SuggestedReplyUpdate,
)
from app.schemas.common import Page, paginate
from app.services.ai.pipeline import generate_reply
from app.services.audit_service import record as audit_record

logger = get_logger("app.replies")

router = APIRouter(prefix="/replies", tags=["Smart replies"])


def _owned_reply(db, user_id: int, reply_id: int) -> SuggestedReply:
    reply = db.scalar(
        select(SuggestedReply).where(SuggestedReply.id == reply_id, SuggestedReply.user_id == user_id)
    )
    if reply is None:
        raise NotFoundError(f"Reply {reply_id} was not found.")
    return reply


@router.get("", response_model=Page[SuggestedReplyOut], summary="List your draft replies")
def list_replies(
    db: DbSession,
    user: CurrentUser,
    email_id: int | None = None,
    reply_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[SuggestedReplyOut]:
    stmt = select(SuggestedReply).where(SuggestedReply.user_id == user.id)
    if email_id is not None:
        stmt = stmt.where(SuggestedReply.email_id == email_id)
    if reply_status:
        allowed = {s.value for s in ReplyStatus}
        if reply_status not in allowed:
            raise ValidationFailedError(
                f"Invalid status: {reply_status}. Allowed: {', '.join(sorted(allowed))}"
            )
        stmt = stmt.where(SuggestedReply.status == reply_status)

    from sqlalchemy import func

    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(
        db.scalars(
            stmt.order_by(SuggestedReply.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return paginate([SuggestedReplyOut.model_validate(r) for r in rows], total, page, page_size)


@router.post(
    "/email/{email_id}",
    response_model=SuggestedReplyOut,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a reply draft for an email",
)
def create_reply(
    email_id: int,
    payload: ReplyGenerateRequest,
    db: DbSession,
    user: CurrentUser,
    provider: AIProviderDep,
    request: Request,
) -> SuggestedReplyOut:
    email = get_owned_email(db, user.id, email_id)
    if email.is_deleted:
        raise NotFoundError(f"Email {email_id} was not found.")

    if not payload.regenerate:
        existing = db.scalar(
            select(SuggestedReply)
            .where(
                SuggestedReply.email_id == email.id,
                SuggestedReply.user_id == user.id,
                SuggestedReply.status == ReplyStatus.draft.value,
                SuggestedReply.tone == payload.tone.value,
            )
            .order_by(SuggestedReply.created_at.desc())
        )
        if existing is not None:
            return SuggestedReplyOut.model_validate(existing)

    if payload.instructions and payload.tone not in set(ReplyTone):
        raise ValidationFailedError("Unsupported reply tone.")

    try:
        reply = generate_reply(
            db,
            email,
            provider,
            tone=payload.tone,
            instructions=payload.instructions,
        )
    finally:
        db.commit()
    audit_record(
        db,
        action="reply.generate",
        user_id=user.id,
        actor_email=user.email,
        object_type="reply",
        object_id=reply.id,
        request=request,
        context={"tone": reply.tone, "email_id": email.id},
    )
    db.commit()
    db.refresh(reply)
    log_event(logger, 20, "Reply draft stored", reply_id=reply.id, email_id=email.id)
    return SuggestedReplyOut.model_validate(reply)


@router.get("/{reply_id}", response_model=SuggestedReplyOut, summary="Reply draft detail")
def get_reply(reply_id: int, db: DbSession, user: CurrentUser) -> SuggestedReplyOut:
    return SuggestedReplyOut.model_validate(_owned_reply(db, user.id, reply_id))


@router.patch("/{reply_id}", response_model=SuggestedReplyOut, summary="Edit or decide on a draft")
def update_reply(
    reply_id: int,
    payload: SuggestedReplyUpdate,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> SuggestedReplyOut:
    reply = _owned_reply(db, user.id, reply_id)

    if payload.body is not None:
        if not reply.original_body:
            reply.original_body = reply.body
        reply.body = payload.body
        reply.is_edited = True
    if payload.tone is not None:
        reply.tone = payload.tone.value
    if payload.status is not None:
        if payload.status not in {ReplyStatus.approved, ReplyStatus.rejected, ReplyStatus.draft}:
            raise ValidationFailedError("Unsupported reply status.")
        reply.status = payload.status.value
        from app.core.utils import utcnow

        reply.decided_at = utcnow()
        audit_record(
            db,
            action="reply.decide",
            user_id=user.id,
            actor_email=user.email,
            object_type="reply",
            object_id=reply.id,
            request=request,
            context={"status": reply.status},
        )
    db.flush()
    db.commit()
    db.refresh(reply)
    return SuggestedReplyOut.model_validate(reply)


@router.delete("/{reply_id}", response_model=dict, summary="Discard a draft")
def delete_reply(reply_id: int, db: DbSession, user: CurrentUser) -> dict:
    reply = _owned_reply(db, user.id, reply_id)
    db.delete(reply)
    db.commit()
    return {"ok": True, "message": "Draft discarded."}
