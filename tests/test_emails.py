"""Inbox CRUD, filtering, state and soft-delete behaviour."""

from __future__ import annotations

from tests.conftest import COMPLAINT_EMAIL, QUIET_EMAIL, URGENT_EMAIL, make_email


def error_of(response) -> dict:
    body = response.json()
    assert "error" in body, body
    return body["error"]


def test_create_email_runs_ai_analysis(client, user):
    email = make_email(client, user, **URGENT_EMAIL)

    assert email["category"] is not None
    assert email["priority"] in {"low", "medium", "high", "critical"}
    assert email["sentiment"] is not None
    assert email["processing_status"] == "completed"
    assert email["analysis"]["provider"] == "mock"
    assert email["analysis"]["summary_short"]
    assert email["analysis"]["prompt_version"]
    assert email["is_urgent"] is True
    assert email["reply_required"] is True
    assert email["action_required"] is True
    # Extracted entities are stored on the analysis, not duplicated on the email.
    assert isinstance(email["extracted"], list)
    assert any(e["field"] == "order_number" for e in email["extracted"])


def test_create_email_requires_content(client, user):
    response = user.post(client, "/emails", json={"subject": "empty"})
    assert response.status_code == 422
    assert error_of(response)["code"] == "validation_error"


def test_duplicate_email_is_rejected(client, user):
    payload = dict(URGENT_EMAIL, received_at="2026-02-01T10:00:00+00:00")
    first = user.post(client, "/emails", json=payload)
    assert first.status_code == 201
    second = user.post(client, "/emails", json=payload)
    assert second.status_code == 422
    assert error_of(second)["code"] == "duplicate_email"


def test_list_is_scoped_to_the_owner(client, user, other_user):
    make_email(client, user, **URGENT_EMAIL)
    assert other_user.get(client, "/emails").json()["total"] == 0
    assert user.get(client, "/emails").json()["total"] == 1


def test_urgent_and_flag_filters(client, user):
    urgent = make_email(client, user, **URGENT_EMAIL)
    make_email(client, user, **QUIET_EMAIL)

    urgent_page = user.get(client, "/emails", params={"urgent": True}).json()
    assert urgent_page["total"] == 1
    assert urgent_page["items"][0]["id"] == urgent["id"]

    reply_page = user.get(client, "/emails", params={"reply_required": True}).json()
    assert urgent["id"] in [item["id"] for item in reply_page["items"]]

    not_urgent = user.get(client, "/emails", params={"urgent": False}).json()
    assert urgent["id"] not in [item["id"] for item in not_urgent["items"]]


def test_category_priority_and_sentiment_filters(client, user):
    urgent = make_email(client, user, **URGENT_EMAIL)
    complaint = make_email(client, user, **COMPLAINT_EMAIL)

    by_category = user.get(
        client, "/emails", params={"category": complaint["category"]}
    ).json()
    assert [item["id"] for item in by_category["items"]] == [complaint["id"]]

    by_priority = user.get(client, "/emails", params={"priority": urgent["priority"]}).json()
    assert urgent["id"] in [item["id"] for item in by_priority["items"]]

    by_sentiment = user.get(
        client, "/emails", params={"sentiment": urgent["sentiment"]}
    ).json()
    assert urgent["id"] in [item["id"] for item in by_sentiment["items"]]


def test_text_search_and_sender_filter(client, user):
    make_email(client, user, **URGENT_EMAIL)
    make_email(client, user, **COMPLAINT_EMAIL)

    search = user.get(client, "/emails", params={"q": "refund"}).json()
    assert search["total"] == 1

    sender = user.get(client, "/emails", params={"from_address": "jane@customer.test"}).json()
    assert sender["total"] == 1

    subject = user.get(client, "/emails", params={"subject": "newsletter"}).json()
    assert subject["total"] == 0


def test_date_range_filter(client, user):
    make_email(client, user, **URGENT_EMAIL)
    make_email(client, user, **QUIET_EMAIL)

    narrow = user.get(
        client, "/emails", params={"date_from": "2026-01-17", "date_to": "2026-01-18"}
    ).json()
    assert narrow["total"] == 1
    assert "Newsletter" in narrow["items"][0]["subject"]

    bad = user.get(client, "/emails", params={"date_from": "2026-01-18", "date_to": "2026-01-17"})
    assert bad.status_code == 422


def test_pagination_envelope(client, user):
    for index in range(5):
        make_email(client, user, subject=f"Message {index}", body_text="body " + str(index))

    page_one = user.get(client, "/emails", params={"page": 1, "page_size": 2}).json()
    assert page_one["total"] == 5
    assert page_one["pages"] == 3
    assert len(page_one["items"]) == 2
    assert page_one["has_next"] is True
    assert page_one["has_previous"] is False

    page_three = user.get(client, "/emails", params={"page": 3, "page_size": 2}).json()
    assert page_three["has_next"] is False
    assert page_three["has_previous"] is True


def test_sorting_by_subject(client, user):
    make_email(client, user, subject="Bravo", body_text="b")
    make_email(client, user, subject="alpha", body_text="a")
    page = user.get(
        client, "/emails", params={"sort_by": "subject", "sort_order": "asc"}
    ).json()
    assert [item["subject"] for item in page["items"]] == ["alpha", "Bravo"]


def test_invalid_sort_field_is_rejected(client, user):
    response = user.get(client, "/emails", params={"sort_by": "body_text"})
    assert response.status_code == 422


def test_read_star_archive_state(client, user):
    email = make_email(client, user, **URGENT_EMAIL)
    url = f"/emails/{email['id']}"

    updated = user.post(
        client, f"/emails/{email['id']}/state", json={"is_read": True, "is_starred": True}
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["is_read"] is True and body["is_starred"] is True

    empty = user.post(client, f"/emails/{email['id']}/state", json={})
    assert empty.status_code == 422
    assert error_of(empty)["code"] == "validation_error"

    archived = user.post(client, f"/emails/{email['id']}/state", json={"is_archived": True})
    assert archived.json()["is_archived"] is True
    assert user.get(client, "/emails").json()["total"] == 0
    visible = user.get(client, "/emails", params={"archived": True}).json()
    assert [item["id"] for item in visible["items"]] == [email["id"]]

    assert user.get(client, url).status_code == 200


def test_soft_delete_hides_and_restore_brings_back(client, user):
    email = make_email(client, user, **URGENT_EMAIL)

    deleted = user.delete(client, f"/emails/{email['id']}")
    assert deleted.status_code == 200

    assert user.get(client, "/emails").json()["total"] == 0
    trash = user.get(client, "/emails", params={"deleted": True}).json()
    assert [item["id"] for item in trash["items"]] == [email["id"]]
    assert user.get(client, f"/emails/{email['id']}").json()["is_deleted"] is True

    restored = user.post(client, f"/emails/{email['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["is_deleted"] is False
    assert user.get(client, "/emails").json()["total"] == 1


def test_detail_of_another_users_email_is_a_404(client, user, other_user):
    email = make_email(client, user, **URGENT_EMAIL)
    response = other_user.get(client, f"/emails/{email['id']}")
    assert response.status_code == 404
    assert error_of(response)["code"] == "not_found"

    # Mutations must fail the same way.
    assert other_user.patch(
        client, f"/emails/{email['id']}", json={"subject": "hijacked"}
    ).status_code == 404
    assert other_user.delete(client, f"/emails/{email['id']}").status_code == 404


def test_edit_email_updates_preview(client, user):
    email = make_email(client, user, **URGENT_EMAIL)
    updated = user.patch(
        client, f"/emails/{email['id']}", json={"subject": "Renamed", "body_text": "New body"}
    )
    assert updated.status_code == 200
    assert updated.json()["subject"] == "Renamed"
    assert "New body" in updated.json()["preview"]


def test_csv_export_neutralises_formulas(client, user):
    make_email(client, user, subject="=cmd()", body_text="=1+1")
    response = user.get(client, "/emails/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Content-Disposition" in response.headers
    assert "'=cmd()" in response.text
