"""Browsing Heretto: folder listings, repositories, breadcrumbs, typed folder
paths and finding files by name — in the client and through ``/heretto``."""

import httpx
import pytest

import hop_core.api.routes.heretto as heretto_routes
import hop_core.heretto.client as client_module
from hop_core.heretto import HerettoError
from tests.conftest import auth_headers, login, register
from tests.test_agent_references import _types, heretto, make_credential  # noqa: F401 (fixtures)
from tests.test_heretto import SERVER, FakeHeretto, files_route

ROOT = "f0000000-0000-0000-0000-000000000000"
GUIDES = "f0000000-0000-0000-0000-000000000001"
INSTALL = "f0000000-0000-0000-0000-000000000002"
IMAGES = "f0000000-0000-0000-0000-000000000003"
LINUX = "a0000000-0000-0000-0000-000000000001"
GETTING_STARTED = "a0000000-0000-0000-0000-000000000002"
SCREEN = "a0000000-0000-0000-0000-000000000003"
OVERVIEW = "a0000000-0000-0000-0000-000000000004"
REPO_ROOT = "/rest/branches/master/repositories/product/documents/"


def folder(folder_id, name, path, parent=None, folders=(), files=()):
    parent_attr = f' parent-folder-id="{parent}"' if parent else ""
    children = "".join(f'<folder name="{n}" id="{i}"/>' for n, i in folders)
    children += "".join(
        f'<resource name="{n}" id="{i}" type="{t}" mime-type="{m}"/>' for n, i, t, m in files
    )
    return (f'<folder id="{folder_id}"{parent_attr}><name>{name}</name>'
            f"<xmldb-uri>{path}</xmldb-uri><children>{children}</children></folder>")


def tree():
    root = folder(ROOT, "documents", "master/product/documents",
                  folders=[("guides", GUIDES), ("images", IMAGES)],
                  files=[("overview.dita", OVERVIEW, "Topic", "application/xml")])
    return {
        REPO_ROOT: root,
        files_route(ROOT): root,
        files_route(GUIDES): folder(
            GUIDES, "guides", "master/product/documents/guides", ROOT,
            folders=[("install", INSTALL)],
            files=[("getting-started.ditamap", GETTING_STARTED, "Map", "application/xml")]),
        files_route(INSTALL): folder(
            INSTALL, "install", "master/product/documents/guides/install", GUIDES,
            files=[("installing-on-linux.dita", LINUX, "Topic", "application/xml"),
                   ("install-screen.png", SCREEN, "", "image/png")]),
        files_route(IMAGES): folder(IMAGES, "images", "master/product/documents/images", ROOT),
        files_route(LINUX): (
            f'<resource id="{LINUX}" last-modified="1791763200000" folder-uuid="{INSTALL}">'
            "<name>installing-on-linux.dita</name>"
            "<xmldb-uri>master/product/documents/guides/install/installing-on-linux.dita</xmldb-uri>"
            "<mime-type>application/xml</mime-type><metadata>"
            '<meta name="title">Installing on Linux</meta><meta name="status">Approved</meta>'
            "</metadata></resource>"),
        "/rest/branches/": (
            '<branches><branch name="master"><repository name="product"/><repository name="training"/>'
            '</branch><branch name="dev"><repository name="product"/></branch>'
            '<branch name="master"><repository name="product"/></branch></branches>'),
    }


@pytest.fixture(autouse=True)
def _skip_dns(monkeypatch):
    monkeypatch.setattr(client_module, "validate_server_url", lambda url: url)


# ── Client ────────────────────────────────────────────────────────────────────

class TestListing:
    async def test_entries_carry_kinds(self):
        async with FakeHeretto(tree()).client() as c:
            guides = await c.get_folder(GUIDES)
            install = await c.get_folder(INSTALL)
        assert [(e.name, e.kind) for e in guides.entries] == [
            ("install", "folder"), ("getting-started.ditamap", "map")]
        assert [e.kind for e in install.entries] == ["topic", "image"]
        assert guides.parent_id == ROOT and guides.repository == ("master", "product")

    async def test_a_file_is_not_a_folder(self):
        async with FakeHeretto(tree()).client() as c:
            with pytest.raises(HerettoError, match="a file, not a folder"):
                await c.get_folder(LINUX)

    async def test_ids_cannot_leave_the_request_path(self):
        fake = FakeHeretto(tree())
        async with fake.client() as c:
            for bad in ("../branches", "x?y=1", "a/b", "%2e%2e", ""):
                with pytest.raises(HerettoError, match="Not a Heretto"):
                    await c.get_folder(bad)
        assert fake.requests == []

    async def test_repositories_are_listed_once_each(self):
        async with FakeHeretto(tree()).client() as c:
            assert await c.list_repositories() == [
                ("master", "product"), ("master", "training"), ("dev", "product")]

    async def test_ancestors_stop_at_documents(self):
        async with FakeHeretto(tree()).client() as c:
            install = await c.get_folder(INSTALL)
            assert [a.name for a in await c.get_ancestors(install)] == ["documents", "guides"]
            assert await c.get_ancestors(await c.get_folder(ROOT)) == []

    async def test_file_record_knows_its_folder(self):
        async with FakeHeretto(tree()).client() as c:
            f = await c.get_file(LINUX)
        assert f.folder_id == INSTALL and f.kind == "topic"


class TestFolderPaths:
    @pytest.mark.parametrize("path", [
        "/guides/install", "guides/install/", "documents/guides/install",
        "master/product/documents/guides/install", "master/product/GUIDES/Install",
        f"{SERVER}/#/folder/{INSTALL}",
    ])
    async def test_forms_of_a_path(self, path):
        async with FakeHeretto(tree()).client() as c:
            assert (await c.resolve_folder("master", "product", path)).id == INSTALL

    async def test_empty_path_is_the_repository(self):
        async with FakeHeretto(tree()).client() as c:
            assert (await c.resolve_folder("master", "product", "/")).id == ROOT

    async def test_wrong_segment_lists_what_is_there(self):
        async with FakeHeretto(tree()).client() as c:
            with pytest.raises(HerettoError) as err:
                await c.resolve_folder("master", "product", "guides/instal")
        assert err.value.message == (
            "No folder named 'instal' in master/product/documents/guides/. "
            "It contains: getting-started.ditamap, install/")
        assert err.value.folder_id == GUIDES

    async def test_a_file_in_the_path(self):
        async with FakeHeretto(tree()).client() as c:
            with pytest.raises(HerettoError, match="is a file, not a folder") as err:
                await c.resolve_folder("master", "product", "guides/getting-started.ditamap")
        assert err.value.folder_id == GUIDES

    async def test_wrong_file_path_names_its_folder(self):
        async with FakeHeretto(tree()).client() as c:
            with pytest.raises(HerettoError, match="No file named 'glossary.dita'") as err:
                await c.resolve("master/product/documents/guides/glossary.dita")
        assert err.value.folder_id == GUIDES


class TestFolderIdentifiers:
    @pytest.mark.parametrize("identifier", [
        "master/product/documents/guides/install", "master/product/guides/install/",
        INSTALL, f"{SERVER}/#/folder/{INSTALL}",
    ])
    async def test_forms(self, identifier):
        async with FakeHeretto(tree()).client() as c:
            assert (await c.resolve_folder_identifier(identifier)).id == INSTALL

    async def test_repository_alone_is_its_documents_folder(self):
        async with FakeHeretto(tree()).client() as c:
            assert (await c.resolve_folder_identifier("master/product")).id == ROOT

    async def test_needs_a_branch_and_repository(self):
        async with FakeHeretto(tree()).client() as c:
            with pytest.raises(HerettoError, match="repository path like"):
                await c.resolve_folder_identifier("guides")


class TestFindByName:
    async def test_matches_below_the_folder(self):
        async with FakeHeretto(tree()).client() as c:
            found = await c.find_by_name("install", ROOT)
        assert [(m.entry.name, m.folder_path) for m in found.matches] == [
            ("install", "/guides"),
            ("install-screen.png", "/guides/install"),
            ("installing-on-linux.dita", "/guides/install"),
        ]
        assert found.folders_searched == 4 and not found.truncated

    async def test_exact_names_first(self):
        async with FakeHeretto(tree()).client() as c:
            found = await c.find_by_name("install-screen.png", ROOT)
        assert found.matches[0].entry.id == SCREEN

    async def test_folder_limit_is_reported(self):
        async with FakeHeretto(tree()).client() as c:
            found = await c.find_by_name("install", ROOT, max_folders=2)
        assert found.truncated and found.folders_searched == 2
        assert [m.entry.name for m in found.matches] == ["install"]

    async def test_depth_limit_is_reported(self):
        async with FakeHeretto(tree()).client() as c:
            found = await c.find_by_name("linux", ROOT, max_depth=1)
        assert found.truncated and found.matches == []

    async def test_complete_search_is_not_truncated(self):
        async with FakeHeretto(tree()).client() as c:
            found = await c.find_by_name("nothing-like-this", ROOT)
        assert found.matches == [] and not found.truncated

    async def test_an_unreadable_folder_is_skipped(self):
        routes = tree()
        routes[files_route(IMAGES)] = httpx.Response(500)
        async with FakeHeretto(routes).client() as c:
            found = await c.find_by_name("linux", ROOT)
        assert [m.entry.id for m in found.matches] == [LINUX]

    async def test_rejected_credentials_end_the_search(self):
        routes = tree()
        routes[files_route(IMAGES)] = httpx.Response(403)
        async with FakeHeretto(routes).client() as c:
            with pytest.raises(HerettoError, match="rejected"):
                await c.find_by_name("linux", ROOT)

    async def test_needs_a_query(self):
        async with FakeHeretto(tree()).client() as c:
            with pytest.raises(HerettoError, match="Enter part of a name"):
                await c.find_by_name("  ", ROOT)


# ── API ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def fake(monkeypatch):
    fake = FakeHeretto(tree())
    monkeypatch.setattr(heretto_routes.HerettoClient, "from_payload",
                        classmethod(lambda cls, payload: fake.client()))
    return fake


def api(heretto_credential, path=""):
    return f"/api/v1/heretto/{heretto_credential['id']}{path}"


class TestApi:
    def test_connections(self, client, new_user, heretto):
        make_credential(client, new_user["headers"], "jira")
        resp = client.get("/api/v1/heretto/connections", headers=new_user["headers"])
        assert resp.json() == [{"id": heretto["id"], "name": heretto["name"], "server_url": SERVER}]

    def test_repositories(self, client, new_user, heretto, fake):
        resp = client.get(api(heretto, "/repositories"), headers=new_user["headers"])
        assert resp.json()[0] == {"branch": "master", "repository": "product"}

    def test_open_repository(self, client, new_user, heretto, fake):
        resp = client.get(api(heretto, "/repositories/master/product"), headers=new_user["headers"])
        body = resp.json()
        assert body["id"] == ROOT and body["ancestors"] == [] and body["parent_id"] is None
        assert body["branch"] == "master" and body["repository"] == "product"
        assert [e["name"] for e in body["entries"]] == ["guides", "images", "overview.dita"]

    def test_open_folder(self, client, new_user, heretto, fake):
        resp = client.get(api(heretto, f"/folders/{INSTALL}"), headers=new_user["headers"])
        body = resp.json()
        assert body["ancestors"] is None and body["parent_id"] == GUIDES
        assert [e["name"] for e in body["entries"]] == ["install-screen.png", "installing-on-linux.dita"]
        assert body["entries"][0]["type"] is None
        assert body["entries"][1] == {"id": LINUX, "name": "installing-on-linux.dita", "kind": "topic",
                                      "type": "Topic", "mime_type": "application/xml"}
        with_crumbs = client.get(api(heretto, f"/folders/{INSTALL}?ancestors=true"),
                                 headers=new_user["headers"]).json()
        assert [a["id"] for a in with_crumbs["ancestors"]] == [ROOT, GUIDES]

    def test_resolve_folder(self, client, new_user, heretto, fake):
        resp = client.post(api(heretto, "/folders/resolve"), headers=new_user["headers"],
                           json={"branch": "master", "repository": "product", "path": "/guides/install"})
        assert resp.json()["id"] == INSTALL
        assert [a["name"] for a in resp.json()["ancestors"]] == ["documents", "guides"]

    def test_resolve_folder_without_a_repository(self, client, new_user, heretto, fake):
        resp = client.post(api(heretto, "/folders/resolve"), headers=new_user["headers"],
                           json={"path": "master/product/documents/guides/install"})
        assert resp.json()["id"] == INSTALL
        assert resp.json()["branch"] == "master" and resp.json()["repository"] == "product"

    def test_resolve_folder_error(self, client, new_user, heretto, fake):
        resp = client.post(api(heretto, "/folders/resolve"), headers=new_user["headers"],
                           json={"branch": "master", "repository": "product", "path": "guides/instal"})
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["reason"] == "error" and detail["folder_id"] == GUIDES
        assert detail["message"].startswith("No folder named 'instal'")

    def test_search(self, client, new_user, heretto, fake):
        resp = client.get(api(heretto, f"/folders/{GUIDES}/search?q=linux"), headers=new_user["headers"])
        assert resp.json() == {
            "query": "linux", "folders_searched": 2, "truncated": False,
            "matches": [{"id": LINUX, "name": "installing-on-linux.dita", "kind": "topic", "type": "Topic",
                         "mime_type": "application/xml", "folder_id": INSTALL, "folder_path": "/install"}],
        }

    def test_file(self, client, new_user, heretto, fake):
        resp = client.get(api(heretto, f"/files/{LINUX}"), headers=new_user["headers"])
        assert resp.json() == {
            "id": LINUX, "name": "installing-on-linux.dita", "title": "Installing on Linux",
            "kind": "topic", "is_map": False,
            "path": "master/product/documents/guides/install/installing-on-linux.dita",
            "folder_id": INSTALL, "mime_type": "application/xml", "status": "Approved",
            "last_modified": "2026-10-12T00:00:00+00:00",
            "editor_url": f"{SERVER}/#/editor/{LINUX}",
            "credential_id": heretto["id"], "credential_name": heretto["name"],
        }

    def test_resolve_file(self, client, new_user, heretto, fake):
        resp = client.post(api(heretto, "/resolve"), headers=new_user["headers"],
                           json={"identifier": "master/product/guides/install/installing-on-linux.dita"})
        assert resp.json()["id"] == LINUX

    def test_resolve_file_error_names_the_folder(self, client, new_user, heretto, fake):
        resp = client.post(api(heretto, "/resolve"), headers=new_user["headers"],
                           json={"identifier": "master/product/guides/glossary.dita"})
        assert resp.status_code == 400 and resp.json()["detail"]["folder_id"] == GUIDES

    def test_rejected_credentials(self, client, new_user, heretto, monkeypatch):
        fake = FakeHeretto(tree(), accept_auth=())
        monkeypatch.setattr(heretto_routes.HerettoClient, "from_payload",
                            classmethod(lambda cls, payload: fake.client()))
        resp = client.get(api(heretto, f"/folders/{ROOT}"), headers=new_user["headers"])
        assert resp.status_code == 400 and resp.json()["detail"]["reason"] == "credentials"

    def test_missing_folder(self, client, new_user, heretto, fake):
        resp = client.get(api(heretto, "/folders/f0000000-0000-0000-0000-00000000dead"),
                          headers=new_user["headers"])
        assert resp.json()["detail"]["reason"] == "not_found"

    def test_needs_an_own_connection(self, client, new_user, fake):
        other = register(client)
        theirs = make_credential(client, auth_headers(login(client, other["email"], other["password"])))
        resp = client.get(api(theirs, f"/folders/{ROOT}"), headers=new_user["headers"])
        assert resp.status_code == 404
        assert fake.requests == []

    def test_needs_sign_in(self, client, heretto):
        client.cookies.clear()
        assert client.get(api(heretto, "/repositories")).status_code == 401
