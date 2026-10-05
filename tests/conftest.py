import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from ai_email import Settings, set_settings


@pytest.fixture(autouse=True)
def default_mock_settings():
    """Every test runs with explicit offline mock settings."""
    set_settings(Settings(provider="mock"))
    yield
    set_settings(Settings(provider="mock"))


@pytest.fixture()
def sample_email() -> dict:
    return {
        "subject": "Refund request for damaged order",
        "sender": "Dana Brooks <dana.brooks@example.test>",
        "recipients": ["support@ourcorp.example"],
        "body": (
            "Hi, my order ORD-55210 arrived damaged. I want a refund of 89.50 USD "
            "within 3 days. Please confirm by Friday. My name is Dana Brooks."
        ),
        "received_at": "2025-09-22T09:00:00+00:00",
        "message_id": "msg-001",
    }
