import pytest

from ai_email import answer_inbox_question
from ai_email.exceptions import InputValidationError
from ai_email.providers import BaseProvider, ProviderRequest, ProviderResponse
from ai_email.schemas import EmailAnalysis, ProcessingStatus

RECORDS = [
    {
        "id": "e1",
        "subject": "Refund request",
        "sender": "dana@example.test",
        "category": "customer_complaint",
        "priority": "high",
        "reply_required": True,
        "short_summary": "Customer reports a damaged order.",
    },
    {
        "id": "e2",
        "subject": "Quote request",
        "sender": "buyer@example.test",
        "category": "sales_inquiry",
        "priority": "medium",
        "reply_required": True,
        "short_summary": "Buyer asks for pricing.",
    },
]


def test_answer_uses_only_supplied_records():
    answer = answer_inbox_question(
        "Which emails need my reply?", RECORDS, reference_datetime="2025-09-22T09:00:00+00:00"
    )
    assert answer.records_supplied == 2
    assert answer.records_matched == 2
    assert set(answer.referenced_email_ids) <= {"e1", "e2"}
    assert "e1" in answer.answer
    assert answer.processing_metadata.processing_status is ProcessingStatus.COMPLETED


def test_question_must_not_be_empty():
    with pytest.raises(InputValidationError):
        answer_inbox_question("   ", RECORDS)


def test_no_records_gives_clear_deterministic_answer():
    answer = answer_inbox_question("What is urgent today?", [])
    assert answer.records_supplied == 0
    assert answer.records_matched == 0
    assert answer.out_of_scope is True
    assert "no records" in answer.answer.lower()


def test_never_claims_full_inbox_search():
    answer = answer_inbox_question("Show urgent complaints", RECORDS[:1])
    assert "full inbox search" in answer.answer.lower() or "supplied" in answer.answer.lower()


class _FabricatingProvider(BaseProvider):
    name = "fabricating"

    def _complete(self, request: ProviderRequest) -> ProviderResponse:
        data = {
            "answer": "There are 999 matching emails, including e-fake and e1.",
            "scope": "supplied_records",
            "records_supplied": 999,
            "records_matched": 999,
            "referenced_email_ids": ["e-fake", "e1"],
            "out_of_scope": False,
            "follow_up_questions": [],
        }
        return ProviderResponse(data=data, provider=self.name, model="fabricator")


def test_model_output_cannot_invent_records():
    from ai_email import Settings

    settings = Settings(provider="mock", max_retries=0)
    answer = answer_inbox_question(
        "Which emails need my reply?", RECORDS, settings=settings, provider=_FabricatingProvider(settings)
    )
    assert answer.records_supplied == 2
    assert answer.records_matched == 2
    assert "e-fake" not in answer.referenced_email_ids
    assert "e1" in answer.referenced_email_ids
    assert answer.out_of_scope is True


def test_matched_count_from_backend_is_preserved():
    answer = answer_inbox_question("Which emails need my reply?", RECORDS, matched_count=1)
    assert answer.records_supplied == 2
    assert answer.records_matched == 1


def test_analysis_objects_are_supported():
    analysis = EmailAnalysis.model_validate(
        {
            "category": "meeting_request",
            "intent": "scheduling_meeting",
            "priority": "medium",
            "priority_reason": "Scheduling a call.",
            "sentiment": "neutral",
            "sentiment_confidence": 0.7,
            "reply_required": True,
            "action_required": True,
            "short_summary": "Partner proposes a meeting.",
            "detailed_summary": "Partner proposes a meeting next week.",
            "email_id": "m-9",
        }
    )
    answer = answer_inbox_question("Any meeting requests?", [analysis])
    assert answer.records_supplied == 1
    assert answer.referenced_email_ids == ["m-9"]


def test_raw_email_dicts_are_supported():
    answer = answer_inbox_question(
        "Show everything",
        [{"message_id": "raw-1", "subject": "Hello", "sender": "a@example.test", "body": "Hi"}],
    )
    assert answer.records_supplied == 1
    assert answer.referenced_email_ids == ["raw-1"]
