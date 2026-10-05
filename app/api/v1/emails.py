"""Email inbox, detail, thread, state and import endpoints."""

from __future__ import annotations

import csv
import io
from datetime import date as _date
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import AIProviderDep, CurrentUser, DbSession
from app.core.config import settings
from app.core.enums import EmailSource
from app.core.errors import (
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaError,
    ValidationFailedError,
)
from app.core.logging import get_logger, log_event
from app.core.rate_limit import enforce_rate_limit
from app.core.utils import utcnow
from app.models.email import Email, EmailThread
from app.schemas.common import OkResponse, Page, paginate
from app.schemas.email import (
    EmailAnalysisOut,
    EmailCreate,
    EmailDetail,
    EmailFilterParams,
    EmailListItem,
    EmailUpdateRequest,
    ExtractedEntityOut,
    ImportRowError,
    ImportSummary,
    StateUpdateRequest,
    ThreadDetail,
    ThreadListItem,
    ThreadMessage,
)
from app.services import email_ingest
from app.services.ai.pipeline import analyze_email
from app.services.audit_service import record as audit_record
from app.services.email_query import search_emails

logger = get_logger("app.emails")

router = APIRouter(tags=["Emails"])


# --- helpers ---------------------------------------------------------------

def get_owned_email(db, user_id: int, email_id: int) -> Email:
    """Object-level ownership check. Another user's row looks like a 404."""
    email = db.scalar(select(Email).where(Email.id == email_id, Email.user_id == user_id))
    if email is None:
        raise NotFoundError(f"Email {email_id} was not found.")
    return email


def get_owned_thread(db, user_id: int, thread_id: int) -> EmailThread:
    thread = db.scalar(
        select(EmailThread).where(EmailThread.id == thread_id, EmailThread.user_id == user_id)
    )
    if thread is None:
        raise NotFoundError(f"Thread {thread_id} was not found.")
    return thread


def is_urgent(analysis) -> bool:
    if analysis is None:
        return False
    return analysis.priority in {"high", "critical"} or analysis.sentiment == "urgent"


def to_list_item(email: Email) -> EmailListItem:
    analysis = email.analysis
    return EmailListItem(
        id=email.id,
        thread_id=email.thread_id,
        subject=email.subject,
        preview=email.preview,
        from_name=email.from_name,
        from_address=email.from_address,
        to=list(email.to or []),
        received_at=email.received_at,
        direction=email.direction,
        is_read=email.is_read,
        is_starred=email.is_starred,
        is_archived=email.is_archived,
        is_deleted=email.is_deleted,
        has_attachments=email.has_attachments,
        source=email.source,
        processing_status=email.processing_status,
        category=analysis.category if analysis else None,
        priority=analysis.priority if analysis else None,
        sentiment=analysis.sentiment if analysis else None,
        reply_required=analysis.reply_required if analysis else None,
        action_required=analysis.action_required if analysis else None,
        is_urgent=is_urgent(analysis),
    )


def to_detail(email: Email) -> EmailDetail:
    analysis = email.analysis
    base = to_list_item(email)
    return EmailDetail(
        **base.model_dump(),
        body_text=email.body_text,
        body_html=email.body_html,
        cc=list(email.cc or []),
        reply_to=email.reply_to,
        message_id=email.message_id,
        in_reply_to=email.in_reply_to,
        attachment_names=list(email.attachment_names or []),
        size_bytes=email.size_bytes,
        created_at=email.created_at,
        processed_at=email.processed_at,
        processing_error=email.processing_error,
        analysis=EmailAnalysisOut.model_validate(analysis) if analysis else None,
        extracted=[ExtractedEntityOut.model_validate(e) for e in (analysis.entities if analysis else [])],
    )


def _parse_day(value: str | None, field: str) -> _date | None:
    if not value:
        return None
    try:
        return _date.fromisoformat(value)
    except ValueError:
        raise ValidationFailedError(
            "Dates must be formatted YYYY-MM-DD.",
            details=[{"field": field, "message": "Expected an ISO date (YYYY-MM-DD)."}],
        ) from None


def _run_analysis(db, user, email: Email, provider, enabled: bool) -> None:
    if not enabled:
        return
    try:
        analyze_email(db, email, provider, user_timezone=user.timezone)
    except Exception as exc:  # noqa: BLE001 - failures are already persisted
        log_event(logger, 30, "AI analysis failed for email", email_id=email.id, error=str(exc)[:200])
    finally:
        db.commit()


# --- creation / import -----------------------------------------------------

@router.post(
    "/emails",
    response_model=EmailDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create an email manually",
)
def create_email(
    payload: EmailCreate,
    db: DbSession,
    user: CurrentUser,
    request: Request,
    provider: AIProviderDep,
) -> EmailDetail:
    enforce_rate_limit(request, "email:write", settings.rate_limit_sensitive_per_minute)
    result = email_ingest.create_email(db, user_id=user.id, payload=payload, source=EmailSource.manual)
    if result.duplicate:
        raise ValidationFailedError(
            "An identical email already exists in your inbox.", code="duplicate_email"
        )
    if result.email is None:  # pragma: no cover - defensive
        raise ValidationFailedError(result.error or "Could not store the email.")
    audit_record(
        db,
        action="email.create",
        user_id=user.id,
        actor_email=user.email,
        actor_role=user.role,
        object_type="email",
        object_id=result.email.id,
        request=request,
        context={"source": EmailSource.manual.value},
    )
    db.commit()
    _run_analysis(db, user, result.email, provider, payload.process_with_ai)
    db.refresh(result.email)
    return to_detail(result.email)


@router.post(
    "/emails/import/eml",
    response_model=ImportSummary,
    summary="Upload one or more .eml files",
)
def import_eml(
    db: DbSession,
    user: CurrentUser,
    request: Request,
    provider: AIProviderDep,
    files: Annotated[list[UploadFile], File(description="One or more .eml files")],
) -> ImportSummary:
    enforce_rate_limit(request, "email:import", settings.rate_limit_sensitive_per_minute)
    summary = ImportSummary(source=EmailSource.eml)
    if not files:
        raise ValidationFailedError("No file was uploaded.", details=[{"field": "files", "message": "required"}])

    for index, upload in enumerate(files, start=1):
        filename = (upload.filename or "message.eml").strip()
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in settings.allowed_upload_extensions:
            summary.failed += 1
            summary.errors.append(
                ImportRowError(
                    row=index, field="file", message=f"Extension '{ext}' is not allowed."
                )
            )
            continue

        raw = upload.file.read(settings.upload_max_bytes + 1)
        if len(raw) > settings.upload_max_bytes:
            raise PayloadTooLargeError(
                f"{filename} exceeds the {settings.upload_max_bytes} byte upload limit.",
                details={"limit_bytes": settings.upload_max_bytes, "size_bytes": len(raw)},
            )
        summary.received += 1
        try:
            payload = email_ingest.parse_eml(raw, filename=filename)
        except ValidationFailedError as exc:
            summary.failed += 1
            summary.errors.append(ImportRowError(row=index, field="file", message=exc.message))
            continue

        result = email_ingest.create_email(db, user_id=user.id, payload=payload, source=EmailSource.eml)
        if result.duplicate:
            summary.duplicates += 1
        elif result.email is not None:
            summary.created += 1
            summary.email_ids.append(result.email.id)
        else:
            summary.failed += 1
            summary.errors.append(
                ImportRowError(row=index, field="file", message=result.error or "Import failed.")
            )

    db.commit()
    for email_id in summary.email_ids:
        email = db.get(Email, email_id)
        if email is not None:
            _run_analysis(db, user, email, provider, True)
    log_event(
        logger,
        20,
        "EML import finished",
        user_id=user.id,
        created=summary.created,
        duplicates=summary.duplicates,
        failed=summary.failed,
    )
    return summary


@router.post(
    "/emails/import/dataset",
    response_model=ImportSummary,
    summary="Import a CSV or JSON dataset",
)
def import_dataset(
    db: DbSession,
    user: CurrentUser,
    request: Request,
    provider: AIProviderDep,
    file: Annotated[UploadFile, File(description="CSV or JSON dataset")],
    process_with_ai: Annotated[bool, Form()] = False,
) -> ImportSummary:
    enforce_rate_limit(request, "email:import", settings.rate_limit_sensitive_per_minute)
    filename = (file.filename or "").strip()
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext and ext not in settings.allowed_upload_extensions:
        raise UnsupportedMediaError(
            f"Extension '{ext}' is not allowed.",
            details={"allowed_extensions": sorted(settings.allowed_upload_extensions)},
        )

    content = file.file.read(settings.upload_max_bytes + 1)
    if len(content) > settings.upload_max_bytes:
        raise PayloadTooLargeError(
            f"File exceeds the {settings.upload_max_bytes} byte upload limit.",
            details={"limit_bytes": settings.upload_max_bytes, "size_bytes": len(content)},
        )
    rows = email_ingest.parse_dataset(
        filename=filename, content_type=file.content_type, content=content
    )
    source = EmailSource.csv if ext == ".csv" else EmailSource.json
    summary = email_ingest.run_dataset_import(
        db, user_id=user.id, rows=rows, source=source, filename=filename or None
    )
    audit_record(
        db,
        action="email.import",
        user_id=user.id,
        actor_email=user.email,
        actor_role=user.role,
        request=request,
        context={
            "source": source.value,
            "created": summary.created,
            "duplicates": summary.duplicates,
            "failed": summary.failed,
        },
    )
    db.commit()

    if process_with_ai:
        for email_id in summary.email_ids:
            email = db.get(Email, email_id)
            if email is not None:
                _run_analysis(db, user, email, provider, True)
    log_event(
        logger,
        20,
        "Dataset import finished",
        user_id=user.id,
        source=source.value,
        created=summary.created,
        duplicates=summary.duplicates,
        failed=summary.failed,
    )
    return summary


# --- listing / search ------------------------------------------------------

@router.get("/emails", summary="List and search emails", response_model=Page[EmailListItem])
def list_emails(
    db: DbSession,
    user: CurrentUser,
    q: str | None = None,
    from_address: str | None = None,
    subject: str | None = None,
    category: str | None = Query(default=None, description="Comma-separated category keys"),
    priority: str | None = None,
    sentiment: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    unread: bool | None = None,
    starred: bool | None = None,
    archived: bool | None = None,
    deleted: bool | None = None,
    urgent: bool | None = None,
    reply_required: bool | None = None,
    action_required: bool | None = None,
    direction: str | None = None,
    processing_status: str | None = None,
    customer: str | None = None,
    order_number: str | None = None,
    has_attachments: bool | None = None,
    thread_id: int | None = None,
    sort_by: str = "received_at",
    sort_order: str = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[EmailListItem]:
    params = EmailFilterParams(
        q=q,
        from_address=from_address,
        subject=subject,
        category=category or [],
        priority=priority or [],
        sentiment=sentiment or [],
        date_from=_parse_day(date_from, "date_from"),
        date_to=_parse_day(date_to, "date_to"),
        unread=unread,
        starred=starred,
        archived=archived,
        deleted=deleted,
        urgent=urgent,
        reply_required=reply_required,
        action_required=action_required,
        direction=direction,
        processing_status=processing_status,
        customer=customer,
        order_number=order_number,
        has_attachments=has_attachments,
        thread_id=thread_id,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    items, total = search_emails(db, user.id, params)
    return paginate([to_list_item(e) for e in items], total, page, page_size)


def _csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection in exported cells."""
    text = str(value or "")
    if text[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + text
    return text


@router.get("/emails/export.csv", summary="Export emails as CSV", response_class=Response)
def export_csv(
    db: DbSession,
    user: CurrentUser,
    q: str | None = None,
    category: str | None = None,
    page_size: int = Query(default=500, ge=1, le=1000),
) -> Response:
    params = EmailFilterParams(q=q, category=category or [], page=1, page_size=page_size)
    items, _total = search_emails(db, user.id, params)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["id", "received_at", "from_name", "from_address", "subject", "category", "priority", "sentiment", "preview"]
    )
    for email in items:
        analysis = email.analysis
        writer.writerow(
            [
                email.id,
                email.received_at.isoformat() if email.received_at else "",
                _csv_safe(email.from_name),
                _csv_safe(email.from_address),
                _csv_safe(email.subject),
                analysis.category if analysis else "",
                analysis.priority if analysis else "",
                analysis.sentiment if analysis else "",
                _csv_safe(email.preview),
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="emails-{utcnow().date().isoformat()}.csv"'
        },
    )


# --- detail / state --------------------------------------------------------

@router.get("/emails/{email_id}", response_model=EmailDetail, summary="Email detail")
def get_email(email_id: int, db: DbSession, user: CurrentUser) -> EmailDetail:
    return to_detail(get_owned_email(db, user.id, email_id))


@router.patch("/emails/{email_id}", response_model=EmailDetail, summary="Edit an email")
def update_email(
    email_id: int,
    payload: EmailUpdateRequest,
    db: DbSession,
    user: CurrentUser,
    request: Request,
) -> EmailDetail:
    email = get_owned_email(db, user.id, email_id)
    if payload.subject is not None:
        email.subject = payload.subject
    if payload.from_name is not None:
        email.from_name = payload.from_name
    if payload.body_text is not None:
        email.body_text = payload.body_text
        email.preview = email_ingest.make_preview(payload.body_text)
    db.flush()
    audit_record(
        db,
        action="email.update",
        user_id=user.id,
        actor_email=user.email,
        object_type="email",
        object_id=email.id,
        request=request,
    )
    db.commit()
    db.refresh(email)
    return to_detail(email)


@router.post("/emails/{email_id}/state", response_model=EmailDetail, summary="Read / star / archive")
def update_state(
    email_id: int,
    payload: StateUpdateRequest,
    db: DbSession,
    user: CurrentUser,
) -> EmailDetail:
    email = get_owned_email(db, user.id, email_id)
    if (
        payload.is_read is None
        and payload.is_starred is None
        and payload.is_archived is None
    ):
        raise ValidationFailedError("No state change was supplied.")
    if payload.is_read is not None:
        email.is_read = payload.is_read
    if payload.is_starred is not None:
        email.is_starred = payload.is_starred
    if payload.is_archived is not None:
        email.is_archived = payload.is_archived
    db.flush()
    _recompute_thread_flags(db, email)
    db.commit()
    db.refresh(email)
    return to_detail(email)


@router.delete("/emails/{email_id}", response_model=OkResponse, summary="Move to trash (soft delete)")
def delete_email(email_id: int, db: DbSession, user: CurrentUser, request: Request) -> OkResponse:
    email = get_owned_email(db, user.id, email_id)
    if not email.is_deleted:
        email.is_deleted = True
        email.deleted_at = utcnow()
        db.flush()
        _recompute_thread_flags(db, email)
        audit_record(
            db,
            action="email.delete",
            user_id=user.id,
            actor_email=user.email,
            object_type="email",
            object_id=email.id,
            request=request,
        )
        db.commit()
    return OkResponse(message="Email moved to trash.")


@router.post("/emails/{email_id}/restore", response_model=EmailDetail, summary="Restore from trash")
def restore_email(email_id: int, db: DbSession, user: CurrentUser) -> EmailDetail:
    email = get_owned_email(db, user.id, email_id)
    if email.is_deleted:
        email.is_deleted = False
        email.deleted_at = None
        db.flush()
        _recompute_thread_flags(db, email)
        db.commit()
        db.refresh(email)
    return to_detail(email)


def _recompute_thread_flags(db, email: Email) -> None:
    if email.thread_id is None:
        return
    thread = db.get(EmailThread, email.thread_id)
    if thread is not None:
        email_ingest.refresh_thread_flags(db, thread)


# --- threads ---------------------------------------------------------------

@router.get("/threads", summary="List threads", response_model=Page[ThreadListItem])
def list_threads(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_archived: bool = False,
) -> Page[ThreadListItem]:
    stmt = select(EmailThread).where(EmailThread.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(
            EmailThread.id.not_in(
                select(Email.thread_id).where(
                    Email.user_id == user.id,
                    Email.is_archived.is_(True),
                    Email.is_deleted.is_(False),
                )
            )
        )
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(
        db.scalars(
            stmt.order_by(EmailThread.last_message_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    items: list[ThreadListItem] = []
    for thread in rows:
        latest = db.scalar(
            select(Email)
            .where(Email.thread_id == thread.id, Email.is_deleted.is_(False))
            .order_by(Email.received_at.desc())
            .limit(1)
        )
        items.append(
            ThreadListItem(
                id=thread.id,
                thread_key=thread.thread_key,
                subject=thread.subject,
                message_count=thread.message_count,
                participant_count=thread.participant_count,
                last_message_at=thread.last_message_at,
                has_unread=thread.has_unread,
                is_starred=thread.is_starred,
                preview=latest.preview if latest else "",
            )
        )
    return paginate(items, total, page, page_size)


@router.get("/threads/{thread_id}", response_model=ThreadDetail, summary="Full thread")
def get_thread(thread_id: int, db: DbSession, user: CurrentUser) -> ThreadDetail:
    thread = get_owned_thread(db, user.id, thread_id)
    emails = list(
        db.scalars(
            select(Email)
            .where(Email.thread_id == thread.id, Email.is_deleted.is_(False))
            .order_by(Email.received_at.asc(), Email.id.asc())
        ).all()
    )
    messages = [
        ThreadMessage(
            id=email.id,
            subject=email.subject,
            from_name=email.from_name,
            from_address=email.from_address,
            to=list(email.to or []),
            received_at=email.received_at,
            direction=email.direction,
            body_text=email.body_text,
            is_read=email.is_read,
            processing_status=email.processing_status,
            category=email.analysis.category if email.analysis else None,
            summary_short=email.analysis.summary_short if email.analysis else None,
        )
        for email in emails
    ]
    return ThreadDetail(
        id=thread.id,
        thread_key=thread.thread_key,
        subject=thread.subject,
        last_message_at=thread.last_message_at,
        message_count=thread.message_count,
        messages=messages,
    )


# --- AI processing ---------------------------------------------------------

@router.post(
    "/emails/{email_id}/process",
    response_model=EmailDetail,
    summary="Run or retry AI analysis",
)
def process_email(
    email_id: int,
    db: DbSession,
    user: CurrentUser,
    provider: AIProviderDep,
    request: Request,
) -> EmailDetail:
    email = get_owned_email(db, user.id, email_id)
    if email.is_deleted:
        raise NotFoundError(f"Email {email_id} was not found.")
    try:
        analyze_email(db, email, provider, user_timezone=user.timezone)
    finally:
        db.commit()
    audit_record(
        db,
        action="email.process",
        user_id=user.id,
        actor_email=user.email,
        object_type="email",
        object_id=email.id,
        request=request,
    )
    db.commit()
    db.refresh(email)
    return to_detail(email)
