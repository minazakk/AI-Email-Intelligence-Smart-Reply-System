"""Action items, deadlines and notifications."""

from __future__ import annotations

from tests.conftest import API, URGENT_EMAIL, make_email


def test_action_items_are_created_and_listed(client, user):
    email = make_email(client, user, **URGENT_EMAIL)

    page = user.get(client, "/actions").json()
    assert page["total"] >= 1
    item = page["items"][0]
    assert item["email_id"] == email["id"]
    assert item["email_subject"] == email["subject"]
    assert item["status"] == "pending"
    assert item["description"]


def test_action_items_are_owner_scoped(client, user, other_user):
    make_email(client, user, **URGENT_EMAIL)
    item_id = user.get(client, "/actions").json()["items"][0]["id"]

    assert other_user.get(client, "/actions").json()["total"] == 0
    assert other_user.post(client, f"/actions/{item_id}/complete").status_code == 404
    assert other_user.delete(client, f"/actions/{item_id}").status_code == 404


def test_complete_and_dismiss_action(client, user):
    make_email(client, user, **URGENT_EMAIL)
    item_id = user.get(client, "/actions").json()["items"][0]["id"]

    completed = user.post(client, f"/actions/{item_id}/complete")
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "completed"
    assert body["completed_at"] is not None

    # Completing twice does not change the original completion timestamp.
    again = user.post(client, f"/actions/{item_id}/complete")
    assert again.json()["completed_at"] == body["completed_at"]

    pending = user.get(client, "/actions", params={"status": "pending"}).json()
    assert item_id not in [row["id"] for row in pending["items"]]


def test_update_action_status(client, user):
    make_email(client, user, **URGENT_EMAIL)
    item_id = user.get(client, "/actions").json()["items"][0]["id"]

    updated = user.patch(client, f"/actions/{item_id}", json={"status": "in_progress"})
    assert updated.json()["status"] == "in_progress"
    assert updated.json()["completed_at"] is None

    dismissed = user.delete(client, f"/actions/{item_id}")
    assert dismissed.status_code == 200
    assert user.get(client, "/actions").json()["items"][0]["status"] == "dismissed"


def test_invalid_action_status_filter(client, user):
    response = user.get(client, "/actions", params={"status": "not-a-status"})
    assert response.status_code == 422


def test_deadlines_endpoint(client, user):
    make_email(client, user, **URGENT_EMAIL)
    response = user.get(client, "/actions/deadlines", params={"horizon_days": 365})
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    for row in response.json():
        assert "days_until" in row
        assert "overdue" in row

    assert user.get(
        client, "/actions/deadlines", params={"horizon_days": 100_000}
    ).status_code == 422


def test_notification_listing_and_unread_count(client, user):
    make_email(client, user, **URGENT_EMAIL)

    page = user.get(client, "/notifications").json()
    assert page["total"] >= 1

    unread = user.get(client, "/notifications/unread-count").json()
    assert unread["unread"] == page["total"]

    first_id = page["items"][0]["id"]
    read = user.post(client, f"/notifications/{first_id}/read", json={})
    assert read.status_code == 200
    assert read.json()["is_read"] is True

    after = user.get(client, "/notifications/unread-count").json()
    assert after["unread"] == unread["unread"] - 1


def test_notification_type_filter_and_validation(client, user):
    make_email(client, user, **URGENT_EMAIL)

    filtered = user.get(client, "/notifications", params={"type": "urgent_email"}).json()
    assert filtered["total"] >= 1
    assert all(item["type"] == "urgent_email" for item in filtered["items"])

    invalid = user.get(client, "/notifications", params={"type": "nope"})
    assert invalid.status_code == 422


def test_mark_all_read_and_delete(client, user):
    make_email(client, user, **URGENT_EMAIL)

    all_read = user.post(client, "/notifications/read-all", json={})
    assert all_read.status_code == 200
    assert all_read.json()["updated"] >= 1
    assert user.get(client, "/notifications/unread-count").json()["unread"] == 0

    notification_id = user.get(client, "/notifications").json()["items"][0]["id"]
    deleted = user.delete(client, f"/notifications/{notification_id}")
    assert deleted.status_code == 200

    missing = user.delete(client, f"/notifications/{notification_id}")
    assert missing.status_code == 404


def test_notification_preferences_round_trip(client, user):
    current = user.get(client, "/notifications/preferences/me").json()
    assert current["in_app_enabled"] is True
    assert "urgent_email" in current["enabled_types"]

    saved = user.put(
        client,
        "/notifications/preferences/me",
        json={"daily_digest": True, "enabled_types": {"urgent_email": False}},
    )
    assert saved.status_code == 200
    assert saved.json()["daily_digest"] is True
    assert saved.json()["enabled_types"]["urgent_email"] is False

    invalid = user.put(
        client,
        "/notifications/preferences/me",
        json={"enabled_types": {"made_up_type": True}},
    )
    assert invalid.status_code == 422


def test_notifications_are_owner_scoped(client, user, other_user):
    make_email(client, user, **URGENT_EMAIL)
    assert other_user.get(client, "/notifications").json()["total"] == 0
    assert other_user.get(client, "/notifications/unread-count").json()["unread"] == 0


def test_endpoints_require_authentication(client):
    for path in ("/actions", "/notifications", "/notifications/preferences/me"):
        assert client.get(f"{API}{path}").status_code == 401
