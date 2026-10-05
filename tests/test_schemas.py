import pytest
from pydantic import ValidationError

from ai_email.schemas import (
    ActionItem,
    ActionStatus,
    AssistantAnswer,
    EmailAnalysis,
    EmailCategory,
    EmailInput,
    EmailSearchIntent,
    ExtractedInformation,
    NormalizedDeadline,
    PriorityLevel,
    ProcessingMetadata,
    ProcessingStatus,
    ReplyTone,
    ResolutionKind,
    Sentiment,
    SmartReplyResult,
)


def _minimal_analysis(**overrides) -> dict:
    payload = {
        "category": "customer_complaint",
        "intent": "requesting_refund",
        "priority": "high",
        "priority_reason": "Customer reports a damaged order.",
        "sentiment": "negative",
        "sentiment_confidence": 0.8,
        "reply_required": True,
        "action_required": True,
        "short_summary": "Customer reports a damaged order and asks for a refund.",
        "detailed_summary": "A customer wrote about a damaged order and requested a refund within three days.",
    }
    payload.update(overrides)
    return payload


def test_valid_analysis_parses():
    analysis = EmailAnalysis.model_validate(_minimal_analysis())
    assert analysis.category is EmailCategory.CUSTOMER_COMPLAINT
    assert analysis.priority is PriorityLevel.HIGH
    assert analysis.sentiment is Sentiment.NEGATIVE
    assert analysis.processing_metadata.processing_status is ProcessingStatus.PENDING


def test_invalid_category_rejected():
    with pytest.raises(ValidationError):
        EmailAnalysis.model_validate(_minimal_analysis(category="urgent_email"))


def test_invalid_priority_rejected():
    with pytest.raises(ValidationError):
        EmailAnalysis.model_validate(_minimal_analysis(priority="asap"))


def test_invalid_sentiment_rejected():
    with pytest.raises(ValidationError):
        EmailAnalysis.model_validate(_minimal_analysis(sentiment="excited"))


def test_confidence_bounds_enforced():
    with pytest.raises(ValidationError):
        EmailAnalysis.model_validate(_minimal_analysis(sentiment_confidence=1.5))
    with pytest.raises(ValidationError):
        EmailAnalysis.model_validate(_minimal_analysis(sentiment_confidence=-0.1))


def test_missing_optional_fields_have_defaults():
    analysis = EmailAnalysis.model_validate(_minimal_analysis())
    assert analysis.extracted_information == ExtractedInformation()
    assert analysis.action_items == []
    assert analysis.key_points == []
    assert analysis.unresolved_issues == []
    assert analysis.participants == []


def test_unknown_extractions_stay_null():
    info = ExtractedInformation()
    assert info.order_number is None
    assert info.invoice_number is None
    assert info.amount is None
    assert info.deadlines == []


def test_invalid_email_address_in_extractions_rejected():
    with pytest.raises(ValidationError):
        ExtractedInformation(email_address="not-an-email")


def test_empty_short_summary_rejected():
    with pytest.raises(ValidationError):
        EmailAnalysis.model_validate(_minimal_analysis(short_summary="   "))


def test_action_status_enum():
    item = ActionItem(description="Send the quotation")
    assert item.status is ActionStatus.PENDING
    with pytest.raises(ValidationError):
        ActionItem(description="Send the quotation", status="done")


def test_reply_tone_enum():
    with pytest.raises(ValidationError):
        SmartReplyResult(draft="Hello", tone="sarcastic")
    assert SmartReplyResult(draft="Hello", tone=ReplyTone.FRIENDLY).tone is ReplyTone.FRIENDLY


def test_smart_reply_can_never_be_sent():
    result = SmartReplyResult(draft="Hello", tone="professional", sent=True, status="sent")
    assert result.sent is False
    assert result.requires_user_approval is True
    assert result.status == "draft"


def test_assistant_counts_must_be_consistent():
    with pytest.raises(ValidationError):
        AssistantAnswer(answer="ok", records_supplied=1, records_matched=5)


def test_search_intent_swaps_inverted_date_range():
    intent = EmailSearchIntent.model_validate({"date_from": "2025-09-20", "date_to": "2025-09-01"})
    assert intent.date_from.isoformat() == "2025-09-01"
    assert intent.date_to.isoformat() == "2025-09-20"


def test_email_input_rejects_oversized_body():
    with pytest.raises(ValidationError):
        EmailInput(body="x" * 200_001)


def test_email_input_rejects_too_many_recipients():
    with pytest.raises(ValidationError):
        EmailInput(sender="a@b.test", recipients=[f"user{i}@b.test" for i in range(51)])


def test_normalized_deadline_defaults():
    deadline = NormalizedDeadline(raw_text="sometime soon")
    assert deadline.resolution is ResolutionKind.NO_DATE
    assert deadline.normalized_date is None
    assert deadline.iso_date is None


def test_processing_metadata_defaults_are_unknown_safe():
    meta = ProcessingMetadata()
    assert meta.provider == "unknown"
    assert meta.prompt_version == "unknown"
    assert meta.processing_status is ProcessingStatus.PENDING
