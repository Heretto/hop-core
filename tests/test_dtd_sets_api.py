"""The /dtd-sets API: uploading packages, processing them in the background,
the organization default, agent choices, versions, and validator_for."""

import io
import uuid
import zipfile

import pytest

from hop_core import dtd_sets
from hop_core.config import get_settings
from hop_core.db import get_session_factory
from hop_core.dita.validator import DitaValidator
from hop_core.models.dtd_set import DtdSetVersion
from tests.conftest import auth_headers, login, make_email, register
from tests.fixtures.dtd_packages import acme_package

needs_xmllint = pytest.mark.skipif(
    not DitaValidator._xmllint_available(), reason="no xmllint able to load DITA grammar here")

API_REF = '<apiRef id="a"><title>API</title><refbody><section><p><codeph>get()</codeph></p></section></refbody></apiRef>'


@pytest.fixture(scope="module")
def acme_zip(tmp_path_factory):
    return acme_package(tmp_path_factory.mktemp("acme")).read_bytes()


def no_catalog_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.dtd", "<!ELEMENT a EMPTY>")
    return buf.getvalue()


@pytest.fixture
def admin(client):
    data = register(client)
    headers = auth_headers(login(client, data["email"], data["password"]))
    org_id = client.get("/api/v1/organizations/current", headers=headers).json()["id"]
    return {**data, "headers": headers, "org_id": org_id}


def upload(client, headers, data: bytes, name="Acme Product DITA", version="v2.3", filename="acme.zip"):
    return client.post("/api/v1/dtd-sets", headers=headers,
                       files={"file": (filename, data, "application/zip")},
                       data={"name": name, "version": version, "description": "Acme DTDs"})


def listing(client, headers):
    return client.get("/api/v1/dtd-sets", headers=headers).json()


def row(listing_body, set_id):
    return next(s for s in listing_body["sets"] if s["id"] == set_id)


@pytest.fixture
def ready_set(client, admin, acme_zip):
    resp = upload(client, admin["headers"], acme_zip)
    assert resp.status_code == 202, resp.text
    set_id = next(s["id"] for s in listing(client, admin["headers"])["sets"] if s["name"] == "Acme Product DITA")
    return set_id, resp.json()["id"]


class TestUpload:
    def test_processes_in_the_background_to_ready(self, client, admin, ready_set):
        set_id, version_id = ready_set
        version = client.get(f"/api/v1/dtd-sets/{set_id}/versions/{version_id}", headers=admin["headers"]).json()
        assert version["status"] == "ready" and version["is_current"]
        assert [s["state"] for s in version["steps"]] == ["done"] * 6
        assert version["steps"][2]["detail"].startswith("catalog.xml · ")
        summary = row(listing(client, admin["headers"]), set_id)
        assert summary["status"] == "ready" and summary["version_label"] == "v2.3"
        assert summary["specialized_count"] == 1 and summary["document_type_count"] == 27
        assert summary["warning_count"] == 2 and summary["based_on"] == "DITA 1.3"

    def test_failed_package_keeps_its_reason(self, client, admin):
        resp = upload(client, admin["headers"], no_catalog_zip(), name="Partner docs", version="v1.0")
        set_id = next(s["id"] for s in listing(client, admin["headers"])["sets"] if s["name"] == "Partner docs")
        version = client.get(f"/api/v1/dtd-sets/{set_id}/versions/{resp.json()['id']}", headers=admin["headers"]).json()
        assert version["status"] == "failed" and version["error"] == "No XML catalog found in the zip."
        assert [s["state"] for s in version["steps"]] == ["done", "done", "failed", "pending", "pending", "pending"]
        summary = row(listing(client, admin["headers"]), set_id)
        assert summary["status"] == "failed" and summary["document_type_count"] is None

    def test_must_be_a_zip(self, client, admin):
        resp = client.post("/api/v1/dtd-sets", headers=admin["headers"],
                           files={"file": ("x.tar", b"x", "application/x-tar")}, data={"name": "X"})
        assert resp.status_code == 400

    def test_size_limit(self, client, admin, monkeypatch):
        monkeypatch.setattr(get_settings(), "dtd_upload_max_mb", 0)
        assert upload(client, admin["headers"], b"PK" + b"x" * 10).status_code == 413

    def test_members_cannot_upload(self, client, admin, acme_zip):
        email = make_email()
        token = client.post("/api/v1/organizations/invitations", headers=admin["headers"],
                            json={"email": email, "role": "member"}).json()["token"]
        client.cookies.clear()
        client.post(f"/api/v1/invitations/accept/{token}",
                    json={"password": "MemberPass123!", "confirm_password": "MemberPass123!"})
        member = auth_headers(login(client, email, "MemberPass123!"))
        assert upload(client, member, acme_zip).status_code == 403
        assert client.get("/api/v1/dtd-sets", headers=member).status_code == 200


class TestListAndDetail:
    def test_built_in_set_is_always_listed_and_the_default(self, client, admin):
        body = listing(client, admin["headers"])
        builtin = row(body, "oasis-dita-1.3")
        assert body["default_id"] == "oasis-dita-1.3" and builtin["is_default"] and builtin["builtin"]
        assert builtin["document_type_count"] == 26 and builtin["status"] == "ready"
        assert body["max_upload_mb"] == get_settings().dtd_upload_max_mb

    def test_built_in_detail_lists_its_document_types(self, client, admin):
        detail = client.get("/api/v1/dtd-sets/oasis-dita-1.3", headers=admin["headers"]).json()
        assert any(d["root"] == "concept" for d in detail["document_types"])

    def test_detail_has_warnings_document_types_and_package(self, client, admin, ready_set):
        detail = client.get(f"/api/v1/dtd-sets/{ready_set[0]}", headers=admin["headers"]).json()
        assert {(i["title"], i["file"], i["line"]) for i in detail["issues"]} == {
            ("Public ID listed twice in the catalog", "catalog.xml", 5),
            ("Unresolved parameter entity %acme-hazard-d-dec;", "acme/acmeExtras.ent", 2),
        }
        api = next(d for d in detail["document_types"] if d["root"] == "apiRef")
        assert (api["kind"], api["specializes"]) == ("specialized", "reference")
        assert detail["package"]["catalog"] == "catalog.xml" and detail["package"]["filename"] == "acme.zip"
        assert detail["uploaded_by"] == admin["email"] and detail["description"] == "Acme DTDs"

    def test_other_organizations_cannot_see_it(self, client, ready_set):
        other = register(client)
        headers = auth_headers(login(client, other["email"], other["password"]))
        assert client.get(f"/api/v1/dtd-sets/{ready_set[0]}", headers=headers).status_code == 404
        assert all(s["builtin"] for s in listing(client, headers)["sets"])


class TestDefaultAndAgents:
    def test_set_default(self, client, admin, ready_set):
        resp = client.put("/api/v1/dtd-sets/default", headers=admin["headers"], json={"dtd_set_id": ready_set[0]})
        assert resp.status_code == 200 and resp.json()["default_id"] == ready_set[0]
        assert resp.json()["sets"][0]["id"] == ready_set[0]   # the default lists first

    def test_failed_set_cannot_be_default(self, client, admin):
        upload(client, admin["headers"], no_catalog_zip(), name="Broken")
        broken = next(s["id"] for s in listing(client, admin["headers"])["sets"] if s["name"] == "Broken")
        resp = client.put("/api/v1/dtd-sets/default", headers=admin["headers"], json={"dtd_set_id": broken})
        assert resp.status_code == 400

    def test_agent_chooses_and_clears_a_set(self, client, admin, ready_set):
        agent = client.post("/api/v1/agents", headers=admin["headers"],
                            json={"name": f"A {uuid.uuid4().hex[:6]}", "dtd_set_id": ready_set[0]}).json()
        assert agent["dtd_set_id"] == ready_set[0]
        detail = client.get(f"/api/v1/dtd-sets/{ready_set[0]}", headers=admin["headers"]).json()
        assert detail["agents"] == [{"id": agent["id"], "name": agent["name"]}] and detail["used_by"] == 1
        cleared = client.put(f"/api/v1/agents/{agent['id']}", headers=admin["headers"], json={"dtd_set_id": None})
        assert cleared.json()["dtd_set_id"] is None

    @pytest.mark.parametrize("bad", ["nope", str(uuid.uuid4())])
    def test_agent_cannot_choose_an_unknown_set(self, client, admin, bad):
        resp = client.post("/api/v1/agents", headers=admin["headers"], json={"name": f"A {bad}", "dtd_set_id": bad})
        assert resp.status_code == 400

    def test_agent_can_choose_the_built_in_set(self, client, admin):
        resp = client.post("/api/v1/agents", headers=admin["headers"],
                           json={"name": f"A {uuid.uuid4().hex[:6]}", "dtd_set_id": "oasis-dita-1.3"})
        assert resp.json()["dtd_set_id"] == "oasis-dita-1.3"


class TestVersionsAndDelete:
    def test_failed_new_version_leaves_the_current_one_in_use(self, client, admin, ready_set, acme_zip):
        set_id, v1 = ready_set
        resp = client.post(f"/api/v1/dtd-sets/{set_id}/versions", headers=admin["headers"],
                           files={"file": ("bad.zip", no_catalog_zip(), "application/zip")}, data={"version": "v2.4"})
        assert resp.status_code == 202
        summary = row(listing(client, admin["headers"]), set_id)
        assert summary["status"] == "ready" and summary["version_label"] == "v2.3"
        assert (summary["latest_label"], summary["latest_status"]) == ("v2.4", "failed")

    def test_new_version_then_restore(self, client, admin, ready_set, acme_zip):
        set_id, v1 = ready_set
        v2 = client.post(f"/api/v1/dtd-sets/{set_id}/versions", headers=admin["headers"],
                         files={"file": ("acme-2.4.zip", acme_zip, "application/zip")},
                         data={"version": "v2.4"}).json()["id"]
        assert row(listing(client, admin["headers"]), set_id)["version_label"] == "v2.4"
        restored = client.post(f"/api/v1/dtd-sets/{set_id}/versions/{v1}/restore", headers=admin["headers"]).json()
        assert restored["version_label"] == "v2.3"
        assert [(v["label"], v["is_current"]) for v in restored["versions"]] == [("v2.4", False), ("v2.3", True)]

    def test_download_returns_the_upload(self, client, admin, ready_set, acme_zip):
        set_id, v1 = ready_set
        resp = client.get(f"/api/v1/dtd-sets/{set_id}/versions/{v1}/download", headers=admin["headers"])
        assert resp.content == acme_zip and "acme.zip" in resp.headers["content-disposition"]

    def test_delete_is_refused_while_in_use(self, client, admin, ready_set):
        set_id, _ = ready_set
        client.put("/api/v1/dtd-sets/default", headers=admin["headers"], json={"dtd_set_id": set_id})
        assert client.delete(f"/api/v1/dtd-sets/{set_id}", headers=admin["headers"]).status_code == 409
        client.put("/api/v1/dtd-sets/default", headers=admin["headers"], json={"dtd_set_id": "oasis-dita-1.3"})
        agent = client.post("/api/v1/agents", headers=admin["headers"],
                            json={"name": f"A {uuid.uuid4().hex[:6]}", "dtd_set_id": set_id}).json()
        resp = client.delete(f"/api/v1/dtd-sets/{set_id}", headers=admin["headers"])
        assert resp.status_code == 409 and "1 agent" in resp.json()["detail"]
        client.put(f"/api/v1/agents/{agent['id']}", headers=admin["headers"], json={"dtd_set_id": None})
        assert client.delete(f"/api/v1/dtd-sets/{set_id}", headers=admin["headers"]).status_code == 200
        assert client.get(f"/api/v1/dtd-sets/{set_id}", headers=admin["headers"]).status_code == 404


class TestService:
    def test_interrupted_processing_is_marked_failed(self, client, admin, ready_set):
        db = get_session_factory()()
        version = db.get(DtdSetVersion, uuid.UUID(ready_set[1]))
        version.status = "processing"
        db.commit()
        assert dtd_sets.recover_interrupted(db) >= 1
        db.refresh(version)
        assert version.status == "failed" and "interrupted" in version.error
        db.close()

    @needs_xmllint
    def test_validator_for_follows_agent_then_default_then_built_in(self, client, admin, ready_set):
        set_id, _ = ready_set
        org_id = uuid.UUID(admin["org_id"])
        db = get_session_factory()()
        assert dtd_sets.validator_for(db, org_id).validate_with_dtd(API_REF)[0] is False   # built in: no apiRef
        client.put("/api/v1/dtd-sets/default", headers=admin["headers"], json={"dtd_set_id": set_id})
        db.expire_all()
        assert dtd_sets.validator_for(db, org_id).validate_with_dtd(API_REF) == (True, None)
        agent = client.post("/api/v1/agents", headers=admin["headers"],
                            json={"name": f"A {uuid.uuid4().hex[:6]}", "dtd_set_id": "oasis-dita-1.3"}).json()
        db.expire_all()
        assert dtd_sets.validator_for(db, org_id, agent_id=uuid.UUID(agent["id"])).validate_with_dtd(API_REF)[0] is False
        db.close()

    @needs_xmllint
    def test_validator_rebuilds_its_grammar_after_the_cache_is_cleared(self, client, admin, ready_set):
        set_id, version_id = ready_set
        client.put("/api/v1/dtd-sets/default", headers=admin["headers"], json={"dtd_set_id": set_id})
        dtd_sets.forget_unpacked(version_id)
        db = get_session_factory()()
        assert dtd_sets.validator_for(db, uuid.UUID(admin["org_id"])).validate_with_dtd(API_REF) == (True, None)
        db.close()
