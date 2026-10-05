"""Health probes, OpenAPI contract, error envelopes and core primitives."""

from __future__ import annotations

import jwt
import pytest

from app.core.config import settings
from app.core.errors import UnauthorizedError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_token,
    hash_password,
    hash_token,
    tokens_match,
    validate_password_strength,
    verify_password,
)
from tests.conftest import API


def test_health_is_public(client):
    response = client.get(f"{API}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["ai_provider"] == "mock"
    assert body["version"]


def test_readiness_checks_the_database(client):
    response = client.get(f"{API}/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "up"


def test_openapi_document_is_complete(client):
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    document = spec.json()

    assert document["openapi"].startswith("3.")
    paths = document["paths"]
    assert len(paths) >= 60
    assert all(path.startswith("/api/v1/") for path in paths)

    for required in (
        "/api/v1/auth/signup",
        "/api/v1/auth/login",
        "/api/v1/emails",
        "/api/v1/replies/email/{email_id}",
        "/api/v1/assistant/query",
        "/api/v1/dashboard/counters",
        "/api/v1/analytics",
        "/api/v1/admin/stats",
        "/api/v1/notifications",
        "/api/v1/actions",
    ):
        assert required in paths, required

    schemas = document["components"]["schemas"]
    for name in ("EmailDetail", "EmailAnalysisOut", "Page_EmailListItem_", "ErrorDetail"):
        assert name in schemas, name

    # The documented error envelope is part of the contract.
    assert set(schemas["ErrorDetail"]["properties"]) >= {"message"}


def test_unknown_route_uses_the_error_envelope(client):
    response = client.get(f"{API}/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"]
    assert body["error"]["request_id"]


def test_method_not_allowed(client, user):
    response = user.delete(client, "/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_unauthenticated_error_envelope(client):
    response = client.get(f"{API}/emails")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["request_id"]


def test_request_id_header_is_echoed(client):
    response = client.get(f"{API}/health", headers={"X-Request-ID": "req-123"})
    assert response.headers.get("x-request-id") == "req-123"


# --- security primitives ----------------------------------------------------

def test_password_hashing_round_trip():
    stored = hash_password("Sup3rSecret!1")
    assert stored != "Sup3rSecret!1"
    assert verify_password(stored, "Sup3rSecret!1") is True
    assert verify_password(stored, "nope") is False
    assert verify_password("", "anything") is False


def test_password_strength_rules():
    assert validate_password_strength("short") == ["Password must be at least 8 characters long."]
    assert validate_password_strength("password")  # too common / too short
    assert validate_password_strength("Sup3rSecret!1") == []


def test_opaque_tokens_hash_one_way():
    token = generate_token()
    digest = hash_token(token)
    assert digest != token
    assert tokens_match(token, digest) is True
    assert tokens_match("other", digest) is False


def test_access_token_round_trip_and_rejection():
    token = create_access_token(subject="42", role="user", token_id="s1")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "user"
    assert payload["type"] == "access"

    forged = jwt.encode(
        {"sub": "1", "type": "access"}, "not-the-configured-secret-key-value", algorithm="HS256"
    )
    with pytest.raises(UnauthorizedError) as exc:
        decode_access_token(forged)
    assert exc.value.code == "token_invalid"

    wrong_type = jwt.encode(
        {"sub": "1", "type": "refresh"}, settings.secret_key, algorithm="HS256"
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(wrong_type)


def test_expired_access_token_is_reported():
    token = create_access_token(subject="1", role="user", token_id="s1", expires_minutes=-1)
    with pytest.raises(UnauthorizedError) as exc:
        decode_access_token(token)
    assert exc.value.code == "token_expired"


def test_sliding_window_rate_limiter():
    limiter = SlidingWindowRateLimiter(window_seconds=60)
    assert limiter.allow("k", 2, now=0.0) is True
    assert limiter.allow("k", 2, now=0.1) is True
    assert limiter.allow("k", 2, now=0.2) is False
    assert limiter.remaining("k", 2, now=0.2) == 0
    # A different key has its own budget.
    assert limiter.allow("other", 2, now=0.2) is True
    # Once the window rolls over the budget is restored.
    assert limiter.allow("k", 2, now=61.0) is True


def test_rate_limits_are_disabled_in_the_test_run():
    from app.core.config import settings as live_settings

    assert live_settings.rate_limit_enabled is False
