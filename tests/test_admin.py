"""Admin-only surfaces: stats, accounts, categories, config and audit."""

from __future__ import annotations

from tests.conftest import API, URGENT_EMAIL, make_email


def error_of(response) -> dict:
    body = response.json()
    assert "error" in body, body
    return body["error"]


def test_admin_endpoints_reject_non_admins(client, user):
    for path in (
        "/admin/stats",
        "/admin/users",
        "/admin/ai/usage",
        "/admin/ai/errors",
        "/admin/audit-logs",
        "/admin/categories",
        "/admin/config",
    ):
        response = user.get(client, path)
        assert response.status_code in {401, 403}, path
        if response.status_code == 403:
            assert error_of(response)["code"] == "forbidden"


def test_stats_are_global(client, user, other_user, admin):
    make_email(client, user, **URGENT_EMAIL)
    make_email(client, other_user, subject="Second", body_text="Body for the second account.")

    stats = admin.get(client, "/admin/stats").json()
    assert stats["users_total"] >= 3
    assert stats["users_active"] >= 3
    assert stats["emails_total"] >= 2
    assert stats["emails_processed"] >= 2
    assert stats["analysis_total"] >= 2
    assert stats["ai_calls_total"] >= 2
    assert stats["ai_calls_failed"] == 0
    assert isinstance(stats["ai_errors_last_24h"], int)


def test_user_list_and_update(client, user, admin):
    make_email(client, user, **URGENT_EMAIL)

    listing = admin.get(client, "/admin/users").json()
    assert listing["total"] >= 3
    target = next(row for row in listing["items"] if row["id"] == user.id)
    assert target["email_count"] == 1

    filtered = admin.get(client, "/admin/users", params={"q": user.email}).json()
    assert [row["id"] for row in filtered["items"]] == [user.id]

    role_filtered = admin.get(client, "/admin/users", params={"role": "admin"}).json()
    assert all(row["role"] == "admin" for row in role_filtered["items"])

    invalid_role = admin.get(client, "/admin/users", params={"role": "root"})
    assert invalid_role.status_code == 422

    updated = admin.patch(
        client, f"/admin/users/{user.id}", json={"role": "admin", "is_verified": True}
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "admin"
    assert updated.json()["is_verified"] is True

    missing = admin.patch(client, "/admin/users/999999", json={"is_active": False})
    assert missing.status_code == 404


def test_admin_cannot_demote_or_deactivate_self(client, admin):
    demote = admin.patch(client, f"/admin/users/{admin.id}", json={"role": "user"})
    assert demote.status_code == 422

    deactivate = admin.patch(client, f"/admin/users/{admin.id}", json={"is_active": False})
    assert deactivate.status_code == 422


def test_category_crud(client, admin):
    listing = admin.get(client, "/admin/categories").json()
    assert len(listing) >= 5

    created = admin.post(
        client,
        "/admin/categories",
        json={"key": "partnership", "label": "Partnership", "description": "Partner mail"},
    )
    assert created.status_code == 201
    category_id = created.json()["id"]

    duplicate = admin.post(client, "/admin/categories", json={"key": "partnership", "label": "Dup"})
    assert duplicate.status_code == 409

    invalid_key = admin.post(client, "/admin/categories", json={"key": "Bad Key", "label": "x"})
    assert invalid_key.status_code == 422

    updated = admin.patch(
        client, f"/admin/categories/{category_id}", json={"is_active": False, "sort_order": 50}
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False
    assert updated.json()["sort_order"] == 50

    assert admin.patch(
        client, "/admin/categories/999999", json={"label": "nope"}
    ).status_code == 404


def test_system_config_round_trip(client, admin):
    listed = admin.get(client, "/admin/config").json()
    assert isinstance(listed, list)

    stored = admin.put(
        client,
        "/admin/config/ai_summary_length",
        json={"value": 240, "description": "Characters used for short summaries."},
    )
    assert stored.status_code == 200
    assert stored.json()["value"] == 240
    assert stored.json()["updated_by"] == admin.id

    updated = admin.put(
        client, "/admin/config/ai_summary_length", json={"value": 400, "description": "Bigger."}
    )
    assert updated.json()["value"] == 400

    assert admin.put(
        client, "/admin/config/" + "x" * 200, json={"value": 1}
    ).status_code == 422

    keys = [row["key"] for row in admin.get(client, "/admin/config").json()]
    assert "ai_summary_length" in keys


def test_audit_log_is_recorded_and_filterable(client, user, admin):
    make_email(client, user, **URGENT_EMAIL)

    logs = admin.get(client, "/admin/audit-logs").json()
    actions = {row["action"] for row in logs}
    assert "auth.signup" in actions
    assert "email.create" in actions

    filtered = admin.get(client, "/admin/audit-logs", params={"action": "email.create"}).json()
    assert filtered
    assert all(row["action"] == "email.create" for row in filtered)


def test_ai_usage_and_error_endpoints(client, user, admin):
    make_email(client, user, **URGENT_EMAIL)

    usage = admin.get(client, "/admin/ai/usage").json()
    assert len(usage) >= 1
    assert all(row["purpose"] in {"analysis", "reply", "assistant"} for row in usage)
    assert all(row["status"] in {"success", "error"} for row in usage)

    errors = admin.get(client, "/admin/ai/errors").json()
    assert isinstance(errors, list)

    analysis_only = admin.get(client, "/admin/ai/usage", params={"purpose": "analysis"}).json()
    assert analysis_only
    assert all(row["purpose"] == "analysis" for row in analysis_only)


def test_admin_requires_authentication(client):
    assert client.get(f"{API}/admin/stats").status_code == 401
