"""Tests for invitation create/list/cancel/accept flows."""

import pytest
from tests.conftest import register, login, auth_headers, make_email


@pytest.fixture
def admin_session(client):
    """Admin user with a pending invitation already created."""
    data = register(client)
    token = login(client, data["email"], data["password"])
    headers = auth_headers(token)
    invitee_email = make_email()

    invite_resp = client.post("/api/v1/organizations/invitations", headers=headers, json={
        "email": invitee_email,
        "role": "member",
    })
    assert invite_resp.status_code == 200, invite_resp.text
    invitation = invite_resp.json()

    return {
        "admin_email": data["email"],
        "admin_password": data["password"],
        "headers": headers,
        "invitee_email": invitee_email,
        "invitation": invitation,
        "token": invitation["token"],
    }


class TestCreateInvitation:
    def test_admin_creates_invitation(self, client, new_user):
        resp = client.post("/api/v1/organizations/invitations", headers=new_user["headers"], json={
            "email": make_email(),
            "role": "member",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body
        assert body["role"] == "member"
        assert "email" in body

    def test_admin_can_invite_as_admin_role(self, client, new_user):
        resp = client.post("/api/v1/organizations/invitations", headers=new_user["headers"], json={
            "email": make_email(),
            "role": "admin",
        })
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    def test_duplicate_invite_rejected(self, client, new_user):
        email = make_email()
        client.post("/api/v1/organizations/invitations", headers=new_user["headers"],
                    json={"email": email, "role": "member"})
        resp = client.post("/api/v1/organizations/invitations", headers=new_user["headers"],
                           json={"email": email, "role": "member"})
        assert resp.status_code == 400


class TestListInvitations:
    def test_lists_pending_invitations(self, client, admin_session):
        resp = client.get("/api/v1/organizations/invitations", headers=admin_session["headers"])
        assert resp.status_code == 200
        invites = resp.json()
        assert any(i["email"] == admin_session["invitee_email"] for i in invites)

    def test_unauthenticated_rejected(self, client):
        resp = client.get("/api/v1/organizations/invitations")
        assert resp.status_code == 401


class TestCancelInvitation:
    def test_cancel_removes_from_list(self, client, admin_session):
        inv_id = admin_session["invitation"]["id"]
        resp = client.delete(f"/api/v1/organizations/invitations/{inv_id}",
                             headers=admin_session["headers"])
        assert resp.status_code == 200

        list_resp = client.get("/api/v1/organizations/invitations",
                               headers=admin_session["headers"])
        assert not any(i["id"] == inv_id for i in list_resp.json())

    def test_cancel_nonexistent_rejected(self, client, new_user):
        import uuid
        resp = client.delete(f"/api/v1/organizations/invitations/{uuid.uuid4()}",
                             headers=new_user["headers"])
        assert resp.status_code == 404


class TestInvitationInfo:
    def test_unauthenticated_can_get_info(self, client, admin_session):
        resp = client.get(f"/api/v1/invitations/info/{admin_session['token']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == admin_session["invitee_email"]
        assert "organization_name" in body
        assert "role" in body
        assert "expires_at" in body

    def test_invalid_token_returns_404(self, client):
        resp = client.get("/api/v1/invitations/info/totally-bogus-token")
        assert resp.status_code == 404


class TestAcceptInvitationNewUser:
    def test_new_user_can_accept(self, client, new_user):
        invitee_email = make_email()
        invite_resp = client.post("/api/v1/organizations/invitations",
                                  headers=new_user["headers"],
                                  json={"email": invitee_email, "role": "member"})
        token = invite_resp.json()["token"]

        # Clear admin cookies so the accept request looks unauthenticated
        client.cookies.clear()

        resp = client.post(f"/api/v1/invitations/accept/{token}", json={
            "password": "NewUserPass123!",
            "confirm_password": "NewUserPass123!",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == invitee_email

        # Can now log in with the chosen password
        new_token = login(client, invitee_email, "NewUserPass123!")
        assert new_token

    def test_password_mismatch_rejected(self, client, new_user):
        invitee_email = make_email()
        invite_resp = client.post("/api/v1/organizations/invitations",
                                  headers=new_user["headers"],
                                  json={"email": invitee_email, "role": "member"})
        token = invite_resp.json()["token"]

        client.cookies.clear()
        resp = client.post(f"/api/v1/invitations/accept/{token}", json={
            "password": "Pass123!",
            "confirm_password": "Different123!",
        })
        assert resp.status_code == 400

    def test_password_too_short_rejected(self, client, new_user):
        invitee_email = make_email()
        invite_resp = client.post("/api/v1/organizations/invitations",
                                  headers=new_user["headers"],
                                  json={"email": invitee_email, "role": "member"})
        token = invite_resp.json()["token"]

        client.cookies.clear()
        resp = client.post(f"/api/v1/invitations/accept/{token}", json={
            "password": "short",
            "confirm_password": "short",
        })
        assert resp.status_code == 400


class TestAcceptInvitationExistingUser:
    def test_existing_user_accepts_via_org_route(self, client, new_user):
        # Register the invitee as an existing user
        invitee = register(client)
        invitee_token = login(client, invitee["email"], invitee["password"])
        invitee_headers = auth_headers(invitee_token)

        # Admin invites the existing user
        invite_resp = client.post("/api/v1/organizations/invitations",
                                  headers=new_user["headers"],
                                  json={"email": invitee["email"], "role": "member"})
        assert invite_resp.status_code == 200, invite_resp.text
        token = invite_resp.json()["token"]

        # Existing user accepts via the authenticated route
        resp = client.post(f"/api/v1/organizations/invitations/accept/{token}",
                           headers=invitee_headers)
        assert resp.status_code == 200

    def test_existing_user_wrong_email_rejected(self, client, new_user):
        invitee_email = make_email()
        invite_resp = client.post("/api/v1/organizations/invitations",
                                  headers=new_user["headers"],
                                  json={"email": invitee_email, "role": "member"})
        token = invite_resp.json()["token"]

        # A different user tries to accept
        other = register(client)
        other_token = login(client, other["email"], other["password"])
        resp = client.post(f"/api/v1/organizations/invitations/accept/{token}",
                           headers=auth_headers(other_token))
        assert resp.status_code == 403
