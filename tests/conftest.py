"""Shared pytest fixtures.

Every environment variable is pinned *before* any ``app.*`` import so the
application builds its engine against a throwaway SQLite database instead of
the live PostgreSQL instance configured in ``.env``.
"""

from __future__ import annotations

import os
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DIR = ROOT / ".test_tmp"
TEST_DIR.mkdir(exist_ok=True)
TEST_DB = TEST_DIR / "pytest.db"
if TEST_DB.exists():
    TEST_DB.unlink()

# Point this at a throwaway PostgreSQL database to run the same suite against
# the production engine, e.g.
#   $env:RUNTIME_TEST_DB_URL="postgresql+psycopg://email_intel:...@127.0.0.1:5432/email_intelligence_test"
TEST_URL = os.environ.get("RUNTIME_TEST_DB_URL") or f"sqlite+pysqlite:///{TEST_DB.as_posix()}"
os.environ.update(
    {
        "DATABASE_URL": TEST_URL,
        "TEST_DATABASE_URL": TEST_URL,
        "APP_ENV": "development",
        "DEBUG": "true",
        "SECRET_KEY": "pytest-only-secret-key-do-not-reuse",
        "RATE_LIMIT_ENABLED": "false",
        "AI_PROVIDER": "mock",
        "AI_API_KEY": "",
        "LOG_JSON": "false",
        "LOG_LEVEL": "WARNING",
        "DEV_MODE_ENABLE_TOKEN_LINKS": "true",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401  (registers every table on Base.metadata)
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402

API = "/api/v1"
DEFAULT_PASSWORD = "Sup3rSecret!1"


# --- database ---------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# --- HTTP -------------------------------------------------------------------

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


# --- actors -----------------------------------------------------------------

class Actor:
    """A signed-in user plus a convenience wrapper for authenticated calls."""

    def __init__(self, payload: dict) -> None:
        self.access_token = payload["access_token"]
        self.refresh_token = payload["refresh_token"]
        self.user = payload["user"]

    @property
    def id(self) -> int:
        return int(self.user["id"])

    @property
    def email(self) -> str:
        return str(self.user["email"])

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def get(self, client: TestClient, path: str, **kwargs):
        return client.get(f"{API}{path}", headers=self.headers, **kwargs)

    def post(self, client: TestClient, path: str, **kwargs):
        return client.post(f"{API}{path}", headers=self.headers, **kwargs)

    def patch(self, client: TestClient, path: str, **kwargs):
        return client.patch(f"{API}{path}", headers=self.headers, **kwargs)

    def put(self, client: TestClient, path: str, **kwargs):
        return client.put(f"{API}{path}", headers=self.headers, **kwargs)

    def delete(self, client: TestClient, path: str, **kwargs):
        return client.delete(f"{API}{path}", headers=self.headers, **kwargs)


@pytest.fixture()
def signup(client):
    def _signup(
        *,
        email: str | None = None,
        password: str = DEFAULT_PASSWORD,
        full_name: str = "Test User",
    ) -> Actor:
        body = {
            "email": email or f"user{uuid.uuid4().hex[:16]}@test.example",
            "password": password,
            "full_name": full_name,
        }
        response = client.post(f"{API}/auth/signup", json=body)
        assert response.status_code == 201, response.text
        return Actor(response.json())

    return _signup


@pytest.fixture()
def user(signup) -> Actor:
    """A standard ``user``-role account."""
    return signup(full_name="Regular User")


@pytest.fixture()
def other_user(signup) -> Actor:
    """A second account used for tenant-isolation assertions."""
    return signup(full_name="Other User")


@pytest.fixture()
def admin(signup, db) -> Actor:
    actor = signup(full_name="Admin User")
    row = db.get(User, actor.id)
    row.role = "admin"
    db.commit()
    db.refresh(row)
    actor.user["role"] = "admin"
    return actor


# --- helpers ----------------------------------------------------------------

def make_email(client: TestClient, actor: Actor, **overrides) -> dict:
    """POST an email and assert it was stored (and analysed)."""
    payload = {
        "subject": "Quarterly invoice for order ORD-1001",
        "from_name": "Acme Billing",
        "from_address": "billing@acme.test",
        "to": [actor.email],
        "body_text": "Please find the invoice for order ORD-1001 attached.",
        "received_at": "2026-01-15T09:30:00+00:00",
    }
    payload.update(overrides)
    response = actor.post(client, "/emails", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


URGENT_EMAIL = {
    "subject": "URGENT: production server is down",
    "from_name": "Acme Ops",
    "from_address": "ops@acme.test",
    "body_text": (
        "Our production server has been down since 09:00 and customers are "
        "affected. This is urgent - please respond ASAP. Order ORD-9911 for "
        "1500.00 must ship by 2026-10-05."
    ),
    "received_at": "2026-01-16T08:00:00+00:00",
}

COMPLAINT_EMAIL = {
    "subject": "Complaint about my recent order",
    "from_name": "Jane Customer",
    "from_address": "jane@customer.test",
    "body_text": (
        "I am very unhappy with the product I received. The delivery was late "
        "and the box was damaged. I want a refund for order ORD-5555. This is "
        "unacceptable and I expect a reply today."
    ),
    "received_at": "2026-01-17T11:00:00+00:00",
}

QUIET_EMAIL = {
    "subject": "Newsletter: product tips for January",
    "from_name": "Acme Marketing",
    "from_address": "news@acme.test",
    "body_text": "Here are five tips for getting the most out of your account.",
    "received_at": "2026-01-18T07:00:00+00:00",
}
