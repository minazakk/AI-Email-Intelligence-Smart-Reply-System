"""AI inbox assistant conversations."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import select

from app.api.deps import AIProviderDep, CurrentUser, DbSession
from app.core.config import settings
from app.core.errors import NotFoundError
from app.core.rate_limit import enforce_rate_limit
from app.core.utils import utcnow
from app.models.assistant import AssistantConversation, AssistantMessage
from app.schemas.assistant import (
    AssistantAnswer,
    AssistantConversationCreate,
    AssistantConversationOut,
    AssistantMessageOut,
    AssistantQuery,
    AssistantResult,
)
from app.schemas.common import Page, paginate
from app.services import assistant_service
from app.services.audit_service import record as audit_record

router = APIRouter(prefix="/assistant", tags=["AI inbox assistant"])


def _owned_conversation(db, user_id: int, conversation_id: int) -> AssistantConversation:
    conversation = db.scalar(
        select(AssistantConversation).where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.user_id == user_id,
        )
    )
    if conversation is None:
        raise NotFoundError(f"Conversation {conversation_id} was not found.")
    return conversation


def _to_conversation_out(conversation: AssistantConversation) -> AssistantConversationOut:
    return AssistantConversationOut(
        id=conversation.id,
        title=conversation.title,
        message_count=conversation.message_count,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        messages=[AssistantMessageOut.model_validate(m) for m in conversation.messages],
    )


@router.get("/conversations", response_model=Page[AssistantConversationOut], summary="List conversations")
def list_conversations(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[AssistantConversationOut]:
    stmt = select(AssistantConversation).where(AssistantConversation.user_id == user.id)
    from sqlalchemy import func

    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(
        db.scalars(
            stmt.order_by(AssistantConversation.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return paginate([_to_conversation_out(c) for c in rows], total, page, page_size)


@router.post(
    "/conversations",
    response_model=AssistantConversationOut,
    status_code=status.HTTP_201_CREATED,
    summary="Start a conversation",
)
def create_conversation(
    payload: AssistantConversationCreate,
    db: DbSession,
    user: CurrentUser,
) -> AssistantConversationOut:
    conversation = AssistantConversation(user_id=user.id, title=payload.title)
    db.add(conversation)
    db.flush()
    db.commit()
    db.refresh(conversation)
    return _to_conversation_out(conversation)


@router.get(
    "/conversations/{conversation_id}",
    response_model=AssistantConversationOut,
    summary="Conversation with messages",
)
def get_conversation(
    conversation_id: int, db: DbSession, user: CurrentUser
) -> AssistantConversationOut:
    return _to_conversation_out(_owned_conversation(db, user.id, conversation_id))


@router.delete("/conversations/{conversation_id}", summary="Delete a conversation")
def delete_conversation(
    conversation_id: int, db: DbSession, user: CurrentUser
) -> dict:
    conversation = _owned_conversation(db, user.id, conversation_id)
    db.delete(conversation)
    db.commit()
    return {"ok": True, "message": "Conversation deleted."}


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AssistantAnswer,
    summary="Ask a question about your inbox",
)
def ask(
    conversation_id: int,
    payload: AssistantQuery,
    db: DbSession,
    user: CurrentUser,
    provider: AIProviderDep,
    request: Request,
) -> AssistantAnswer:
    enforce_rate_limit(request, "assistant", settings.rate_limit_sensitive_per_minute)
    conversation = _owned_conversation(db, user.id, conversation_id)

    result = assistant_service.answer_question(
        db, user.id, provider, payload.query, limit=settings.ai_context_email_limit
    )

    user_message = AssistantMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        role="user",
        content=payload.query,
        citations=[r["id"] for r in result["results"]],
    )
    db.add(user_message)
    db.flush()

    assistant_message = AssistantMessage(
        conversation_id=conversation.id,
        user_id=user.id,
        role="assistant",
        content=result["answer"],
        filters=result["applied_filters"],
        citations=[r["id"] for r in result["results"]],
    )
    db.add(assistant_message)
    conversation.message_count += 2
    conversation.last_message_at = utcnow()
    if conversation.title in {"New conversation", ""} and payload.query.strip():
        conversation.title = payload.query.strip()[:80]

    audit_record(
        db,
        action="assistant.ask",
        user_id=user.id,
        actor_email=user.email,
        actor_role=user.role,
        object_type="assistant_conversation",
        object_id=conversation.id,
        request=request,
        context={
            "matches": result["total_matches"],
            "deterministic": result["deterministic"],
            "filters": result["applied_filters"],
        },
    )
    db.commit()
    db.refresh(assistant_message)

    return AssistantAnswer(
        conversation_id=conversation.id,
        message=AssistantMessageOut.model_validate(assistant_message),
        applied_filters=result["applied_filters"],
        total_matches=result["total_matches"],
        results=[AssistantResult(**r) for r in result["results"]],
        answer=result["answer"],
        deterministic=result["deterministic"],
    )


@router.post("/query", response_model=AssistantAnswer, summary="One-off inbox question")
def query_once(
    payload: AssistantQuery,
    db: DbSession,
    user: CurrentUser,
    provider: AIProviderDep,
    request: Request,
) -> AssistantAnswer:
    enforce_rate_limit(request, "assistant", settings.rate_limit_sensitive_per_minute)
    result = assistant_service.answer_question(
        db, user.id, provider, payload.query, limit=settings.ai_context_email_limit
    )
    audit_record(
        db,
        action="assistant.query",
        user_id=user.id,
        actor_email=user.email,
        actor_role=user.role,
        request=request,
        context={"matches": result["total_matches"], "deterministic": result["deterministic"]},
    )
    db.commit()

    return AssistantAnswer(
        conversation_id=None,
        message=AssistantMessageOut(
            id=0,
            role="assistant",
            content=result["answer"],
            filters=result["applied_filters"],
            citations=[r["id"] for r in result["results"]],
            created_at=utcnow(),
        ),
        applied_filters=result["applied_filters"],
        total_matches=result["total_matches"],
        results=[AssistantResult(**r) for r in result["results"]],
        answer=result["answer"],
        deterministic=result["deterministic"],
    )
