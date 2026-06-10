"""Shared fixtures and helpers for the hop-core test suite."""

import os
import uuid
import pytest
from functools import lru_cache
from starlette.testclient import TestClient

import hop_core.core.security as _security
from hop_core.config import HopCoreSettings
from hop_core.app_factory import create_hop_app

_TEST_DB_PATH = "/tmp/hop_core_test.db"


class _TestSettings(HopCoreSettings):
    redis_url: str = "redis://localhost:6379"

    class Config(HopCoreSettings.Config):
        env_file = "/dev/null"


@lru_cache
def _get_test_settings() -> _TestSettings:
    return _TestSettings(
        app_secret_key="test-secret-key-for-unit-tests-only-1",
        database_url=f"sqlite:///{_TEST_DB_PATH}",
        jwt_secret_key="test-jwt-secret-key-for-unit-tests-12",
        encryption_key="test-encryption-key-for-tests",
    )


@pytest.fixture(scope="session", autouse=True)
def _clean_test_db():
    _security._fernet = None
    _security._legacy_fernet = None
    try:
        os.remove(_TEST_DB_PATH)
    except FileNotFoundError:
        pass


@pytest.fixture(scope="session")
def app(_clean_test_db):
    return create_hop_app(settings_factory=_get_test_settings)


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# The session-scope TestClient keeps a cookie jar that persists across tests.
# Auth cookies set during a login call would carry into the next test, making
# "unauthenticated" requests appear authenticated.  Clear them after every test.
@pytest.fixture(autouse=True)
def _clear_cookies(client):
    yield
    client.cookies.clear()


# Reset all rate-limit counters before each test so per-endpoint limits
# (e.g. "20/minute" on /auth/register) don't accumulate across the test suite.
@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from hop_core.core.rate_limit import limiter
    limiter.reset()


# ── Helpers (importable by test modules) ──────────────────────────────────────

def make_email() -> str:
    return f"test-{uuid.uuid4().hex[:8]}@example.com"


def register(client, email: str = None, password: str = "SecurePass123!") -> dict:
    email = email or make_email()
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"email": email, "password": password, "user": resp.json()}


def login(client, email: str, password: str = "SecurePass123!") -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Common fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def new_user(client):
    """Register and log in a fresh user; yields auth context dict."""
    data = register(client)
    token = login(client, data["email"], data["password"])
    return {
        "email": data["email"],
        "password": data["password"],
        "token": token,
        "headers": auth_headers(token),
    }
