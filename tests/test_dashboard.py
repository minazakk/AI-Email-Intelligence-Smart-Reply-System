"""Dashboard counters, distributions and the analytics report."""

from __future__ import annotations

from tests.conftest import API, COMPLAINT_EMAIL, QUIET_EMAIL, URGENT_EMAIL, make_email


def test_counters_reflect_the_inbox(client, user):
    make_email(client, user, **URGENT_EMAIL)
    make_email(client, user, **QUIET_EMAIL)

    counters = user.get(client, "/dashboard/counters").json()
    assert counters["total_emails"] == 2
    assert counters["unread_emails"] == 2
    assert counters["urgent_emails"] == 1
    assert counters["reply_required"] >= 1
    assert counters["processed_emails"] == 2
    assert counters["failed_emails"] == 0
    assert counters["pending_processing"] == 0


def test_counters_are_per_user(client, user, other_user):
    make_email(client, user, **URGENT_EMAIL)
    assert other_user.get(client, "/dashboard/counters").json()["total_emails"] == 0


def test_summary_bundle(client, user):
    make_email(client, user, **URGENT_EMAIL)
    make_email(client, user, **COMPLAINT_EMAIL)

    summary = user.get(client, "/dashboard/summary").json()
    assert summary["counters"]["total_emails"] == 2
    assert summary["category_distribution"]
    assert summary["sentiment_distribution"]
    assert summary["priority_distribution"]
    assert isinstance(summary["recent_emails"], list)
    assert isinstance(summary["recent_activity"], list)

    total = sum(row["count"] for row in summary["category_distribution"])
    assert total == 2


def test_distributions_add_up(client, user):
    make_email(client, user, **URGENT_EMAIL)
    make_email(client, user, **COMPLAINT_EMAIL)

    categories = user.get(client, "/dashboard/categories").json()
    priorities = user.get(client, "/dashboard/priorities").json()
    sentiments = user.get(client, "/dashboard/sentiments").json()

    assert sum(row["count"] for row in categories) == 2
    assert sum(row["count"] for row in priorities) == 2
    assert sum(row["count"] for row in sentiments) == 2
    percentages = [row["percentage"] for row in categories]
    assert all(0.0 <= p <= 100.0 for p in percentages)


def test_recent_emails_and_activity(client, user):
    make_email(client, user, **URGENT_EMAIL)
    make_email(client, user, **COMPLAINT_EMAIL)

    recent = user.get(client, "/dashboard/recent-emails", params={"limit": 1}).json()
    assert len(recent) == 1

    activity = user.get(client, "/dashboard/activity", params={"days": 365}).json()
    assert isinstance(activity, list)


def test_analytics_report_over_a_range(client, user):
    make_email(client, user, **URGENT_EMAIL)
    make_email(client, user, **COMPLAINT_EMAIL)

    report = user.get(
        client,
        "/analytics",
        params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
    ).json()
    assert report["date_from"] == "2026-01-01"
    assert report["date_to"] == "2026-01-31"
    assert report["emails_received"] == 2
    assert report["urgent_emails"] >= 1
    assert report["customer_complaints"] >= 1
    assert report["by_category"]
    assert report["pending_actions"] >= 0


def test_analytics_rejects_inverted_range(client, user):
    response = user.get(
        client,
        "/analytics",
        params={"date_from": "2026-02-01", "date_to": "2026-01-01"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_analytics_rejects_bad_date_format(client, user):
    response = user.get(
        client, "/analytics", params={"date_from": "01/02/2026"}
    )
    assert response.status_code == 422


def test_dashboard_requires_authentication(client):
    assert client.get(f"{API}/dashboard/counters").status_code == 401
    assert client.get(f"{API}/analytics").status_code == 401
