from datetime import UTC, date, datetime

import pytest

from ai_email.date_normalizer import (
    coerce_reference_datetime,
    normalize_deadline,
    normalize_deadlines,
)
from ai_email.exceptions import InputValidationError
from ai_email.schemas import ResolutionKind

REF = datetime(2025, 9, 22, 10, 0, tzinfo=UTC)  # Monday


def test_tomorrow():
    result = normalize_deadline("by tomorrow", REF)
    assert result.resolution is ResolutionKind.RESOLVED
    assert result.normalized_date == date(2025, 9, 23)


def test_today():
    assert normalize_deadline("due today", REF).normalized_date == date(2025, 9, 22)


def test_bare_weekday_uses_next_occurrence():
    # Monday -> Friday of the same week
    assert normalize_deadline("by Friday", REF).normalized_date == date(2025, 9, 26)
    # Saturday -> next Saturday
    assert normalize_deadline("by Saturday", REF).normalized_date == date(2025, 9, 27)


def test_same_weekday_counts_as_today():
    assert normalize_deadline("by Monday", REF).normalized_date == date(2025, 9, 22)


def test_next_weekday_means_following_iso_week():
    assert normalize_deadline("next Monday", REF).normalized_date == date(2025, 9, 29)
    assert normalize_deadline("next Friday", REF).normalized_date == date(2025, 10, 3)


def test_next_weekday_across_year_boundary():
    ref = datetime(2025, 12, 29, 9, 0, tzinfo=UTC)  # Monday
    result = normalize_deadline("next Monday", ref)
    assert result.normalized_date == date(2026, 1, 5)


def test_within_days():
    assert normalize_deadline("within 3 days", REF).normalized_date == date(2025, 9, 25)


def test_end_of_month():
    assert normalize_deadline("by the end of this month", REF).normalized_date == date(2025, 9, 30)
    december = datetime(2025, 12, 15, 9, 0, tzinfo=UTC)
    assert normalize_deadline("by the end of this month", december).normalized_date == date(2025, 12, 31)


def test_explicit_day_month():
    assert normalize_deadline("by 25 September", REF).normalized_date == date(2025, 9, 25)
    assert normalize_deadline("before 5 October 2025", REF).normalized_date == date(2025, 10, 5)


def test_explicit_date_in_past_rolls_to_next_year():
    ref = datetime(2025, 12, 20, 9, 0, tzinfo=UTC)
    result = normalize_deadline("by 5 March", ref)
    assert result.normalized_date == date(2026, 3, 5)


def test_iso_date():
    assert normalize_deadline("due 2026-01-31", REF).normalized_date == date(2026, 1, 31)


def test_month_name_case_insensitive():
    assert normalize_deadline("by 5 OCT", REF).normalized_date == date(2025, 10, 5)


def test_leap_year_date():
    assert normalize_deadline("by 29 February 2024", REF).normalized_date == date(2024, 2, 29)


def test_invalid_date_is_not_guessed():
    result = normalize_deadline("by 30 February 2025", REF)
    assert result.resolution is ResolutionKind.AMBIGUOUS
    assert result.normalized_date is None


def test_ambiguous_phrase_returns_null():
    for phrase in ("sometime next week", "as soon as possible", "TBD", "at your earliest convenience"):
        result = normalize_deadline(phrase, REF)
        assert result.resolution is ResolutionKind.AMBIGUOUS, phrase
        assert result.normalized_date is None
        assert result.raw_text == phrase


def test_ambiguous_numeric_date_returns_null():
    result = normalize_deadline("by 05/06/2025", REF)
    assert result.resolution is ResolutionKind.AMBIGUOUS
    assert result.normalized_date is None


def test_unambiguous_numeric_date_with_day_first():
    result = normalize_deadline("by 25/06/2025", REF)
    assert result.resolution is ResolutionKind.RESOLVED
    assert result.normalized_date == date(2025, 6, 25)


def test_empty_phrase():
    result = normalize_deadline("", REF)
    assert result.resolution is ResolutionKind.NO_DATE
    assert result.raw_text == ""


def test_missing_reference_uses_supplied_timezone_only_when_provided():
    result = normalize_deadline("by tomorrow", None, "UTC")
    assert result.normalized_date is not None


def test_naive_reference_is_localized():
    naive = datetime(2025, 9, 22, 23, 30)
    aware = coerce_reference_datetime(naive, "Asia/Tokyo")
    assert aware.tzinfo is not None
    assert normalize_deadline("by tomorrow", naive, "Asia/Tokyo").normalized_date == date(2025, 9, 23)


def test_timezone_conversion_changes_reference_date():
    utc = datetime(2025, 9, 22, 23, 0, tzinfo=UTC)
    # 2025-09-23 08:00 in Tokyo
    assert normalize_deadline("due today", utc, "Asia/Tokyo").normalized_date == date(2025, 9, 23)
    assert normalize_deadline("due today", utc, "UTC").normalized_date == date(2025, 9, 22)


def test_unknown_timezone_raises():
    with pytest.raises(InputValidationError):
        normalize_deadline("by tomorrow", REF, "Not/AZone")


def test_invalid_reference_string_raises():
    with pytest.raises(InputValidationError):
        normalize_deadline("by tomorrow", "not-a-date")


def test_relative_reference_string_accepted():
    assert normalize_deadline("in 2 days", "2025-09-22T10:00:00+00:00").normalized_date == date(2025, 9, 24)


def test_list_wrapper():
    results = normalize_deadlines(["by tomorrow", "next Monday"], REF)
    assert [item.normalized_date for item in results] == [date(2025, 9, 23), date(2025, 9, 29)]
