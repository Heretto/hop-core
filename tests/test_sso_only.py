"""SSO_ONLY: the identity provider is the only way in."""

import uuid

import pytest

from hop_core.config import get_settings
from hop_core.core.security import (
    create_access_token, create_password_reset_token, create_refresh_token,
)
from hop_core.db import get_session_factory
from tests.conftest import register, login, auth_headers, make_email

SSO_DETAIL = "Password sign-in is disabled. Please sign in using SSO."


@pytest.fixture
def sso_only(monkeypatch):
    monkeypatch.setattr(get_settings(), "sso_only", True)


@pytest.fixture
def db():
    session = get_session_factory()()
    yield session
    session.close()


def _sso_user(db, email=None):
    """Create (or link) an account through the SSO path; return auth headers and the user."""
    from hop_core.api.routes.sso import _build_token_data, _handle_sso_login

    user = _handle_sso_login(db, "google", f"google-{uuid.uuid4().hex}", email or make_email(), None)
    token = create_access_token(data=_build_token_data(user, db))
    return auth_headers(token), user


def _invite(client, admin_headers, email):
    resp = client.post("/api/v1/organizations/invitations", headers=admin_headers,
                       json={"email": email, "role": "member"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


class TestFlagOff:
    """Nothing changes unless the flag is set."""

    def test_password_login_and_reset_work(self, client):
        data = register(client)
        assert login(client, data["email"], data["password"])
        resp = client.post("/api/v1/auth/reset-password", json={
            "token": create_password_reset_token(data["email"]), "new_password": "NewPass456!",
        })
        assert resp.status_code == 200


class TestPasswordEndpointsRefused:
    def test_register(self, client, sso_only):
        resp = client.post("/api/v1/auth/register",
                           json={"email": make_email(), "password": "SecurePass123!"})
        assert resp.status_code == 403

    def test_login_with_a_correct_password(self, client, monkeypatch):
        data = register(client)
        monkeypatch.setattr(get_settings(), "sso_only", True)
        resp = client.post("/api/v1/auth/login",
                           json={"email": data["email"], "password": data["password"]})
        assert resp.status_code == 403
        assert resp.json()["detail"] == SSO_DETAIL
        assert "access_token" not in resp.cookies

    def test_forgot_password(self, client, sso_only):
        resp = client.post("/api/v1/auth/forgot-password", json={"email": make_email()})
        assert resp.status_code == 403

    def test_reset_password_with_a_token_issued_before_the_flag(self, client, monkeypatch):
        data = register(client)
        token = create_password_reset_token(data["email"])
        monkeypatch.setattr(get_settings(), "sso_only", True)
        resp = client.post("/api/v1/auth/reset-password",
                           json={"token": token, "new_password": "NewPass456!"})
        assert resp.status_code == 403

    def test_invitation_accept_as_new_user(self, client, new_user, monkeypatch):
        token = _invite(client, new_user["headers"], make_email())
        client.cookies.clear()
        monkeypatch.setattr(get_settings(), "sso_only", True)
        resp = client.post(f"/api/v1/invitations/accept/{token}",
                           json={"password": "NewUserPass123!", "confirm_password": "NewUserPass123!"})
        assert resp.status_code == 403

    def test_invitation_accept_as_existing_user_with_password(self, client, new_user, monkeypatch):
        invitee = register(client)
        token = _invite(client, new_user["headers"], invitee["email"])
        client.cookies.clear()
        monkeypatch.setattr(get_settings(), "sso_only", True)
        resp = client.post(f"/api/v1/invitations/accept-existing/{token}",
                           json={"password": invitee["password"]})
        assert resp.status_code == 403


class TestExistingSessions:
    def test_password_only_account_cannot_refresh(self, client, db, monkeypatch):
        data = register(client)
        user_id = data["user"]["id"]
        monkeypatch.setattr(get_settings(), "sso_only", True)
        resp = client.post("/api/v1/auth/refresh",
                           json={"refresh_token": create_refresh_token({"sub": user_id})})
        assert resp.status_code == 401

    def test_sso_linked_account_can_refresh(self, client, db, sso_only):
        _, user = _sso_user(db)
        resp = client.post("/api/v1/auth/refresh",
                           json={"refresh_token": create_refresh_token({"sub": str(user.id)})})
        assert resp.status_code == 200, resp.text

    def test_password_account_moves_over_by_signing_in_with_sso(self, client, db, monkeypatch):
        data = register(client)
        monkeypatch.setattr(get_settings(), "sso_only", True)
        _, user = _sso_user(db, data["email"])
        assert str(user.id) == data["user"]["id"]
        resp = client.post("/api/v1/auth/refresh",
                           json={"refresh_token": create_refresh_token({"sub": str(user.id)})})
        assert resp.status_code == 200


class TestInvitationsThroughSso:
    def test_sso_user_accepts_through_the_authenticated_route(self, client, db, sso_only):
        admin_headers, _ = _sso_user(db)
        invitee_email = make_email()
        token = _invite(client, admin_headers, invitee_email)

        invitee_headers, _ = _sso_user(db, invitee_email)
        resp = client.post(f"/api/v1/organizations/invitations/accept/{token}", headers=invitee_headers)
        assert resp.status_code == 200, resp.text


class TestAccountSettings:
    def test_password_change_refused(self, client, db, sso_only):
        headers, _ = _sso_user(db)
        resp = client.put("/api/v1/account/me", headers=headers, json={"new_password": "NewPass456!"})
        assert resp.status_code == 403

    def test_email_change_refused(self, client, db, sso_only):
        headers, user = _sso_user(db)
        resp = client.put("/api/v1/account/me", headers=headers, json={"email": make_email()})
        assert resp.status_code == 403

    def test_resubmitting_the_current_email_is_allowed(self, client, db, sso_only):
        headers, user = _sso_user(db)
        resp = client.put("/api/v1/account/me", headers=headers, json={"email": user.email})
        assert resp.status_code == 200

    def test_providers_endpoint_reports_the_flag(self, client, sso_only):
        assert client.get("/api/v1/auth/sso/providers").json()["sso_only"] is True
