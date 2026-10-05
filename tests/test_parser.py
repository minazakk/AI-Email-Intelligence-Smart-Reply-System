import pytest

from ai_email.email_parser import (
    clean_body,
    normalize_email,
    normalize_thread,
    parse_email_text,
    parse_eml,
)
from ai_email.exceptions import InputValidationError


def test_parse_raw_text_with_headers():
    raw = (
        "Subject: Invoice question\n"
        "From: Payer <payer@example.test>\n"
        "To: billing@ourcorp.example, finance@ourcorp.example\n"
        "Cc: audit@ourcorp.example\n"
        "Date: Mon, 22 Sep 2025 09:00:00 +0000\n"
        "\n"
        "Could you confirm the payment due date?\n"
    )
    email = parse_email_text(raw)
    assert email.subject == "Invoice question"
    assert email.sender == "Payer <payer@example.test>"
    assert "billing@ourcorp.example" in email.recipients
    assert "audit@ourcorp.example" in email.recipients
    assert email.received_at is not None
    assert "payment due date" in email.body


def test_parse_plain_text_without_headers():
    email = parse_email_text("Just a plain message body")
    assert email.subject is None
    assert "plain message" in email.body


def test_empty_text_rejected():
    with pytest.raises(InputValidationError):
        parse_email_text("   ")


def test_normalize_email_requires_content():
    with pytest.raises(InputValidationError):
        normalize_email({"subject": "", "sender": "", "body": ""})


def test_normalize_email_notes_missing_fields():
    normalized = normalize_email({"subject": "", "sender": "", "body": "Hello"})
    assert "missing subject" in normalized.notes
    assert "missing received_at" in " ".join(normalized.notes)


def test_clean_body_removes_quoted_chain():
    body = "Thanks for the update.\n\nOn Mon, Sep 22, 2025, someone wrote:\n> Old message here."
    assert "Old message here" not in clean_body(body)
    assert "Thanks for the update." in clean_body(body)


def test_clean_body_removes_signature():
    body = "Hello there.\n\n-- \nAlex Morgan\nSales Director"
    cleaned = clean_body(body)
    assert "Sales Director" not in cleaned
    assert "Hello there." in cleaned


def test_clean_body_strips_html():
    cleaned = clean_body("<p>Hello <b>world</b></p><script>alert(1)</script>")
    assert "Hello" in cleaned
    assert "alert" not in cleaned


def test_oversized_body_is_rejected_by_schema():
    with pytest.raises(InputValidationError):
        normalize_email({"subject": "big", "sender": "a@b.test", "body": "x" * 200_001})


def test_truncation_marker_applied():
    normalized = normalize_email(
        {"subject": "long", "sender": "a@b.test", "body": "word " * 5000},
        max_body_chars=500,
    )
    assert normalized.truncated is True
    assert "truncated" in normalized.text_for_analysis


def test_normalize_thread_orders_chronologically():
    messages = normalize_thread(
        [
            {"sender": "b@x.test", "body": "second", "sent_at": "2025-09-22T10:00:00+00:00"},
            {"sender": "a@x.test", "body": "first", "sent_at": "2025-09-21T10:00:00+00:00"},
        ]
    )
    assert [message.body for message in messages] == ["first", "second"]


def test_normalize_thread_rejects_bad_message():
    with pytest.raises(InputValidationError):
        normalize_thread(["not-a-message"])


def test_parse_eml_reads_text_and_ignores_attachments():
    eml = (
        b"From: sender@example.test\r\n"
        b"To: team@ourcorp.example\r\n"
        b"Subject: Quarterly report\r\n"
        b"Date: Mon, 22 Sep 2025 09:00:00 +0000\r\n"
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/mixed; boundary="BOUND"\r\n'
        b"\r\n"
        b"--BOUND\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Please find the report attached.\r\n"
        b"--BOUND\r\n"
        b'Content-Type: application/pdf; name="report.pdf"\r\n'
        b'Content-Disposition: attachment; filename="report.pdf"\r\n'
        b"\r\n"
        b"%PDF-fake\r\n"
        b"--BOUND--\r\n"
    )
    email = parse_eml(eml)
    assert email.subject == "Quarterly report"
    assert "Please find the report" in email.body
    assert "PDF" not in email.body
    assert email.received_at is not None


def test_parse_eml_rejects_oversized_payload():
    with pytest.raises(InputValidationError):
        parse_eml(b"From: a@b.test\r\n\r\n" + b"x" * 100, max_bytes=10)


def test_parse_eml_rejects_empty_payload():
    with pytest.raises(InputValidationError):
        parse_eml(b"")


def test_parse_eml_tolerates_missing_mime_headers():
    email = parse_eml(b"From: a@b.test\r\nSubject: Hi\r\n\r\nJust the body\r\n")
    assert email.subject == "Hi"
    assert "Just the body" in email.body
