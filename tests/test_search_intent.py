from datetime import date

import pytest

from ai_email import parse_search_query
from ai_email.exceptions import InputValidationError
from ai_email.schemas import EmailCategory, PriorityLevel, ReadState, Sentiment

REF = "2025-09-22T09:00:00+00:00"  # Monday


def test_question_must_not_be_empty():
    with pytest.raises(InputValidationError):
        parse_search_query("")


def test_category_detection():
    intent = parse_search_query("Show all urgent customer complaints", REF)
    assert EmailCategory.CUSTOMER_COMPLAINT in intent.categories
    assert intent.urgent is True
    assert PriorityLevel.HIGH in intent.priorities


def test_payment_keywords():
    intent = parse_search_query("Find payment-related emails from this week", REF)
    assert EmailCategory.INVOICE_PAYMENT in intent.categories
    assert "payment" in intent.keywords
    assert intent.date_from == date(2025, 9, 22)
    assert intent.date_to == date(2025, 9, 22)


def test_reply_required_intent():
    intent = parse_search_query("Which emails need my reply?", REF)
    assert intent.reply_required is True


def test_action_required_intent():
    intent = parse_search_query("What are today's pending actions?", REF)
    assert intent.action_required is True
    assert intent.date_from == date(2025, 9, 22)


def test_sentiment_intent():
    intent = parse_search_query("Find all angry customers", REF)
    assert Sentiment.ANGRY in intent.sentiments
    assert EmailCategory.CUSTOMER_COMPLAINT in intent.categories


def test_customers_waiting_for_response_maps_to_reply_required():
    intent = parse_search_query("Which customers are waiting for a response?", REF)
    assert intent.reply_required is True


def test_unread_filter():
    intent = parse_search_query("show unread emails", REF)
    assert intent.read_state is ReadState.UNREAD


def test_date_ranges():
    this_week = parse_search_query("emails from this week", REF)
    assert this_week.date_from == date(2025, 9, 22)
    assert this_week.date_to == date(2025, 9, 22)

    last_week = parse_search_query("emails from last week", REF)
    assert last_week.date_from == date(2025, 9, 15)
    assert last_week.date_to == date(2025, 9, 21)

    yesterday = parse_search_query("what arrived yesterday", REF)
    assert yesterday.date_from == date(2025, 9, 21)
    assert yesterday.date_to == date(2025, 9, 21)


def test_quoted_keyword_is_captured():
    intent = parse_search_query('find emails mentioning "contract renewal"', REF)
    assert "contract renewal" in intent.keywords


def test_combined_filters():
    intent = parse_search_query("urgent support tickets from this week", REF)
    assert EmailCategory.SUPPORT_REQUEST in intent.categories
    assert intent.urgent is True
    assert intent.date_from == date(2025, 9, 22)


def test_unmatched_question_still_returns_valid_intent():
    intent = parse_search_query("asdfghjkl", REF)
    assert intent.categories == []
    assert intent.matched_rules == ["free_text_only"]
    assert intent.free_text == "asdfghjkl"


def test_intent_is_json_serializable():
    intent = parse_search_query("urgent complaints today", REF)
    payload = intent.model_dump(mode="json")
    assert payload["date_from"] == "2025-09-22"
    assert isinstance(payload["matched_rules"], list)
