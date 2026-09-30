"""Email input parsing and normalization for AI processing.

The original email body is always preserved by the caller; this module only
produces an additional normalized representation used to build prompts.
Attachments and embedded content are never executed.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from .exceptions import InputValidationError
from .schemas import EmailInput, ThreadMessage

_MAX_HEADER_LINES = 60

_QUOTED_LINE = re.compile(r"^(?:>|On .+wrote:|\d{4}-\d{2}-\d{2} .+wrote:|-{2,}\s*Original Message\s*-{2,}|_{5,})")
_SIGNATURE = re.compile(
    r"^(--\s*$|--\s|\d{4}\s*\|.*\|\s*\d{4}|Get Outlook for|Sent from my iPhone|Sent from Mail app)",
    re.IGNORECASE,
)
_HTML_TAG = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_HTML_TAG_ANY = re.compile(r"<[^>]+>")
_HEADER_KEYWORDS = ("subject", "from", "to", "cc", "date", "reply-to", "message-id")


@dataclass
class NormalizedEmail:
    """A prompt-ready view of an email, derived from the original input."""

    original: EmailInput
    subject: str
    sender: str
    sender_name: str
    sender_address: str
    recipients: list[str]
    body_original: str
    body_clean: str
    text_for_analysis: str
    truncated: bool
    received_at: datetime | None
    participants: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def email_id(self) -> str | None:
        return self.original.message_id or self.original.metadata.get("id")


def _strip_html(text: str) -> str:
    text = _HTML_TAG.sub(" ", text)
    text = _HTML_TAG_ANY.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", text)


def _split_quoted(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        if _QUOTED_LINE.match(line.strip()):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def _strip_signature(text: str) -> str:
    lines = text.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if _SIGNATURE.match(lines[index].strip()):
            return "\n".join(lines[:index]).rstrip()
    return text


def clean_body(text: str) -> str:
    """Remove quoted chains, signatures and surplus blank lines."""
    cleaned = text or ""
    if "<" in cleaned and ">" in cleaned:
        cleaned = _strip_html(cleaned)
    cleaned = _split_quoted(cleaned)
    cleaned = _strip_signature(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def truncate_for_analysis(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    cut = text[:max_chars]
    boundary = cut.rfind(" ")
    if boundary > max_chars * 0.6:
        cut = cut[:boundary]
    return cut.rstrip() + "\n\n[... truncated: body exceeds configured AI_MAX_BODY_CHARS ...]", True


def normalize_email(
    email: EmailInput | dict[str, Any] | None,
    *,
    max_body_chars: int = 20_000,
    require_content: bool = True,
) -> NormalizedEmail:
    """Validate and normalize a standalone email object."""
    if email is None:
        raise InputValidationError("email input is required")
    if isinstance(email, dict):
        try:
            email = EmailInput.model_validate(email)
        except Exception as exc:  # pydantic ValidationError
            raise InputValidationError(f"invalid email input: {exc}") from exc
    if not isinstance(email, EmailInput):
        raise InputValidationError(f"unsupported email input type: {type(email).__name__}")

    body_original = email.body or ""
    body_clean = clean_body(body_original)
    subject = (email.subject or "").strip()

    if require_content and not subject and not body_clean:
        raise InputValidationError("email must contain a subject or a body")

    text_for_analysis, truncated = truncate_for_analysis(body_clean, max_body_chars)

    sender_address, sender_name = parseaddr(email.sender or "")
    notes: list[str] = []
    if not subject:
        notes.append("missing subject")
    if not body_clean:
        notes.append("empty body")
    if truncated:
        notes.append("body truncated for analysis")
    if not email.received_at:
        notes.append("missing received_at; deadlines needing a reference point stay unresolved")

    participants: list[str] = []
    for candidate in [email.sender, *email.recipients]:
        address, name = parseaddr(candidate or "")
        display = name.strip() or address.strip()
        if display and display not in participants:
            participants.append(display)

    return NormalizedEmail(
        original=email,
        subject=subject,
        sender=(email.sender or "").strip(),
        sender_name=sender_name.strip(),
        sender_address=sender_address.strip(),
        recipients=[item.strip() for item in (email.recipients or []) if item and item.strip()],
        body_original=body_original,
        body_clean=body_clean,
        text_for_analysis=text_for_analysis,
        truncated=truncated,
        received_at=email.received_at,
        participants=participants,
        notes=notes,
    )


def normalize_thread(
    messages: list[ThreadMessage | dict[str, Any]] | None,
    *,
    max_body_chars: int = 20_000,
) -> list[ThreadMessage]:
    """Validate thread messages and keep them in chronological order."""
    normalized: list[ThreadMessage] = []
    for index, item in enumerate(messages or []):
        if isinstance(item, dict):
            try:
                message = ThreadMessage.model_validate(item)
            except Exception as exc:
                raise InputValidationError(f"invalid thread message at index {index}: {exc}") from exc
        elif isinstance(item, ThreadMessage):
            message = item
        else:
            raise InputValidationError(f"unsupported thread message type: {type(item).__name__}")
        body_clean = clean_body(message.body or "")
        text, _ = truncate_for_analysis(body_clean, max_body_chars)
        normalized.append(message.model_copy(update={"body": text}))
    # Chronological order when timestamps are available.
    if all(message.sent_at for message in normalized):
        normalized.sort(key=lambda message: message.sent_at or datetime.min)
    return normalized


def parse_email_text(text: str, *, fallback_sender: str = "") -> EmailInput:
    """Parse pasted raw email text.

    Recognizes a simple ``Header: value`` block when present; otherwise the
    whole text becomes the body.
    """
    if text is None or not str(text).strip():
        raise InputValidationError("email text is empty")

    raw = str(text).replace("\r\n", "\n").strip()
    lines = raw.split("\n")

    headers: dict[str, str] = {}
    body_start = 0
    seen_separator = False
    current_key: str | None = None
    header_lines = 0

    for index, line in enumerate(lines):
        if header_lines > _MAX_HEADER_LINES:
            break
        if line.strip() == "":
            if headers and not seen_separator:
                seen_separator = True
                body_start = index + 1
                continue
            body_start = index + 1 if seen_separator else body_start
            continue
        if seen_separator:
            break
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            key = key.strip().lower()
            if key in _HEADER_KEYWORDS:
                headers[key] = value.strip()
                current_key = key
                header_lines += 1
                body_start = index + 1
                continue
            current_key = None
            body_start = index + 1
        elif current_key and line.startswith((" ", "\t")):
            headers[current_key] += " " + line.strip()
            body_start = index + 1
            continue
        else:
            break

    body = "\n".join(lines[body_start:]).strip() if headers else raw
    if headers and not body:
        body = raw

    received_at: datetime | None = None
    if headers.get("date"):
        try:
            received_at = parsedate_to_datetime(headers["date"])
        except (TypeError, ValueError, IndexError):
            received_at = None

    sender = headers.get("from") or fallback_sender
    recipients = [item.strip() for item in (headers.get("to") or "").split(",") if item.strip()]
    if headers.get("cc"):
        recipients += [item.strip() for item in headers["cc"].split(",") if item.strip()]

    return EmailInput(
        subject=headers.get("subject"),
        sender=sender,
        recipients=recipients,
        body=body,
        received_at=received_at,
    )


def parse_eml(data: bytes, *, max_bytes: int = 2_000_000) -> EmailInput:
    """Safely parse an ``.eml`` file into an :class:`EmailInput`.

    Attachments are ignored, only ``text/plain`` (or ``text/html`` as a
    fallback) parts are read, and oversized payloads are rejected.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise InputValidationError(".eml payload must be bytes")
    if len(data) == 0:
        raise InputValidationError(".eml file is empty")
    if len(data) > max_bytes:
        raise InputValidationError(f".eml file exceeds the {max_bytes} byte limit")

    try:
        message = BytesParser(policy=policy.default).parsebytes(bytes(data))
    except Exception as exc:
        raise InputValidationError(f"unable to parse .eml file: {exc}") from exc

    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        disposition = (part.get_content_disposition() or "").lower()
        if disposition == "attachment":
            continue
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            continue
        try:
            payload = part.get_content()
        except Exception:
            try:
                payload = part.get_payload(decode=True) or b""
                payload = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            except Exception:
                continue
        if not isinstance(payload, str):
            continue
        if content_type == "text/plain":
            plain_parts.append(payload)
        else:
            html_parts.append(payload)

    body = "\n".join(plain_parts).strip() or _strip_html("\n".join(html_parts)).strip()

    sender = parseaddr(message.get("From") or "")[1] or (message.get("From") or "").strip()
    full_sender = (message.get("From") or "").strip()
    recipients = [item.strip() for item in (message.get("To") or "").split(",") if item.strip()]
    recipients += [item.strip() for item in (message.get("Cc") or "").split(",") if item.strip()]

    received_at: datetime | None = None
    if message.get("Date"):
        try:
            received_at = parsedate_to_datetime(message.get("Date"))
        except (TypeError, ValueError, IndexError):
            received_at = None

    return EmailInput(
        subject=(message.get("Subject") or "").strip() or None,
        sender=full_sender or sender,
        recipients=recipients,
        body=body,
        received_at=received_at,
        message_id=(message.get("Message-ID") or "").strip() or None,
        metadata={"in_reply_to": (message.get("In-Reply-To") or "").strip()},
    )


__all__ = [
    "NormalizedEmail",
    "clean_body",
    "normalize_email",
    "normalize_thread",
    "parse_email_text",
    "parse_eml",
    "truncate_for_analysis",
]
