"""Deterministic deadline/date normalization.

Relative phrases are resolved against an explicit reference datetime and a
configured timezone - never against the server's local clock. When a phrase
is ambiguous the raw text is preserved and ``normalized_date`` stays
``None``; the module never guesses.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .exceptions import InputValidationError
from .schemas import NormalizedDeadline, ResolutionKind

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_WEEKDAY_SHORT = {
    "mon": 0,
    "tue": 1,
    "tues": 1,
    "wed": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}
_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

# Phrases that clearly do not describe a resolvable point in time.
_AMBIGUOUS_PHRASES = (
    "next week",
    "next month",
    "sometime",
    "asap",
    "soon",
    "tbd",
    "to be determined",
    "to be confirmed",
    "tbc",
    "at your earliest convenience",
    "when possible",
)

# Abbreviation protection: never interpret "sept." style tokens as numbers.
_DATE_PATTERNS: list[re.Pattern[str]] = [
    # ISO: 2025-09-25
    re.compile(r"\b(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})\b", re.IGNORECASE),
    # 25 September 2025 / 25 Sep 2025
    re.compile(
        r"\b(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?P<mon>[a-z]+)\.?(?:\s+(?P<y>\d{4}))?\b",
        re.IGNORECASE,
    ),
    # September 25, 2025 / Sep 25 2025
    re.compile(
        r"\b(?P<mon>[a-z]+)\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<y>\d{4}))?\b",
        re.IGNORECASE,
    ),
    # Numeric 25/09/2025 or 25-09-2025 (only used when unambiguous)
    re.compile(r"\b(?P<a>\d{1,2})/(?P<b>\d{1,2})/(?P<y>\d{4})\b"),
    re.compile(r"\b(?P<a>\d{1,2})-(?P<b>\d{1,2})-(?P<y>\d{4})\b"),
]


def _resolve_timezone(tz_name: str) -> tzinfo:
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InputValidationError(f"unknown timezone: {tz_name!r}") from exc


def coerce_reference_datetime(reference_datetime: datetime | date | str | None, tz_name: str) -> datetime:
    """Normalize the caller supplied reference point to a tz-aware datetime."""
    tz = _resolve_timezone(tz_name)
    if reference_datetime is None:
        return datetime.now(tz)
    if isinstance(reference_datetime, str):
        try:
            reference_datetime = datetime.fromisoformat(reference_datetime)
        except ValueError as exc:
            raise InputValidationError(f"invalid reference_datetime: {reference_datetime!r}") from exc
    if isinstance(reference_datetime, date) and not isinstance(reference_datetime, datetime):
        reference_datetime = datetime(reference_datetime.year, reference_datetime.month, reference_datetime.day)
    if reference_datetime.tzinfo is None:
        return reference_datetime.replace(tzinfo=tz)
    return reference_datetime.astimezone(tz)


def _next_weekday(ref: date, weekday: int, *, following_week: bool) -> date:
    """Return ``weekday`` occurrence.

    ``following_week=False`` -> next occurrence on/after ``ref`` (today counts).
    ``following_week=True``  -> the occurrence inside the ISO week *after*
    ``ref``'s ISO week ("next Monday" semantics).
    """
    if following_week:
        iso_year, iso_week, _ = ref.isocalendar()
        try:
            base = date.fromisocalendar(iso_year, iso_week + 1, 1)
        except ValueError:  # week 53 does not exist in this year
            base = date.fromisocalendar(iso_year + 1, 1, 1)
        target = base + timedelta(days=weekday)
        if target <= ref:
            # Overflow guard (rare calendar layouts).
            target = target + timedelta(days=7)
        return target
    delta = (weekday - ref.weekday()) % 7
    return ref + timedelta(days=delta)


def _pick_year(candidate: date, ref: date) -> date:
    """Attach the nearest plausible year when the phrase omitted one."""
    if candidate >= ref:
        return candidate
    next_year = candidate.replace(year=ref.year + 1)
    # Only roll forward if it happens within ~370 days (handles leap years).
    if (next_year - ref).days <= 370:
        return next_year
    return candidate


def _is_valid_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve_absolute(text: str, ref: date) -> date | None:
    for index, pattern in enumerate(_DATE_PATTERNS):
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groupdict()
        if index == 0:
            parsed = _is_valid_date(int(groups["y"]), int(groups["m"]), int(groups["d"]))
            if parsed:
                return parsed
            return None
        if index in (1, 2):
            month = _MONTHS.get((groups["mon"] or "").lower().rstrip("."))
            if not month:
                continue
            year = int(groups["y"]) if groups.get("y") else None
            parsed = _is_valid_date(year or ref.year, month, int(groups["d"]))
            if parsed is None:
                return None
            if year is None:
                parsed = _pick_year(parsed, ref)
            return parsed
        # numeric d/m/Y vs m/d/Y
        a, b = int(groups["a"]), int(groups["b"])
        if a > 12 >= b:
            parsed = _is_valid_date(int(groups["y"]), b, a)
        elif b > 12 >= a:
            parsed = _is_valid_date(int(groups["y"]), a, b)
        else:
            # Both <= 12: day/month order is ambiguous - do not guess.
            return None
        return parsed
    return None


def normalize_deadline(
    raw_text: str,
    reference_datetime: datetime | date | str | None = None,
    timezone: str = "UTC",
) -> NormalizedDeadline:
    """Resolve a deadline phrase against an explicit reference point.

    Returns the raw phrase always, plus ``normalized_date`` only when the
    phrase is unambiguous. Ambiguous/absent dates yield ``resolution =
    ambiguous|no_date`` with a ``None`` date.
    """
    if raw_text is None or not str(raw_text).strip():
        return NormalizedDeadline(
            raw_text="",
            timezone=timezone,
            resolution=ResolutionKind.NO_DATE,
            reason="empty deadline phrase",
        )

    phrase = str(raw_text).strip()
    ref_dt = coerce_reference_datetime(reference_datetime, timezone)
    ref = ref_dt.date()
    lowered = re.sub(r"\s+", " ", phrase.lower())

    def resolved(day: date) -> NormalizedDeadline:
        return NormalizedDeadline(
            raw_text=phrase,
            normalized_date=day,
            timezone=timezone,
            resolution=ResolutionKind.RESOLVED,
        )

    def ambiguous(reason: str) -> NormalizedDeadline:
        return NormalizedDeadline(
            raw_text=phrase,
            normalized_date=None,
            timezone=timezone,
            resolution=ResolutionKind.AMBIGUOUS,
            reason=reason,
        )

    for needle in _AMBIGUOUS_PHRASES:
        if needle in lowered:
            return ambiguous(f"phrase {needle!r} does not identify a specific date")

    # Absolute dates first - they win over relative words in the same phrase.
    absolute = _resolve_absolute(phrase, ref)
    if absolute is not None:
        return resolved(absolute)

    # "within 3 days" / "in 3 days" / "in 2 weeks"
    relative = re.search(r"\b(?:within|in)\s+(\d{1,3})\s+(day|days|week|weeks|business day|business days)\b", lowered)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        if unit.startswith("day"):
            return resolved(ref + timedelta(days=amount))
        return resolved(ref + timedelta(weeks=amount))

    if re.search(r"\b(end of (?:the |this )?(?:month|week)\b)", lowered):
        if re.search(r"end of (?:the |this )?month|end of month", lowered):
            if ref.month == 12:
                last = date(ref.year, 12, 31)
            else:
                nxt = date(ref.year, ref.month + 1, 1)
                last = nxt - timedelta(days=1)
            return resolved(last)
        return resolved(ref + timedelta(days=6 - ref.weekday()))  # end of ISO week = Sunday

    if re.search(r"\btoday\b|\btonight\b|\bby close of business today\b|\bcob today\b|\beod today\b", lowered):
        return resolved(ref)

    if re.search(r"\btomorrow\b", lowered):
        return resolved(ref + timedelta(days=1))

    # "next Friday" / "next mon"
    next_match = re.search(r"\bnext\s+([a-z]+)\.?\b", lowered)
    if next_match:
        token = next_match.group(1)
        weekday = _WEEKDAYS.get(token) if token in _WEEKDAYS else _WEEKDAY_SHORT.get(token)
        if weekday is not None:
            return resolved(_next_weekday(ref, weekday, following_week=True))

    # Bare weekday: "by Friday", "send it Friday"
    words = re.findall(r"[a-z]+", lowered)
    for word in words:
        weekday = _WEEKDAYS.get(word) if word in _WEEKDAYS else _WEEKDAY_SHORT.get(word)
        if weekday is not None:
            return resolved(_next_weekday(ref, weekday, following_week=False))

    # ISO date fragment without year, e.g. "25/09" - ambiguous, do not guess.
    if re.search(r"\b\d{1,2}[/-]\d{1,2}\b", lowered):
        return ambiguous("numeric date without a year is ambiguous")

    return ambiguous("no recognizable date pattern in the phrase")


def normalize_deadlines(
    raw_texts: list[str],
    reference_datetime: datetime | date | str | None = None,
    timezone: str = "UTC",
) -> list[NormalizedDeadline]:
    """Convenience wrapper for a list of deadline phrases."""
    return [normalize_deadline(text, reference_datetime, timezone) for text in raw_texts]


def reference_now(timezone: str = "UTC") -> datetime:
    return datetime.now(_resolve_timezone(timezone))
