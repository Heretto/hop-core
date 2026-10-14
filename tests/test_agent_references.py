"""Agent references: URLs and Heretto files with guidance and a type —
stored through the API, composed into the prompt, and read during runs."""

import uuid

import httpx
import pytest

import hop_core.api.routes.agents as agent_routes
import hop_core.heretto.client as client_module
from hop_core.agents import AgentDefinition, AgentReferenceSpec, AgentRunner, AiConfiguration, providers
from hop_core.ai import ChatMessage, GenerationRequest
from hop_core.credentials import AI_PROVIDER_TYPES, register_builtin_types
from hop_core.db import get_session_factory
from hop_core.heretto import HerettoClient, HerettoError, ReferenceContent
from hop_core.heretto.content import default_cache
from hop_core.models.agent import Agent
from hop_core.models.enums import CredentialTypeRegistry
from tests.conftest import auth_headers, login, register
from tests.test_agent_chat import FakeResponse, fake_http  # noqa: F401 (fixture)
from tests.test_heretto import MAP_ID, SERVER, TOPIC_A, FakeHeretto, map_routes

STYLE = "cccccccc-0000-0000-0000-000000000001"
HI = [ChatMessage(role="user", content="hi")]


def unique(prefix="Agent"):
    return f"{prefix} {uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _types():
    CredentialTypeRegistry.clear()
    register_builtin_types("jira", "heretto", *AI_PROVIDER_TYPES)
    default_cache.clear()
    yield
    CredentialTypeRegistry.clear()
    default_cache.clear()


def make_credential(client, headers, type_="heretto", **values):
    defaults = {
        "heretto": {"server_url": SERVER, "username": "writer@acme.com", "token": "tok-123"},
        "anthropic": {"api_key": "sk-ant", "model": "claude-opus-5"},
        "jira": {"server_url": "https://acme.atlassian.net", "email": "a@b.c", "api_token": "t"},
    }[type_]
    resp = client.post("/api/v1/credentials", headers=headers, json={
        "type": type_, "name": unique(type_), "credentials": {**defaults, **values},
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


def heretto_ref(credential_id, file_id=TOPIC_A, **kw):
    return {"kind": "heretto", "credential_id": credential_id, "file_id": file_id,
            "title": kw.pop("title", "Alpha"), **kw}


def create_agent(client, headers, **body):
    resp = client.post("/api/v1/agents", headers=headers, json={"name": unique(), **body})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture
def heretto(client, new_user):
    return make_credential(client, new_user["headers"])


# ── Storing references ────────────────────────────────────────────────────────

class TestStoringReferences:
    def test_create_with_url_and_heretto_references(self, client, new_user, heretto):
        agent = create_agent(client, new_user["headers"], references=[
            {"kind": "url", "url": "HTTPS://Docs.Example.com/api/", "guidance": "For API facts."},
            heretto_ref(heretto["id"], reference_type="style_guide", guidance="  House style.  "),
        ])
        url, style = agent["references"]
        assert url["url"] == "https://docs.example.com/api" and url["guidance"] == "For API facts."
        assert style["reference_type"] == "style_guide" and style["guidance"] == "House style."
        assert style["credential_name"] == heretto["name"] and style["available"]
        # URL references still populate the legacy field for older clients.
        assert agent["permitted_urls"] == ["https://docs.example.com/api"]

    def test_heretto_type_defaults_to_general(self, client, new_user, heretto):
        agent = create_agent(client, new_user["headers"], references=[heretto_ref(heretto["id"])])
        assert agent["references"][0]["reference_type"] == "general"

    def test_order_is_kept(self, client, new_user, heretto):
        refs = [{"kind": "url", "url": f"https://e.com/{i}"} for i in range(3)]
        agent = create_agent(client, new_user["headers"], references=refs)
        assert [r["url"] for r in agent["references"]] == [r["url"] for r in refs]

    @pytest.mark.parametrize("bad", [
        {"kind": "url"},
        {"kind": "url", "url": "ftp://x"},
        {"kind": "heretto", "credential_id": str(uuid.uuid4())},
        {"kind": "heretto", "credential_id": str(uuid.uuid4()), "file_id": "not-an-id"},
        {"kind": "heretto", "credential_id": str(uuid.uuid4()), "file_id": TOPIC_A, "reference_type": "recipes"},
    ])
    def test_invalid_references_are_rejected(self, client, new_user, bad):
        resp = client.post("/api/v1/agents", headers=new_user["headers"],
                           json={"name": unique(), "references": [bad]})
        assert resp.status_code == 422

    def test_connection_must_be_heretto(self, client, new_user):
        jira = make_credential(client, new_user["headers"], "jira")
        resp = client.post("/api/v1/agents", headers=new_user["headers"],
                           json={"name": unique(), "references": [heretto_ref(jira["id"])]})
        assert resp.status_code == 400

    def test_connection_must_be_in_the_organization(self, client, new_user):
        other = register(client)
        other_headers = auth_headers(login(client, other["email"], other["password"]))
        theirs = make_credential(client, other_headers)
        resp = client.post("/api/v1/agents", headers=new_user["headers"],
                           json={"name": unique(), "references": [heretto_ref(theirs["id"])]})
        assert resp.status_code == 400

    def test_update_replaces_the_list(self, client, new_user, heretto):
        agent = create_agent(client, new_user["headers"], references=[
            {"kind": "url", "url": "https://a.com"}, heretto_ref(heretto["id"]),
        ])
        resp = client.put(f"/api/v1/agents/{agent['id']}", headers=new_user["headers"],
                          json={"references": [heretto_ref(heretto["id"], reference_type="terminology")]})
        assert resp.status_code == 200, resp.text
        [ref] = resp.json()["references"]
        assert ref["reference_type"] == "terminology"
        assert resp.json()["permitted_urls"] == []

    def test_deleted_connection_leaves_the_reference_unavailable(self, client, new_user, heretto):
        agent = create_agent(client, new_user["headers"], references=[heretto_ref(heretto["id"])])
        client.delete(f"/api/v1/credentials/{heretto['id']}", headers=new_user["headers"])
        [ref] = client.get(f"/api/v1/agents/{agent['id']}", headers=new_user["headers"]).json()["references"]
        assert ref["available"] is False and ref["credential_name"] is None
        assert ref["title"] == "Alpha"

    def test_unavailable_reference_can_be_saved_back(self, client, new_user, heretto):
        """The editor sends the list back as it got it; a deleted connection
        must not block saving unrelated changes."""
        agent = create_agent(client, new_user["headers"], references=[heretto_ref(heretto["id"])])
        client.delete(f"/api/v1/credentials/{heretto['id']}", headers=new_user["headers"])
        refs = client.get(f"/api/v1/agents/{agent['id']}", headers=new_user["headers"]).json()["references"]
        resp = client.put(f"/api/v1/agents/{agent['id']}", headers=new_user["headers"],
                          json={"name": unique(), "references": refs})
        assert resp.status_code == 200, resp.text
        [ref] = resp.json()["references"]
        assert ref["available"] is False and ref["file_id"] == TOPIC_A


class TestOlderClients:
    def test_permitted_urls_on_create_become_url_references(self, client, new_user):
        agent = create_agent(client, new_user["headers"], permitted_urls=["https://a.com/x"])
        assert agent["references"] == [{**agent["references"][0], "kind": "url", "url": "https://a.com/x"}]

    def test_permitted_urls_update_keeps_heretto_references_and_url_guidance(self, client, new_user, heretto):
        agent = create_agent(client, new_user["headers"], references=[
            {"kind": "url", "url": "https://keep.com", "guidance": "Kept."},
            {"kind": "url", "url": "https://drop.com"},
            heretto_ref(heretto["id"], reference_type="style_guide"),
        ])
        resp = client.put(f"/api/v1/agents/{agent['id']}", headers=new_user["headers"],
                          json={"permitted_urls": ["https://keep.com", "https://new.com"]})
        refs = resp.json()["references"]
        assert [(r["kind"], r.get("url"), r["guidance"]) for r in refs] == [
            ("url", "https://keep.com", "Kept."), ("url", "https://new.com", ""), ("heretto", None, ""),
        ]
        assert refs[2]["reference_type"] == "style_guide"

    def test_agent_saved_before_references_reads_its_urls(self, client, new_user):
        agent = create_agent(client, new_user["headers"])
        db = get_session_factory()()
        row = db.get(Agent, uuid.UUID(agent["id"]))
        row.permitted_urls = ["https://legacy.example.com"]
        db.commit()
        body = client.get(f"/api/v1/agents/{agent['id']}", headers=new_user["headers"]).json()
        assert body["permitted_urls"] == ["https://legacy.example.com"]
        assert body["references"][0]["url"] == "https://legacy.example.com"
        db.refresh(row)
        assert AgentDefinition.from_model(row).permitted_urls == ["https://legacy.example.com"]
        db.close()


# ── Heretto endpoints ─────────────────────────────────────────────────────────

class TestHerettoEndpoints:
    def test_lists_only_heretto_connections(self, client, new_user, heretto):
        make_credential(client, new_user["headers"], "jira")
        resp = client.get("/api/v1/agents/heretto-connections", headers=new_user["headers"])
        assert resp.status_code == 200
        assert resp.json() == [{"id": heretto["id"], "name": heretto["name"], "server_url": SERVER}]

    @pytest.fixture
    def fake_heretto(self, monkeypatch):
        fake = FakeHeretto(map_routes())
        monkeypatch.setattr(client_module, "validate_server_url", lambda url: url)
        monkeypatch.setattr(agent_routes.HerettoClient, "from_payload",
                            classmethod(lambda cls, payload: fake.client()))
        return fake

    def test_resolve_describes_the_file(self, client, new_user, heretto, fake_heretto):
        resp = client.post("/api/v1/agents/heretto/resolve", headers=new_user["headers"],
                           json={"credential_id": heretto["id"], "identifier": f"{SERVER}/x/{MAP_ID}"})
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"file_id": MAP_ID, "title": "Writer's Guide", "name": "guide.ditamap",
                               "path": "master/product/documents/guide.ditamap", "is_map": True}

    def test_resolve_reports_heretto_errors(self, client, new_user, heretto, fake_heretto):
        resp = client.post("/api/v1/agents/heretto/resolve", headers=new_user["headers"],
                           json={"credential_id": heretto["id"], "identifier": str(uuid.uuid4())})
        assert resp.status_code == 400
        assert "no file or folder" in resp.json()["detail"]

    def test_resolve_needs_an_own_connection(self, client, new_user):
        other = register(client)
        theirs = make_credential(client, auth_headers(login(client, other["email"], other["password"])))
        resp = client.post("/api/v1/agents/heretto/resolve", headers=new_user["headers"],
                           json={"credential_id": theirs["id"], "identifier": TOPIC_A})
        assert resp.status_code == 404


# ── Prompt and runner ─────────────────────────────────────────────────────────

class FakeSource:
    def __init__(self, texts=None, error=None):
        self.texts = texts or {}
        self.error = error
        self.reads = []

    async def read(self, credential_id, file_id):
        self.reads.append(file_id)
        if self.error:
            raise self.error
        return ReferenceContent(file_id, "T", self.texts.get(file_id, f"text of {file_id}"))


def definition(*refs, urls=()):
    return AgentDefinition(
        name="Writer", agent_id="a1",
        ai_configuration=AiConfiguration(credential_id="c", name="AI", provider="anthropic", model="m"),
        permitted_urls=list(urls),
        references=[AgentReferenceSpec(**r) for r in refs],
    )


def ref(id_, type_, **kw):
    return {"id": id_, "kind": "heretto", "credential_id": "cred", "file_id": f"file-{id_}",
            "title": f"Title {id_}", "reference_type": type_, **kw}


class RecordingService:
    def __init__(self):
        self.requests = []

    async def generate(self, request: GenerationRequest):
        self.requests.append(request)
        return type("R", (), {"content": "ok"})()


class ToolService(RecordingService):
    def __init__(self, calls):
        super().__init__()
        self.calls = calls
        self.results = []

    async def generate_with_tools(self, request, executor):
        self.requests.append(request)
        for name, args in self.calls:
            self.results.append(await executor(name, args))
        return type("R", (), {"content": "ok"})()


class TestPromptAndRunner:
    async def test_included_types_are_in_the_prompt_with_their_framing(self):
        source = FakeSource({"file-s": "Use sentence case.", "file-t": "**API**: interface"})
        service = RecordingService()
        await AgentRunner(service, reference_source=source).chat(
            definition(ref("t", "terminology"), ref("s", "style_guide", guidance="Applies to UI text.")),
            HI,
        )
        prompt = service.requests[0].system_prompt
        assert "## Reference material" in prompt
        # Ordered by type, whatever order they were added in.
        assert prompt.index("### Style guide: Title s") < prompt.index("### Terminology: Title t")
        assert "Guidance from the agent's operator: Applies to UI text." in prompt
        assert "Use sentence case." in prompt and "**API**: interface" in prompt
        assert "the style guide wins" in prompt

    async def test_general_content_is_listed_not_included(self):
        source = FakeSource({"file-g": "BODY"})
        service = ToolService([])
        await AgentRunner(service, reference_source=source).run(
            definition(ref("g", "general", is_map=True, guidance="Product facts.")),
            __import__("hop_core.agents", fromlist=["AgentRequest"]).AgentRequest(instructions="x"),
        )
        prompt = service.requests[0].system_prompt
        assert "## Heretto content you can read" in prompt
        assert "`g` — Title g (a map" in prompt and "Guidance: Product facts." in prompt
        assert "BODY" not in prompt and source.reads == []
        assert [t.name for t in service.requests[0].tools] == ["read_heretto"]

    async def test_read_heretto_reads_listed_references_only(self):
        source = FakeSource({"file-g": "BODY"})
        service = ToolService([
            ("read_heretto", {"reference_id": "g"}),
            ("read_heretto", {"reference_id": "s"}),     # included, not readable on demand
            ("read_heretto", {"reference_id": "nope"}),
        ])
        await AgentRunner(service, reference_source=source).chat(
            definition(ref("g", "general"), ref("s", "style_guide")),
            HI,
        )
        assert service.results[0] == "BODY"
        assert "No readable reference" in service.results[1]
        assert "No readable reference" in service.results[2]

    async def test_unreadable_included_reference_is_noted_not_fatal(self):
        service = RecordingService()
        result = await AgentRunner(service, reference_source=FakeSource(error=HerettoError("Heretto is down"))).chat(
            definition(ref("s", "style_guide")), HI,
        )
        assert result.output == "ok"
        assert "This reference could not be included: Heretto is down." in service.requests[0].system_prompt

    async def test_without_a_source_heretto_is_unavailable(self):
        service = ToolService([])
        await AgentRunner(service).chat(
            definition(ref("s", "style_guide"), ref("g", "general"), urls=["https://a.com"]),
            HI,
        )
        request = service.requests[0]
        assert "not available to this runner" in request.system_prompt
        assert [t.name for t in request.tools] == ["read_url"]

    async def test_url_guidance_is_shown(self):
        service = RecordingService()
        await AgentRunner(service).chat(
            AgentDefinition(name="W", ai_configuration=AiConfiguration(credential_id="c", name="AI", provider="x"),
                            references=[AgentReferenceSpec(id="u", kind="url", url="https://a.com", guidance="API docs.")]),
            HI,
        )
        assert "- https://a.com\n  Guidance: API docs." in service.requests[0].system_prompt

    async def test_a_definition_with_only_urls_is_unchanged(self):
        service = RecordingService()
        await AgentRunner(service).chat(definition(urls=["https://a.com"]), HI)
        prompt = service.requests[0].system_prompt
        assert "## Permitted reference URLs" in prompt and "Reference material" not in prompt


class TestChatEndToEnd:
    """The chat route reads references through the organization's connection."""

    def test_style_guide_and_on_demand_map(self, client, new_user, heretto, monkeypatch, fake_http):
        fake = FakeHeretto({
            **map_routes(),
            f"/rest/all-files/{STYLE}": f'<resource id="{STYLE}"><name>style.dita</name></resource>',
            f"/rest/all-files/{STYLE}/content":
                "<concept id='s'><title>House style</title><conbody><p>Use sentence case.</p></conbody></concept>",
        })
        monkeypatch.setattr(client_module, "validate_server_url", lambda url: url)
        monkeypatch.setattr(HerettoClient, "from_payload", classmethod(lambda cls, payload: fake.client()))
        ai = make_credential(client, new_user["headers"], "anthropic")
        agent = create_agent(client, new_user["headers"], ai_configuration_id=ai["id"], references=[
            heretto_ref(heretto["id"], STYLE, reference_type="style_guide", title="House style"),
            heretto_ref(heretto["id"], MAP_ID, title="Writer's Guide", is_map=True),
        ])
        map_ref_id = agent["references"][1]["id"]

        http = fake_http(
            FakeResponse(200, {"stop_reason": "tool_use", "content": [
                {"type": "tool_use", "id": "t1", "name": "read_heretto", "input": {"reference_id": map_ref_id}},
            ]}),
            FakeResponse(200, {"content": [{"type": "text", "text": "Done."}]}),
        )
        resp = client.post(f"/api/v1/agents/{agent['id']}/chat", headers=new_user["headers"],
                           json={"messages": [{"role": "user", "content": "Summarize the guide."}]})
        assert resp.status_code == 200, resp.text
        assert resp.json()["message"]["content"] == "Done."

        prompt = resp.json()["system_prompt"]
        assert "### Style guide: House style" in prompt and "Use sentence case." in prompt
        assert f"`{map_ref_id}` — Writer's Guide" in prompt

        first, second = http.requests
        assert {t["name"] for t in first["json"]["tools"]} == {"read_heretto"}
        tool_result = second["json"]["messages"][-1]["content"][0]["content"]
        assert tool_result.startswith("# Writer's Guide") and "## Alpha" in tool_result
