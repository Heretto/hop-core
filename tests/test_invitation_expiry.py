"""Expired invitations, and email case, in both invitation-creating routes.

The pending list hides expired invitations, so creating one must not be
blocked by them either; and Ada@x.com is the same person as ada@x.com.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from hop_core.core.invitations import PENDING_INVITATION_DETAIL
from hop_core.db import get_session_factory
from hop_core.models.organization import OrganizationInvitation
from hop_core.models.user import User
from tests.conftest import auth_headers, login, make_email, register


@pytest.fixture
def db():
    session = get_session_factory()()
    yield session
    session.close()


@pytest.fixture(params=["organization admin", "superadmin"])
def inviter(request, client, db):
    """Both routes that create invitations, which must behave identically."""
    data = register(client)
    if request.param == "superadmin":
        db.query(User).filter(User.email == data["email"]).update({"is_superuser": True})
        db.commit()
    headers = auth_headers(login(client, data["email"], data["password"]))
    org_id = client.get("/api/v1/organizations/current", headers=headers).json()["id"]

    def invite(email):
        path = ("/api/v1/organizations/invitations" if request.param == "organization admin"
                else f"/api/v1/superadmin/organizations/{org_id}/invitations")
        return client.post(path, headers=headers, json={"email": email, "role": "member"})

    def pending():
        return client.get("/api/v1/organizations/invitations", headers=headers).json()

    return type("Inviter", (), {"invite": staticmethod(invite), "pending": staticmethod(pending),
                                "org_id": org_id, "headers": headers})


def expire(db, email):
    db.query(OrganizationInvitation).filter(OrganizationInvitation.email == email.lower()).update(
        {"expires_at": datetime.now(timezone.utc) - timedelta(days=1)})
    db.commit()


class TestExpiredInvitations:
    def test_reinviting_after_expiry_succeeds(self, inviter, db):
        email = make_email()
        assert inviter.invite(email).status_code == 200
        expire(db, email)
        assert [i["email"] for i in inviter.pending()] == []

        resp = inviter.invite(email)
        assert resp.status_code == 200, resp.text
        assert [i["email"] for i in inviter.pending()] == [email]

    def test_expired_rows_are_deleted_not_left_behind(self, inviter, db):
        email = make_email()
        inviter.invite(email)
        expire(db, email)
        inviter.invite(email)
        db.expire_all()
        rows = db.query(OrganizationInvitation).filter(OrganizationInvitation.email == email).all()
        assert len(rows) == 1

    def test_several_expired_leftovers_are_all_cleared(self, inviter, db):
        """Databases from before the fix can hold more than one dead row."""
        email = make_email()
        for _ in range(2):
            db.add(OrganizationInvitation(
                organization_id=uuid.UUID(inviter.org_id), email=email, role="MEMBER",
                token=uuid.uuid4().hex, expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
        db.commit()
        assert inviter.invite(email).status_code == 200
        assert len(inviter.pending()) == 1

    def test_live_invitation_still_blocks_with_an_actionable_message(self, inviter):
        email = make_email()
        inviter.invite(email)
        resp = inviter.invite(email)
        assert resp.status_code == 400
        assert resp.json()["detail"] == PENDING_INVITATION_DETAIL
        assert "sent" not in resp.json()["detail"]

    def test_expired_invitation_cannot_be_accepted(self, inviter, client, db):
        email = make_email()
        token = inviter.invite(email).json()["token"]
        expire(db, email)
        client.cookies.clear()
        resp = client.post(f"/api/v1/invitations/accept/{token}",
                           json={"password": "NewUserPass123!", "confirm_password": "NewUserPass123!"})
        assert resp.status_code == 400


class TestEmailCase:
    def test_stored_lowercased(self, inviter):
        resp = inviter.invite("Ada.Lovelace@Example.COM")
        assert resp.status_code == 200, resp.text
        assert resp.json()["email"] == "ada.lovelace@example.com"

    def test_duplicate_check_ignores_case(self, inviter):
        local = uuid.uuid4().hex[:8]
        assert inviter.invite(f"{local}@example.com").status_code == 200
        resp = inviter.invite(f"{local.upper()}@EXAMPLE.com")
        assert resp.status_code == 400
        assert resp.json()["detail"] == PENDING_INVITATION_DETAIL

    def test_member_check_ignores_case(self, inviter, client):
        member = register(client)
        token = inviter.invite(member["email"]).json()["token"]
        member_headers = auth_headers(login(client, member["email"], member["password"]))
        assert client.post(f"/api/v1/organizations/invitations/accept/{token}",
                           headers=member_headers).status_code == 200
        resp = inviter.invite(member["email"].upper())
        assert resp.status_code == 400
        assert "already a member" in resp.json()["detail"]

    def test_existing_account_with_different_case_accepts(self, inviter, client):
        """An account registered as Bob@X.com accepts an invitation to bob@x.com."""
        local = uuid.uuid4().hex[:8]
        account = register(client, email=f"{local.capitalize()}@Example.com")
        token = inviter.invite(f"{local}@example.com").json()["token"]
        client.cookies.clear()
        resp = client.post(f"/api/v1/invitations/accept-existing/{token}",
                           json={"password": account["password"]})
        assert resp.status_code == 200, resp.text
