"""Category catalogue maintenance."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import CATEGORIES
from app.models.category import CategoryConfig

DEFAULT_LABELS: dict[str, tuple[str, str]] = {
    "sales_inquiry": ("Sales inquiry", "Requests for pricing, quotations or purchasing."),
    "customer_complaint": ("Customer complaint", "Expressions of dissatisfaction or requests for redress."),
    "support_request": ("Support request", "Technical or account help requests."),
    "meeting_request": ("Meeting request", "Requests to schedule a call or meeting."),
    "invoice_payment": ("Invoice / payment", "Invoices, receipts and payment correspondence."),
    "job_application": ("Job application", "Applications and recruiting correspondence."),
    "general_information": ("General information", "Neutral informational messages."),
    "spam": ("Spam", "Unsolicited or promotional messages."),
    "urgent": ("Urgent notice", "Messages whose primary purpose is urgency."),
    "other": ("Other", "Everything that does not fit another category."),
}


def seed_default_categories(db: Session) -> list[CategoryConfig]:
    """Idempotently insert the canonical category list."""
    created: list[CategoryConfig] = []
    existing = {row.key for row in db.scalars(select(CategoryConfig)).all()}
    for index, key in enumerate(CATEGORIES):
        if key in existing:
            continue
        label, description = DEFAULT_LABELS.get(key, (key.replace("_", " ").title(), ""))
        row = CategoryConfig(key=key, label=label, description=description, sort_order=index)
        db.add(row)
        created.append(row)
    db.flush()
    return created


__all__ = ["DEFAULT_LABELS", "seed_default_categories"]
