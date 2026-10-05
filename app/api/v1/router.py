"""Version 1 API router aggregation."""

from fastapi import APIRouter

from app.api.v1 import (
    actions,
    admin,
    assistant,
    auth,
    dashboard,
    emails,
    health,
    notifications,
    replies,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(emails.router)
api_router.include_router(actions.router)
api_router.include_router(replies.router)
api_router.include_router(notifications.router)
api_router.include_router(assistant.router)
api_router.include_router(dashboard.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]
