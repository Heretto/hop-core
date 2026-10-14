"""The Heretto client, DITA-to-text conversion, and reading references
(topics, maps and their linked topics) — against a fake Heretto."""

import base64

import httpx
import pytest

import hop_core.heretto.client as client_module
from hop_core.heretto import (
    HerettoClient,
    HerettoError,
    ReferenceContentSource,
    TTLReferenceCache,
    dita_to_text,
)
from hop_core.heretto import content as content_module

MAP_ID = "11111111-1111-1111-1111-111111111111"
TOPIC_A = "aaaaaaaa-0000-0000-0000-000000000001"
TOPIC_B = "aaaaaaaa-0000-0000-0000-000000000002"
TOPIC_C = "aaaaaaaa-0000-0000-0000-000000000003"
SUBMAP = "bbbbbbbb-0000-0000-0000-000000000001"
SERVER = "https://acme.heretto.com"


def record(file_id, name, title=None, content_type=None, path=None):
    meta = ""
    if title:
        meta += f'<meta name="title">{title}</meta>'
    if content_type:
        meta += f'<meta name="content-type">{content_type}</meta>'
    return (
        f'<resource id="{file_id}" last-modified="1"><name>{name}</name>'
        f"<xmldb-uri>{path or 'master/product/documents/' + name}</xmldb-uri>"
        f"<mime-type>application/xml</mime-type><metadata>{meta}</metadata></resource>"
    )


def topic(title, body):
    return f'<?xml version="1.0"?><concept id="c"><title>{title}</title><conbody><p>{body}</p></conbody></concept>'


def deps(**uri_to_id):
    rows = "".join(f'<resource id="{i}" relative-uri="{u}"/>' for u, i in uri_to_id.items())
    return f"<dependencies>{rows}</dependencies>"


class FakeHeretto:
    """Serves canned bodies by path; records each request's Authorization."""

    def __init__(self, routes, accept_auth=("Basic",)):
        self.routes = dict(routes)
        self.accept_auth = accept_auth
        self.requests = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("authorization", "")
        self.requests.append((request.url.path, auth.split(" ")[0]))
        if not any(auth.startswith(scheme) for scheme in self.accept_auth):
            return httpx.Response(401)
        body = self.routes.get(request.url.path)
        if body is None:
            return httpx.Response(404)
        if isinstance(body, httpx.Response):
            return body
        return httpx.Response(200, content=body.encode())

    def client(self, **kw):
        return HerettoClient(SERVER, "writer@acme.com", "tok-123",
                             transport=httpx.MockTransport(self.handler), **kw)

    def paths(self):
        return [p for p, _ in self.requests]


@pytest.fixture(autouse=True)
def _skip_dns(monkeypatch):
    """The SSRF check resolves hostnames; the fake host does not exist."""
    monkeypatch.setattr(client_module, "validate_server_url", lambda url: url)


def files_route(file_id):
    return f"/rest/all-files/{file_id}"


# ── Client ────────────────────────────────────────────────────────────────────

class TestClient:
    async def test_basic_auth_with_the_api_token(self):
        fake = FakeHeretto({files_route(TOPIC_A): record(TOPIC_A, "a.dita", "Alpha")})
        async with fake.client() as c:
            f = await c.get_file(TOPIC_A)
        assert f.title == "Alpha" and not f.is_map
        assert fake.requests == [(files_route(TOPIC_A), "Basic")]

    async def test_falls_back_to_bearer_and_remembers_it(self):
        fake = FakeHeretto({
            files_route(TOPIC_A): record(TOPIC_A, "a.dita"),
            files_route(TOPIC_B): record(TOPIC_B, "b.dita"),
        }, accept_auth=("Bearer",))
        async with fake.client() as c:
            await c.get_file(TOPIC_A)
            await c.get_file(TOPIC_B)
        assert [a for _, a in fake.requests] == ["Basic", "Bearer", "Bearer"]

    async def test_rejected_credentials(self):
        fake = FakeHeretto({}, accept_auth=())
        async with fake.client() as c:
            with pytest.raises(HerettoError, match="rejected the connection"):
                await c.get_file(TOPIC_A)

    async def test_missing_file(self):
        async with FakeHeretto({}).client() as c:
            with pytest.raises(HerettoError, match="no file or folder"):
                await c.get_file(TOPIC_A)

    async def test_redirects_are_not_followed(self):
        fake = FakeHeretto({files_route(TOPIC_A): httpx.Response(302, headers={"location": "http://10.0.0.1/"})})
        async with fake.client() as c:
            with pytest.raises(HerettoError, match="redirected"):
                await c.get_file(TOPIC_A)

    def test_private_server_url_is_refused(self, monkeypatch):
        from hop_core.core.security import validate_server_url
        monkeypatch.setattr(client_module, "validate_server_url", validate_server_url)
        with pytest.raises(HerettoError, match="not allowed"):
            HerettoClient("https://127.0.0.1", "u", "t")

    def test_incomplete_connection(self):
        with pytest.raises(HerettoError, match="missing"):
            HerettoClient.from_payload({"server_url": SERVER, "username": "u"})

    def test_map_detection(self):
        f = client_module.parse_file(record(MAP_ID, "guide.ditamap").encode())
        assert f.is_map
        f = client_module.parse_file(record(MAP_ID, "x.xml", content_type="Map").encode())
        assert f.is_map


class TestResolve:
    async def test_file_id(self):
        fake = FakeHeretto({files_route(TOPIC_A): record(TOPIC_A, "a.dita")})
        async with fake.client() as c:
            assert (await c.resolve(TOPIC_A.upper())).id == TOPIC_A

    async def test_heretto_url(self):
        fake = FakeHeretto({files_route(TOPIC_A): record(TOPIC_A, "a.dita")})
        async with fake.client() as c:
            f = await c.resolve(f"{SERVER}/heretto/ezd/#/editor/{TOPIC_A}?x=1")
        assert f.id == TOPIC_A

    async def test_repository_path_walks_folders(self):
        fake = FakeHeretto({
            "/rest/branches/master/repositories/product/documents/":
                '<folder id="root"><children><folder name="Guides" id="g1"/></children></folder>',
            files_route("g1"):
                f'<folder id="g1"><children><resource name="style.dita" id="{TOPIC_A}"/></children></folder>',
            files_route(TOPIC_A): record(TOPIC_A, "style.dita", "Style"),
        })
        async with fake.client() as c:
            f = await c.resolve("master/product/documents/guides/STYLE.dita")
        assert f.title == "Style"

    async def test_path_without_documents_segment(self):
        fake = FakeHeretto({
            "/rest/branches/master/repositories/product/documents/":
                f'<folder id="root"><children><resource name="x.dita" id="{TOPIC_A}"/></children></folder>',
            files_route(TOPIC_A): record(TOPIC_A, "x.dita"),
        })
        async with fake.client() as c:
            assert (await c.resolve("master/product/x.dita")).id == TOPIC_A

    async def test_wrong_path_lists_what_is_there(self):
        fake = FakeHeretto({
            "/rest/branches/master/repositories/product/documents/":
                '<folder id="root"><children><folder name="Guides" id="g1"/>'
                '<resource name="readme.dita" id="r"/></children></folder>',
        })
        async with fake.client() as c:
            with pytest.raises(HerettoError, match=r"Guides/, readme\.dita"):
                await c.resolve("master/product/documents/Nope/x.dita")

    async def test_folder_is_not_a_file(self):
        fake = FakeHeretto({files_route(TOPIC_A): '<folder id="f"><children/></folder>'})
        async with fake.client() as c:
            with pytest.raises(HerettoError, match="folder, not a file"):
                await c.resolve(TOPIC_A)

    async def test_nonsense(self):
        async with FakeHeretto({}).client() as c:
            with pytest.raises(HerettoError, match="Not a Heretto identifier"):
                await c.resolve("style guide please")


# ── DITA to text ──────────────────────────────────────────────────────────────

class TestDitaToText:
    def test_structure(self):
        title, text = dita_to_text(
            b'<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">'
            b'<concept id="v"><title>Voice</title><shortdesc>How we sound.</shortdesc>'
            b'<prolog><metadata><keywords><keyword>hidden</keyword></keywords></metadata></prolog>'
            b'<conbody><p>Use <b>second person</b>&nbsp;and <codeph>present</codeph>.</p>'
            b'<note type="important">No <i>please</i>.</note>'
            b'<section><title>Lists</title><ol><li>One</li><li>Two</li></ol></section>'
            b'<draft-comment>secret</draft-comment></conbody></concept>', 2)
        assert title == "Voice"
        assert text.startswith("## Voice\n\nHow we sound.")
        assert "Use **second person** and `present`." in text
        assert "> **Important:** No *please*." in text
        assert "### Lists" in text and "1. One" in text
        assert "hidden" not in text and "secret" not in text

    def test_glossary_entry(self):
        _, text = dita_to_text(b"<glossentry id='g'><glossterm>Topic</glossterm>"
                               b"<glossdef>A unit of content.</glossdef></glossentry>")
        assert text == "# Topic\n\nA unit of content."

    def test_definition_list_and_table(self):
        _, text = dita_to_text(
            b"<reference id='r'><title>T</title><refbody><section>"
            b"<dl><dlentry><dt>DITA</dt><dd>An XML standard.</dd></dlentry></dl>"
            b"<simpletable><sthead><stentry>Use</stentry><stentry>Avoid</stentry></sthead>"
            b"<strow><stentry>select</stentry><stentry>click on</stentry></strow></simpletable>"
            b"</section></refbody></reference>")
        assert "- **DITA**: An XML standard." in text
        assert "| Use | Avoid |\n| select | click on |" in text

    def test_malformed_falls_back_to_text(self):
        title, text = dita_to_text(b"<topic><title>Broken</title><p>still readable")
        assert title is None and "still readable" in text


# ── Reading references ────────────────────────────────────────────────────────

MAP_XML = f"""<?xml version="1.0"?><map><title>Writer's Guide</title>
<topicref href="topics/a.dita">
  <topicref href="topics/b.dita#section"/>
</topicref>
<topicref href="https://example.com" scope="external"/>
<topicref href="images/logo.png"/>
<mapref href="sub/terms.ditamap"/>
<topicref href="topics/a.dita"/>
<topicref href="topics/missing.dita"/>
</map>"""
SUBMAP_XML = '<map><title>Terms</title><topicref href="c.dita"/></map>'


def map_routes():
    return {
        files_route(MAP_ID): record(MAP_ID, "guide.ditamap", "Writer's Guide"),
        files_route(MAP_ID) + "/content": MAP_XML,
        files_route(MAP_ID) + "/links/dependencies":
            deps(**{"topics/a.dita": TOPIC_A, "topics/b.dita": TOPIC_B, "sub/terms.ditamap": SUBMAP}),
        files_route(SUBMAP) + "/content": SUBMAP_XML,
        files_route(SUBMAP) + "/links/dependencies": deps(**{"c.dita": TOPIC_C}),
        files_route(TOPIC_A) + "/content": topic("Alpha", "First."),
        files_route(TOPIC_B) + "/content": topic("Beta", "Second."),
        files_route(TOPIC_C) + "/content": topic("Gamma", "Third."),
        files_route(TOPIC_A): record(TOPIC_A, "a.dita", "Alpha"),
    }


def source_for(fake, cache=None):
    async def load(_cid):
        return {"server_url": SERVER, "username": "u", "token": "t"}
    return ReferenceContentSource(
        load, cache=cache or TTLReferenceCache(),
        client_factory=lambda payload: fake.client(),
    )


class TestReadingReferences:
    async def test_topic_reads_as_itself(self):
        fake = FakeHeretto(map_routes())
        content = await source_for(fake).read("cred", TOPIC_A)
        assert content.title == "Alpha"
        assert content.text == "# Alpha\n\nFirst."

    async def test_map_reads_as_its_topics_in_order(self):
        fake = FakeHeretto(map_routes())
        content = await source_for(fake).read("cred", MAP_ID)
        text = content.text
        assert text.startswith("# Writer's Guide")
        # Nesting follows the map; the submap's title heads its topics.
        assert text.index("## Alpha") < text.index("### Beta") < text.index("## Terms") < text.index("### Gamma")
        assert content.topic_count == 3

    async def test_map_skips_links_that_are_not_content(self):
        fake = FakeHeretto(map_routes())
        content = await source_for(fake).read("cred", MAP_ID)
        assert "example.com" not in content.text and "logo" not in content.text
        assert content.text.count("## Alpha") == 1  # linked twice, included once
        assert any("topics/missing.dita" in n for n in content.notes)
        assert "_Note:" in content.as_prompt_text()

    async def test_topic_limit_is_reported(self, monkeypatch):
        monkeypatch.setattr(content_module, "MAX_TOPICS", 1)
        content = await source_for(FakeHeretto(map_routes())).read("cred", MAP_ID)
        assert content.topic_count == 1
        assert any("first 1 topics" in n for n in content.notes)

    async def test_size_limit_is_reported(self, monkeypatch):
        monkeypatch.setattr(content_module, "MAX_CHARS", 40)
        content = await source_for(FakeHeretto(map_routes())).read("cred", MAP_ID)
        assert len(content.text) <= 40
        assert any("cut off" in n for n in content.notes)

    async def test_unreadable_linked_topic_is_noted_not_fatal(self):
        routes = map_routes()
        del routes[files_route(TOPIC_B) + "/content"]
        content = await source_for(FakeHeretto(routes)).read("cred", MAP_ID)
        assert "## Alpha" in content.text and "Beta" not in content.text
        assert any("could not be read" in n for n in content.notes)

    async def test_cache_serves_repeat_reads(self):
        fake = FakeHeretto(map_routes())
        source = source_for(fake)
        await source.read("cred", TOPIC_A)
        before = len(fake.requests)
        await source.read("cred", TOPIC_A)
        assert len(fake.requests) == before

    async def test_cache_expires(self):
        fake = FakeHeretto(map_routes())
        source = source_for(fake, cache=TTLReferenceCache(ttl=-1))
        await source.read("cred", TOPIC_A)
        before = len(fake.requests)
        await source.read("cred", TOPIC_A)
        assert len(fake.requests) > before
