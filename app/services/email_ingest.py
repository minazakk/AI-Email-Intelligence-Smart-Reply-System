"""Email ingestion: manual creation, ``.eml`` parsing, CSV/JSON imports.

Everything here treats input as untrusted: size limits, header sanitisation,
malformed-file handling and per-row validation errors. Original content is
stored verbatim (after control-character stripping) and never executed.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import EmailDirection, EmailSource, ProcessingStatus
from app.core.errors import (
    PayloadTooLargeError,
    UnsupportedMediaError,
    ValidationFailedError,
)
from app.core.utils import dedupe_fingerprint, utcnow
from app.models.email import Email, EmailThread
from app.schemas.email import EmailCreate, ImportRowError, ImportSummary

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HEADER_CONTROL = re.compile(r"[\r\n\x00-\x1f\x7f]")
_MAX_HEADER = 998
_MAX_PREVIEW = 300


def clean_text(value: str | None, *, limit: int | None = None) -> str:
    if not value:
        return ""
    cleaned = _CONTROL_CHARS.sub("", str(value))
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    if limit is not None:
        return cleaned[:limit]
    return cleaned


def clean_header(value: str | None, *, limit: int = _MAX_HEADER) -> str:
    """Headers must never carry newlines (header injection)."""
    if not value:
        return ""
    return _HEADER_CONTROL.sub(" ", str(value)).strip()[:limit]


def make_preview(body: str) -> str:
    flat = re.sub(r"\s+", " ", body or "").strip()
    return flat[:_MAX_PREVIEW]


def compute_size(email_create: EmailCreate | dict[str, Any]) -> int:
    payload = email_create.model_dump() if isinstance(email_create, EmailCreate) else email_create
    raw = json.dumps(payload, ensure_ascii=False, default=str)
    return len(raw.encode("utf-8"))


# --- thread resolution -----------------------------------------------------

def _thread_key_for(*, message_id: str | None, in_reply_to: str | None, subject: str) -> str:
    if in_reply_to:
        return hashlib.sha256(in_reply_to.strip().lower().encode("utf-8")).hexdigest()[:64]
    if message_id:
        return hashlib.sha256(message_id.strip().lower().encode("utf-8")).hexdigest()[:64]
    normalised_subject = re.sub(r"^\s*(re|fwd|fw)\s*:", "", subject or "", flags=re.I).strip().lower()
    normalised_subject = re.sub(r"\s+", " ", normalised_subject)[:180]
    if normalised_subject:
        return hashlib.sha256(normalised_subject.encode("utf-8")).hexdigest()[:64]
    return "unthreaded"


def resolve_thread(db: Session, user_id: int, *, message_id: str | None, in_reply_to: str | None,
                   subject: str) -> EmailThread:
    key = _thread_key_for(message_id=message_id, in_reply_to=in_reply_to, subject=subject)
    thread = db.scalar(
        select(EmailThread).where(EmailThread.user_id == user_id, EmailThread.thread_key == key)
    )
    if thread is None:
        thread = EmailThread(
            user_id=user_id, thread_key=key, subject=clean_header(subject)[:255]
        )
        db.add(thread)
        db.flush()
    return thread


def refresh_thread_flags(db: Session, thread: EmailThread | None) -> None:
    if thread is None:
        return
    count, participants, last_at = db.execute(
        select(
            func.count(Email.id),
            func.count(func.distinct(Email.from_address)),
            func.max(Email.received_at),
        ).where(Email.thread_id == thread.id, Email.is_deleted.is_(False))
    ).one()
    thread.message_count = int(count or 0)
    thread.participant_count = int(participants or 0)
    if last_at is not None:
        thread.last_message_at = last_at
    unread = db.scalar(
        select(func.count(Email.id)).where(
            Email.thread_id == thread.id, Email.is_deleted.is_(False), Email.is_read.is_(False)
        )
    )
    thread.has_unread = bool(unread)
    starred = db.scalar(
        select(func.count(Email.id)).where(
            Email.thread_id == thread.id, Email.is_deleted.is_(False), Email.is_starred.is_(True)
        )
    )
    thread.is_starred = bool(starred)
    db.flush()


# Backwards-compatible internal name.
_refresh_thread = refresh_thread_flags


# --- creation --------------------------------------------------------------

@dataclass
class IngestResult:
    email: Email | None = None
    duplicate: bool = False
    error: str | None = None


def create_email(
    db: Session,
    *,
    user_id: int,
    payload: EmailCreate,
    source: EmailSource = EmailSource.manual,
    commit: bool = False,
    skip_duplicate_check: bool = False,
) -> IngestResult:
    subject = clean_header(payload.subject)
    from_name = clean_header(payload.from_name, limit=255)
    from_address = clean_header(payload.from_address, limit=320).lower()
    body_text = clean_text(payload.body_text)
    body_html = clean_text(payload.body_html) or None
    received_at = payload.received_at or utcnow()
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=UTC)

    fingerprint = dedupe_fingerprint(
        user_id=user_id,
        from_address=from_address,
        subject=subject,
        received_at=received_at,
        body_text=body_text,
    )
    if not skip_duplicate_check:
        existing = db.scalar(
            select(Email.id).where(Email.user_id == user_id, Email.dedupe_hash == fingerprint)
        )
        if existing is not None:
            return IngestResult(duplicate=True, error="Duplicate email skipped.")

    thread = resolve_thread(
        db,
        user_id,
        message_id=payload.message_id,
        in_reply_to=None,
        subject=subject,
    )

    email = Email(
        user_id=user_id,
        thread_id=thread.id,
        message_id=clean_header(payload.message_id, limit=255) or None,
        from_name=from_name,
        from_address=from_address,
        to=[clean_header(v, limit=320) for v in payload.to[:50]],
        cc=[clean_header(v, limit=320) for v in payload.cc[:50]],
        reply_to=clean_header(payload.reply_to, limit=320) or None,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        preview=make_preview(body_text or re.sub(r"<[^>]+>", " ", body_html or "")),
        received_at=received_at,
        sent_at=received_at if payload.direction == EmailDirection.outbound else None,
        direction=payload.direction.value,
        source=source.value,
        has_attachments=bool(payload.has_attachments or payload.attachment_names),
        attachment_names=[clean_header(v, limit=255) for v in payload.attachment_names[:50]],
        size_bytes=compute_size(payload),
        dedupe_hash=fingerprint,
        processing_status=ProcessingStatus.pending.value,
    )
    db.add(email)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return IngestResult(duplicate=True, error="Duplicate email skipped.")

    _refresh_thread(db, thread)

    if commit:
        db.commit()
    return IngestResult(email=email)


def recreate_email_from_row(db: Session, user_id: int, row: dict[str, Any],
                            source: EmailSource) -> IngestResult:
    """Validate a dict row (CSV/JSON) and turn it into an :class:`EmailCreate`."""
    errors = validate_row(row)
    if errors:
        return IngestResult(error="; ".join(f"{e.field}: {e.message}" for e in errors))
    payload = row_to_create(row)
    return create_email(db, user_id=user_id, payload=payload, source=source)


# --- row validation --------------------------------------------------------

def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)


def _split_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [p.strip() for p in re.split(r"[,;]", str(value)) if p.strip()]


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def validate_row(row: dict[str, Any]) -> list[ImportRowError]:
    problems: list[ImportRowError] = []
    subject = _as_text(row.get("subject")).strip()
    from_address = _as_text(row.get("from_address") or row.get("from")).strip()
    body = _as_text(row.get("body_text") or row.get("body") or row.get("snippet")).strip()

    if not body and not _as_text(row.get("body_html")).strip():
        problems.append(ImportRowError(row=0, field="body_text", message="Body is required."))
    if not subject and not from_address:
        problems.append(
            ImportRowError(row=0, field="subject", message="At least subject or from_address is required.")
        )
    if from_address and len(from_address) > 320:
        problems.append(ImportRowError(row=0, field="from_address", message="Address is too long."))
    received = row.get("received_at") or row.get("date")
    if received not in (None, "") and _parse_dt(received) is None:
        problems.append(
            ImportRowError(row=0, field="received_at", message="Unrecognised date format.")
        )
    return problems


def row_to_create(row: dict[str, Any]) -> EmailCreate:
    from_field = _as_text(row.get("from") or row.get("from_address")).strip()
    from_name = _as_text(row.get("from_name")).strip()
    address = from_field
    if "<" in from_field and ">" in from_field:
        match = re.search(r"<([^>]+)>", from_field)
        address = match.group(1).strip() if match else from_field
        if not from_name:
            from_name = from_field.split("<")[0].strip().strip('"')

    return EmailCreate(
        subject=_as_text(row.get("subject"))[:998],
        from_name=from_name[:255],
        from_address=address[:320],
        to=_split_list(row.get("to")),
        cc=_split_list(row.get("cc")),
        reply_to=_as_text(row.get("reply_to")).strip() or None,
        body_text=_as_text(row.get("body_text") or row.get("body") or row.get("snippet")),
        body_html=_as_text(row.get("body_html")) or None,
        received_at=_parse_dt(row.get("received_at") or row.get("date")),
        direction=EmailDirection.outbound
        if _as_text(row.get("direction")).lower().startswith("out")
        else EmailDirection.inbound,
        message_id=_as_text(row.get("message_id")).strip() or None,
        has_attachments=str(row.get("has_attachments", "")).lower() in {"1", "true", "yes"},
        attachment_names=_split_list(row.get("attachment_names")),
        process_with_ai=True,
    )


# --- .eml ------------------------------------------------------------------

def parse_eml(raw: bytes, *, filename: str = "message.eml") -> EmailCreate:
    if not raw:
        raise ValidationFailedError("The uploaded file is empty.")
    if len(raw) > settings.upload_max_bytes:
        raise PayloadTooLargeError(
            f"File exceeds the {settings.upload_max_bytes} byte upload limit.",
            details={"limit_bytes": settings.upload_max_bytes, "size_bytes": len(raw)},
        )
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
    except Exception as exc:  # pragma: no cover - parser raises assorted errors
        raise ValidationFailedError("The uploaded file is not a valid .eml message.") from exc

    def header(name: str) -> str:
        value = message.get(name)
        return clean_header(str(value)) if value is not None else ""

    from_name, from_address = "", ""
    if message.get("From"):
        parsed = getaddresses([str(message.get("From"))])
        if parsed:
            from_name, from_address = parsed[0]

    to_list = [f"{n} <{a}>" if n else a for n, a in getaddresses(message.get_all("To", []))]
    cc_list = [f"{n} <{a}>" if n else a for n, a in getaddresses(message.get_all("Cc", []))]

    body_text, body_html = _extract_bodies(message)
    received = None
    if message.get("Date"):
        try:
            received = parsedate_to_datetime(str(message.get("Date")))
            if received.tzinfo is None:
                received = received.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            received = None

    attachments: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            filename = part.get_filename()
            if filename:
                attachments.append(clean_header(str(filename), limit=255))

    if not body_text and not body_html:
        raise ValidationFailedError("The .eml file contains no readable body.")

    return EmailCreate(
        subject=header("Subject")[:998],
        from_name=clean_header(from_name, limit=255),
        from_address=clean_header(from_address, limit=320),
        to=[clean_header(v, limit=320) for v in to_list[:50]],
        cc=[clean_header(v, limit=320) for v in cc_list[:50]],
        reply_to=header("Reply-To")[:320] or None,
        body_text=body_text,
        body_html=body_html,
        received_at=received,
        message_id=header("Message-ID")[:255] or None,
        has_attachments=bool(attachments),
        attachment_names=attachments[:50],
    )


def _extract_bodies(message) -> tuple[str, str]:
    text_parts: list[str] = []
    html_parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.is_multipart():
                continue
            content_type = part.get_content_type()
            try:
                payload = part.get_content()
            except Exception:  # pragma: no cover - undecodable part
                continue
            if not isinstance(payload, str):
                continue
            if content_type == "text/plain":
                text_parts.append(clean_text(payload))
            elif content_type == "text/html":
                html_parts.append(clean_text(payload))
    else:
        try:
            payload = message.get_content()
        except Exception:  # pragma: no cover
            payload = None
        if isinstance(payload, str):
            if message.get_content_type() == "text/html":
                html_parts.append(clean_text(payload))
            else:
                text_parts.append(clean_text(payload))
    return "\n".join(t for t in text_parts if t).strip(), "\n".join(h for h in html_parts if h).strip()


# --- CSV / JSON datasets ---------------------------------------------------

_REQUIRED_HINTS = ("subject", "from", "body", "to")


def detect_format(filename: str | None, content_type: str | None, sample: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".csv") or (content_type or "").endswith("csv"):
        return "csv"
    if name.endswith(".json") or (content_type or "").endswith("json"):
        return "json"
    stripped = sample.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return "json"
    if "," in sample.splitlines()[0] if sample.splitlines() else False:
        return "csv"
    raise UnsupportedMediaError(
        "Could not determine the dataset format. Upload a .csv or .json file.",
        details={"allowed_extensions": sorted(settings.allowed_upload_extensions)},
    )


def parse_dataset(
    *,
    filename: str | None,
    content_type: str | None,
    content: bytes,
    fmt: str | None = None,
) -> list[dict[str, Any]]:
    if len(content) > settings.upload_max_bytes:
        raise PayloadTooLargeError(
            f"File exceeds the {settings.upload_max_bytes} byte upload limit.",
            details={"limit_bytes": settings.upload_max_bytes, "size_bytes": len(content)},
        )
    if not content:
        raise ValidationFailedError("The uploaded file is empty.")

    if fmt is None:
        fmt = detect_format(filename, content_type, content[:2000].decode("utf-8", errors="replace"))

    if fmt == "eml":
        raise ValidationFailedError("Use the .eml upload endpoint for individual messages.")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationFailedError("The file is not valid UTF-8.") from exc

    if fmt == "csv":
        return _parse_csv(text)
    return _parse_json(text)


def _parse_csv(text: str) -> list[dict[str, Any]]:
    # Guard against CSV formula injection when values are later re-exported.
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValidationFailedError("The CSV file has no header row.")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(reader, start=2):
        if len(rows) >= settings.import_max_rows:
            break
        row = {(k or "").strip().lower(): (v if v is not None else "") for k, v in raw.items()}
        row["__row__"] = index
        if not any(str(v).strip() for k, v in row.items() if k != "__row__"):
            continue
        rows.append(row)
    if not rows:
        raise ValidationFailedError("The CSV file contains no data rows.")
    header_join = ",".join(h.lower() for h in reader.fieldnames or [])
    if not any(hint in header_join for hint in _REQUIRED_HINTS):
        raise ValidationFailedError(
            "The CSV header does not look like an email dataset.",
            details={"expected_any_of": list(_REQUIRED_HINTS), "received": reader.fieldnames},
        )
    return rows


def _parse_json(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationFailedError(f"Invalid JSON: {exc.msg} at line {exc.lineno}.") from exc

    if isinstance(data, dict):
        for key in ("emails", "items", "data", "rows"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            data = [data]
    if not isinstance(data, list):
        raise ValidationFailedError("JSON dataset must be a list of email objects.")
    if not data:
        raise ValidationFailedError("The JSON file contains no records.")

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(data[: settings.import_max_rows], start=1):
        if not isinstance(item, dict):
            continue
        row = {str(k).strip().lower(): v for k, v in item.items()}
        row["__row__"] = index
        rows.append(row)
    if not rows:
        raise ValidationFailedError("The JSON file contains no object records.")
    return rows


def run_dataset_import(
    db: Session,
    *,
    user_id: int,
    rows: Iterable[dict[str, Any]],
    source: EmailSource,
    filename: str | None = None,
    commit: bool = True,
) -> ImportSummary:
    summary = ImportSummary(source=source, filename=filename)
    seen_fingerprints: set[str] = set()

    for offset, raw_row in enumerate(rows, start=1):
        summary.received += 1
        row_number = raw_row.get("__row__", offset)
        row = {k: v for k, v in raw_row.items() if k != "__row__"}

        problems = validate_row(row)
        if problems:
            summary.failed += 1
            summary.errors.append(
                ImportRowError(
                    row=int(row_number) if isinstance(row_number, (int, float)) else offset,
                    field=problems[0].field,
                    message="; ".join(p.message for p in problems),
                )
            )
            continue

        try:
            payload = row_to_create(row)
        except Exception as exc:  # noqa: BLE001 - surfaced as a row error
            summary.failed += 1
            summary.errors.append(
                ImportRowError(row=offset, field=None, message=f"Invalid row: {exc}")
            )
            continue

        from app.core.utils import dedupe_fingerprint as _fp

        fingerprint = _fp(
            user_id=user_id,
            from_address=payload.from_address.lower(),
            subject=payload.subject,
            received_at=payload.received_at,
            body_text=payload.body_text,
        )
        if fingerprint in seen_fingerprints:
            summary.duplicates += 1
            continue
        seen_fingerprints.add(fingerprint)

        result = create_email(db, user_id=user_id, payload=payload, source=source)
        if result.duplicate:
            summary.duplicates += 1
        elif result.error:
            summary.failed += 1
            summary.errors.append(ImportRowError(row=offset, field=None, message=result.error))
        elif result.email is not None:
            summary.created += 1
            summary.email_ids.append(result.email.id)
        else:  # pragma: no cover - defensive
            summary.failed += 1
            summary.errors.append(ImportRowError(row=offset, field=None, message="Unknown import failure."))

    if commit:
        db.commit()
    return summary


__all__ = [
    "IngestResult",
    "clean_header",
    "clean_text",
    "create_email",
    "detect_format",
    "make_preview",
    "parse_dataset",
    "parse_eml",
    "refresh_thread_flags",
    "resolve_thread",
    "row_to_create",
    "run_dataset_import",
    "validate_row",
]
