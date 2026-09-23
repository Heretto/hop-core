"""Tests for talking to an agent — the provider layer and /agents/{id}/chat."""

import uuid
import pytest

from hop_core.agents import (
    AgentDefinition,
    AgentNotConfigured,
    AgentRunner,
    AiConfiguration,
    AiProviderError,
    AiProviderRegistry,
    ContextFile,
    CredentialAiService,
)
from hop_core.agents import providers
from hop_core.ai import ChatMessage, GenerationRequest
from hop_core.credentials import AI_PROVIDER_TYPES, register_builtin_types
from hop_core.models.enums import CredentialTypeRegistry
from tests.conftest import register, login, auth_headers


def unique_name(prefix: str = "Agent") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _registered_types():
    CredentialTypeRegistry.clear()
    register_builtin_types("jira", *AI_PROVIDER_TYPES)
    yield
    CredentialTypeRegistry.clear()


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text if text is not None else str(self._payload)

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        if "json" in kwargs:
            kwargs["json"] = dict(kwargs["json"])
        self.requests.append({"url": url, **kwargs})
        return self.responses.pop(0)


@pytest.fixture
def fake_http(monkeypatch):
    def install(*responses):
        client = FakeClient(*responses)
        monkeypatch.setattr(providers, "_client", lambda: client)
        return client
    return install


def make_definition(**overrides) -> AgentDefinition:
    fields = {
        "name": "Release Notes Writer",
        "description": "Writes customer-facing notes.",
        "ai_configuration": AiConfiguration(
            credential_id=str(uuid.uuid4()), name="Anthropic - Opus 5",
            provider="anthropic", model="claude-opus-5",
        ),
        "context_files": [ContextFile(name="voice.md", content="Plain, direct.")],
        "permitted_urls": [],
        "feedback_memory": "Keep entries short.",
    }
    fields.update(overrides)
    return AgentDefinition(**fields)


class RecordingService:
    def __init__(self, content="Hello from the agent."):
        self.content = content
        self.last_request = None

    async def generate(self, request: GenerationRequest):
        self.last_request = request
        return type("R", (), {"content": self.content})()


# ── Provider generators ───────────────────────────────────────────────────────

class TestAnthropicGenerator:
    async def test_sends_system_prompt_and_conversation(self, fake_http):
        client = fake_http(FakeResponse(200, {
            "content": [{"type": "text", "text": "Hi there."}],
        }))

        result = await providers.generate_with_anthropic("sk-ant", "claude-opus-5",
            GenerationRequest(
                system_prompt="You are a writer.", user_prompt="second",
                messages=[ChatMessage(role="user", content="first"),
                          ChatMessage(role="assistant", content="ok"),
                          ChatMessage(role="user", content="second")],
            ))

        body = client.requests[0]["json"]
        assert body["system"] == "You are a writer."
        assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
        assert result.content == "Hi there."

    async def test_falls_back_to_the_single_prompt(self, fake_http):
        client = fake_http(FakeResponse(200, {"content": [{"type": "text", "text": "ok"}]}))

        await providers.generate_with_anthropic("sk-ant", "claude-opus-5",
            GenerationRequest(system_prompt="s", user_prompt="just this"))

        assert client.requests[0]["json"]["messages"] == [
            {"role": "user", "content": "just this"}
        ]

    async def test_joins_multiple_text_blocks(self, fake_http):
        fake_http(FakeResponse(200, {"content": [
            {"type": "text", "text": "one "},
            {"type": "thinking", "thinking": "ignored"},
            {"type": "text", "text": "two"},
        ]}))

        result = await providers.generate_with_anthropic("k", "m",
            GenerationRequest(system_prompt="s", user_prompt="p"))

        assert result.content == "one two"

    async def test_error_carries_the_vendors_message(self, fake_http):
        fake_http(FakeResponse(404, {"error": {"message": "model: nope not found"}}))

        with pytest.raises(AiProviderError) as excinfo:
            await providers.generate_with_anthropic("k", "nope",
                GenerationRequest(system_prompt="s", user_prompt="p"))

        assert "model: nope not found" in str(excinfo.value)
        assert excinfo.value.status_code == 404


class TestOpenAiGenerator:
    async def test_system_prompt_leads_the_messages(self, fake_http):
        client = fake_http(FakeResponse(200, {
            "choices": [{"message": {"content": "Hi."}}],
        }))

        await providers.generate_with_openai("sk", "gpt-5", GenerationRequest(
            system_prompt="You are a writer.", user_prompt="hello",
        ))

        messages = client.requests[0]["json"]["messages"]
        assert messages[0] == {"role": "system", "content": "You are a writer."}
        assert messages[1] == {"role": "user", "content": "hello"}

    async def test_retries_with_max_tokens(self, fake_http):
        client = fake_http(
            FakeResponse(400, text="Unsupported parameter: max_completion_tokens"),
            FakeResponse(200, {"choices": [{"message": {"content": "ok"}}]}),
        )

        result = await providers.generate_with_openai("sk", "gpt-4",
            GenerationRequest(system_prompt="s", user_prompt="p"))

        assert result.content == "ok"
        assert "max_tokens" in client.requests[1]["json"]


class TestGeminiGenerator:
    async def test_maps_assistant_to_model_role(self, fake_http):
        client = fake_http(FakeResponse(200, {
            "candidates": [{"content": {"parts": [{"text": "Hi."}]}}],
        }))

        await providers.generate_with_gemini("k", "gemini-2.5-pro", GenerationRequest(
            system_prompt="You are a writer.", user_prompt="b",
            messages=[ChatMessage(role="user", content="a"),
                      ChatMessage(role="assistant", content="x"),
                      ChatMessage(role="user", content="b")],
        ))

        body = client.requests[0]["json"]
        assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
        assert body["systemInstruction"]["parts"][0]["text"] == "You are a writer."

    async def test_key_stays_out_of_the_url(self, fake_http):
        client = fake_http(FakeResponse(200, {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
        }))

        await providers.generate_with_gemini("goog-secret", "gemini-2.5-pro",
            GenerationRequest(system_prompt="s", user_prompt="p"))

        assert "goog-secret" not in client.requests[0]["url"]
        assert client.requests[0]["headers"]["x-goog-api-key"] == "goog-secret"


class TestCredentialAiService:
    async def test_dispatches_on_the_credential_type(self, fake_http):
        fake_http(FakeResponse(200, {"content": [{"type": "text", "text": "hi"}]}))
        service = CredentialAiService("anthropic", "claude-opus-5", "sk-ant")

        result = await service.generate(
            GenerationRequest(system_prompt="s", user_prompt="p")
        )

        assert result.content == "hi"

    async def test_unknown_provider_is_an_error(self):
        service = CredentialAiService("mystery", "m", "k")

        with pytest.raises(AiProviderError, match="No generator is registered"):
            await service.generate(GenerationRequest(system_prompt="s", user_prompt="p"))

    async def test_configuration_without_a_model_is_an_error(self):
        service = CredentialAiService("anthropic", "", "sk-ant")

        with pytest.raises(AiProviderError, match="does not name a model"):
            await service.generate(GenerationRequest(system_prompt="s", user_prompt="p"))

    def test_repr_never_shows_the_key(self):
        assert "sk-ant-secret" not in repr(
            CredentialAiService("anthropic", "m", "sk-ant-secret")
        )


# ── AgentRunner.chat ──────────────────────────────────────────────────────────

class TestAgentRunnerChat:
    async def test_sends_the_agents_system_prompt(self):
        service = RecordingService()

        await AgentRunner(service).chat(
            make_definition(), [ChatMessage(role="user", content="hello")]
        )

        assert "You are Release Notes Writer." in service.last_request.system_prompt
        assert "### voice.md" in service.last_request.system_prompt
        assert "Keep entries short." in service.last_request.system_prompt

    async def test_passes_the_whole_conversation(self):
        service = RecordingService()
        messages = [
            ChatMessage(role="user", content="first"),
            ChatMessage(role="assistant", content="answer"),
            ChatMessage(role="user", content="second"),
        ]

        await AgentRunner(service).chat(make_definition(), messages)

        assert len(service.last_request.messages) == 3
        assert service.last_request.messages[2].content == "second"

    async def test_repeats_the_last_user_turn_as_user_prompt(self):
        """So a service written before conversations still answers something."""
        service = RecordingService()

        await AgentRunner(service).chat(make_definition(), [
            ChatMessage(role="user", content="first"),
            ChatMessage(role="assistant", content="answer"),
            ChatMessage(role="user", content="latest question"),
        ])

        assert service.last_request.user_prompt == "latest question"

    async def test_returns_the_reply_and_what_produced_it(self):
        service = RecordingService("Release 1.2.0 is out.")

        result = await AgentRunner(service).chat(
            make_definition(), [ChatMessage(role="user", content="hi")]
        )

        assert result.output == "Release 1.2.0 is out."
        assert result.provider == "anthropic"
        assert result.model == "claude-opus-5"
        assert result.ai_configuration_name == "Anthropic - Opus 5"

    async def test_unconfigured_agent_refuses(self):
        with pytest.raises(AgentNotConfigured):
            await AgentRunner(RecordingService()).chat(
                make_definition(ai_configuration=None),
                [ChatMessage(role="user", content="hi")],
            )

    async def test_empty_conversation_refused(self):
        with pytest.raises(ValueError, match="at least one message"):
            await AgentRunner(RecordingService()).chat(make_definition(), [])


# ── Endpoint ──────────────────────────────────────────────────────────────────

class TestChatEndpoint:
    @pytest.fixture
    def agent_with_configuration(self, client, new_user):
        configuration = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "anthropic", "name": unique_name("Anthropic"),
            "credentials": {"api_key": "sk-ant-secret", "model": "claude-opus-5"},
        }).json()
        agent = client.post("/api/v1/agents", headers=new_user["headers"], json={
            "name": unique_name("Writer"),
            "description": "Writes notes.",
            "ai_configuration_id": configuration["id"],
            "context_files": [{"name": "voice.md", "content": "Plain."}],
        }).json()
        return {**new_user, "agent": agent, "configuration": configuration}

    def test_returns_the_agents_reply(self, client, agent_with_configuration, fake_http):
        fake_http(FakeResponse(200, {"content": [{"type": "text", "text": "Hello."}]}))

        resp = client.post(
            f"/api/v1/agents/{agent_with_configuration['agent']['id']}/chat",
            headers=agent_with_configuration["headers"],
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["message"] == {"role": "assistant", "content": "Hello."}
        assert body["provider"] == "anthropic"
        assert body["model"] == "claude-opus-5"

    def test_returns_the_composed_system_prompt(self, client, agent_with_configuration, fake_http):
        """The tester needs to see what the agent is actually being told."""
        fake_http(FakeResponse(200, {"content": [{"type": "text", "text": "ok"}]}))

        resp = client.post(
            f"/api/v1/agents/{agent_with_configuration['agent']['id']}/chat",
            headers=agent_with_configuration["headers"],
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

        assert "### voice.md" in resp.json()["system_prompt"]

    def test_uses_the_stored_api_key(self, client, agent_with_configuration, fake_http):
        client_spy = fake_http(FakeResponse(200, {"content": [{"type": "text", "text": "ok"}]}))

        client.post(
            f"/api/v1/agents/{agent_with_configuration['agent']['id']}/chat",
            headers=agent_with_configuration["headers"],
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

        assert client_spy.requests[0]["headers"]["x-api-key"] == "sk-ant-secret"

    def test_never_returns_the_api_key(self, client, agent_with_configuration, fake_http):
        fake_http(FakeResponse(200, {"content": [{"type": "text", "text": "ok"}]}))

        resp = client.post(
            f"/api/v1/agents/{agent_with_configuration['agent']['id']}/chat",
            headers=agent_with_configuration["headers"],
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

        assert "sk-ant-secret" not in resp.text

    def test_provider_failure_is_a_502_with_the_reason(
        self, client, agent_with_configuration, fake_http
    ):
        fake_http(FakeResponse(404, {"error": {"message": "model not found"}}))

        resp = client.post(
            f"/api/v1/agents/{agent_with_configuration['agent']['id']}/chat",
            headers=agent_with_configuration["headers"],
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

        assert resp.status_code == 502
        assert "model not found" in resp.json()["detail"]

    def test_agent_without_a_configuration_rejected(self, client, new_user):
        agent = client.post("/api/v1/agents", headers=new_user["headers"], json={
            "name": unique_name("Unconfigured"),
        }).json()

        resp = client.post(f"/api/v1/agents/{agent['id']}/chat",
                           headers=new_user["headers"],
                           json={"messages": [{"role": "user", "content": "hi"}]})

        assert resp.status_code == 400
        assert "no AI configuration" in resp.json()["detail"]

    def test_empty_conversation_rejected(self, client, agent_with_configuration):
        resp = client.post(
            f"/api/v1/agents/{agent_with_configuration['agent']['id']}/chat",
            headers=agent_with_configuration["headers"],
            json={"messages": []},
        )

        assert resp.status_code == 422

    def test_other_organizations_agent_is_404(self, client, agent_with_configuration):
        other = register(client)
        token = login(client, other["email"], other["password"])

        resp = client.post(
            f"/api/v1/agents/{agent_with_configuration['agent']['id']}/chat",
            headers=auth_headers(token),
            json={"messages": [{"role": "user", "content": "hi"}]},
        )

        assert resp.status_code == 404

    def test_unauthenticated_rejected(self, client, agent_with_configuration):
        agent_id = agent_with_configuration["agent"]["id"]
        client.cookies.clear()

        resp = client.post(f"/api/v1/agents/{agent_id}/chat",
                           json={"messages": [{"role": "user", "content": "hi"}]})

        assert resp.status_code == 401

    def test_nothing_is_stored(self, client, agent_with_configuration, fake_http):
        """A test conversation leaves no trace on the agent."""
        fake_http(FakeResponse(200, {"content": [{"type": "text", "text": "ok"}]}))
        agent_id = agent_with_configuration["agent"]["id"]

        client.post(f"/api/v1/agents/{agent_id}/chat",
                    headers=agent_with_configuration["headers"],
                    json={"messages": [{"role": "user", "content": "remember this"}]})

        after = client.get(f"/api/v1/agents/{agent_id}",
                           headers=agent_with_configuration["headers"]).json()
        assert after["feedback_memory"] == ""
        assert len(after["context_files"]) == 1
