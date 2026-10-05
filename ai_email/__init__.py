"""AI Email Intelligence & Smart Reply System - standalone AI module.

Import and use this package without a backend, database or web server::

    from ai_email import analyze_email, generate_smart_reply

    analysis = analyze_email({"subject": "Order issue", "sender": "a@b.com", "body": "..."})
    print(analysis.model_dump_json(indent=2))
"""

from __future__ import annotations

from .config import Settings, get_settings, reset_settings, set_settings
from .date_normalizer import normalize_deadline, normalize_deadlines
from .email_parser import (
    NormalizedEmail,
    normalize_email,
    normalize_thread,
    parse_email_text,
    parse_eml,
)
from .exceptions import (
    AIEmailError,
    ConfigurationError,
    InputValidationError,
    PromptTemplateError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SchemaValidationError,
)
from .schemas import (
    ActionItem,
    ActionStatus,
    AssistantAnswer,
    DeadlineMention,
    EmailAnalysis,
    EmailCategory,
    EmailInput,
    EmailSearchIntent,
    ExtractedInformation,
    NormalizedDeadline,
    PriorityLevel,
    ProcessingMetadata,
    ProcessingStatus,
    ReadState,
    ReplyTone,
    ResolutionKind,
    Sentiment,
    SmartReplyResult,
    ThreadMessage,
)
from .services import (
    analyze_email,
    analyze_emails,
    answer_inbox_question,
    generate_smart_reply,
    parse_search_query,
)

__version__ = "1.0.0"

__all__ = [
    "AIEmailError",
    "ActionItem",
    "ActionStatus",
    "AssistantAnswer",
    "ConfigurationError",
    "DeadlineMention",
    "EmailAnalysis",
    "EmailCategory",
    "EmailInput",
    "EmailSearchIntent",
    "ExtractedInformation",
    "InputValidationError",
    "NormalizedDeadline",
    "NormalizedEmail",
    "PriorityLevel",
    "ProcessingMetadata",
    "ProcessingStatus",
    "PromptTemplateError",
    "ProviderAuthError",
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "ReadState",
    "ReplyTone",
    "ResolutionKind",
    "SchemaValidationError",
    "Sentiment",
    "Settings",
    "SmartReplyResult",
    "ThreadMessage",
    "__version__",
    "analyze_email",
    "analyze_emails",
    "answer_inbox_question",
    "generate_smart_reply",
    "get_settings",
    "normalize_deadline",
    "normalize_deadlines",
    "normalize_email",
    "normalize_thread",
    "parse_email_text",
    "parse_eml",
    "parse_search_query",
    "reset_settings",
    "set_settings",
]
