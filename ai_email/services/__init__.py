"""Service layer: analysis, smart reply, assistant and search intent."""

from .analysis_service import analyze_email, analyze_emails
from .assistant_service import answer_inbox_question
from .reply_service import generate_smart_reply
from .search_intent_service import parse_search_query

__all__ = [
    "analyze_email",
    "analyze_emails",
    "answer_inbox_question",
    "generate_smart_reply",
    "parse_search_query",
]
