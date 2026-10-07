"""SINGLE_ORG_MODE on a fresh database: the organization is created on first
sign-up and its first member becomes admin."""

import uuid

import pytest

from hop_core.config import configure, get_settings
from hop_core.core.single_org import _default_name
from hop_core.db import get_session_factory
from hop_core.models.enums import OrganizationRole
from hop_core.models.organization import Organization, OrganizationMember
from hop_core.models.user import User
from tests.conftest import _get_test_settings, login, make_email, register


@pytest.fixture
def slug(monkeypatch):
    """Turn single-org mode on with a slug no organization has yet."""
    value = f"acme-{uuid.uuid4().hex[:8]}"
    settings = get_settings()
    monkeypatch.setattr(settings, "single_org_mode", True)
    monkeypatch.setattr(settings, "single_org_slug", value)
    return value


@pytest.fixture
def db():
    session = get_session_factory()()
    yield session
    session.close()


def _orgs(db, slug):
    db.expire_all()
    return db.query(Organization).filter(Organization.slug == slug).all()


def _membership(db, email):
    db.expire_all()
    user = db.query(User).filter(User.email == email).one()
    members = db.query(OrganizationMember).filter(OrganizationMember.user_id == user.id).all()
    return user, members


def _sso_sign_up(db, email):
    from hop_core.api.routes.sso import _handle_sso_login
    return _handle_sso_login(db, "google", f"google-{uuid.uuid4().hex}", email, "Someone")


class TestPasswordRegistration:
    def test_first_sign_up_creates_the_org_and_becomes_admin(self, client, db, slug):
        data = register(client)

        [org] = _orgs(db, slug)
        user, [member] = _membership(db, data["email"])
        assert member.organization_id == org.id
        assert member.role == OrganizationRole.ADMIN
        assert user.current_organization_id == org.id

    def test_later_sign_ups_join_the_same_org_as_members(self, client, db, slug):
        first = register(client)
        second = register(client)

        [org] = _orgs(db, slug)
        _, [first_member] = _membership(db, first["email"])
        _, [second_member] = _membership(db, second["email"])
        assert first_member.role == OrganizationRole.ADMIN
        assert second_member.role == OrganizationRole.MEMBER
        assert second_member.organization_id == org.id

    def test_no_personal_org_is_created(self, client, db, slug):
        data = register(client)
        _, members = _membership(db, data["email"])
        assert len(members) == 1

    def test_first_user_logs_in_as_admin_of_the_org(self, client, db, slug):
        data = register(client)
        resp = client.post("/api/v1/auth/login", json={"email": data["email"], "password": data["password"]})
        assert resp.status_code == 200, resp.text
        [org_info] = resp.json()["organizations"]
        assert org_info["slug"] == slug
        assert org_info["role"] == "admin"

    def test_name_comes_from_the_slug_by_default(self, client, db, slug):
        register(client)
        [org] = _orgs(db, slug)
        assert org.name == _default_name(slug)

    def test_single_org_name_is_used_when_set(self, client, db, slug, monkeypatch):
        monkeypatch.setattr(get_settings(), "single_org_name", "Acme Corporation")
        register(client)
        [org] = _orgs(db, slug)
        assert org.name == "Acme Corporation"


class TestExistingOrganization:
    def test_existing_org_is_reused_and_keeps_its_name(self, client, db, slug):
        db.add(Organization(id=uuid.uuid4(), name="Hand Made", slug=slug))
        db.commit()
        register(client)
        [org] = _orgs(db, slug)
        assert org.name == "Hand Made"

    def test_first_joiner_of_an_empty_existing_org_becomes_admin(self, client, db, slug):
        db.add(Organization(id=uuid.uuid4(), name="Hand Made", slug=slug))
        db.commit()
        data = register(client)
        _, [member] = _membership(db, data["email"])
        assert member.role == OrganizationRole.ADMIN


class TestSsoSignUp:
    def test_first_sso_sign_up_creates_the_org_and_becomes_admin(self, db, slug):
        email = make_email()
        user = _sso_sign_up(db, email)

        [org] = _orgs(db, slug)
        _, [member] = _membership(db, email)
        assert user.current_organization_id == org.id
        assert member.role == OrganizationRole.ADMIN

    def test_password_and_sso_sign_ups_share_the_org(self, client, db, slug):
        first = register(client)
        email = make_email()
        _sso_sign_up(db, email)

        [org] = _orgs(db, slug)
        _, [member] = _membership(db, email)
        assert member.organization_id == org.id
        assert member.role == OrganizationRole.MEMBER


class TestModeOff:
    def test_each_sign_up_gets_its_own_org(self, client, db):
        a, b = register(client), register(client)
        _, [ma] = _membership(db, a["email"])
        _, [mb] = _membership(db, b["email"])
        assert ma.organization_id != mb.organization_id
        assert ma.role == mb.role == OrganizationRole.ADMIN


class TestStartupGuard:
    def _create(self, **overrides):
        from hop_core.app_factory import create_hop_app
        settings = _get_test_settings().model_copy(update=overrides)
        try:
            return create_hop_app(settings_factory=lambda: settings)
        finally:
            # create_hop_app registers its factory globally; put the suite's back.
            configure(_get_test_settings)

    def test_mode_without_a_slug_refuses_to_start(self):
        with pytest.raises(RuntimeError, match="SINGLE_ORG_SLUG"):
            self._create(single_org_mode=True, single_org_slug=None)

    def test_blank_slug_refuses_to_start(self):
        with pytest.raises(RuntimeError, match="SINGLE_ORG_SLUG"):
            self._create(single_org_mode=True, single_org_slug="  ")

    def test_mode_with_a_slug_starts(self):
        assert self._create(single_org_mode=True, single_org_slug="acme") is not None


@pytest.mark.parametrize("slug,name", [
    ("acme", "Acme"),
    ("acme-corp", "Acme Corp"),
    ("acme_corp", "Acme Corp"),
    ("acme--corp-", "Acme Corp"),
])
def test_default_name(slug, name):
    assert _default_name(slug) == name


class TestConcurrentFirstSignUps:
    def test_losing_the_creation_race_reuses_the_winners_org(self, db, slug):
        """Another request creates the org between our lookup and our insert."""
        from hop_core.core.single_org import get_or_create_single_org

        winner = get_session_factory()()
        winner.add(Organization(id=uuid.uuid4(), name="Winner", slug=slug))
        winner.commit()
        winner.close()

        class StaleFirstLookup:
            """Session whose first lookup still sees no organization."""
            def __init__(self, session):
                self._session, self._stale = session, True

            def query(self, *args):
                q = self._session.query(*args)
                if self._stale:
                    self._stale = False
                    return type("Miss", (), {"filter": lambda *_: type("F", (), {"first": lambda *_: None})()})()
                return q

            def __getattr__(self, name):
                return getattr(self._session, name)

        org = get_or_create_single_org(StaleFirstLookup(db))
        assert org.name == "Winner"
        assert len(_orgs(db, slug)) == 1
