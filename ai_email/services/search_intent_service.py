"""Deterministic natural-language search intent parsing.

Produces a validated :class:`EmailSearchIntent` filter object. The backend
applies these filters with parameterized queries; no model-generated SQL is
ever executed, and counts stay a backend concern.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from ..config import Settings, get_settings
from ..date_normalizer import coerce_reference_datetime
from ..exceptions import InputValidationError
from ..schemas import (
    EmailCategory,
    EmailSearchIntent,
    PriorityLevel,
    ReadState,
    Sentiment,
)

_REPLY_PATTERN = re.compile(
    r"\bneed(?:s|ing)?\s+(?:my\s+)?reply\b|\bawaiting\s+(?:my\s+)?(?:reply|response)\b"
    r"|\bwaiting\s+for\s+(?:a\s+)?(?:reply|response)\b|\bawaiting\s+response\b|\bno\s+reply\s+yet\b"
)
_ACTION_PATTERN = re.compile(
    r"\bpending\s+actions?\b|\baction\s+required\b|\bneeds?\s+action\b"
    r"|\bto-?do\b|\btasks?\b|\bdeadlines?\b"
)

_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "for",
    "and",
    "or",
    "in",
    "on",
    "at",
    "to",
    "from",
    "with",
    "my",
    "me",
    "i",
    "all",
    "any",
    "show",
    "find",
    "which",
    "emails",
    "email",
    "mail",
    "list",
    "please",
    "what",
    "are",
    "is",
    "do",
    "does",
    "this",
    "that",
    "them",
    "their",
    "there",
    "been",
    "be",
    "was",
    "were",
    "it",
    "its",
    "who",
    "whose",
    "when",
    "how",
    "many",
    "much",
    "get",
    "give",
    "us",
    "our",
}

_CATEGORY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    (
        "customer_complaint",
        ("complaint", "complaints", "complain", "unhappy customer", "dissatisfied customer", "angry customer"),
    ),
    ("sales_inquiry", ("sales", "sales inquiry", "quote", "quotation", "pricing", "lead", "prospect")),
    ("support_request", ("support", "technical issue", "bug", "ticket", "problem", "issue")),
    ("meeting_request", ("meeting", "call with", "appointment", "calendar invite")),
    ("invoice_payment", ("invoice", "payment", "payments", "billing", "payable", "remittance", "receipt")),
    ("job_application", ("job application", "candidate", "resume", "cv", "applicant", "hiring")),
    ("general_information", ("newsletter", "announcement", "informational", "fyi")),
    ("spam", ("spam", "junk", "promotional", "marketing email", "unsubscribe")),
]

_PRIORITY_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("critical", ("critical", "life-threatening", "p1")),
    ("high", ("urgent", "asap", "high priority", "important", "priority", "time sensitive")),
    ("low", ("low priority", "not important", "minor")),
]

_SENTIMENT_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("angry", ("angry", "furious", "outraged", "irate")),
    ("negative", ("negative", "unhappy", "dissatisfied", "disappointed", "frustrated", "upset")),
    ("positive", ("positive", "happy", "pleased", "thankful", "satisfied")),
    ("urgent", ("stressed", "panicking")),
]


def _add_category(intent: EmailSearchIntent, value: str, rule: str) -> None:
    category = EmailCategory(value)
    if category not in intent.categories:
        intent.categories.append(category)
        intent.matched_rules.append(rule)


def _parse_date_range(question: str, reference: datetime) -> tuple[date | None, date | None, str | None]:
    ref = reference.date()
    lowered = question.lower()

    if re.search(r"\btoday\b", lowered):
        return ref, ref, "date:today"
    if re.search(r"\byesterday\b", lowered):
        day = ref - timedelta(days=1)
        return day, day, "date:yesterday"
    if re.search(r"\blast week\b", lowered):
        monday = ref - timedelta(days=ref.weekday()) - timedelta(days=7)
        return monday, monday + timedelta(days=6), "date:last_week"
    if re.search(r"\bthis week\b", lowered):
        monday = ref - timedelta(days=ref.weekday())
        return monday, ref, "date:this_week"
    if re.search(r"\blast month\b", lowered):
        first = ref.replace(day=1) - timedelta(days=1)
        return first.replace(day=1), first, "date:last_month"
    if re.search(r"\bthis month\b", lowered):
        return ref.replace(day=1), ref, "date:this_month"
    if re.search(r"\blast year\b", lowered):
        return date(ref.year - 1, 1, 1), date(ref.year - 1, 12, 31), "date:last_year"
    if re.search(r"\bthis year\b", lowered):
        return date(ref.year, 1, 1), ref, "date:this_year"
    if re.search(r"\blast (\d{1,2}) days?\b", lowered):
        match = re.search(r"\blast (\d{1,2}) days?\b", lowered)
        days = int(match.group(1))
        return ref - timedelta(days=days), ref, f"date:last_{days}_days"
    return None, None, None


def _parse_keywords(question: str) -> list[str]:
    keywords: list[str] = []

    for phrase in re.findall(r'"([^"]{2,40})"', question):
        keywords.append(phrase.strip().lower())

    for match in re.finditer(r"\b([\w]+)-related\b", question, re.IGNORECASE):
        keywords.append(match.group(1).lower())

    for pattern in (
        r"\bmentions?\s+(?:about\s+|of\s+)?([\w-]+)",
        r"\bconcerning\s+(?:the\s+)?([\w-]+)",
        r"\babout\s+(?:the\s+)?([\w-]+)",
    ):
        for match in re.finditer(pattern, question, re.IGNORECASE):
            token = match.group(1).lower()
            if token not in _STOPWORDS and len(token) > 2:
                keywords.append(token)

    seen: list[str] = []
    for keyword in keywords:
        if keyword not in seen:
            seen.append(keyword)
    return seen[:25]


def parse_search_query(
    question: str,
    reference_datetime: datetime | date | str | None = None,
    timezone: str = "UTC",
    *,
    settings: Settings | None = None,
) -> EmailSearchIntent:
    """Turn a natural-language inbox question into validated filters."""
    settings = settings or get_settings()
    if not question or not str(question).strip():
        raise InputValidationError("question must not be empty")

    text = str(question).strip()
    lowered = text.lower()
    reference = coerce_reference_datetime(reference_datetime, timezone or settings.default_timezone)

    intent = EmailSearchIntent(free_text=text)

    for value, patterns in _CATEGORY_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            _add_category(intent, value, f"category:{value}")

    for value, patterns in _PRIORITY_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            priority = PriorityLevel(value)
            if priority not in intent.priorities:
                intent.priorities.append(priority)
                intent.matched_rules.append(f"priority:{value}")

    if "urgent" in lowered or "asap" in lowered:
        intent.urgent = True
        intent.matched_rules.append("urgent:true")
        if not intent.priorities:
            intent.priorities.append(PriorityLevel.HIGH)
            intent.matched_rules.append("priority:high")

    for value, patterns in _SENTIMENT_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            sentiment = Sentiment(value)
            if sentiment not in intent.sentiments:
                intent.sentiments.append(sentiment)
                intent.matched_rules.append(f"sentiment:{value}")

    if _REPLY_PATTERN.search(lowered):
        intent.reply_required = True
        intent.matched_rules.append("reply_required:true")
    if re.search(r"\balready\s+replied\b|\bno\s+reply\s+needed\b|\breplied\b", lowered):
        intent.reply_required = False
        intent.matched_rules.append("reply_required:false")

    if _ACTION_PATTERN.search(lowered):
        intent.action_required = True
        intent.matched_rules.append("action_required:true")

    if re.search(r"\bunread\b", lowered):
        intent.read_state = ReadState.UNREAD
        intent.matched_rules.append("read_state:unread")
    elif re.search(r"\balready\s+read\b|\bread\s+emails\b", lowered):
        intent.read_state = ReadState.READ
        intent.matched_rules.append("read_state:read")

    date_from, date_to, date_rule = _parse_date_range(lowered, reference)
    intent.date_from = date_from
    intent.date_to = date_to
    if date_rule:
        intent.matched_rules.append(date_rule)

    keywords = _parse_keywords(text)
    if keywords:
        intent.keywords = keywords
        intent.matched_rules.append("keywords:" + ",".join(keywords))

    if not intent.matched_rules:
        intent.matched_rules.append("free_text_only")

    return intent


__all__ = ["parse_search_query"]
