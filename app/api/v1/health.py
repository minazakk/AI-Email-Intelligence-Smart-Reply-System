"""Liveness and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness probe (no database access)")
def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "ai_provider": settings.ai_provider,
    }


@router.get("/health/ready", summary="Readiness probe (checks the database)")
def readiness(db: DbSession, response: Response) -> dict:
    try:
        db.execute(text("SELECT 1"))
        database = "up"
        ready = True
    except Exception:  # pragma: no cover - exercised when the DB is down
        db.rollback()
        database = "down"
        ready = False
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if ready else "not_ready",
        "database": database,
        "ai_provider": settings.ai_provider,
    }
