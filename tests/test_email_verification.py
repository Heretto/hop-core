"""Email verification: REQUIRE_EMAIL_VERIFICATION gates password sign-ups."""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

import hop_core.email
from hop_core.config import configure, get_settings
from hop_core.core.security import (
    create_email_verification_token, create_password_reset_token, create_refresh_token,
)
from hop_core.db import get_session_factory
from hop_core.models.email_verification import PendingEmailVerification
from hop_core.models.user import User
from tests.conftest import _get_test_settings, make_email

PASSWORD = "SecurePass123!"


@pytest.fixture
def sent(monkeypatch):
    """Capture verification emails instead of sending them: [(email, token)]."""
    outbox = []

    async def capture(to_email, token):
        outbox.append((to_email, token))

    monkeypatch.setattr(hop_core.email, "send_verification_email", capture)
    return outbox


@pytest.fixture
def verification_on(monkeypatch, sent):
    monkeypatch.setattr(get_settings(), "require_email_verification", True)
    return sent


@pytest.fixture
def db():
    session = get_session_factory()()
    yield session
    session.close()


def _register(client, email=None):
    email = email or make_email()
    resp = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return email, resp.json()


def _login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _verify(client, token):
    return client.post("/api/v1/auth/verify-email", json={"token": token})


def _user(db, email) -> User:
    db.expire_all()
    return db.query(User).filter(User.email == email).one()


class TestFlagOff:
    def test_register_does_not_require_verification(self, client, sent):
        email, body = _register(client)
        assert body["email_verification_required"] is False
        assert sent == []
        assert _login(client, email).status_code == 200

    def test_leftover_pending_rows_are_ignored(self, client, monkeypatch, sent):
        monkeypatch.setattr(get_settings(), "require_email_verification", True)
        email, _ = _register(client)
        monkeypatch.setattr(get_settings(), "require_email_verification", False)
        assert _login(client, email).status_code == 200


class TestRegistration:
    def test_register_reports_verification_and_sends_link(self, client, verification_on):
        email, body = _register(client)
        assert body["email_verification_required"] is True
        assert [to for to, _ in verification_on] == [email]

    def test_unverified_login_is_refused_with_a_code(self, client, verification_on):
        email, _ = _register(client)
        resp = _login(client, email)
        assert resp.status_code == 403
        assert resp.json()["code"] == "email_not_verified"
        assert "access_token" not in resp.json()
        assert "access_token" not in resp.cookies

    def test_wrong_password_does_not_reveal_verification_state(self, client, verification_on):
        email, _ = _register(client)
        resp = _login(client, email, "wrong-password")
        assert resp.status_code == 401
        assert "code" not in resp.json()

    def test_failed_send_still_creates_the_account(self, client, monkeypatch):
        monkeypatch.setattr(get_settings(), "require_email_verification", True)

        async def boom(*_):
            raise ConnectionError("smtp down")

        monkeypatch.setattr(hop_core.email, "send_verification_email", boom)
        email, body = _register(client)
        assert body["email_verification_required"] is True
        assert _login(client, email).status_code == 403

    def test_existing_accounts_are_grandfathered(self, client, monkeypatch, sent):
        email, _ = _register(client)
        monkeypatch.setattr(get_settings(), "require_email_verification", True)
        assert _login(client, email).status_code == 200


class TestVerifyEmail:
    def test_link_verifies_and_login_then_succeeds(self, client, verification_on, db):
        email, _ = _register(client)
        _, token = verification_on[0]

        resp = _verify(client, token)
        assert resp.status_code == 200, resp.text
        assert _user(db, email).pending_email_verification is None
        assert _login(client, email).status_code == 200

    def test_second_click_still_succeeds(self, client, verification_on):
        _register(client)
        _, token = verification_on[0]
        assert _verify(client, token).status_code == 200
        assert _verify(client, token).status_code == 200

    def test_garbage_token_is_rejected(self, client, verification_on):
        resp = _verify(client, "not-a-token")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid verification link"

    def test_expired_token_is_rejected(self, client, verification_on, db):
        email, _ = _register(client)
        user = _user(db, email)
        settings = get_settings()
        token = jwt.encode(
            {
                "sub": str(user.id), "email": email, "type": "email_verification",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            },
            settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
        )
        resp = _verify(client, token)
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"]
        assert _login(client, email).status_code == 403

    def test_password_reset_token_is_not_accepted(self, client, verification_on):
        email, _ = _register(client)
        resp = _verify(client, create_password_reset_token(email))
        assert resp.status_code == 400
        assert _login(client, email).status_code == 403

    def test_token_for_another_address_is_rejected(self, client, verification_on, db):
        email, _ = _register(client)
        user = _user(db, email)
        resp = _verify(client, create_email_verification_token(str(user.id), make_email()))
        assert resp.status_code == 400
        assert _login(client, email).status_code == 403

    def test_token_for_unknown_user_is_rejected(self, client, verification_on):
        token = create_email_verification_token(str(uuid.uuid4()), make_email())
        assert _verify(client, token).status_code == 400

    def test_non_uuid_subject_is_rejected(self, client, verification_on):
        token = create_email_verification_token("not-a-uuid", make_email())
        assert _verify(client, token).status_code == 400


class TestResend:
    def _resend(self, client, email):
        return client.post("/api/v1/auth/resend-verification", json={"email": email})

    def test_pending_account_gets_a_new_link(self, client, verification_on):
        email, _ = _register(client)
        verification_on.clear()
        resp = self._resend(client, email)
        assert resp.status_code == 200
        assert [to for to, _ in verification_on] == [email]
        assert _verify(client, verification_on[0][1]).status_code == 200

    def test_response_is_identical_for_every_address(self, client, verification_on):
        pending, _ = _register(client)
        verified, _ = _register(client)
        _verify(client, verification_on[-1][1])
        verification_on.clear()

        bodies = {
            self._resend(client, addr).text
            for addr in (pending, verified, make_email())
        }
        assert len(bodies) == 1
        assert [to for to, _ in verification_on] == [pending]


class TestOtherPathsProveTheAddress:
    def test_password_reset_clears_pending_verification(self, client, verification_on):
        email, _ = _register(client)
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": create_password_reset_token(email), "new_password": "NewPass456!"},
        )
        assert resp.status_code == 200
        assert _login(client, email, "NewPass456!").status_code == 200

    def test_sso_link_verifies_and_drops_the_unproven_password(self, client, verification_on, db):
        from hop_core.api.routes.sso import _handle_sso_login

        email, _ = _register(client)
        _handle_sso_login(db, "google", f"google-{uuid.uuid4().hex}", email, None)

        user = _user(db, email)
        assert user.pending_email_verification is None
        assert user.password_hash is None
        assert _login(client, email).status_code == 401

    def test_sso_link_keeps_a_verified_password(self, client, monkeypatch, sent, db):
        from hop_core.api.routes.sso import _handle_sso_login

        email, _ = _register(client)
        _handle_sso_login(db, "google", f"google-{uuid.uuid4().hex}", email, None)
        assert _login(client, email).status_code == 200


class TestRefreshAndDeletion:
    def test_refresh_is_refused_while_pending(self, client, verification_on, db):
        email, _ = _register(client)
        token = create_refresh_token({"sub": str(_user(db, email).id)})
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
        assert resp.status_code == 401

    def test_deleting_the_user_removes_the_pending_row(self, client, verification_on, db):
        email, _ = _register(client)
        user = _user(db, email)
        user_id = user.id
        db.delete(user)
        db.commit()
        assert db.get(PendingEmailVerification, user_id) is None


class TestStartupGuard:
    def _settings(self, **overrides):
        base = _get_test_settings()
        return base.model_copy(update={"require_email_verification": True, **overrides})

    def _create(self, settings):
        from hop_core.app_factory import create_hop_app
        try:
            return create_hop_app(settings_factory=lambda: settings)
        finally:
            # create_hop_app registers its factory globally; put the suite's back.
            configure(_get_test_settings)

    def test_refuses_to_start_without_smtp_outside_development(self):
        with pytest.raises(RuntimeError, match="REQUIRE_EMAIL_VERIFICATION"):
            self._create(self._settings(app_env="production"))

    def test_development_starts_without_smtp(self):
        assert self._create(self._settings(app_env="development")) is not None

    def test_starts_with_smtp(self):
        settings = self._settings(app_env="production", smtp_host="smtp.example.com",
                                  smtp_from_email="noreply@example.com")
        assert self._create(settings) is not None
