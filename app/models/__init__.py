"""Model package. Importing this module registers every table on ``Base``."""

from app.models.action import ActionItem, SuggestedReply
from app.models.ai import AIErrorLog, AIUsageRecord, SystemConfig
from app.models.analysis import EmailAnalysis, ExtractedEntity
from app.models.assistant import AssistantConversation, AssistantMessage
from app.models.audit import AuditLog
from app.models.category import CategoryConfig
from app.models.email import Email, EmailThread
from app.models.notification import Notification, NotificationPreference
from app.models.user import AuthToken, SessionToken, User, UserPreference

__all__ = [
    "ActionItem",
    "AIErrorLog",
    "AIUsageRecord",
    "AssistantConversation",
    "AssistantMessage",
    "AuditLog",
    "AuthToken",
    "CategoryConfig",
    "Email",
    "EmailAnalysis",
    "EmailThread",
    "ExtractedEntity",
    "Notification",
    "NotificationPreference",
    "SessionToken",
    "SuggestedReply",
    "SystemConfig",
    "User",
    "UserPreference",
]
