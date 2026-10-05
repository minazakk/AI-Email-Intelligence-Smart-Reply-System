"""Action items and deadline endpoints."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.enums import ActionStatus, NotificationType
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.utils import utcnow
from app.models.action import ActionItem
from app.models.email import Email
from app.schemas.action import ActionItemOut, ActionItemUpdate, DeadlineOut
from app.schemas.common import OkResponse, Page, paginate
from app.services.notification_service import notify

router = APIRouter(prefix="/actions", tags=["Actions and deadlines"])


def get_owned_action(db, user_id: int, action_id: int) -> ActionItem:
    item = db.scalar(
        select(ActionItem).where(ActionItem.id == action_id, ActionItem.user_id == user_id)
    )
    if item is None:
        raise NotFoundError(f"Action item {action_id} was not found.")
    return item


def _to_out(item: ActionItem, subject: str | None = None) -> ActionItemOut:
    return ActionItemOut(
        id=item.id,
        email_id=item.email_id,
        description=item.description,
        owner=item.owner,
        due_text=item.due_text,
        due_date=item.due_date,
        due_at=item.due_at,
        due_date_estimated=item.due_date_estimated,
        status=item.status,
        priority=item.priority,
        completed_at=item.completed_at,
        created_at=item.created_at,
        email_subject=subject,
    )


@router.get("", response_model=Page[ActionItemOut], summary="List your action items")
def list_actions(
    db: DbSession,
    user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    email_id: int | None = None,
    overdue: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[ActionItemOut]:
    stmt = select(ActionItem, Email.subject).join(Email, Email.id == ActionItem.email_id).where(
        ActionItem.user_id == user.id
    )
    if status_filter:
        allowed = {s.value for s in ActionStatus}
        values = [v.strip() for v in status_filter.split(",") if v.strip()]
        bad = [v for v in values if v not in allowed]
        if bad:
            raise ValidationFailedError(
                f"Invalid status: {', '.join(bad)}. Allowed: {', '.join(sorted(allowed))}"
            )
        stmt = stmt.where(ActionItem.status.in_(values))
    if email_id is not None:
        stmt = stmt.where(ActionItem.email_id == email_id)
    if overdue is not None:
        today = utcnow().date()
        if overdue:
            stmt = stmt.where(
                ActionItem.due_date.is_not(None),
                ActionItem.due_date < today,
                ActionItem.status.in_(["pending", "in_progress"]),
            )
        else:
            stmt = stmt.where(
                ActionItem.status.in_(["pending", "in_progress"]),
            )

    from sqlalchemy import func as _func  # retained for subquery counting

    total = int(db.scalar(select(_func.count()).select_from(stmt.subquery())) or 0)
    rows = (
        db.execute(
            stmt.order_by(ActionItem.due_date.asc().nullslast(), ActionItem.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .all()
    )
    items = [_to_out(item, subject) for item, subject in rows]
    return paginate(items, total, page, page_size)


@router.patch("/{action_id}", response_model=ActionItemOut, summary="Update an action item")
def update_action(
    action_id: int,
    payload: ActionItemUpdate,
    db: DbSession,
    user: CurrentUser,
) -> ActionItemOut:
    item = get_owned_action(db, user.id, action_id)
    if payload.description is not None:
        item.description = payload.description
    if payload.owner is not None:
        item.owner = payload.owner
    if payload.due_text is not None:
        item.due_text = payload.due_text
    if payload.due_date is not None:
        item.due_date = payload.due_date
        item.due_date_estimated = True
    if payload.status is not None:
        if payload.status == ActionStatus.completed and item.status != ActionStatus.completed:
            item.completed_at = utcnow()
        if payload.status != ActionStatus.completed:
            item.completed_at = None
        if payload.status == ActionStatus.dismissed:
            item.dismissed_at = utcnow()
        item.status = payload.status.value
    db.flush()
    db.commit()
    db.refresh(item)
    subject = db.scalar(select(Email.subject).where(Email.id == item.email_id))
    return _to_out(item, subject)


@router.post("/{action_id}/complete", response_model=ActionItemOut, summary="Mark as completed")
def complete_action(action_id: int, db: DbSession, user: CurrentUser) -> ActionItemOut:
    item = get_owned_action(db, user.id, action_id)
    if item.status not in {ActionStatus.completed.value, ActionStatus.dismissed.value}:
        item.status = ActionStatus.completed.value
        item.completed_at = utcnow()
        db.flush()
        db.commit()
        db.refresh(item)
    subject = db.scalar(select(Email.subject).where(Email.id == item.email_id))
    return _to_out(item, subject)


@router.delete("/{action_id}", response_model=OkResponse, summary="Dismiss an action item")
def dismiss_action(action_id: int, db: DbSession, user: CurrentUser) -> OkResponse:
    item = get_owned_action(db, user.id, action_id)
    if item.status != ActionStatus.dismissed.value:
        item.status = ActionStatus.dismissed.value
        item.dismissed_at = utcnow()
        db.flush()
        db.commit()
    return OkResponse(message="Action item dismissed.")


@router.get(
    "/deadlines/upcoming",
    response_model=list[DeadlineOut],
    summary="Deadlines inside a horizon (default 14 days)",
)
@router.get(
    "/deadlines",
    response_model=list[DeadlineOut],
    summary="Deadlines inside a horizon (alias)",
)
def upcoming_deadlines(
    db: DbSession,
    user: CurrentUser,
    horizon_days: int = Query(default=14, ge=0, le=365),
) -> list[DeadlineOut]:
    today = utcnow().date()
    horizon = today + timedelta(days=horizon_days)
    rows = db.execute(
        select(ActionItem)
        .where(
            ActionItem.user_id == user.id,
            ActionItem.status.in_(["pending", "in_progress"]),
            ActionItem.due_date.is_not(None),
            ActionItem.due_date <= horizon,
        )
        .order_by(ActionItem.due_date.asc())
    ).scalars()

    output: list[DeadlineOut] = []
    for item in rows:
        days_until = (item.due_date - today).days if item.due_date else None
        if days_until is not None and days_until <= 1:
            notify(
                db,
                user_id=user.id,
                ntype=NotificationType.deadline_upcoming,
                title=f"Deadline approaching: {item.description[:120]}",
                body=f"Due {item.due_date.isoformat()}.",
                severity="warning",
                email_id=item.email_id,
                action_id=item.id,
            )
        output.append(
            DeadlineOut(
                action_id=item.id,
                email_id=item.email_id,
                description=item.description,
                due_date=item.due_date,
                due_text=item.due_text,
                status=item.status,
                days_until=days_until,
                overdue=bool(days_until is not None and days_until < 0),
            )
        )
    db.commit()
    return output
