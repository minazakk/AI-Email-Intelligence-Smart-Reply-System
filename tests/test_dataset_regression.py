"""Regression coverage over the synthetic dataset (offline, mock provider)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_email import Settings, analyze_email, set_settings

DATASET_PATH = ROOT / "tests" / "fixtures" / "sample_emails.json"
GROUPS = (
    "customer_complaint",
    "sales_inquiry",
    "support_request",
    "meeting_request",
    "invoice_payment",
    "job_application",
    "general_information",
    "urgent",
    "spam",
)


@pytest.fixture(scope="module")
def dataset():
    assert DATASET_PATH.is_file(), "run `python scripts/generate_dataset.py` first"
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def test_dataset_shape(dataset):
    emails = dataset["emails"]
    assert len(emails) >= 50
    for group in GROUPS:
        count = sum(1 for email in emails if email["group"] == group)
        assert count >= 10, f"group {group} has only {count} examples"


def test_dataset_has_no_real_personal_data(dataset):
    joined = json.dumps(dataset).lower()
    for forbidden in ("@gmail.", "@yahoo.", "@hotmail.", "@outlook.", "ssn", "passport"):
        assert forbidden not in joined


def test_dataset_is_reproducible(dataset):
    import scripts.generate_dataset as generator  # type: ignore

    rebuilt = generator.build_dataset()
    assert rebuilt["emails"] == dataset["emails"]


def test_expected_deadlines_are_consistent(dataset):
    for email in dataset["emails"]:
        expected = email["expected"]
        if expected.get("deadline_text") is None:
            continue
        assert expected.get("due_date") is not None or expected["deadline_text"] == "within 24 hours"


def _run(email: dict, settings: Settings):
    return analyze_email(
        {
            "subject": email["subject"],
            "sender": email["sender"],
            "recipients": email.get("recipients", []),
            "body": email["body"],
            "received_at": email["received_at"],
            "message_id": email["id"],
        },
        timezone=dataset_timezone(),
        settings=settings,
    )


def dataset_timezone() -> str:
    return "UTC"


@pytest.fixture(scope="module")
def settings():
    return Settings(provider="mock")


def test_dataset_label_accuracy_is_measured_at_threshold(dataset, settings):
    set_settings(settings)
    total = 0
    correct = 0
    failures = []
    for email in dataset["emails"]:
        expected = email["expected"]
        analysis = _run(email, settings)
        checks = {
            "category": analysis.category.value in (expected.get("category_any_of") or [expected["category"]]),
            "priority": analysis.priority.value == expected["priority"],
            "sentiment": analysis.sentiment.value == expected["sentiment"],
            "reply_required": analysis.reply_required == expected["reply_required"],
            "action_required": analysis.action_required == expected["action_required"],
        }
        for field, ok in checks.items():
            total += 1
            if ok:
                correct += 1
            else:
                failures.append(
                    f"{email['id']} {field}: predicted={getattr(analysis, field, analysis.category.value)} "
                    f"expected={expected[field if field != 'category' else 'category']}"
                )
    accuracy = correct / total if total else 0.0
    assert not failures, f"{len(failures)} label mismatches: {failures[:10]}"
    assert accuracy >= 0.95, f"measured label accuracy {accuracy:.3f} below threshold"


def test_dataset_never_invents_required_fields(dataset, settings):
    set_settings(settings)
    invented = []
    for email in dataset["emails"]:
        expected = email["expected"]
        analysis = _run(email, settings)
        info = analysis.extracted_information
        for field in expected.get("must_be_absent", []):
            if getattr(info, field, None) is not None:
                invented.append(f"{email['id']}: {field}")
    assert not invented, f"invented fields: {invented[:10]}"


def test_dataset_deadlines_match_expectations(dataset, settings):
    set_settings(settings)
    problems = []
    for email in dataset["emails"]:
        expected = email["expected"]
        if expected.get("deadline_text") is None:
            continue
        analysis = _run(email, settings)
        phrase = expected["deadline_text"].lower()
        matches = [d for d in analysis.extracted_information.deadlines if phrase in d.text.lower()]
        if not matches:
            problems.append(f"{email['id']}: missing deadline {phrase!r}")
            continue
        got = matches[0].normalized_date.isoformat() if matches[0].normalized_date else None
        if got != expected.get("due_date"):
            problems.append(f"{email['id']}: expected {expected.get('due_date')}, got {got}")
    assert not problems, problems[:10]


def test_every_dataset_analysis_is_schema_valid(dataset, settings):
    set_settings(settings)
    for email in dataset["emails"]:
        analysis = _run(email, settings)
        assert analysis.processing_metadata.processing_status.value == "completed", email["id"]
        assert analysis.short_summary, email["id"]
