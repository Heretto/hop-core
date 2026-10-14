"""Invited users join the organization that invited them, and only that one,
and then work in it (hop_core.core.org_context).

The case that broke: someone was invited, signed up or signed in with SSO
before using the invitation link, and got an empty organization of their own.
Sign-in then put them in that one (it picked the first membership the database
listed), so they saw none of the inviting organization's data.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from hop_core.core.security import decode_token
from hop_core.db import get_session_factory
from hop_core.models.organization import Organization, OrganizationInvitation, OrganizationMember
from hop_core.models.user import User

from tests.conftest import auth_headers, login, make_email, register


def _current_org(client, token: str) -> str:
    resp = client.get("/api/v1/organizations/current", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _invite(client, admin_token: str, email: str, role: str = "admin") -> str:
    resp = client.post("/api/v1/organizations/invitations", headers=auth_headers(admin_token),
                       json={"email": email, "role": role})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _anonymous_post(client, url: str, json: dict):
    """As a browser without a session would: no cookies, so no CSRF check."""
    client.cookies.clear()
    return client.post(url, json=json)


def _memberships(email: str) -> list[tuple[str, str]]:
    db = get_session_factory()()
    try:
        user = db.query(User).filter(User.email == email).one_or_none()
        if user is None:
            return []
        return [
            (str(m.organization_id), str(getattr(m.role, "value", m.role)).lower())
            for m in db.query(OrganizationMember).filter(OrganizationMember.user_id == user.id)
        ]
    finally:
        db.close()


@pytest.fixture
def admin(client):
    data = register(client)
    token = login(client, data["email"], data["password"])
    return {**data, "token": token, "org": _current_org(client, token)}


@pytest.fixture
def existing_invitee(client, admin):
    """Someone who already had an account (with their own organization) before
    being invited, which is legitimate: they keep it and gain the new one."""
    data = register(client)
    token = login(client, data["email"], data["password"])
    return {**data, "token": token, "org": _current_org(client, token)}


# ── No extra organization for invited users ──────────────────────────────────


class TestInvitedUsersGetNoOrganizationOfTheirOwn:
    def test_invitation_link_creates_the_account_in_the_inviting_org_only(self, client, admin):
        email = make_email()
        token = _invite(client, admin["token"], email)
        resp = _anonymous_post(client, f"/api/v1/invitations/accept/{token}",
                               {"password": "SecurePass123!", "confirm_password": "SecurePass123!"})
        assert resp.status_code == 200, resp.text
        assert _memberships(email) == [(admin["org"], "admin")]
        assert _current_org(client, login(client, email)) == admin["org"]

    def test_registering_while_invited_creates_nothing(self, client, admin):
        email = make_email()
        _invite(client, admin["token"], email)
        db = get_session_factory()()
        try:
            orgs_before = db.query(Organization).count()
        finally:
            db.close()

        client.cookies.clear()
        resp = client.post("/api/v1/auth/register", json={"email": email, "password": "SecurePass123!"})
        assert resp.status_code == 409
        assert "invited to" in resp.json()["detail"] and "invitation email" in resp.json()["detail"]

        db = get_session_factory()()
        try:
            assert db.query(User).filter(User.email == email).count() == 0
            assert db.query(Organization).count() == orgs_before
        finally:
            db.close()

    def test_registering_matches_the_invitation_case_insensitively(self, client, admin):
        email = make_email()
        _invite(client, admin["token"], email)
        client.cookies.clear()
        resp = client.post("/api/v1/auth/register", json={"email": email.upper(), "password": "SecurePass123!"})
        assert resp.status_code == 409

    @pytest.mark.parametrize("state", ["expired", "accepted"])
    def test_registering_after_the_invitation_is_over_works_as_usual(self, client, admin, state):
        email = make_email()
        token = _invite(client, admin["token"], email)
        db = get_session_factory()()
        try:
            invitation = db.query(OrganizationInvitation).filter(OrganizationInvitation.token == token).one()
            if state == "expired":
                invitation.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
            else:
                invitation.accepted_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()
        client.cookies.clear()
        assert client.post("/api/v1/auth/register", json={"email": email, "password": "SecurePass123!"}).status_code == 200

    def test_first_sso_sign_in_joins_the_inviting_orgs(self, client, admin):
        """The identity provider verified the address: join every organization
        that invited it (newest current), and create none."""
        from hop_core.api.routes.sso import _handle_sso_login

        other = register(client)
        other_org = _current_org(client, login(client, other["email"], other["password"]))
        email = make_email()
        older = _invite(client, login(client, other["email"], other["password"]), email, role="member")
        _invite(client, admin["token"], email)  # newest

        db = get_session_factory()()
        try:
            # SQLite's timestamps have one-second precision: make "newest" unambiguous.
            first = db.query(OrganizationInvitation).filter(OrganizationInvitation.token == older).one()
            first.created_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
            orgs_before = db.query(Organization).count()
            user = _handle_sso_login(db, "google", f"google-{uuid.uuid4().hex}", email, "Someone")
            assert db.query(Organization).count() == orgs_before
            assert str(user.current_organization_id) == admin["org"]
            pending = db.query(OrganizationInvitation).filter(
                OrganizationInvitation.email == email, OrganizationInvitation.accepted_at.is_(None)
            ).count()
            assert pending == 0
        finally:
            db.close()
        assert sorted(_memberships(email)) == sorted([(admin["org"], "admin"), (other_org, "member")])

    def test_first_sso_sign_in_without_an_invitation_still_gets_an_org(self, client):
        from hop_core.api.routes.sso import _handle_sso_login

        db = get_session_factory()()
        try:
            orgs_before = db.query(Organization).count()
            user = _handle_sso_login(db, "google", f"google-{uuid.uuid4().hex}", make_email(), "Someone")
            assert db.query(Organization).count() == orgs_before + 1
            assert user.current_organization_id is not None
        finally:
            db.close()


# ── Accepting makes the invited organization current ─────────────────────────


class TestAcceptingSwitchesOrganization:
    def test_existing_user_password_accept(self, client, admin, existing_invitee):
        token = _invite(client, admin["token"], existing_invitee["email"])
        resp = _anonymous_post(client, f"/api/v1/invitations/accept-existing/{token}",
                               {"password": existing_invitee["password"]})
        assert resp.status_code == 200, resp.text
        fresh = login(client, existing_invitee["email"], existing_invitee["password"])
        assert _current_org(client, fresh) == admin["org"]

    def test_signed_in_accept_switches_at_once(self, client, admin, existing_invitee):
        """Accepting while signed in returns tokens for the new organization
        (and sets them as cookies), as switching organization does."""
        token = _invite(client, admin["token"], existing_invitee["email"], role="member")
        resp = client.post(f"/api/v1/organizations/invitations/accept/{token}",
                           headers=auth_headers(existing_invitee["token"]))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["message"] == "Successfully joined the organization"
        assert body["organization_id"] == admin["org"]
        claims = decode_token(body["access_token"])
        assert (claims["org_id"], claims["org_role"]) == (admin["org"], "member")
        assert _current_org(client, body["access_token"]) == admin["org"]
        assert "access_token" in resp.cookies
        fresh = login(client, existing_invitee["email"], existing_invitee["password"])
        assert _current_org(client, fresh) == admin["org"]


# ── Signing in uses the current organization ─────────────────────────────────


class TestSignInUsesTheCurrentOrganization:
    def _join(self, client, admin, invitee):
        token = _invite(client, admin["token"], invitee["email"])
        resp = _anonymous_post(client, f"/api/v1/invitations/accept-existing/{token}",
                               {"password": invitee["password"]})
        assert resp.status_code == 200, resp.text

    def test_switch_survives_signing_in_again(self, client, admin, existing_invitee):
        self._join(client, admin, existing_invitee)
        signed_in = login(client, existing_invitee["email"], existing_invitee["password"])
        resp = client.post(f"/api/v1/organizations/switch/{existing_invitee['org']}", headers=auth_headers(signed_in))
        assert resp.status_code == 200, resp.text
        fresh = login(client, existing_invitee["email"], existing_invitee["password"])
        assert _current_org(client, fresh) == existing_invitee["org"]

    def test_falls_back_when_no_longer_a_member(self, client, admin, existing_invitee):
        self._join(client, admin, existing_invitee)
        db = get_session_factory()()
        try:
            invitee_id = db.query(User).filter(User.email == existing_invitee["email"]).one().id
        finally:
            db.close()
        resp = client.delete(f"/api/v1/organizations/members/{invitee_id}", headers=auth_headers(admin["token"]))
        assert resp.status_code == 200, resp.text
        fresh = login(client, existing_invitee["email"], existing_invitee["password"])
        assert _current_org(client, fresh) == existing_invitee["org"]  # the membership they still have

    def test_refresh_keeps_the_current_organization(self, client, admin, existing_invitee):
        self._join(client, admin, existing_invitee)
        client.cookies.clear()
        resp = client.post("/api/v1/auth/login",
                           json={"email": existing_invitee["email"], "password": existing_invitee["password"]})
        assert resp.status_code == 200, resp.text
        refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": resp.json()["refresh_token"]})
        assert refreshed.status_code == 200, refreshed.text
        assert _current_org(client, refreshed.json()["access_token"]) == admin["org"]

    def test_sso_token_uses_the_current_organization(self, client, admin, existing_invitee):
        from hop_core.api.routes.sso import _build_token_data

        self._join(client, admin, existing_invitee)
        db = get_session_factory()()
        try:
            user = db.query(User).filter(User.email == existing_invitee["email"]).one()
            claims = _build_token_data(user, db)
        finally:
            db.close()
        assert (claims["org_id"], claims["org_role"]) == (admin["org"], "admin")

    def test_user_without_an_organization_gets_no_org_claim(self, client):
        from hop_core.core.org_context import token_org_claims

        db = get_session_factory()()
        try:
            user = User(email=make_email(), is_active=True)
            db.add(user)
            db.commit()
            assert token_org_claims(db, user) == {}
        finally:
            db.close()


# ── Coming back to an invitation already used ────────────────────────────────


class TestInvitationAlreadyUsed:
    """With SSO, an invitee's first sign-in joins them, and the provider sends
    them back to the invitation page, which accepts again."""

    def _sso_invitee(self, client, admin):
        from hop_core.api.routes.sso import _build_token_data, _handle_sso_login
        from hop_core.core.security import create_access_token

        email = make_email()
        token = _invite(client, admin["token"], email)
        db = get_session_factory()()
        try:
            user = _handle_sso_login(db, "google", f"google-{uuid.uuid4().hex}", email, None)
            access = create_access_token(data=_build_token_data(user, db))
        finally:
            db.close()
        return token, access

    def test_info_says_accepted(self, client, admin):
        token, _ = self._sso_invitee(client, admin)
        client.cookies.clear()
        resp = client.get(f"/api/v1/invitations/info/{token}")
        assert resp.status_code == 200, resp.text
        assert resp.json()["accepted"] is True

    def test_info_for_a_pending_invitation(self, client, admin):
        token = _invite(client, admin["token"], make_email())
        client.cookies.clear()
        assert client.get(f"/api/v1/invitations/info/{token}").json()["accepted"] is False

    def test_accepting_again_takes_them_to_the_org(self, client, admin):
        token, access = self._sso_invitee(client, admin)
        resp = client.post(f"/api/v1/organizations/invitations/accept/{token}", headers=auth_headers(access))
        assert resp.status_code == 200, resp.text
        assert _current_org(client, resp.json()["access_token"]) == admin["org"]

    def test_someone_else_cannot_reuse_it(self, client, admin):
        token, _ = self._sso_invitee(client, admin)
        other = register(client)
        other_token = login(client, other["email"], other["password"])
        resp = client.post(f"/api/v1/organizations/invitations/accept/{token}", headers=auth_headers(other_token))
        assert resp.status_code == 403

    def test_used_by_them_but_since_removed(self, client, admin):
        """Removed from the organization: the old invitation doesn't let them back in."""
        token, access = self._sso_invitee(client, admin)
        db = get_session_factory()()
        try:
            user_id = db.query(User).filter(User.email == decode_token(access)["email"]).one().id
        finally:
            db.close()
        assert client.delete(f"/api/v1/organizations/members/{user_id}", headers=auth_headers(admin["token"])).status_code == 200
        resp = client.post(f"/api/v1/organizations/invitations/accept/{token}", headers=auth_headers(access))
        assert resp.status_code == 404
