"""Tests for /api/v1/organizations/* endpoints."""

import pytest
from tests.conftest import register, login, auth_headers, make_email


class TestListOrganizations:
    def test_new_user_has_one_org(self, client, new_user):
        resp = client.get("/api/v1/organizations", headers=new_user["headers"])
        assert resp.status_code == 200
        orgs = resp.json()
        assert len(orgs) >= 1
        assert all("id" in o and "name" in o and "slug" in o for o in orgs)

    def test_unauthenticated_rejected(self, client):
        resp = client.get("/api/v1/organizations")
        assert resp.status_code == 401


class TestCreateOrganization:
    def test_creates_and_makes_user_admin(self, client, new_user):
        name = f"Extra Org {uuid_suffix()}"
        resp = client.post("/api/v1/organizations", headers=new_user["headers"],
                           json={"name": name})
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == name
        assert "id" in body
        assert "slug" in body
        assert body["member_count"] == 1

    def test_duplicate_name_rejected(self, client, new_user):
        name = f"Unique Org {uuid_suffix()}"
        client.post("/api/v1/organizations", headers=new_user["headers"], json={"name": name})
        resp = client.post("/api/v1/organizations", headers=new_user["headers"], json={"name": name})
        assert resp.status_code == 400

    def test_user_can_see_all_their_orgs(self, client, new_user):
        name = f"Second Org {uuid_suffix()}"
        client.post("/api/v1/organizations", headers=new_user["headers"], json={"name": name})

        resp = client.get("/api/v1/organizations", headers=new_user["headers"])
        assert len(resp.json()) >= 2


class TestCurrentOrganization:
    def test_get_returns_org_details(self, client, new_user):
        resp = client.get("/api/v1/organizations/current", headers=new_user["headers"])
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert "name" in body
        assert "slug" in body
        assert body["member_count"] >= 1

    def test_admin_can_rename(self, client, new_user):
        new_name = f"Renamed {uuid_suffix()}"
        resp = client.patch("/api/v1/organizations/current", headers=new_user["headers"],
                            json={"name": new_name})
        assert resp.status_code == 200
        assert resp.json()["name"] == new_name

    def test_rename_to_existing_name_rejected(self, client):
        user1 = _new_auth(client)
        user2 = _new_auth(client)

        # Get user1's org name
        org1 = client.get("/api/v1/organizations/current", headers=user1["headers"]).json()
        # Try to rename user2's org to user1's org name
        resp = client.patch("/api/v1/organizations/current", headers=user2["headers"],
                            json={"name": org1["name"]})
        assert resp.status_code == 400


class TestSwitchOrganization:
    def test_switch_returns_new_token(self, client, new_user):
        org_resp = client.post("/api/v1/organizations", headers=new_user["headers"],
                               json={"name": f"Switch Target {uuid_suffix()}"})
        org_id = org_resp.json()["id"]

        resp = client.post(f"/api/v1/organizations/switch/{org_id}",
                           headers=new_user["headers"])
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_switch_to_non_member_org_rejected(self, client, new_user):
        other_user = _new_auth(client)
        other_org = client.get("/api/v1/organizations/current",
                               headers=other_user["headers"]).json()

        resp = client.post(f"/api/v1/organizations/switch/{other_org['id']}",
                           headers=new_user["headers"])
        assert resp.status_code == 403


class TestOrganizationMembers:
    def test_list_includes_self(self, client, new_user):
        resp = client.get("/api/v1/organizations/current/members", headers=new_user["headers"])
        assert resp.status_code == 200
        members = resp.json()
        assert len(members) >= 1
        assert any(m["user_email"] == new_user["email"] for m in members)
        assert any(m["role"] == "admin" for m in members)

    def test_cannot_remove_last_admin(self, client, new_user):
        me_resp = client.get("/api/v1/account/me", headers=new_user["headers"])
        user_id = me_resp.json()["id"]

        resp = client.delete(f"/api/v1/organizations/members/{user_id}",
                             headers=new_user["headers"])
        assert resp.status_code == 400
        assert "last admin" in resp.json()["detail"].lower()

    def test_admin_can_remove_member(self, client, new_user):
        # Invite and accept a second user via the new-user invite flow
        invitee_email = make_email()
        invite_resp = client.post("/api/v1/organizations/invitations",
                                  headers=new_user["headers"],
                                  json={"email": invitee_email, "role": "member"})
        assert invite_resp.status_code == 200, invite_resp.text
        token = invite_resp.json()["token"]
        admin_cookies = dict(client.cookies)

        client.cookies.clear()
        client.post(f"/api/v1/invitations/accept/{token}",
                    json={"password": "MemberPass123!", "confirm_password": "MemberPass123!"})
        client.cookies.update(admin_cookies)

        # Find the new member
        members_resp = client.get("/api/v1/organizations/current/members",
                                  headers=new_user["headers"])
        member = next(m for m in members_resp.json() if m["user_email"] == invitee_email)

        resp = client.delete(f"/api/v1/organizations/members/{member['user_id']}",
                             headers=new_user["headers"])
        assert resp.status_code == 200

    def test_admin_can_update_member_role(self, client, new_user):
        invitee_email = make_email()
        invite_resp = client.post("/api/v1/organizations/invitations",
                                  headers=new_user["headers"],
                                  json={"email": invitee_email, "role": "member"})
        token = invite_resp.json()["token"]
        saved = dict(client.cookies)
        client.cookies.clear()
        client.post(f"/api/v1/invitations/accept/{token}",
                    json={"password": "MemberPass123!", "confirm_password": "MemberPass123!"})
        client.cookies.update(saved)

        members_resp = client.get("/api/v1/organizations/current/members",
                                  headers=new_user["headers"])
        member = next(m for m in members_resp.json() if m["user_email"] == invitee_email)

        resp = client.patch(f"/api/v1/organizations/members/{member['user_id']}",
                            headers=new_user["headers"],
                            json={"role": "admin"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"


# ── Private helpers ────────────────────────────────────────────────────────────

def uuid_suffix() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


def _new_auth(client) -> dict:
    data = register(client)
    token = login(client, data["email"], data["password"])
    return {"email": data["email"], "headers": auth_headers(token)}
