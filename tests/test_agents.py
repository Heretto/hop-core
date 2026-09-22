"""Tests for /api/v1/agents/* endpoints and the agent runtime."""

import uuid
import pytest

from hop_core.agents import (
    AgentDefinition,
    AgentNotConfigured,
    AgentRequest,
    AgentRunner,
    AiConfiguration,
    ContextFile,
    is_url_permitted,
    normalize_url,
)
from hop_core.agents.urls import InvalidPermittedUrl
from hop_core.ai import GenerationRequest
from hop_core.models.enums import CredentialTypeRegistry
from tests.conftest import register, login, auth_headers, make_email


def unique_name(prefix: str = "Release Notes Writer") -> str:
    """Agent names are unique per organization, so tests must not collide."""
    return f"{prefix} {uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _registered_ai_types():
    """Most tests need at least one credential type to be an AI configuration."""
    CredentialTypeRegistry.clear()
    CredentialTypeRegistry.register("anthropic", label="Anthropic", is_ai_configuration=True)
    CredentialTypeRegistry.register("openai", label="OpenAI", is_ai_configuration=True)
    CredentialTypeRegistry.register("jira", label="Jira")
    yield
    CredentialTypeRegistry.clear()


def make_ai_configuration(client, headers, name: str = None, model: str = "claude-opus-5",
                          provider: str = "anthropic") -> dict:
    """Create an AI configuration the way a host app would — a credential."""
    resp = client.post("/api/v1/credentials", headers=headers, json={
        "type": provider,
        "name": name or unique_name("AI Config"),
        "credentials": {"api_key": "sk-test-abc123", "model": model},
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


def agent_payload(name: str = None, **overrides) -> dict:
    payload = {
        "name": name or unique_name(),
        "description": "Turns merged pull requests into customer-facing notes.",
        "context_files": [
            {"name": "voice-and-tone.md", "content": "# Voice\n\nPlain, direct."},
            {"name": "audience.md", "content": "# Audience\n\nTechnical writers."},
        ],
        "permitted_urls": ["https://docs.example.com/style"],
        "feedback_memory": "Keep entries under two sentences.",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def user_with_agent(client, new_user):
    """User whose org already has one agent."""
    resp = client.post("/api/v1/agents", headers=new_user["headers"], json=agent_payload())
    assert resp.status_code == 200, resp.text
    return {**new_user, "agent": resp.json()}


class TestCreateAgent:
    def test_creates_with_full_configuration(self, client, new_user):
        payload = agent_payload()
        resp = client.post("/api/v1/agents", headers=new_user["headers"], json=payload)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == payload["name"]
        assert body["permitted_urls"] == ["https://docs.example.com/style"]
        assert body["feedback_memory"] == "Keep entries under two sentences."
        assert body["is_active"] is True
        assert body["created_by"] == new_user["email"]

    def test_context_files_keep_their_order(self, client, new_user):
        resp = client.post("/api/v1/agents", headers=new_user["headers"], json=agent_payload())
        files = resp.json()["context_files"]

        assert [f["name"] for f in files] == ["voice-and-tone.md", "audience.md"]
        assert [f["position"] for f in files] == [0, 1]
        assert files[0]["content"].startswith("# Voice")

    def test_minimal_agent_needs_only_a_name(self, client, new_user):
        resp = client.post("/api/v1/agents", headers=new_user["headers"], json={
            "name": unique_name("Minimal"),
        })

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ai_configuration_id"] is None
        assert body["ai_configuration"] is None
        assert body["context_files"] == []
        assert body["permitted_urls"] == []
        assert body["feedback_memory"] == ""

    def test_duplicate_name_rejected(self, client, user_with_agent):
        resp = client.post("/api/v1/agents", headers=user_with_agent["headers"], json=agent_payload(
            name=user_with_agent["agent"]["name"],
        ))

        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_selects_an_ai_configuration(self, client, new_user):
        configuration = make_ai_configuration(client, new_user["headers"])

        resp = client.post("/api/v1/agents", headers=new_user["headers"], json=agent_payload(
            ai_configuration_id=configuration["id"],
        ))

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["ai_configuration_id"] == configuration["id"]
        assert body["ai_configuration"]["name"] == configuration["name"]
        assert body["ai_configuration"]["provider"] == "anthropic"
        assert body["ai_configuration"]["provider_label"] == "Anthropic"
        assert body["ai_configuration"]["model"] == "claude-opus-5"

    def test_ai_configuration_never_returns_the_api_key(self, client, new_user):
        configuration = make_ai_configuration(client, new_user["headers"])

        resp = client.post("/api/v1/agents", headers=new_user["headers"], json=agent_payload(
            ai_configuration_id=configuration["id"],
        ))

        assert "sk-test-abc123" not in resp.text
        assert "api_key" not in resp.text

    def test_permitted_urls_are_normalized(self, client, new_user):
        resp = client.post("/api/v1/agents", headers=new_user["headers"], json=agent_payload(
            permitted_urls=["HTTPS://Docs.Example.com:443/guide/", "https://docs.example.com/guide"],
        ))

        assert resp.status_code == 200, resp.text
        assert resp.json()["permitted_urls"] == ["https://docs.example.com/guide"]

    def test_non_http_url_rejected(self, client, new_user):
        resp = client.post("/api/v1/agents", headers=new_user["headers"], json=agent_payload(
            permitted_urls=["ftp://files.example.com/docs"],
        ))
        assert resp.status_code == 422

    def test_unknown_ai_configuration_rejected(self, client, new_user):
        resp = client.post("/api/v1/agents", headers=new_user["headers"], json=agent_payload(
            ai_configuration_id=str(uuid.uuid4()),
        ))

        assert resp.status_code == 400
        assert "AI configuration not found" in resp.json()["detail"]

    def test_non_ai_credential_rejected(self, client, new_user):
        """A Jira credential is a credential, but it is not a model configuration."""
        jira = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "jira",
            "name": unique_name("Jira"),
            "credentials": {"api_token": "t"},
        }).json()

        resp = client.post("/api/v1/agents", headers=new_user["headers"], json=agent_payload(
            ai_configuration_id=jira["id"],
        ))

        assert resp.status_code == 400
        assert "AI configuration not found" in resp.json()["detail"]

    def test_another_organizations_configuration_rejected(self, client, new_user):
        other = register(client)
        other_token = login(client, other["email"], other["password"])
        foreign = make_ai_configuration(client, auth_headers(other_token))

        resp = client.post("/api/v1/agents", headers=new_user["headers"], json=agent_payload(
            ai_configuration_id=foreign["id"],
        ))

        assert resp.status_code == 400

    def test_unauthenticated_rejected(self, client):
        resp = client.post("/api/v1/agents", json=agent_payload())
        assert resp.status_code == 401


class TestListAgents:
    def test_returns_list(self, client, new_user):
        resp = client.get("/api/v1/agents", headers=new_user["headers"])
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_created_agents_appear(self, client, user_with_agent):
        resp = client.get("/api/v1/agents", headers=user_with_agent["headers"])
        assert resp.status_code == 200
        assert user_with_agent["agent"]["id"] in [a["id"] for a in resp.json()]

    def test_summary_omits_context_bodies(self, client, user_with_agent):
        resp = client.get("/api/v1/agents", headers=user_with_agent["headers"])
        summary = next(a for a in resp.json() if a["id"] == user_with_agent["agent"]["id"])

        assert "context_files" not in summary
        assert summary["context_file_count"] == 2
        assert summary["has_feedback_memory"] is True

    def test_scoped_to_organization(self, client, user_with_agent):
        other = register(client)
        token = login(client, other["email"], other["password"])

        resp = client.get("/api/v1/agents", headers=auth_headers(token))
        assert resp.status_code == 200
        assert user_with_agent["agent"]["id"] not in [a["id"] for a in resp.json()]

    def test_unauthenticated_rejected(self, client):
        assert client.get("/api/v1/agents").status_code == 401


class TestGetAgent:
    def test_returns_full_agent(self, client, user_with_agent):
        resp = client.get(
            f"/api/v1/agents/{user_with_agent['agent']['id']}",
            headers=user_with_agent["headers"],
        )

        assert resp.status_code == 200
        assert len(resp.json()["context_files"]) == 2

    def test_other_organization_gets_404(self, client, user_with_agent):
        other = register(client)
        token = login(client, other["email"], other["password"])

        resp = client.get(
            f"/api/v1/agents/{user_with_agent['agent']['id']}",
            headers=auth_headers(token),
        )
        assert resp.status_code == 404


class TestUpdateAgent:
    def test_updates_name_and_description(self, client, user_with_agent):
        new_name = unique_name("Renamed")
        resp = client.put(
            f"/api/v1/agents/{user_with_agent['agent']['id']}",
            headers=user_with_agent["headers"],
            json={"name": new_name, "description": "Updated."},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == new_name
        assert resp.json()["description"] == "Updated."

    def test_omitted_fields_are_untouched(self, client, user_with_agent):
        agent = user_with_agent["agent"]
        resp = client.put(
            f"/api/v1/agents/{agent['id']}",
            headers=user_with_agent["headers"],
            json={"description": "Only this changed."},
        )

        body = resp.json()
        assert body["name"] == agent["name"]
        assert len(body["context_files"]) == 2
        assert body["feedback_memory"] == agent["feedback_memory"]

    def test_context_files_are_replaced_wholesale(self, client, user_with_agent):
        resp = client.put(
            f"/api/v1/agents/{user_with_agent['agent']['id']}",
            headers=user_with_agent["headers"],
            json={"context_files": [{"name": "only.md", "content": "# Only"}]},
        )

        assert resp.status_code == 200, resp.text
        assert [f["name"] for f in resp.json()["context_files"]] == ["only.md"]

    def test_renaming_onto_another_agent_rejected(self, client, user_with_agent):
        other = client.post(
            "/api/v1/agents", headers=user_with_agent["headers"], json=agent_payload()
        ).json()

        resp = client.put(
            f"/api/v1/agents/{other['id']}",
            headers=user_with_agent["headers"],
            json={"name": user_with_agent["agent"]["name"]},
        )
        assert resp.status_code == 400

    def test_explicit_null_name_leaves_the_name_alone(self, client, user_with_agent):
        """A name is never blanked — only description is clearable."""
        resp = client.put(
            f"/api/v1/agents/{user_with_agent['agent']['id']}",
            headers=user_with_agent["headers"],
            json={"name": None},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == user_with_agent["agent"]["name"]

    def test_description_can_be_cleared(self, client, user_with_agent):
        resp = client.put(
            f"/api/v1/agents/{user_with_agent['agent']['id']}",
            headers=user_with_agent["headers"],
            json={"description": None},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["description"] is None

    def test_can_change_and_clear_the_ai_configuration(self, client, user_with_agent):
        headers = user_with_agent["headers"]
        configuration = make_ai_configuration(client, headers)
        agent_id = user_with_agent["agent"]["id"]

        selected = client.put(f"/api/v1/agents/{agent_id}", headers=headers,
                              json={"ai_configuration_id": configuration["id"]})
        assert selected.json()["ai_configuration"]["model"] == "claude-opus-5"

        cleared = client.put(f"/api/v1/agents/{agent_id}", headers=headers,
                             json={"ai_configuration_id": None})
        assert cleared.json()["ai_configuration_id"] is None
        assert cleared.json()["ai_configuration"] is None

    def test_deleting_the_configuration_unsets_it_but_keeps_the_agent(
        self, client, new_user
    ):
        """A deleted credential must not take its agents down with it."""
        headers = new_user["headers"]
        configuration = make_ai_configuration(client, headers)
        agent = client.post("/api/v1/agents", headers=headers, json=agent_payload(
            ai_configuration_id=configuration["id"],
        )).json()

        assert client.delete(
            f"/api/v1/credentials/{configuration['id']}", headers=headers
        ).status_code == 200

        resp = client.get(f"/api/v1/agents/{agent['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["ai_configuration"] is None

    def test_can_deactivate(self, client, user_with_agent):
        resp = client.put(
            f"/api/v1/agents/{user_with_agent['agent']['id']}",
            headers=user_with_agent["headers"],
            json={"is_active": False},
        )
        assert resp.json()["is_active"] is False

    def test_other_organization_gets_404(self, client, user_with_agent):
        other = register(client)
        token = login(client, other["email"], other["password"])

        resp = client.put(
            f"/api/v1/agents/{user_with_agent['agent']['id']}",
            headers=auth_headers(token),
            json={"description": "hijacked"},
        )
        assert resp.status_code == 404


class TestAgentMemory:
    def test_replace_overwrites_memory(self, client, user_with_agent):
        resp = client.put(
            f"/api/v1/agents/{user_with_agent['agent']['id']}/memory",
            headers=user_with_agent["headers"],
            json={"feedback_memory": "Start over."},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["feedback_memory"] == "Start over."

    def test_append_keeps_existing_memory(self, client, user_with_agent):
        resp = client.post(
            f"/api/v1/agents/{user_with_agent['agent']['id']}/memory",
            headers=user_with_agent["headers"],
            json={"feedback": "Link to the issue tracker.", "heading": "2026-09-19 review"},
        )

        assert resp.status_code == 200, resp.text
        memory = resp.json()["feedback_memory"]
        assert "Keep entries under two sentences." in memory
        assert "### 2026-09-19 review" in memory
        assert "Link to the issue tracker." in memory

    def test_append_to_empty_memory_has_no_leading_blank(self, client, new_user):
        agent = client.post("/api/v1/agents", headers=new_user["headers"], json=agent_payload(
            feedback_memory="",
        )).json()

        resp = client.post(
            f"/api/v1/agents/{agent['id']}/memory",
            headers=new_user["headers"],
            json={"feedback": "First note.", "heading": "Review"},
        )
        assert resp.json()["feedback_memory"] == "### Review\n\nFirst note."

    def test_memory_is_separate_from_context_files(self, client, user_with_agent):
        """Feedback lands in memory, never in the context files."""
        resp = client.post(
            f"/api/v1/agents/{user_with_agent['agent']['id']}/memory",
            headers=user_with_agent["headers"],
            json={"feedback": "Do not bury the lede."},
        )

        body = resp.json()
        assert len(body["context_files"]) == 2
        assert "Do not bury the lede." not in str(body["context_files"])


class TestDeleteAgent:
    def test_deletes_agent(self, client, user_with_agent):
        agent_id = user_with_agent["agent"]["id"]
        resp = client.delete(f"/api/v1/agents/{agent_id}", headers=user_with_agent["headers"])

        assert resp.status_code == 200
        assert client.get(
            f"/api/v1/agents/{agent_id}", headers=user_with_agent["headers"]
        ).status_code == 404

    def test_other_organization_gets_404(self, client, user_with_agent):
        other = register(client)
        token = login(client, other["email"], other["password"])

        resp = client.delete(
            f"/api/v1/agents/{user_with_agent['agent']['id']}",
            headers=auth_headers(token),
        )
        assert resp.status_code == 404


class TestAiConfigurations:
    def test_lists_the_organizations_ai_configurations(self, client, new_user):
        configuration = make_ai_configuration(client, new_user["headers"])

        resp = client.get("/api/v1/agents/ai-configurations", headers=new_user["headers"])

        assert resp.status_code == 200, resp.text
        listed = next(c for c in resp.json() if c["id"] == configuration["id"])
        assert listed["name"] == configuration["name"]
        assert listed["provider"] == "anthropic"
        assert listed["provider_label"] == "Anthropic"
        assert listed["model"] == "claude-opus-5"

    def test_never_returns_the_api_key(self, client, new_user):
        make_ai_configuration(client, new_user["headers"])

        resp = client.get("/api/v1/agents/ai-configurations", headers=new_user["headers"])

        assert "sk-test-abc123" not in resp.text
        assert "api_key" not in resp.text

    def test_excludes_non_ai_credentials(self, client, new_user):
        jira = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "jira",
            "name": unique_name("Jira"),
            "credentials": {"api_token": "t"},
        }).json()

        resp = client.get("/api/v1/agents/ai-configurations", headers=new_user["headers"])

        assert jira["id"] not in [c["id"] for c in resp.json()]

    def test_scoped_to_organization(self, client, new_user):
        other = register(client)
        other_token = login(client, other["email"], other["password"])
        foreign = make_ai_configuration(client, auth_headers(other_token))

        resp = client.get("/api/v1/agents/ai-configurations", headers=new_user["headers"])

        assert foreign["id"] not in [c["id"] for c in resp.json()]

    def test_empty_when_no_ai_types_registered(self, client, new_user):
        """An app that registers no AI credential type simply offers nothing."""
        make_ai_configuration(client, new_user["headers"])
        CredentialTypeRegistry.clear()

        resp = client.get("/api/v1/agents/ai-configurations", headers=new_user["headers"])

        assert resp.status_code == 200
        assert resp.json() == []

    def test_configuration_without_a_model_reads_as_blank(self, client, new_user):
        configuration = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "anthropic",
            "name": unique_name("Key only"),
            "credentials": {"api_key": "sk-test-abc123"},
        }).json()

        resp = client.get("/api/v1/agents/ai-configurations", headers=new_user["headers"])

        listed = next(c for c in resp.json() if c["id"] == configuration["id"])
        assert listed["model"] == ""

    def test_unauthenticated_rejected(self, client):
        assert client.get("/api/v1/agents/ai-configurations").status_code == 401


# ── Permitted-URL matching ────────────────────────────────────────────────────

class TestPermittedUrls:
    def test_normalizes_case_default_port_and_trailing_slash(self):
        assert normalize_url("HTTPS://Docs.Example.COM:443/guide/") == "https://docs.example.com/guide"

    def test_keeps_non_default_port(self):
        assert normalize_url("http://localhost:8080/docs") == "http://localhost:8080/docs"

    def test_rejects_non_http_scheme(self):
        with pytest.raises(InvalidPermittedUrl):
            normalize_url("ftp://files.example.com")

    def test_rejects_missing_host(self):
        with pytest.raises(InvalidPermittedUrl):
            normalize_url("https:///just-a-path")

    def test_permits_exact_and_nested_paths(self):
        permitted = ["https://docs.example.com/guide"]
        assert is_url_permitted("https://docs.example.com/guide", permitted)
        assert is_url_permitted("https://docs.example.com/guide/install", permitted)

    def test_sibling_path_is_not_permitted(self):
        """/guide must not permit /guidebook — the prefix stops at a segment."""
        assert not is_url_permitted(
            "https://docs.example.com/guidebook", ["https://docs.example.com/guide"]
        )

    def test_host_only_entry_permits_whole_host(self):
        assert is_url_permitted("https://docs.example.com/anything", ["https://docs.example.com"])

    def test_other_host_is_not_permitted(self):
        assert not is_url_permitted("https://evil.example.net/x", ["https://docs.example.com"])

    def test_scheme_must_match(self):
        assert not is_url_permitted("http://docs.example.com/x", ["https://docs.example.com"])

    def test_wildcard_subdomain(self):
        permitted = ["https://*.example.com"]
        assert is_url_permitted("https://docs.example.com/x", permitted)
        assert is_url_permitted("https://example.com/x", permitted)
        assert not is_url_permitted("https://example.net/x", permitted)

    def test_malformed_candidate_is_not_permitted(self):
        assert not is_url_permitted("not a url", ["https://docs.example.com"])

    def test_empty_list_permits_nothing(self):
        assert not is_url_permitted("https://docs.example.com", [])


# ── Definition and runner ─────────────────────────────────────────────────────

def make_definition(**overrides) -> AgentDefinition:
    fields = {
        "name": "Release Notes Writer",
        "description": "Turns merged pull requests into customer-facing notes.",
        "ai_configuration": AiConfiguration(
            credential_id=str(uuid.uuid4()),
            name="Anthropic — Opus 5",
            provider="anthropic",
            model="claude-opus-5",
        ),
        "context_files": [ContextFile(name="voice.md", content="Plain, direct.")],
        "permitted_urls": ["https://docs.example.com/style"],
        "feedback_memory": "Keep entries under two sentences.",
    }
    fields.update(overrides)
    return AgentDefinition(**fields)


class FakeAIService:
    """Records the request it was given and returns a canned result."""

    def __init__(self, content: str = "Generated output"):
        self.content = content
        self.last_request = None

    async def generate(self, request: GenerationRequest):
        self.last_request = request
        return type("Result", (), {"content": self.content})()


class TestAgentDefinition:
    def test_system_prompt_includes_every_section(self):
        prompt = make_definition().build_system_prompt()

        assert "You are Release Notes Writer." in prompt
        assert "Turns merged pull requests" in prompt
        assert "### voice.md" in prompt
        assert "Plain, direct." in prompt
        assert "https://docs.example.com/style" in prompt
        assert "Keep entries under two sentences." in prompt

    def test_empty_sections_are_omitted(self):
        prompt = make_definition(
            description=None, context_files=[], permitted_urls=[], feedback_memory=""
        ).build_system_prompt()

        assert prompt == "You are Release Notes Writer."

    def test_blank_context_file_is_skipped(self):
        prompt = make_definition(
            context_files=[ContextFile(name="empty.md", content="   ")]
        ).build_system_prompt()

        assert "Context files" not in prompt

    def test_is_url_permitted_uses_the_agent_list(self):
        definition = make_definition()

        assert definition.is_url_permitted("https://docs.example.com/style/voice")
        assert not definition.is_url_permitted("https://docs.example.com/internal")

    def test_from_model_round_trips_a_stored_agent(self, client, new_user):
        """The runtime view is built from the row, not from the API payload."""
        from hop_core.db import get_session_factory
        from hop_core.models.agent import Agent

        configuration = make_ai_configuration(client, new_user["headers"])
        agent = client.post("/api/v1/agents", headers=new_user["headers"], json=agent_payload(
            ai_configuration_id=configuration["id"],
        )).json()

        db = get_session_factory()()
        try:
            row = db.query(Agent).filter(Agent.id == uuid.UUID(agent["id"])).one()
            definition = AgentDefinition.from_model(row)
        finally:
            db.close()

        assert definition.name == agent["name"]
        assert definition.ai_configuration.model == "claude-opus-5"
        assert definition.ai_configuration.provider == "anthropic"
        assert definition.ai_configuration.credential_id == configuration["id"]
        assert [f.name for f in definition.context_files] == ["voice-and-tone.md", "audience.md"]
        assert definition.permitted_urls == ["https://docs.example.com/style"]
        assert definition.feedback_memory == "Keep entries under two sentences."

    def test_from_model_leaves_an_unconfigured_agent_unconfigured(self, client, user_with_agent):
        from hop_core.db import get_session_factory
        from hop_core.models.agent import Agent

        db = get_session_factory()()
        try:
            row = db.query(Agent).filter(
                Agent.id == uuid.UUID(user_with_agent["agent"]["id"])
            ).one()
            definition = AgentDefinition.from_model(row)
        finally:
            db.close()

        assert definition.ai_configuration is None


class TestAgentRunner:
    async def test_returns_the_service_output(self):
        service = FakeAIService("## Release 1.2.0\n\nFaster builds.")
        result = await AgentRunner(service).run(
            make_definition(),
            AgentRequest(instructions="Write the notes", input="PR #12: faster builds"),
        )

        assert result.output == "## Release 1.2.0\n\nFaster builds."
        assert result.agent_name == "Release Notes Writer"
        assert result.provider == "anthropic"
        assert result.model == "claude-opus-5"

    async def test_sends_the_composed_system_prompt(self):
        service = FakeAIService()
        await AgentRunner(service).run(
            make_definition(), AgentRequest(instructions="Write the notes")
        )

        assert "You are Release Notes Writer." in service.last_request.system_prompt
        assert "### voice.md" in service.last_request.system_prompt

    async def test_user_prompt_carries_instructions_and_input(self):
        service = FakeAIService()
        await AgentRunner(service).run(
            make_definition(),
            AgentRequest(instructions="Write the notes", input="PR #12: faster builds"),
        )

        prompt = service.last_request.user_prompt
        assert "## Instructions\n\nWrite the notes" in prompt
        assert "## Input\n\nPR #12: faster builds" in prompt

    async def test_input_section_omitted_when_empty(self):
        service = FakeAIService()
        await AgentRunner(service).run(
            make_definition(), AgentRequest(instructions="Write the notes")
        )

        assert "## Input" not in service.last_request.user_prompt

    async def test_generation_knobs_come_from_the_request(self):
        """The AI configuration owns provider and model; the run owns the knobs."""
        service = FakeAIService()
        await AgentRunner(service).run(
            make_definition(),
            AgentRequest(instructions="Write the notes", temperature=0.9, max_tokens=100),
        )

        assert service.last_request.temperature == 0.9
        assert service.last_request.max_tokens == 100

    async def test_reports_which_configuration_ran(self):
        service = FakeAIService()
        result = await AgentRunner(service).run(
            make_definition(), AgentRequest(instructions="Write the notes")
        )

        assert result.ai_configuration_name == "Anthropic — Opus 5"

    async def test_unconfigured_agent_refuses_to_run(self):
        """Better a loud error than silently falling back to a service default."""
        service = FakeAIService()

        with pytest.raises(AgentNotConfigured):
            await AgentRunner(service).run(
                make_definition(ai_configuration=None),
                AgentRequest(instructions="Write the notes"),
            )

        assert service.last_request is None
