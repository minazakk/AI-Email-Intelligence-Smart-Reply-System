"""CSV / JSON / .eml ingestion and duplicate handling."""

from __future__ import annotations

import io

CSV_SAMPLE = (
    "subject,from,body_text,received_at\n"
    'Invoice for order ORD-7788,billing@vendor.test,"Please pay invoice INV-22 by 2026-03-01.",2026-01-10T09:00:00+00:00\n'
    'Meeting request,ops@vendor.test,"Can we meet on 2026-01-20 at 14:00 to discuss the roadmap?",2026-01-11T10:00:00+00:00\n'
)

JSON_SAMPLE = (
    '[{"subject": "Order ORD-4242 shipped", "from_address": "ship@vendor.test",'
    ' "body_text": "Your order ORD-4242 has shipped and arrives on 2026-02-02.",'
    ' "received_at": "2026-01-12T08:00:00+00:00"}]'
)

EML_SAMPLE = b"""From: Alice Example <alice@example.test>
To: Bob Example <bob@example.test>
Subject: Follow-up on the proposal
Date: Fri, 09 Jan 2026 09:15:00 +0000
Message-ID: <followup-001@example.test>
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"

Hi Bob,

Could you review the proposal and reply by 2026-01-30?

Thanks,
Alice
"""


def _upload(client, actor, *, filename: str, content: bytes, content_type: str, data=None):
    files = {"file": (filename, io.BytesIO(content), content_type)}
    return actor.post(client, "/emails/import/dataset", files=files, data=data or {})


def test_csv_import_creates_and_analyses(client, user):
    response = _upload(
        client,
        user,
        filename="inbox.csv",
        content=CSV_SAMPLE.encode(),
        content_type="text/csv",
        data={"process_with_ai": "true"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "csv"
    assert body["created"] == 2
    assert body["failed"] == 0
    assert len(body["email_ids"]) == 2

    page = user.get(client, "/emails").json()
    assert page["total"] == 2
    assert all(item["processing_status"] == "completed" for item in page["items"])


def test_csv_import_without_ai_leaves_emails_pending(client, user):
    response = _upload(
        client, user, filename="inbox.csv", content=CSV_SAMPLE.encode(), content_type="text/csv"
    )
    assert response.status_code == 200
    assert response.json()["created"] == 2
    page = user.get(client, "/emails").json()
    assert all(item["processing_status"] == "pending" for item in page["items"])


def test_csv_import_reports_duplicate_rows(client, user):
    for _ in range(2):
        response = _upload(
            client, user, filename="inbox.csv", content=CSV_SAMPLE.encode(), content_type="text/csv"
        )
    assert response.json()["duplicates"] == 2
    assert user.get(client, "/emails").json()["total"] == 2


def test_csv_import_rejects_non_email_headers(client, user):
    response = _upload(
        client,
        user,
        filename="people.csv",
        content=b"name,age\nAlice,30\n",
        content_type="text/csv",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_csv_import_surfaces_invalid_rows(client, user):
    broken = "subject,from,body_text\nNo body,x@y.test,\n"
    response = _upload(
        client, user, filename="broken.csv", content=broken.encode(), content_type="text/csv"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["failed"] == 1
    assert body["errors"][0]["field"] == "body_text"


def test_json_import(client, user):
    response = _upload(
        client,
        user,
        filename="inbox.json",
        content=JSON_SAMPLE.encode(),
        content_type="application/json",
    )
    assert response.status_code == 200, response.text
    assert response.json()["created"] == 1
    assert response.json()["source"] == "json"


def test_json_import_rejects_malformed_payload(client, user):
    response = _upload(
        client,
        user,
        filename="bad.json",
        content=b"[{" ,
        content_type="application/json",
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_disallowed_extension_is_rejected(client, user):
    response = _upload(
        client, user, filename="payload.exe", content=b"MZ", content_type="application/octet-stream"
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


def test_eml_import(client, user):
    files = {"files": ("message.eml", io.BytesIO(EML_SAMPLE), "message/rfc822")}
    response = user.post(client, "/emails/import/eml", files=files)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["source"] == "eml"
    assert body["created"] == 1

    detail = user.get(client, f"/emails/{body['email_ids'][0]}").json()
    assert detail["subject"] == "Follow-up on the proposal"
    assert detail["from_address"] == "alice@example.test"
    assert detail["message_id"] == "<followup-001@example.test>"
    assert detail["processing_status"] == "completed"
    assert detail["is_read"] is False


def test_eml_reimport_is_a_duplicate(client, user):
    files = {"files": ("message.eml", io.BytesIO(EML_SAMPLE), "message/rfc822")}
    user.post(client, "/emails/import/eml", files=files)
    second = user.post(client, "/emails/import/eml", files=files)
    assert second.json()["duplicates"] == 1
    assert user.get(client, "/emails").json()["total"] == 1


def test_eml_rejects_extension(client, user):
    files = {"files": ("note.txt", io.BytesIO(b"hello"), "text/plain")}
    response = user.post(client, "/emails/import/eml", files=files)
    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert "not allowed" in response.json()["errors"][0]["message"]


def test_threads_group_replies_by_subject(client, user):
    user.post(
        client,
        "/emails",
        json={
            "subject": "Re: Proposal",
            "from_name": "Bob",
            "from_address": "bob@vendor.test",
            "body_text": "Looks good, thanks!",
            "received_at": "2026-01-10T10:00:00+00:00",
        },
    )
    user.post(
        client,
        "/emails",
        json={
            "subject": "Fwd: Proposal",
            "from_name": "Bob",
            "from_address": "bob@vendor.test",
            "body_text": "Forwarding this along.",
            "received_at": "2026-01-10T11:00:00+00:00",
        },
    )

    threads = user.get(client, "/threads").json()
    assert threads["total"] == 1
    thread_id = threads["items"][0]["id"]

    detail = user.get(client, f"/threads/{thread_id}").json()
    assert detail["message_count"] == 2
    assert detail["messages"][0]["received_at"] <= detail["messages"][1]["received_at"]
