"""Machine-readable enumerations shared by the database, API and AI layer."""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    user = "user"
    admin = "admin"


class EmailCategory(StrEnum):
    sales_inquiry = "sales_inquiry"
    customer_complaint = "customer_complaint"
    support_request = "support_request"
    meeting_request = "meeting_request"
    invoice_payment = "invoice_payment"
    job_application = "job_application"
    general_information = "general_information"
    spam = "spam"
    urgent = "urgent"
    other = "other"


class EmailPriority(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class EmailSentiment(StrEnum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"
    angry = "angry"
    urgent = "urgent"


class ReplyTone(StrEnum):
    professional = "professional"
    friendly = "friendly"
    short = "short"
    detailed = "detailed"
    apologetic = "apologetic"
    formal = "formal"


class ActionStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    dismissed = "dismissed"


class ProcessingStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class EmailSource(StrEnum):
    manual = "manual"
    eml = "eml"
    csv = "csv"
    json = "json"
    api = "api"
    seed = "seed"


class EmailDirection(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class ReplyStatus(StrEnum):
    draft = "draft"
    approved = "approved"
    rejected = "rejected"


class NotificationType(StrEnum):
    urgent_email = "urgent_email"
    customer_complaint = "customer_complaint"
    reply_required = "reply_required"
    deadline_upcoming = "deadline_upcoming"
    action_item = "action_item"
    ai_processing_completed = "ai_processing_completed"
    ai_processing_failed = "ai_processing_failed"


class TokenPurpose(StrEnum):
    email_verify = "email_verify"
    password_reset = "password_reset"


class AssistantRole(StrEnum):
    user = "user"
    assistant = "assistant"


class ExtractedField(StrEnum):
    customer_name = "customer_name"
    company = "company"
    phone = "phone"
    email = "email"
    order_number = "order_number"
    invoice_number = "invoice_number"
    product = "product"
    amount = "amount"
    currency = "currency"
    date = "date"
    deadline = "deadline"
    meeting_date = "meeting_date"
    location = "location"
    requested_action = "requested_action"


class AiPurpose(StrEnum):
    analysis = "analysis"
    reply = "reply"
    assistant = "assistant"


# Canonical label sets used by validation and documentation.
CATEGORIES: tuple[str, ...] = tuple(m.value for m in EmailCategory)
PRIORITIES: tuple[str, ...] = tuple(m.value for m in EmailPriority)
SENTIMENTS: tuple[str, ...] = tuple(m.value for m in EmailSentiment)
REPLY_TONES: tuple[str, ...] = tuple(m.value for m in ReplyTone)
ACTION_STATUSES: tuple[str, ...] = tuple(m.value for m in ActionStatus)
PROCESSING_STATUSES: tuple[str, ...] = tuple(m.value for m in ProcessingStatus)

# An email counts as "urgent" for dashboard/filter purposes when either the
# priority or the sentiment says so. Documented in docs/API_CONTRACT.md.
URGENT_PRIORITIES: tuple[str, ...] = (EmailPriority.high.value, EmailPriority.critical.value)
