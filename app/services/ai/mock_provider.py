"""Deterministic, credential-free AI provider.

``MockAIProvider`` powers the test-suite and local development. It performs
keyword/regex based classification directly on the email text so results are
reproducible and never invent facts. It also supports configurable failure
modes so error handling can be tested without a live provider.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from datetime import date as _date
from typing import Any, Literal

from app.core.errors import AIProviderError
from app.services.ai.base import AIProviderResponse, BaseProvider

FailureMode = Literal["timeout", "malformed", "rate_limit", "server_error", "empty"]

_JSON_HINT = {"type": "object"}


def _load_email_block(user_prompt: str) -> dict[str, Any]:
    match = re.search(r"<email_content>\s*(.*?)\s*</email_content>", user_prompt, re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _sentences(text: str, limit: int) -> list[str]:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()][:limit]


_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("customer_complaint", (
        "complaint", "complain", "disappointed", "unacceptable", "dissatisfied",
        "unhappy", "refund", "damaged", "faulty", "broken", "rude", "worst",
        "escalate", "escalation", "fed up", "terrible", "poor service",
    )),
    ("invoice_payment", (
        "invoice", "payment", "receipt", "remittance", "bank transfer", "billing",
        "overdue", "outstanding balance", "payable", "wire transfer", "purchase order",
    )),
    ("meeting_request", (
        "meeting", "schedule a", "calendar", "appointment", "video call",
        "available on", "availability", "let's sync", "zoom call", "call scheduled",
    )),
    ("job_application", (
        "resume", "curriculum vitae", " cv", "cover letter", "job application",
        "applied for", "hiring", "vacancy", "interview", "candidate",
    )),
    ("sales_inquiry", (
        "quotation", "quote", "pricing", "price list", "interested in buying",
        "bulk order", "discount", "proposal for", "product catalogue", "we would like to purchase",
    )),
    ("support_request", (
        "support", "not working", "error", "bug", "unable to", "help me",
        "how do i", "issue with", "problem with", "troubleshoot", "login issue",
        "assistance", "failing", "crash",
    )),
    ("spam", (
        "unsubscribe", "winner", "lottery", "crypto investment", "limited offer",
        "click here", "viagra", "casino", "you have been selected", "guaranteed income",
        "work from home", "claim your prize",
    )),
]

_URGENT_WORDS = (
    "urgent", "asap", "immediately", "immediate", "right away", "critical",
    "outage", "down", "security breach", "deadline", "overdue", "final notice",
    "time sensitive", "end of day", "eod", "today", "by tomorrow", "act now",
    "action required", "priority",
)

_ANGRY_WORDS = (
    "angry", "furious", "outraged", "unacceptable", "ridiculous", "incompetent",
    "disgusted", "fed up", "worst experience", "rude", "threaten", "lawsuit",
    "legal action", "escalate to", "complaint against",
)

_NEGATIVE_WORDS = (
    "disappointed", "frustrated", "dissatisfied", "unhappy", "concerned",
    "problem", "issue", "error", "failed", "failure", "broken", "not working",
    "delayed", "overcharged", "wrong", "missing", "still waiting", "no response",
)

_POSITIVE_WORDS = (
    "thank you", "thanks", "appreciate", "great job", "excellent", "pleased",
    "happy with", "looks good", "agreed", "well done", "love it", "satisfied",
)

_REPLY_HINTS = (
    "please reply", "let us know", "let me know", "please confirm", "please advise",
    "could you", "can you", "would you", "look forward to hearing", "your thoughts",
    "please respond", "kindly revert", "do you", "is this possible", "?",
)

_ACTION_HINTS = (
    "please send", "please provide", "please complete", "please submit",
    "please sign", "please review", "please update", "please pay", "please arrange",
    "action required", "as soon as possible", "return the signed", "confirm your",
    "deadline", "due by", "by friday", "by monday", "by tomorrow", "by end of",
)

_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
_MONTH_PATTERN = "|".join(_MONTHS)
_MONTH_RE = rf"(?i:\b({_MONTH_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b)"
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_DUE_PHRASE_RE = re.compile(
    r"(?i)\b(by|before|until|till|no later than|due)\s+"
    r"(the\s+)?(end of (?:day|business day)|eod|eob|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"tomorrow|today|next week|"
    r"\d{4}-\d{2}-\d{2}|" + _MONTH_RE + r")"
)

_ACTION_SENTENCE_RE = re.compile(
    r"(?i)\b(please|kindly|could you|can you|would you|you need to|we need you to)\s+"
    r"(send|provide|complete|submit|sign|review|update|pay|arrange|confirm|share|reply|respond|return|book|schedule|call|check)\b"
)


class MockAIProvider(BaseProvider):
    name = "mock"

    def __init__(self, model: str = "mock-classifier-1", failure_mode: FailureMode | None = None) -> None:
        self.model = model
        self.failure_mode = failure_mode

    # -- entry point ------------------------------------------------------
    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema_hint: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> AIProviderResponse:
        started = time.monotonic()
        self._maybe_fail()

        lowered = system.lower()
        if "classification engine" in lowered:
            payload: dict[str, Any] = self._analyse(_load_email_block(user))
        elif "draft business email replies" in lowered:
            payload = self._draft_reply(system, user)
        elif "validated filter object" in lowered:
            payload = self._interpret_query(user)
        elif "inbox assistant" in lowered:
            payload = self._answer(user)
        else:  # pragma: no cover - defensive default
            payload = {"answer": "No applicable handler for this prompt.", "requires_data": False}

        latency = self._measure(started)
        return AIProviderResponse(
            raw_text=json.dumps(payload, ensure_ascii=False),
            parsed=payload,
            provider=self.name,
            model=self.model,
            latency_ms=latency,
            prompt_tokens=len(json.dumps(payload)) // 4,
            completion_tokens=len(json.dumps(payload)) // 4,
            total_tokens=len(json.dumps(payload)) // 2,
        )

    def _maybe_fail(self) -> None:
        mode = self.failure_mode
        if not mode:
            return
        if mode == "timeout":
            raise AIProviderError("AI provider timed out.", code="ai_timeout", retryable=True)
        if mode == "rate_limit":
            raise AIProviderError(
                "AI provider rate limited the request.", code="ai_rate_limited", retryable=True
            )
        if mode == "server_error":
            raise AIProviderError(
                "AI provider returned a server error.", code="ai_server_error", retryable=True
            )
        if mode == "empty":
            raise AIProviderError("AI provider returned an empty response.", code="ai_empty", retryable=False)
        if mode == "malformed":
            # Deliberately return text that is not JSON so the parser path runs.
            raise AIProviderError(
                "AI provider returned malformed JSON.", code="ai_response_invalid", retryable=False
            )

    # -- analysis ---------------------------------------------------------
    def _analyse(self, email: dict[str, Any]) -> dict[str, Any]:
        subject = str(email.get("subject", "") or "")
        body = str(email.get("body_text", "") or "")
        haystack = f"{subject}\n{body}".lower()
        sentences = _sentences(body, 8)

        category, matched = self._classify(haystack, subject)
        priority, priority_reason, urgent_hits = self._priority(haystack, sentences, category)
        sentiment, sentiment_conf = self._sentiment(haystack)
        if sentiment == "neutral" and urgent_hits and not any(w in haystack for w in _ANGRY_WORDS):
            # Urgency without negative emotion maps to the `urgent` sentiment.
            sentiment = "urgent"
            sentiment_conf = 0.7

        reply_required = any(h in haystack for h in _REPLY_HINTS)
        action_required = any(h in haystack for h in _ACTION_HINTS) or bool(
            self._find_action_items(sentences, haystack)
        )

        short = " ".join(sentences[:2])[:600]
        detailed = " ".join(sentences[:5])[:4000]
        key_points = [s[:220] for s in sentences[:4]]
        unresolved = []
        if "?" in body:
            unresolved = [s[:220] for s in sentences if "?" in s][:5]

        extracted = self._extract(email, body, subject)
        actions = self._find_action_items(sentences, haystack)

        return {
            "category": category,
            "category_confidence": 0.75 if matched else 0.4,
            "intent": self._intent(category, matched),
            "priority": priority,
            "priority_reason": priority_reason,
            "sentiment": sentiment,
            "sentiment_confidence": sentiment_conf,
            "reply_required": reply_required,
            "action_required": action_required or bool(actions),
            "summary_short": short,
            "summary_detailed": detailed,
            "key_points": key_points,
            "unresolved_issues": unresolved,
            "extracted": extracted,
            "action_items": actions,
        }

    @staticmethod
    def _classify(haystack: str, subject: str) -> tuple[str, bool]:
        best_category = "general_information"
        best_hits = 0
        for category, keywords in _CATEGORY_RULES:
            hits = sum(1 for kw in keywords if kw in haystack)
            if hits > best_hits:
                best_hits, best_category = hits, category
        if best_hits == 0:
            if any(w in haystack for w in _URGENT_WORDS):
                return "urgent", True
            return "general_information", False
        return best_category, True

    @staticmethod
    def _intent(category: str, matched: bool) -> str:
        return {
            "customer_complaint": "Raise a service complaint and obtain redress",
            "sales_inquiry": "Request product or pricing information",
            "support_request": "Get technical or account support",
            "meeting_request": "Arrange a meeting or call",
            "invoice_payment": "Settle or query an invoice/payment",
            "job_application": "Apply for a role",
            "spam": "Unsolicited or promotional message",
            "urgent": "Convey an urgent operational matter",
            "general_information": "Share general information",
            "other": "Unclassified correspondence",
        }.get(category, "Unclassified correspondence") if matched else "Share general information"

    @staticmethod
    def _priority(
        haystack: str, sentences: list[str], category: str
    ) -> tuple[str, str, list[str]]:
        hits = [w for w in _URGENT_WORDS if w in haystack]
        evidence = next((s for s in sentences if any(w in s.lower() for w in hits)), "")
        reason = f"Evidence: {evidence[:200]}" if evidence else ""

        critical_markers = (
            "outage", "security breach", "data breach", "legal action", "lawsuit",
            "final notice", "immediately", "production down", "system is down",
        )
        if any(m in haystack for m in critical_markers):
            return "critical", reason or "Explicit critical-impact wording detected.", hits
        if hits:
            if category == "spam":
                return "low", "Unsolicited message; urgency wording is promotional.", hits
            return "high", reason or "Urgency wording detected.", hits
        if category in {"customer_complaint", "invoice_payment"}:
            return "medium", "Customer-impacting correspondence without explicit urgency.", hits
        if category in {"meeting_request", "job_application", "sales_inquiry", "support_request"}:
            return "medium", "Routine business correspondence.", hits
        return "low", "Informational correspondence without time pressure.", hits

    @staticmethod
    def _sentiment(haystack: str) -> tuple[str, float | None]:
        angry = sum(1 for w in _ANGRY_WORDS if w in haystack)
        negative = sum(1 for w in _NEGATIVE_WORDS if w in haystack)
        positive = sum(1 for w in _POSITIVE_WORDS if w in haystack)
        urgent = sum(1 for w in _URGENT_WORDS if w in haystack)

        if angry:
            return "angry", min(0.95, 0.6 + 0.1 * angry)
        if negative:
            return "negative", min(0.95, 0.55 + 0.1 * negative)
        if urgent:
            return "urgent", min(0.9, 0.55 + 0.1 * urgent)
        if positive:
            return "positive", min(0.95, 0.6 + 0.1 * positive)
        return "neutral", 0.6

    # -- extraction -------------------------------------------------------
    def _extract(self, email: dict[str, Any], body: str, subject: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add(field: str, value: str, *, raw: str | None = None, norm: str | None = None,
                evidence: str | None = None, confidence: float = 0.8) -> None:
            key = (field, value.lower())
            if not value or key in seen:
                return
            seen.add(key)
            found.append(
                {
                    "field": field,
                    "value": value,
                    "raw_phrase": raw or value[:255],
                    "normalized_value": norm,
                    "confidence": confidence,
                    "evidence": (evidence or "")[:500] or None,
                }
            )

        addresses = re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", body)
        for addr in addresses[:5]:
            add("email", addr, raw=addr, confidence=0.95, evidence=addr)

        if email.get("from_address"):
            add("email", str(email["from_address"]), raw=str(email["from_address"]), confidence=0.95)

        for match in re.finditer(r"(\+?\d[\d\s\-().]{7,}\d)", body):
            phone = match.group(1).strip()
            digits = re.sub(r"\D", "", phone)
            # Skip ISO dates and other numeric identifiers.
            if len(digits) < 7 or len(digits) > 15 or re.fullmatch(r"\d{4}-\d{2}-\d{2}", phone):
                continue
            add("phone", phone, raw=phone, evidence=phone, confidence=0.85)
            if len([f for f in found if f["field"] == "phone"]) >= 2:
                break

        order = re.search(r"(?i)order\s*(?:number|#|no\.?|id)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-_/]{2,})", body)
        if order:
            add("order_number", order.group(1), raw=order.group(0).strip(), evidence=order.group(0).strip())

        invoice = re.search(r"(?i)invoice\s*(?:number|#|no\.?|id)?\s*[:#]?\s*([A-Z0-9][A-Z0-9\-_/]{2,})", body)
        if invoice:
            add("invoice_number", invoice.group(1), raw=invoice.group(0).strip(), evidence=invoice.group(0).strip())

        amount = re.search(
            r"(?i)(?:USD|EUR|GBP|INR|CAD|AUD|\$|€|£|₹)\s?([0-9][0-9,]*(?:\.\d{1,2})?)"
            r"|([0-9][0-9,]*(?:\.\d{1,2})?)\s?(?:USD|EUR|GBP|INR|dollars)",
            body,
        )
        if amount:
            value = amount.group(1) or amount.group(2)
            add("amount", value, raw=amount.group(0).strip(), evidence=amount.group(0).strip(), confidence=0.9)
            symbol = amount.group(0).strip()[:3]
            currency = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR"}.get(
                symbol[:1], re.sub(r"[^A-Z]", "", symbol.upper()) or None
            )
            if currency and len(currency) == 3:
                add("currency", currency, raw=symbol, confidence=0.8)

        iso = _ISO_DATE_RE.search(body)
        month = re.search(_MONTH_RE, body)
        raw_date = None
        norm_date = None
        evidence = None
        if iso:
            raw_date, evidence = iso.group(1), iso.group(0)
            try:
                norm_date = _date.fromisoformat(iso.group(1)).isoformat()
            except ValueError:
                norm_date = None
        elif month:
            raw_date, evidence = month.group(0), month.group(0)
            if month.group(3):
                try:
                    month_number = _MONTHS.index(month.group(1).lower()) + 1
                    norm_date = _date(int(month.group(3)), month_number, int(month.group(2))).isoformat()
                except (ValueError, TypeError):
                    norm_date = None
        if raw_date:
            add("date", raw_date, raw=raw_date, norm=norm_date, evidence=evidence, confidence=0.85)

        due = _DUE_PHRASE_RE.search(body)
        if due:
            raw_due = due.group(0)
            norm_due = None
            if _ISO_DATE_RE.search(raw_due):
                try:
                    norm_due = _date.fromisoformat(_ISO_DATE_RE.search(raw_due).group(1)).isoformat()
                except ValueError:
                    norm_due = None
            add("deadline", raw_due, raw=raw_due, norm=norm_due, evidence=raw_due, confidence=0.75)

        if re.search(r"(?i)\b(meeting|call|appointment)\b", body) and (iso or month):
            add(
                "meeting_date",
                raw_date or "",
                raw=raw_date,
                norm=norm_date,
                evidence=evidence,
                confidence=0.8,
            )

        loc = re.search(
            r"(?i)\b(?:at|in|venue[:\s])\s+((?:[A-Z][\w'&.-]*)(?:\s+[A-Z][\w'&.-]*){0,4}(?:\s+(?:Office|Center|Centre|Hall|Room|Building|HQ|Campus)))\b",
            body,
        )
        if loc:
            add("location", loc.group(1).strip(), raw=loc.group(0).strip(), evidence=loc.group(0).strip(), confidence=0.7)

        greeting = re.search(r"(?i)\b(?:hi|hello|dear|good (?:morning|afternoon))\s+([A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)?)", body)
        if greeting:
            add(
                "customer_name",
                greeting.group(1).strip(),
                raw=greeting.group(0).strip(),
                evidence=greeting.group(0).strip(),
                confidence=0.7,
            )
        elif str(email.get("from_name", "")).strip():
            add(
                "customer_name",
                str(email["from_name"]).strip(),
                raw=str(email["from_name"]).strip(),
                evidence=f"From: {email['from_name']}",
                confidence=0.75,
            )

        company = re.search(
            r"\b(?:from|at|on behalf of|For)\s+([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,3})\b",
            body,
        )
        if company and len(company.group(1).split()) <= 4 and "@" not in company.group(1):
            add("company", company.group(1).strip(), raw=company.group(0).strip(), confidence=0.6)

        action = _ACTION_SENTENCE_RE.search(body)
        if action:
            sentence = next(
                (s for s in _sentences(body, 12) if _ACTION_SENTENCE_RE.search(s)),
                action.group(0),
            )
            add(
                "requested_action",
                sentence[:500],
                raw=action.group(0),
                evidence=sentence[:500],
                confidence=0.8,
            )

        product = re.search(
            r"(?i)\b(?:the\s+)?([A-Z][\w+.-]*(?:\s+[A-Z][\w+.-]*){0,3}\s+(?:model|series|plan|package|edition|version))\b",
            body,
        ) or re.search(r"(?i)\b(?:model|sku|product)\s*[:#]?\s*([A-Z0-9][\w\-/]{2,})\b", body)
        if product:
            add(
                "product",
                (product.group(1) if product.lastindex else product.group(0)).strip(),
                raw=product.group(0).strip(),
                confidence=0.7,
            )

        return found[:40]

    def _find_action_items(self, sentences: list[str], haystack: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for sentence in sentences:
            lower = sentence.lower()
            if not _ACTION_SENTENCE_RE.search(sentence) and not any(
                h in lower for h in ("deadline", "due by", "please send", "action required")
            ):
                continue
            due_match = _DUE_PHRASE_RE.search(sentence)
            due_text = due_match.group(0) if due_match else None
            due_date = None
            if due_text:
                iso = _ISO_DATE_RE.search(due_text)
                if iso:
                    try:
                        due_date = _date.fromisoformat(iso.group(1)).isoformat()
                    except ValueError:
                        due_date = None
                else:
                    month = re.search(_MONTH_RE, due_text)
                    if month and month.group(3):
                        try:
                            month_number = _MONTHS.index(month.group(1).lower()) + 1
                            due_date = _date(int(month.group(3)), month_number, int(month.group(2))).isoformat()
                        except (ValueError, TypeError):
                            due_date = None
            items.append(
                {
                    "description": sentence[:1000],
                    "owner": None,
                    "due_text": due_text,
                    "due_date": due_date,
                    "priority": "high" if due_text else "medium",
                }
            )
            if len(items) >= 10:
                break
        if not items and "action required" in haystack:
            items.append(
                {
                    "description": "Email is marked action required by the sender.",
                    "owner": None,
                    "due_text": None,
                    "due_date": None,
                    "priority": "medium",
                }
            )
        return items

    # -- replies ----------------------------------------------------------
    def _draft_reply(self, system: str, user: str) -> dict[str, Any]:
        email = _load_email_block(user)
        subject = str(email.get("subject", "") or "your message")
        sender = str(email.get("from_name", "") or "").strip()
        first = sender.split()[0] if sender else "there"
        tone_match = re.search(r"Tone:\s*([a-z]+)", system)
        tone = tone_match.group(1) if tone_match else "professional"

        opener = {
            "professional": f"Hello {first},\n\nThank you for your email regarding \"{subject}\".",
            "friendly": f"Hi {first},\n\nThanks for getting in touch about \"{subject}\"!",
            "short": f"Hi {first},\n\nThanks for your email about \"{subject}\".",
            "detailed": (
                f"Dear {first},\n\nThank you for taking the time to write to us regarding \"{subject}\". "
                "I have reviewed your message and the details you shared."
            ),
            "apologetic": (
                f"Dear {first},\n\nThank you for bringing \"{subject}\" to our attention. "
                "I am sorry for the inconvenience this has caused you."
            ),
            "formal": (
                f"Dear {first},\n\nWe refer to your correspondence concerning \"{subject}\" "
                "and acknowledge receipt of the same."
            ),
        }.get(
            tone,
            f"Hello {first},\n\nThank you for your email regarding \"{subject}\".",
        )

        closer = {
            "professional": "I am reviewing the details and will revert with a precise update shortly.\n\nBest regards,"
            if tone != "formal" else "We are reviewing the matter and shall revert shortly.\n\nYours faithfully,",
            "friendly": "I'll look into this and come back to you shortly.\n\nBest,",
            "short": "\nI'll revert shortly.\n\nRegards,",
            "detailed": (
                "I am reviewing the specifics you raised. So that my response is accurate, "
                "I may come back to you if any detail is missing. I will follow up shortly with "
                "a concrete update.\n\nKind regards,"
            ),
            "apologetic": (
                "I am looking into this personally and will come back to you with a concrete update. "
                "Thank you for your patience.\n\nSincerely,"
            ),
            "formal": "We shall revert to you with a considered response in due course.\n\nYours faithfully,",
        }.get(tone, "I will revert shortly.\n\nBest regards,")

        body = f"{opener}\n\n{closer}"
        return {"body": body, "tone": tone}

    # -- query interpretation --------------------------------------------
    def _interpret_query(self, user: str) -> dict[str, Any]:
        match = re.search(r"<user_question>\s*(.*?)\s*</user_question>", user, re.DOTALL)
        question = (match.group(1) if match else user).strip().lower()

        filters: dict[str, Any] = {
            "q": None,
            "from_address": None,
            "category": [],
            "priority": [],
            "sentiment": [],
            "date_from": None,
            "date_to": None,
            "unread": None,
            "urgent": None,
            "reply_required": None,
            "action_required": None,
            "order_number": None,
        }
        mode = "summary"

        if any(w in question for w in ("urgent", "asap", "critical")):
            filters["urgent"] = True
            mode = "filter"
        if "need my reply" in question or "need a reply" in question or "reply?" in question:
            filters["reply_required"] = True
            mode = "filter"
        if "pending action" in question or "action item" in question or "to-do" in question:
            filters["action_required"] = True
            mode = "filter"
        if "unread" in question:
            filters["unread"] = True
            mode = "filter"
        if "angry" in question:
            filters["sentiment"] = ["angry"]
            mode = "filter"
        if "complaint" in question or "complaints" in question:
            filters["category"] = ["customer_complaint"]
            mode = "filter"
        if "sales" in question or "quotation" in question:
            filters["category"] = ["sales_inquiry"]
            mode = "filter"
        if "support" in question:
            filters["category"] = ["support_request"]
            mode = "filter"
        if "payment" in question or "invoice" in question:
            filters["category"] = ["invoice_payment"]
            mode = "filter"
        if "meeting" in question:
            filters["category"] = ["meeting_request"]
            mode = "filter"
        if "job application" in question or "applicant" in question:
            filters["category"] = ["job_application"]
            mode = "filter"
        if "spam" in question:
            filters["category"] = ["spam"]
            mode = "filter"

        order = re.search(r"order\s*(?:number|#|no\.?)?\s*([A-Z0-9][A-Z0-9\-_/]{2,})", question)
        if order:
            filters["order_number"] = order.group(1).upper()
            mode = "filter"

        # Relative date windows resolved against today (UTC). Skipped when an
        # intent filter is already active: "which emails need my reply today"
        # asks about pending work, not messages received during the day, and
        # narrowing to a calendar window would silently return nothing.
        intent_active = any(
            filters[key] for key in ("urgent", "reply_required", "action_required", "unread")
        )
        if not intent_active and any(
            w in question for w in ("today", "this week", "last week", "yesterday", "this month")
        ):
            today = datetime.now(UTC).date()
            if "today" in question or "yesterday" in question:
                filters["date_from"] = today.isoformat()
                filters["date_to"] = today.isoformat()
            elif "this week" in question:
                start = today.fromordinal(today.toordinal() - today.weekday())
                filters["date_from"] = start.isoformat()
                filters["date_to"] = today.isoformat()
            elif "this month" in question:
                filters["date_from"] = today.replace(day=1).isoformat()
                filters["date_to"] = today.isoformat()
            elif "last week" in question:
                end = today.fromordinal(today.toordinal() - today.weekday() - 1)
                start = end.fromordinal(end.toordinal() - 6)
                filters["date_from"] = start.isoformat()
                filters["date_to"] = end.isoformat()
            mode = "filter"

        keyword = re.search(r"(?:mention|mentions|mentioning|containing|about|keyword)\s+[\"']?([\w\s-]{3,60})", question)
        if keyword and mode == "summary":
            filters["q"] = keyword.group(1).strip()
            mode = "filter"
        elif not mode and question:
            mode = "summary"

        return {"filters": filters, "mode": mode}

    # -- assistant answers -------------------------------------------------
    def _answer(self, user: str) -> dict[str, Any]:
        question_match = re.search(r"Question:\s*(.*?)\n\nRetrieved records", user, re.DOTALL)
        question = (question_match.group(1) if question_match else "").strip()
        records_match = re.search(r"Retrieved records \(untrusted data\):\s*(\[.*\])", user, re.DOTALL)
        records: list[dict[str, Any]] = []
        if records_match:
            try:
                parsed = json.loads(records_match.group(1))
                if isinstance(parsed, list):
                    records = parsed
            except json.JSONDecodeError:
                records = []

        if not records:
            return {
                "answer": "I could not find any emails in your inbox matching that question.",
                "requires_data": True,
            }

        cites = ", ".join(f"[#{r.get('id')}]" for r in records[:8])
        subjects = "; ".join(str(r.get("subject", ""))[:60] for r in records[:3])
        answer = (
            f"I found {len(records)} matching email(s) for \"{question[:120]}\". "
            f"Most recent: {subjects}. References: {cites}."
        )
        return {"answer": answer[:6000], "requires_data": True}


__all__ = ["MockAIProvider"]
