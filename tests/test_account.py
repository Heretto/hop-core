"""Tests for /api/v1/account/me endpoints."""

from tests.conftest import register, login, auth_headers, make_email


class TestGetAccount:
    def test_returns_own_profile(self, client, new_user):
        resp = client.get("/api/v1/account/me", headers=new_user["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == new_user["email"]
        assert "id" in body
        assert body["is_active"] is True
        assert body["has_password"] is True

    def test_includes_org_context(self, client, new_user):
        resp = client.get("/api/v1/account/me", headers=new_user["headers"])
        body = resp.json()
        assert body["organization_id"] is not None
        assert body["organization_name"] is not None
        assert body["organization_role"] in ("admin", "member")

    def test_unauthenticated_rejected(self, client):
        resp = client.get("/api/v1/account/me")
        assert resp.status_code == 401


class TestUpdateAccount:
    def test_update_email(self, client, new_user):
        new_email = make_email()
        resp = client.put("/api/v1/account/me", headers=new_user["headers"], json={
            "email": new_email,
        })
        assert resp.status_code == 200
        assert resp.json()["email"] == new_email

    def test_update_email_to_existing_rejected(self, client, new_user):
        other = register(client)
        resp = client.put("/api/v1/account/me", headers=new_user["headers"], json={
            "email": other["email"],
        })
        assert resp.status_code == 400

    def test_change_password(self, client):
        data = register(client)
        token = login(client, data["email"], data["password"])

        resp = client.put("/api/v1/account/me", headers=auth_headers(token), json={
            "current_password": data["password"],
            "new_password": "NewSecurePass456!",
        })
        assert resp.status_code == 200

        new_token = login(client, data["email"], "NewSecurePass456!")
        assert new_token

    def test_change_password_wrong_current_rejected(self, client, new_user):
        resp = client.put("/api/v1/account/me", headers=new_user["headers"], json={
            "current_password": "WrongCurrent!",
            "new_password": "NewSecurePass456!",
        })
        assert resp.status_code == 400

    def test_new_password_too_short_rejected(self, client, new_user):
        resp = client.put("/api/v1/account/me", headers=new_user["headers"], json={
            "current_password": new_user["password"],
            "new_password": "short",
        })
        assert resp.status_code == 400


class TestDeleteAccount:
    def test_requires_confirm_flag(self, client, new_user):
        resp = client.request("DELETE", "/api/v1/account/me",
                              headers=new_user["headers"], json={"confirm": False})
        assert resp.status_code == 400

    def test_deletes_account(self, client):
        data = register(client)
        token = login(client, data["email"], data["password"])

        resp = client.request("DELETE", "/api/v1/account/me",
                              headers=auth_headers(token), json={"confirm": True})
        assert resp.status_code == 200

        login_resp = client.post("/api/v1/auth/login", json={
            "email": data["email"],
            "password": data["password"],
        })
        assert login_resp.status_code == 401
