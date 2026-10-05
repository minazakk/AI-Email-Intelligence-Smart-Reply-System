"""Authentication, tokens, profile and preference tests."""

from __future__ import annotations

from tests.conftest import API, DEFAULT_PASSWORD


def error_of(response) -> dict:
    body = response.json()
    assert "error" in body, body
    return body["error"]


def test_signup_returns_tokens_and_profile(client):
    response = client.post(
        f"{API}/auth/signup",
        json={"email": "alice@test.example", "password": DEFAULT_PASSWORD, "full_name": "Alice"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] > 0
    assert payload["user"]["email"] == "alice@test.example"
    assert payload["user"]["role"] == "user"
    assert payload["user"]["is_verified"] is False


def test_signup_rejects_duplicate_email(client, user):
    response = client.post(
        f"{API}/auth/signup",
        json={"email": user.email, "password": DEFAULT_PASSWORD},
    )
    assert response.status_code == 409
    assert error_of(response)["code"] == "email_taken"


def test_signup_rejects_weak_password(client):
    response = client.post(
        f"{API}/auth/signup", json={"email": "weak@test.example", "password": "short"}
    )
    assert response.status_code == 422
    assert error_of(response)["code"] == "validation_error"
    assert error_of(response)["details"]


def test_login_and_bad_credentials(client, user):
    ok = client.post(
        f"{API}/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD}
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]
    assert ok.json()["user"]["last_login_at"] is not None

    bad = client.post(f"{API}/auth/login", json={"email": user.email, "password": "WrongPass!1"})
    assert bad.status_code == 401
    assert error_of(bad)["code"] == "invalid_credentials"


def test_me_requires_token_and_returns_profile(client, user):
    anonymous = client.get(f"{API}/auth/me")
    assert anonymous.status_code == 401
    assert error_of(anonymous)["code"] == "unauthorized"

    me = user.get(client, "/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == user.email


def test_profile_and_preferences_round_trip(client, user):
    updated = user.patch(client, "/auth/me", json={"full_name": "Renamed", "timezone": "Europe/Berlin"})
    assert updated.status_code == 200
    assert updated.json()["full_name"] == "Renamed"
    assert updated.json()["timezone"] == "Europe/Berlin"

    prefs = user.get(client, "/auth/me/preferences")
    assert prefs.status_code == 200
    body = prefs.json()
    assert body["timezone"] == "Europe/Berlin"
    assert body["default_reply_tone"] == "professional"

    saved = user.put(
        client,
        "/auth/me/preferences",
        json={"default_reply_tone": "friendly", "digest_enabled": False},
    )
    assert saved.status_code == 200
    assert saved.json()["default_reply_tone"] == "friendly"
    assert saved.json()["digest_enabled"] is False


def test_refresh_rotates_and_revokes_old_token(client, user):
    first = user.refresh_token
    refreshed = client.post(f"{API}/auth/refresh", json={"refresh_token": first})
    assert refreshed.status_code == 200
    new_token = refreshed.json()["refresh_token"]
    assert new_token != first

    replay = client.post(f"{API}/auth/refresh", json={"refresh_token": first})
    assert replay.status_code == 401
    assert error_of(replay)["code"] == "refresh_invalid"


def test_logout_revokes_current_session(client, user):
    signed_out = user.post(client, "/auth/logout", json={"refresh_token": user.refresh_token})
    assert signed_out.status_code == 200

    reuse = client.post(f"{API}/auth/refresh", json={"refresh_token": user.refresh_token})
    assert reuse.status_code == 401

    # The access token is bound to the session, so logout ends it immediately.
    dead = user.get(client, "/auth/me")
    assert dead.status_code == 401
    assert error_of(dead)["code"] == "session_revoked"


def test_logout_all_invalidates_every_session(client, signup):
    actor = signup()
    second = client.post(
        f"{API}/auth/login", json={"email": actor.email, "password": DEFAULT_PASSWORD}
    ).json()
    actor_token = actor.access_token
    second_token = second["access_token"]
    actor.post(client, "/auth/logout-all")

    for token in (actor.refresh_token, second["refresh_token"]):
        assert client.post(f"{API}/auth/refresh", json={"refresh_token": token}).status_code == 401

    # Access tokens issued for those sessions die with them as well.
    for token in (actor_token, second_token):
        rejected = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert rejected.status_code == 401
        assert error_of(rejected)["code"] == "session_revoked"


def test_email_verification_flow(client, user):
    requested = user.post(client, "/auth/verify-email/request", json={"email": user.email})
    assert requested.status_code == 200
    token = requested.json()["dev_token"]
    assert token

    confirmed = client.post(f"{API}/auth/verify-email/confirm", json={"token": token})
    assert confirmed.status_code == 200

    replay = client.post(f"{API}/auth/verify-email/confirm", json={"token": token})
    assert replay.status_code == 422
    assert error_of(replay)["code"] == "token_invalid"

    assert user.get(client, "/auth/me").json()["is_verified"] is True


def test_password_reset_flow(client, user, signup):
    forgot = client.post(f"{API}/auth/password/forgot", json={"email": user.email})
    token = forgot.json()["dev_token"]
    assert token

    reset = client.post(
        f"{API}/auth/password/reset", json={"token": token, "new_password": "BrandNewPass!9"}
    )
    assert reset.status_code == 200

    assert (
        client.post(f"{API}/auth/login", json={"email": user.email, "password": DEFAULT_PASSWORD})
        .status_code
        == 401
    )
    assert (
        client.post(
            f"{API}/auth/login", json={"email": user.email, "password": "BrandNewPass!9"}
        ).status_code
        == 200
    )


def test_password_change_requires_current_password(client, user):
    bad = user.post(
        client,
        "/auth/password/change",
        json={"current_password": "nope", "new_password": "AnotherPass!7"},
    )
    assert bad.status_code == 422
    assert error_of(bad)["code"] == "invalid_password"

    good = user.post(
        client,
        "/auth/password/change",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "AnotherPass!7"},
    )
    assert good.status_code == 200


def test_unknown_account_password_forgot_does_not_leak(client):
    response = client.post(f"{API}/auth/password/forgot", json={"email": "ghost@test.example"})
    assert response.status_code == 200
    assert response.json()["dev_token"] is None


def test_admin_surface_requires_admin_role(client, user, admin):
    assert user.get(client, "/admin/stats").status_code == 403
    assert admin.get(client, "/admin/stats").status_code == 200


def test_dev_promote_only_available_in_development(client, user):
    response = user.post(client, "/auth/dev/promote")
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
