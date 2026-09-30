"""Deterministic offline heuristics used by :class:`MockProvider`.

The mock provider exists so that the module (and its tests, demo CLI and
evaluation) run without any API key. Its output is ALWAYS labelled
``provider="mock"`` and must never be presented as live AI analysis.

The heuristics derive facts only from the supplied email text; unknown
fields stay ``None``/empty. Nothing is invented.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from ..date_normalizer import normalize_deadline

# ---------------------------------------------------------------------------
# Keyword tables
# ---------------------------------------------------------------------------

_SPAM_WORDS = (
    "unsubscribe",
    "lottery",
    "you have won",
    "winner",
    "click here now",
    "limited time offer",
    "act now",
    "crypto profit",
    "double your money",
    "100% free",
    "congratulations you",
    "viagra",
    "work from home",
    "exclusive deal",
    "flash sale",
    "prize draw",
    "you have been selected",
)
_COMPLAINT_WORDS = (
    "complaint",
    "complain",
    "disappointed",
    "dissatisfied",
    "unacceptable",
    "refund",
    "damaged",
    "broken",
    "poor service",
    "worst",
    "frustrated",
    "escalate",
    "escalation",
    "lawsuit",
    "still waiting",
    "no response",
    "rude",
    "terrible",
    "not acceptable",
    "money back",
)
_SUPPORT_WORDS = (
    "bug",
    "error",
    "issue",
    "problem",
    "not working",
    "fails",
    "failing",
    "crash",
    "crashes",
    "unable to",
    "cannot log",
    "can't log",
    "login issue",
    "troubleshoot",
    "help me with",
    "how do i",
    "ticket",
    "outage",
    "broken link",
    "500 error",
    "timeout",
    "glitch",
    "fault",
)
_SALES_WORDS = (
    "quotation",
    "quote",
    "pricing",
    "price list",
    "how much does",
    "cost",
    "interested in",
    "proposal",
    "discount",
    "bulk order",
    "catalogue",
    "catalog",
    "purchase",
    "buy",
    "subscription plan",
    "vendor",
    "rm a quote",
)
_MEETING_WORDS = (
    "meeting",
    "schedule a call",
    "calendar",
    "availability",
    "sync up",
    "appointment",
    "slot",
    "discuss further",
    "video call",
    "zoom link",
    "teams link",
    "reschedule",
    "invite you",
)
_INVOICE_WORDS = (
    "invoice",
    "payment",
    "bank transfer",
    "overdue",
    "remittance",
    "payable",
    "billing",
    "receipt",
    "purchase order",
    "due date",
    "outstanding balance",
)
_JOB_WORDS = (
    "resume",
    "cv",
    "job application",
    "applying for",
    "vacancy",
    "opening",
    "cover letter",
    "interview",
    "hiring",
    "candidate",
    "position of",
)
_GENERAL_WORDS = (
    "newsletter",
    "announcement",
    "fyi",
    "for your information",
    "update for",
    "please be informed",
    "kindly note",
    "bulletin",
)
_URGENT_WORDS = (
    "urgent",
    "asap",
    "immediately",
    "right away",
    "emergency",
    "critical",
    "time sensitive",
    "priority",
    "escalate today",
)
_CRITICAL_PHRASES = (
    "asap",
    "immediately",
    "right away",
    "emergency",
    "critical",
    "production down",
    "system down",
    "data loss",
    "within the next hour",
    "by end of day today",
    "before end of day",
)
_HIGH_PHRASES = (
    "urgent",
    "within 24 hours",
    "24 hours",
    "by tomorrow",
    "overdue",
    "final notice",
    "escalate",
    "end of business tomorrow",
    "deadline",
)
_ANGRY_WORDS = (
    "furious",
    "outraged",
    "disgusted",
    "unacceptable",
    "ridiculous",
    "angry",
    "livid",
    "worst experience",
    "sue",
    "legal action",
    "enough is enough",
)
_NEGATIVE_WORDS = (
    "disappointed",
    "dissatisfied",
    "poor",
    "broken",
    "damaged",
    "failed",
    "failure",
    "not working",
    "problem",
    "issue",
    "error",
    "unhappy",
    "annoyed",
    "inconvenience",
    "lost",
    "missing",
    "overcharged",
)
_POSITIVE_WORDS = (
    "thank you",
    "thanks",
    "appreciate",
    "great job",
    "excellent",
    "pleased",
    "happy with",
    "well done",
    "grateful",
    "love the",
)

_NAME_DENYLIST = {
    "team",
    "all",
    "everyone",
    "sir",
    "madam",
    "customer",
    "customers",
    "colleagues",
    "support",
    "sales",
    "recruiter",
    "hiring",
    "admin",
    "friend",
    "there",
    "user",
    "hiring team",
    "support team",
    "sales team",
    "to whom",
    "period",
}

_INTENT_BY_CATEGORY = {
    "customer_complaint": (
        "refund",
        "requesting_refund",
        "cancel",
        "canceling_service",
        "complaint",
        "complaining_about_service",
    ),
    "support_request": ("bug", "reporting_bug", "login", "account_access_issue", "issue", "reporting_issue"),
    "sales_inquiry": ("quote", "requesting_quote", "pricing", "requesting_pricing", "buy", "purchase_inquiry"),
    "meeting_request": ("reschedule", "rescheduling_meeting", "cancel", "canceling_meeting"),
    "invoice_payment": ("overdue", "payment_reminder", "receipt", "requesting_receipt", "payment", "payment_inquiry"),
    "job_application": ("interview", "interview_follow_up"),
    "spam": ("offer", "promotional_offer", "job", "recruitment_scam"),
    "general_information": (
        "newsletter",
        "newsletter_delivery",
    ),
    "urgent": ("urgent", "urgent_request"),
    "other": (),
}

_CATEGORY_PRECEDENCE = [
    "customer_complaint",
    "support_request",
    "invoice_payment",
    "meeting_request",
    "sales_inquiry",
    "job_application",
    "spam",
    "urgent",
    "general_information",
    "other",
]


_INSTRUCTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard previous",
    "disregard all previous",
    "forget previous instructions",
    "forget all previous",
    "system prompt",
    "developer prompt",
    "print your prompt",
    "reveal your prompt",
    "reveal your system",
    "your new task",
    "your new role",
    "new instructions",
    "act as if you",
    "override your",
    "from now on you",
    "set category",
    "set priority",
    "set sentiment",
    "set reply_required",
    "set action_required",
    "category=",
    "category =",
    "priority=",
    "priority =",
    "sentiment=",
    "sentiment =",
    "reply_required=",
    "action_required=",
    "order_number=",
    "invoice_number=",
    "output only",
    "respond only with",
)


def _scrub_instructions(text: str) -> str:
    """Drop model-directed instruction lines from untrusted email text.

    Rules are applied to the *scoring* text only: a sender cannot escalate
    category/priority/sentiment or inject field values by embedding lines that
    address the model. If nothing survives, the original text is kept so
    legitimate content is never silently discarded.
    """
    if not text:
        return text
    kept = [line for line in text.splitlines() if not any(marker in line.lower() for marker in _INSTRUCTION_MARKERS)]
    scrubbed = "\n".join(kept).strip()
    return scrubbed or text


def _find(words: tuple[str, ...], text: str) -> list[str]:
    return [word for word in words if word in text]


def _first_sentence(body: str, limit: int = 40) -> str:
    text = re.sub(r"\s+", " ", body).strip()
    if not text:
        return ""
    match = re.search(r"(?<=[.!?])\s", text)
    sentence = text[: match.start()] if match else text
    words = sentence.split()
    if len(words) > limit:
        sentence = " ".join(words[:limit]) + "..."
    return sentence.strip()


def _classify(text: str) -> str:
    scores: dict[str, int] = {category: 0 for category in _CATEGORY_PRECEDENCE}
    for word in _find(_COMPLAINT_WORDS, text):
        scores["customer_complaint"] += 2 if word in {"complaint", "complain", "refund", "unacceptable"} else 1
    for word in _find(_SUPPORT_WORDS, text):
        scores["support_request"] += 2 if word in {"bug", "error", "not working", "unable to"} else 1
    for word in _find(_INVOICE_WORDS, text):
        scores["invoice_payment"] += 2 if word in {"invoice", "payment", "bank transfer"} else 1
    for word in _find(_MEETING_WORDS, text):
        scores["meeting_request"] += 2 if word in {"meeting", "schedule a call", "availability"} else 1
    for word in _find(_SALES_WORDS, text):
        scores["sales_inquiry"] += 2 if word in {"quote", "quotation", "pricing", "cost"} else 1
    for word in _find(_JOB_WORDS, text):
        scores["job_application"] += (
            2
            if word
            in {"resume", "cv", "job application", "cover letter", "interview", "candidate", "hiring", "applying for"}
            else 1
        )
    for word in _find(_SPAM_WORDS, text):
        scores["spam"] += 3 if word in {"unsubscribe", "lottery", "click here now", "act now"} else 2
    for _word in _find(_GENERAL_WORDS, text):
        scores["general_information"] += 1
    for _word in _find(_URGENT_WORDS, text):
        scores["urgent"] += 1

    if all(value == 0 for value in scores.values()):
        return "general_information"

    best = max(
        _CATEGORY_PRECEDENCE,
        key=lambda category: (scores[category], -_CATEGORY_PRECEDENCE.index(category)),
    )
    if scores[best] == 0:
        return "general_information"
    return best


def _intent_for(category: str, text: str) -> str:
    entries = _INTENT_BY_CATEGORY.get(category, ())
    for index in range(0, len(entries), 2):
        keyword, intent = entries[index], entries[index + 1]
        if keyword in text:
            return intent
    return {
        "customer_complaint": "complaining_about_service",
        "support_request": "requesting_support",
        "sales_inquiry": "product_inquiry",
        "meeting_request": "scheduling_meeting",
        "invoice_payment": "payment_inquiry",
        "job_application": "job_application_submission",
        "general_information": "informational_update",
        "spam": "unsolicited_message",
        "urgent": "urgent_request",
        "other": "general_inquiry",
    }.get(category, "general_inquiry")


def _priority(category: str, text: str, today_hits: list[str]) -> tuple[str, str]:
    if category == "spam":
        return "low", "Unsolicited bulk content with no business action required."

    critical = _find(_CRITICAL_PHRASES, text)
    if today_hits:
        critical = critical + [f"deadline falls on {today_hits[0]}"]
    if critical:
        return "critical", f"The email asks for action {critical[0]!r}, which indicates immediate business impact."

    high = _find(_HIGH_PHRASES, text)
    if high:
        return "high", f"The email contains a time-sensitive marker {high[0]!r} requiring prompt handling."

    if category in {"customer_complaint", "support_request", "invoice_payment", "urgent"}:
        return "medium", f"A {category.replace('_', ' ')} normally needs a response within normal business turnaround."
    if category in {"general_information", "job_application"}:
        return "low", f"A {category.replace('_', ' ')} email has no immediate time pressure."
    return "medium", f"A {category.replace('_', ' ')} email requires a standard business response."


def _sentiment(text: str, priority: str) -> tuple[str, float]:
    angry = _find(_ANGRY_WORDS, text)
    if angry or text.count("!!") >= 2:
        return "angry", min(0.95, 0.75 + 0.05 * len(angry))
    negative = _find(_NEGATIVE_WORDS, text)
    if negative:
        return "negative", min(0.93, 0.7 + 0.04 * len(negative))
    positive = _find(_POSITIVE_WORDS, text)
    if positive:
        return "positive", min(0.93, 0.72 + 0.04 * len(positive))
    if priority == "critical":
        return "urgent", 0.8
    if _find(_URGENT_WORDS, text):
        return "urgent", 0.7
    return "neutral", 0.65


def _extract_money(text: str) -> tuple[str | None, str | None]:
    symbol = re.search(r"(?P<sym>[$€£])\s?(?P<amt>\d[\d,]*(?:\.\d{1,2})?)", text)
    if symbol:
        currency = {"$": "USD", "€": "EUR", "£": "GBP"}[symbol.group("sym")]
        return symbol.group("amt"), currency
    code = re.search(r"\b(?P<code>USD|EUR|GBP|CAD|AUD|INR)\s?(?P<amt>\d[\d,]*(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if code:
        return code.group("amt"), code.group("code").upper()
    suffix = re.search(
        r"\b(?P<amt>\d[\d,]*\.\d{2})\s(?P<code>USD|EUR|GBP|CAD|AUD|INR)\b",
        text,
        re.IGNORECASE,
    )
    if suffix:
        return suffix.group("amt"), suffix.group("code").upper()
    bare = re.search(r"\b(?P<amt>\d[\d,]*\.\d{2})\b", text)
    if bare:
        return bare.group("amt"), None
    return None, None


def _extract_deadline_phrases(text: str) -> list[str]:
    pattern = re.compile(
        r"\b(?:by|before|due(?:\s+by)?|due on|no later than|within|deadline(?:\s+is)?)\s+"
        r"(?:the end of |eod |cob )?"
        r"[^.,;!\n]{2,45}",
        re.IGNORECASE,
    )
    phrases: list[str] = []
    for match in pattern.finditer(text):
        phrase = match.group(0).strip()
        if phrase and phrase not in phrases:
            phrases.append(phrase)
    return phrases[:5]


def _extract_information(
    body: str,
    sender: str,
    text: str,
    reference_datetime: str | None,
    timezone: str,
) -> dict[str, Any]:
    email_address = None
    match = re.search(r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b", body)
    if match:
        email_address = match.group(0)
    elif re.search(r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b", sender or ""):
        email_address = re.search(r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b", sender).group(0)

    phone = re.search(r"(?<!\d)(?:\+\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?!\d)", body)
    order_number = re.search(
        r"\b(?:orders?|ord\.?|order no\.?|order number|po)\b\s*(?:number|no\.?|#)?\s*[:#]?\s*"
        r"((?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,19})\b",
        body,
        re.IGNORECASE,
    )
    invoice_number = re.search(
        r"\b(?:invoices?|inv\.?|invoice no\.?|invoice number)\b\s*(?:number|no\.?|#)?\s*[:#]?\s*"
        r"((?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{3,19})\b",
        body,
        re.IGNORECASE,
    )
    amount, currency = _extract_money(body)

    company = None
    company_match = re.search(
        r"\b(?:at|from|with|on behalf of)\s+"
        r"([A-Z][\w&'.-]+(?:\s+[A-Z][\w&'.-]+){0,3}\s?(?:Inc|LLC|Ltd|Limited|GmbH|Corp|Corporation|Co|SA|PLC)\.?)\b",
        body,
    )
    if company_match:
        company = company_match.group(1).strip()
    else:
        suffix_match = re.search(
            r"\b([A-Z][\w&'.-]+(?:\s+[A-Z][\w&'.-]+){0,3}\s?(?:Inc|LLC|Ltd|Limited|GmbH|Corp|Corporation)\.?)\b",
            body,
        )
        if suffix_match:
            company = suffix_match.group(1).strip()

    customer_name = None
    greeting = re.search(
        r"(?:^|\n)\s*(?i:hi|hello|dear|good (?:morning|afternoon))\s*(?:,|-)?\s*"
        r"(?:mr\.?|mrs\.?|ms\.?|dr\.?)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        body,
    )
    if greeting and greeting.group(1).strip().lower() not in _NAME_DENYLIST:
        customer_name = greeting.group(1).strip()
    else:
        intro = re.search(r"\b(?i:my name is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", body)
        if intro:
            customer_name = intro.group(1).strip()

    date_phrases: list[str] = []
    for pattern in (
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?(?:\s+\d{4})?\b",
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ):
        for found in re.findall(pattern, body, flags=re.IGNORECASE):
            if isinstance(found, tuple):
                found = found[0]
            if found and found not in date_phrases:
                date_phrases.append(found)

    deadline_phrases = _extract_deadline_phrases(body)
    deadlines: list[dict[str, Any]] = []
    for phrase in deadline_phrases:
        normalized = normalize_deadline(phrase, reference_datetime, timezone)
        deadlines.append(
            {
                "text": phrase,
                "normalized_date": normalized.normalized_date.isoformat() if normalized.normalized_date else None,
            }
        )

    meeting_date = None
    if date_phrases and re.search(
        r"\bmeeting|call|appointment|demo|workshop|interview|calendar\b", body, re.IGNORECASE
    ):
        meeting_date = date_phrases[0]

    location = None
    location_match = re.search(
        r"\b(?:room|suite|floor|building|hall|office|center|centre|arena|hotel|street|road|avenue|ave\.?|blvd)\b[^.\n]{0,40}",
        body,
        re.IGNORECASE,
    )
    if location_match:
        location = location_match.group(0).strip()
    elif re.search(r"\bon zoom\b|\bvia teams\b|\bgoogle meet\b", body, re.IGNORECASE):
        location = "virtual meeting"

    requested_action = None
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        if re.search(
            r"\bplease\b|\bkindly\b|\bcould you\b|\bwe need\b|\bneed you to\b|\baction required\b",
            sentence,
            re.IGNORECASE,
        ):
            requested_action = sentence.strip()[:300]
            break

    product = None
    product_match = re.search(
        r"\b(?:product|item|model)\s*(?:number|no\.?|name)?\s*[:#]\s*([\w \-]{2,40})", body, re.IGNORECASE
    )
    if product_match:
        product = product_match.group(1).strip()

    return {
        "customer_name": customer_name,
        "company": company,
        "phone_number": phone.group(0).strip() if phone else None,
        "email_address": email_address,
        "order_number": order_number.group(1) if order_number else None,
        "invoice_number": invoice_number.group(1) if invoice_number else None,
        "product": product,
        "amount": amount,
        "currency": currency,
        "dates": date_phrases[:10],
        "deadlines": deadlines,
        "meeting_date": meeting_date,
        "location": location,
        "requested_action": requested_action,
    }


def _action_items(body: str, reference_datetime: str | None, timezone: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for sentence in re.split(r"(?<=[.!?])\s+", body):
        sentence = sentence.strip()
        if not sentence or len(sentence) < 10:
            continue
        if re.search(
            r"\bplease\b|\bkindly\b|\bcould you\b|\bwe need\b|\bneed to\b|\bmust\b|\baction required\b|\bto do\b",
            sentence,
            re.IGNORECASE,
        ):
            deadline_phrases = _extract_deadline_phrases(sentence)
            deadline_text = deadline_phrases[0] if deadline_phrases else None
            due_date = None
            if deadline_text:
                due_date = normalize_deadline(deadline_text, reference_datetime, timezone).normalized_date
            items.append(
                {
                    "description": sentence[:400],
                    "owner": None,
                    "deadline_text": deadline_text,
                    "due_date": due_date.isoformat() if due_date else None,
                    "status": "pending",
                    "evidence": sentence[:200],
                }
            )
        if len(items) >= 5:
            break
    return items


def mock_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    """Deterministic, rule-based analysis of one email."""
    email = payload.get("email") or {}
    subject = str(email.get("subject") or "")
    body = _scrub_instructions(str(email.get("body") or ""))
    sender = str(email.get("sender") or "")
    reference_datetime = payload.get("reference_datetime")
    timezone = str(payload.get("timezone") or "UTC")

    combined = f"{_scrub_instructions(subject)}\n{body}".strip()
    lowered = combined.lower()

    category = _classify(lowered)
    intent = _intent_for(category, lowered)

    today_hits: list[str] = []
    if reference_datetime:
        try:
            today = datetime.fromisoformat(str(reference_datetime)).date()
            explicit_due_today = re.search(
                r"\bdue(?:\s+by)?\s+today\b|\bby\s+today\b|\beod today\b|"
                r"\b(?:by|before)\s+(?:the\s+)?end of (?:the\s+)?day(?:\s+today)?\b",
                lowered,
            )
            if explicit_due_today:
                today_hits.append(str(today))
        except ValueError:
            pass

    priority, priority_reason = _priority(category, lowered, today_hits)
    sentiment, sentiment_confidence = _sentiment(lowered, priority)

    if category == "spam" or re.search(r"\bdo not reply\b|\bno reply\b|\bunsubscrib", lowered) or not body:
        reply_required = False
    else:
        reply_required = True

    action_required = category in {
        "customer_complaint",
        "support_request",
        "invoice_payment",
        "meeting_request",
        "sales_inquiry",
        "job_application",
        "urgent",
    } or bool(_extract_deadline_phrases(body))

    extracted = _extract_information(body, sender, lowered, reference_datetime, timezone)
    action_items = _action_items(body, reference_datetime, timezone)

    first = _first_sentence(body)
    if not first:
        first = subject or "The email has no readable body."
    short_summary = first[:400]

    detail_parts = [
        f'{sender or "A sender"} wrote about "{subject}".'
        if subject
        else f"{sender or 'A sender'} wrote to the recipient."
    ]
    detail_parts.append(f"Primary category: {category.replace('_', ' ')}; sentiment: {sentiment}.")
    if extracted.get("requested_action"):
        detail_parts.append(f"Requested action: {extracted['requested_action']}")
    if extracted.get("deadlines"):
        texts = ", ".join(item["text"] for item in extracted["deadlines"][:2])
        detail_parts.append(f"Mentioned deadline(s): {texts}.")
    if first and first.lower() not in detail_parts[0].lower():
        detail_parts.append(first)

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if len(s.strip()) > 15]
    key_points = [s[:160] for s in sentences[:5]]
    unresolved = [s[:160] for s in sentences if s.endswith("?")][:5]

    participants = [item for item in [sender, *(email.get("recipients") or [])] if item][:5]

    return {
        "category": category,
        "intent": intent,
        "priority": priority,
        "priority_reason": priority_reason,
        "sentiment": sentiment,
        "sentiment_confidence": round(sentiment_confidence, 2),
        "reply_required": reply_required,
        "action_required": action_required,
        "short_summary": short_summary,
        "detailed_summary": " ".join(detail_parts)[:2900],
        "participants": participants,
        "extracted_information": extracted,
        "action_items": action_items,
        "key_points": key_points,
        "unresolved_issues": unresolved,
        "email_id": email.get("id"),
    }


# ---------------------------------------------------------------------------
# Smart reply
# ---------------------------------------------------------------------------

_GREETINGS = {
    "professional": "Hello",
    "friendly": "Hi",
    "short": "Hi",
    "detailed": "Hello",
    "apologetic": "Hello",
    "formal": "Dear Sir or Madam",
}
_SIGNOFFS = {
    "professional": "Best regards,",
    "friendly": "Best,",
    "short": "Thanks,",
    "detailed": "Kind regards,",
    "apologetic": "Sincerely sorry for the inconvenience,",
    "formal": "Yours sincerely,",
}


def _open_questions(latest_body: str, thread_bodies: list[str]) -> list[str]:
    answered = " ".join(thread_bodies).lower()
    questions: list[str] = []
    for sentence in re.split(r"(?<=[.?])\s+", latest_body):
        sentence = sentence.strip()
        if not sentence.endswith("?"):
            continue
        key = sentence.lower()
        if any(token in answered for token in re.findall(r"[a-z]{5,}", key)[:3]):
            continue
        if "ignore previous" in key or "system prompt" in key:
            continue
        questions.append(sentence)
    return questions[:2]


def mock_smart_reply(payload: dict[str, Any]) -> dict[str, Any]:
    """Template-based draft that never invents business facts."""
    email = payload.get("email") or {}
    thread = payload.get("thread") or []
    tone = str(payload.get("tone") or "professional")
    length = str(payload.get("length_preference") or "")
    business_context = str(payload.get("business_context") or "").strip()

    subject = str(email.get("subject") or "").strip()
    body = _scrub_instructions(str(email.get("body") or ""))
    sender = str(email.get("sender") or "")
    name_match = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.sub(r"<[^>]+>", "", sender).strip())
    recipient_name = name_match.group(1) if name_match else ""
    previous = [_scrub_instructions(str(item.get("body") or "")) for item in thread[:-1]]

    greeting_name = recipient_name.split()[0] if recipient_name else ""
    greeting = _GREETINGS.get(tone, "Hello")
    if greeting_name and tone != "formal":
        greeting = f"{greeting} {greeting_name},"
    else:
        greeting = f"{greeting},"

    ack_subject = f' regarding "{subject}"' if subject else ""
    lines = [greeting, "", f"Thank you for your email{ack_subject}."]

    questions = _open_questions(body, previous)
    if questions:
        lines.append("")
        lines.append("To make sure I address everything:")
        for question in questions:
            lines.append(f"- {question}")

    if business_context:
        lines.append("")
        lines.append(business_context)

    if tone == "apologetic":
        lines.append("")
        lines.append("I am sorry for the trouble this has caused and I appreciate your patience while I look into it.")
    elif tone == "detailed":
        lines.append("")
        lines.append(
            "I have reviewed the details you shared and will come back to you with a considered response "
            "covering each point you raised."
        )
    elif tone == "short":
        lines = [greeting, "", f"Thanks for your note{ack_subject}."]
        if questions:
            lines.append(f"Could you confirm: {questions[0]}")
    else:
        lines.append("")
        lines.append("I will review the details and come back to you shortly.")

    if length == "short" and tone not in {"short"}:
        lines = [greeting, "", f"Thank you for your email{ack_subject}. I will review and respond shortly."]

    lines += ["", _SIGNOFFS.get(tone, "Best regards,"), "Alex Morgan"]

    warnings = [
        "Draft generated by the offline mock provider - replace with a live provider for real AI drafts.",
        "Draft requires explicit user approval; the system never sends email automatically.",
    ]
    if re.search(r"\b\d+\.\d{2}\b|\b[$€£]\s?\d", body):
        warnings.append("The email mentions an amount - verify it before quoting it back.")
    if _extract_deadline_phrases(body):
        warnings.append("The email mentions a deadline - confirm it before agreeing to it.")

    return {
        "draft": "\n".join(lines).strip(),
        "tone": tone,
        "subject_line": f"Re: {subject}" if subject else None,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Inbox assistant
# ---------------------------------------------------------------------------


def mock_assistant(payload: dict[str, Any]) -> dict[str, Any]:
    """Answer strictly from the records supplied by the caller."""
    records = payload.get("records") or []
    actions = payload.get("pending_actions") or []
    supplied = int(payload.get("records_supplied", len(records)))
    matched = int(payload.get("records_matched", len(records)))

    if not records:
        return {
            "answer": (
                "No matching records were supplied for this question, so I cannot answer it from the inbox. "
                "Try widening the filters (category, priority or date range)."
            ),
            "scope": "supplied_records",
            "records_supplied": supplied,
            "records_matched": 0,
            "referenced_email_ids": [],
            "out_of_scope": True,
            "follow_up_questions": ["Which date range should I search instead?"],
        }

    lines = [f"From the {matched} record(s) supplied:"]
    ids: list[str] = []
    for record in records[:8]:
        record_id = str(record.get("id") or record.get("email_id") or "unknown-id")
        ids.append(record_id)
        subject = str(record.get("subject") or "(no subject)")
        sender = str(record.get("sender") or "")
        category = str(record.get("category") or "no category supplied")
        priority = str(record.get("priority") or "no priority supplied")
        lines.append(f"- [{record_id}] {subject} from {sender} ({category}, {priority}).")

    if actions:
        lines.append(f"Pending actions supplied: {len(actions)}.")
        for action in actions[:3]:
            description = str(action.get("description") or action.get("title") or action)
            due = action.get("due_date") or action.get("deadline_text")
            lines.append(f"- {description}" + (f" (due {due})" if due else ""))

    lines.append("These results cover only the records supplied to me, not a full inbox search.")

    return {
        "answer": "\n".join(lines)[:3900],
        "scope": "supplied_records",
        "records_supplied": supplied,
        "records_matched": matched,
        "referenced_email_ids": ids,
        "out_of_scope": matched > len(records),
        "follow_up_questions": [f"Filter these {matched} records by category or date?"] if matched else [],
    }


__all__ = ["mock_analysis", "mock_assistant", "mock_smart_reply"]
