"""Tests for /api/v1/auth/* endpoints."""

from tests.conftest import register, login, make_email


class TestRegister:
    def test_success(self, client):
        data = register(client)
        u = data["user"]
        assert u["email"] == data["email"]
        assert "id" in u

    def test_with_custom_org_name(self, client):
        email = make_email()
        resp = client.post("/api/v1/auth/register", json={
            "email": email,
            "password": "SecurePass123!",
            "organization_name": f"Org for {email}",
        })
        assert resp.status_code == 200

    def test_duplicate_email_rejected(self, client):
        data = register(client)
        resp = client.post("/api/v1/auth/register", json={
            "email": data["email"],
            "password": "AnotherPass123!",
        })
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"].lower()

    def test_password_too_short_rejected(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": make_email(),
            "password": "short",
        })
        assert resp.status_code == 422

    def test_invalid_email_rejected(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "email": "notanemail",
            "password": "SecurePass123!",
        })
        assert resp.status_code == 422


class TestLogin:
    def test_success_returns_tokens(self, client):
        data = register(client)
        resp = client.post("/api/v1/auth/login", json={
            "email": data["email"],
            "password": data["password"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert "expires_at" in body
        assert len(body.get("organizations", [])) >= 1

    def test_wrong_password_rejected(self, client):
        data = register(client)
        resp = client.post("/api/v1/auth/login", json={
            "email": data["email"],
            "password": "WrongPassword!",
        })
        assert resp.status_code == 401

    def test_unknown_email_rejected(self, client):
        resp = client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "SecurePass123!",
        })
        assert resp.status_code == 401


class TestLogout:
    def test_clears_session(self, client, new_user):
        resp = client.post("/api/v1/auth/logout", headers=new_user["headers"])
        assert resp.status_code == 200
        assert "logged out" in resp.json()["message"].lower()


class TestRefresh:
    def test_success_issues_new_token(self, client):
        data = register(client)
        login_resp = client.post("/api/v1/auth/login", json={
            "email": data["email"],
            "password": data["password"],
        })
        refresh_token = login_resp.json()["refresh_token"]

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    def test_invalid_token_rejected(self, client):
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "not.a.real.token"})
        assert resp.status_code == 401

    def test_missing_token_rejected(self, client):
        resp = client.post("/api/v1/auth/refresh", json={})
        assert resp.status_code == 401


class TestForgotPassword:
    def test_returns_503_when_smtp_not_configured(self, client):
        resp = client.post("/api/v1/auth/forgot-password", json={"email": "any@example.com"})
        assert resp.status_code == 503
