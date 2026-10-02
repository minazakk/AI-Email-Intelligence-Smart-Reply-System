"""Admin-only endpoints. Every route requires the ``admin`` role."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentAdmin, DbSession
from app.core.enums import UserRole
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.utils import utcnow
from app.models.action import ActionItem, SuggestedReply
from app.models.ai import AIErrorLog, AIUsageRecord, SystemConfig
from app.models.analysis import EmailAnalysis
from app.models.audit import AuditLog
from app.models.category import CategoryConfig
from app.models.email import Email
from app.models.user import User
from app.schemas.admin import (
    AdminStats,
    AdminUserList,
    AdminUserOut,
    AdminUserUpdate,
    AIErrorOut,
    AIUsageOut,
    AuditLogOut,
    CategoryConfigOut,
    CategoryConfigUpdate,
    CategoryConfigUpsert,
    SystemConfigOut,
    SystemConfigUpdate,
)
from app.schemas.common import paginate

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats", response_model=AdminStats, summary="System-wide statistics")
def stats(db: DbSession, admin: CurrentAdmin) -> AdminStats:
    users_total = int(db.scalar(select(func.count(User.id))) or 0)
    users_active = int(db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0)
    emails_total = int(db.scalar(select(func.count(Email.id))) or 0)
    emails_processed = int(
        db.scalar(select(func.count(Email.id)).where(Email.processing_status == "completed")) or 0
    )
    emails_failed = int(
        db.scalar(select(func.count(Email.id)).where(Email.processing_status == "failed")) or 0
    )
    analysis_total = int(db.scalar(select(func.count(EmailAnalysis.id))) or 0)
    replies_total = int(db.scalar(select(func.count(SuggestedReply.id))) or 0)
    action_items_total = int(db.scalar(select(func.count(ActionItem.id))) or 0)
    ai_calls_total = int(db.scalar(select(func.count(AIUsageRecord.id))) or 0)
    ai_calls_failed = int(
        db.scalar(select(func.count(AIUsageRecord.id)).where(AIUsageRecord.status != "success")) or 0
    )
    ai_tokens_total = int(
        db.scalar(select(func.coalesce(func.sum(AIUsageRecord.total_tokens), 0))) or 0
    )
    cutoff = utcnow() - timedelta(hours=24)
    ai_errors_last_24h = int(
        db.scalar(select(func.count(AIErrorLog.id)).where(AIErrorLog.created_at >= cutoff)) or 0
    )
    return AdminStats(
        users_total=users_total,
        users_active=users_active,
        emails_total=emails_total,
        emails_processed=emails_processed,
        emails_failed=emails_failed,
        analysis_total=analysis_total,
        replies_total=replies_total,
        action_items_total=action_items_total,
        ai_calls_total=ai_calls_total,
        ai_calls_failed=ai_calls_failed,
        ai_tokens_total=ai_tokens_total,
        ai_errors_last_24h=ai_errors_last_24h,
    )


@router.get("/users", response_model=AdminUserList, summary="List accounts")
def list_users(
    db: DbSession,
    admin: CurrentAdmin,
    q: str | None = None,
    role: str | None = None,
    active: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> AdminUserList:
    stmt = select(User)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(User.email).like(needle), func.lower(User.full_name).like(needle))
        )
    if role:
        allowed = {r.value for r in UserRole}
        if role not in allowed:
            raise ValidationFailedError(f"Invalid role: {role}. Allowed: {', '.join(sorted(allowed))}")
        stmt = stmt.where(User.role == role)
    if active is not None:
        stmt = stmt.where(User.is_active.is_(active))

    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    users = list(
        db.scalars(
            stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        ).all()
    )
    counts = dict(
        db.execute(
            select(Email.user_id, func.count(Email.id))
            .where(Email.user_id.in_([u.id for u in users] or [-1]))
            .group_by(Email.user_id)
        ).all()
    )
    items = [
        AdminUserOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            is_active=u.is_active,
            is_verified=u.is_verified,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
            email_count=int(counts.get(u.id, 0)),
        )
        for u in users
    ]
    page_result = paginate(items, total, page, page_size)
    return AdminUserList(
        items=page_result.items,
        total=page_result.total,
        page=page_result.page,
        page_size=page_result.page_size,
        pages=page_result.pages,
    )


@router.patch("/users/{user_id}", response_model=AdminUserOut, summary="Update an account")
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: DbSession,
    admin: CurrentAdmin,
) -> AdminUserOut:
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError(f"User {user_id} was not found.")
    if target.id == admin.id and payload.role is not None and payload.role != admin.role:
        raise ValidationFailedError("You cannot change your own role.")
    if payload.role is not None:
        target.role = payload.role.value
    if payload.is_active is not None:
        if target.id == admin.id and not payload.is_active:
            raise ValidationFailedError("You cannot deactivate your own account.")
        target.is_active = payload.is_active
    if payload.is_verified is not None:
        target.is_verified = payload.is_verified
        if payload.is_verified and target.email_verified_at is None:
            target.email_verified_at = utcnow()
    db.flush()
    db.commit()
    db.refresh(target)
    count = int(db.scalar(select(func.count(Email.id)).where(Email.user_id == target.id)) or 0)
    return AdminUserOut(
        id=target.id,
        email=target.email,
        full_name=target.full_name,
        role=target.role,
        is_active=target.is_active,
        is_verified=target.is_verified,
        created_at=target.created_at,
        last_login_at=target.last_login_at,
        email_count=count,
    )


@router.get("/ai/usage", response_model=list[AIUsageOut], summary="AI usage records")
def ai_usage(
    db: DbSession,
    admin: CurrentAdmin,
    purpose: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[AIUsageOut]:
    stmt = select(AIUsageRecord)
    if purpose:
        stmt = stmt.where(AIUsageRecord.purpose == purpose)
    rows = list(db.scalars(stmt.order_by(AIUsageRecord.created_at.desc()).limit(limit)).all())
    return [AIUsageOut.model_validate(r) for r in rows]


@router.get("/ai/errors", response_model=list[AIErrorOut], summary="AI processing errors")
def ai_errors(
    db: DbSession,
    admin: CurrentAdmin,
    error_code: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[AIErrorOut]:
    stmt = select(AIErrorLog)
    if error_code:
        stmt = stmt.where(AIErrorLog.error_code == error_code)
    rows = list(db.scalars(stmt.order_by(AIErrorLog.created_at.desc()).limit(limit)).all())
    return [AIErrorOut.model_validate(r) for r in rows]


@router.get("/audit-logs", response_model=list[AuditLogOut], summary="Audit trail")
def audit_logs(
    db: DbSession,
    admin: CurrentAdmin,
    action: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[AuditLogOut]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = list(db.scalars(stmt.order_by(AuditLog.created_at.desc()).limit(limit)).all())
    return [AuditLogOut.model_validate(r) for r in rows]


# --- categories ------------------------------------------------------------

@router.get("/categories", response_model=list[CategoryConfigOut], summary="Category catalogue")
def list_categories(db: DbSession, admin: CurrentAdmin) -> list[CategoryConfigOut]:
    rows = list(
        db.scalars(select(CategoryConfig).order_by(CategoryConfig.sort_order, CategoryConfig.key)).all()
    )
    if not rows:
        from app.services.category_service import seed_default_categories

        seed_default_categories(db)
        db.commit()
        rows = list(
            db.scalars(
                select(CategoryConfig).order_by(CategoryConfig.sort_order, CategoryConfig.key)
            ).all()
        )
    return [CategoryConfigOut.model_validate(r) for r in rows]


@router.post(
    "/categories",
    response_model=CategoryConfigOut,
    status_code=201,
    summary="Add a category",
)
def create_category(
    payload: CategoryConfigUpsert, db: DbSession, admin: CurrentAdmin
) -> CategoryConfigOut:
    existing = db.scalar(select(CategoryConfig).where(CategoryConfig.key == payload.key))
    if existing is not None:
        raise ConflictError(f"Category '{payload.key}' already exists.")
    row = CategoryConfig(
        key=payload.key,
        label=payload.label,
        description=payload.description,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(row)
    db.flush()
    db.commit()
    db.refresh(row)
    return CategoryConfigOut.model_validate(row)


@router.patch("/categories/{category_id}", response_model=CategoryConfigOut, summary="Edit a category")
def update_category(
    category_id: int,
    payload: CategoryConfigUpdate,
    db: DbSession,
    admin: CurrentAdmin,
) -> CategoryConfigOut:
    row = db.get(CategoryConfig, category_id)
    if row is None:
        raise NotFoundError(f"Category {category_id} was not found.")
    if payload.label is not None:
        row.label = payload.label
    if payload.description is not None:
        row.description = payload.description
    if payload.is_active is not None:
        row.is_active = payload.is_active
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    db.flush()
    db.commit()
    db.refresh(row)
    return CategoryConfigOut.model_validate(row)


# --- system configuration --------------------------------------------------

@router.get("/config", response_model=list[SystemConfigOut], summary="System configuration")
def list_config(db: DbSession, admin: CurrentAdmin) -> list[SystemConfigOut]:
    rows = list(db.scalars(select(SystemConfig).order_by(SystemConfig.key)).all())
    return [
        SystemConfigOut(
            key=r.key,
            value=r.value,
            description=r.description,
            updated_at=r.updated_at,
            updated_by=r.updated_by,
        )
        for r in rows
    ]


@router.put("/config/{key}", response_model=SystemConfigOut, summary="Set a configuration value")
def set_config(
    key: str,
    payload: SystemConfigUpdate,
    db: DbSession,
    admin: CurrentAdmin,
) -> SystemConfigOut:
    if not key.strip() or len(key) > 80:
        raise ValidationFailedError("Configuration key must be 1-80 characters.")
    row = db.get(SystemConfig, key.strip())
    if row is None:
        row = SystemConfig(
            key=key.strip(),
            value=payload.value,
            description=payload.description,
            updated_by=admin.id,
        )
        db.add(row)
    else:
        row.value = payload.value
        row.description = payload.description
        row.updated_by = admin.id
    db.flush()
    db.commit()
    db.refresh(row)
    return SystemConfigOut(
        key=row.key,
        value=row.value,
        description=row.description,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )
