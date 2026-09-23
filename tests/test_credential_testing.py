"""Tests for credential connection testing."""

import json
import uuid
import pytest

from hop_core.credentials import (
    AI_PROVIDER_TYPES,
    CredentialTestResult,
    CredentialTesterRegistry,
    get_spec,
    register_builtin_types,
    run_test,
)
from hop_core.credentials import testers
from hop_core.models.enums import CredentialTypeRegistry
from tests.conftest import register, login, auth_headers


def unique_name(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


JIRA = {"server_url": "https://acme.atlassian.net", "email": "me@acme.com",
        "api_token": "jira-secret-token"}
ANTHROPIC = {"api_key": "sk-ant-secret", "model": "claude-opus-5"}


@pytest.fixture(autouse=True)
def _registered_types():
    CredentialTypeRegistry.clear()
    CredentialTesterRegistry.clear()
    register_builtin_types("jira", "heretto", *AI_PROVIDER_TYPES)
    yield
    CredentialTypeRegistry.clear()
    CredentialTesterRegistry.clear()


class FakeResponse:
    """Enough of an httpx.Response for the testers."""

    def __init__(self, status_code: int, payload=None, text: str = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload) if text is None else text

    @property
    def is_redirect(self) -> bool:
        return 300 <= self.status_code < 400

    def json(self):
        return self._payload


class FakeClient:
    """Records requests and replays canned responses."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _record(self, method, url, **kwargs):
        # Copy the body: a tester may mutate and resend the same dict, which
        # would otherwise rewrite the request already recorded.
        if "json" in kwargs:
            kwargs["json"] = dict(kwargs["json"])
        self.requests.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)

    async def get(self, url, **kwargs):
        return await self._record("GET", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self._record("POST", url, **kwargs)


@pytest.fixture
def fake_http(monkeypatch):
    """Swap the testers' HTTP client for one that answers from a script."""
    holder = {}

    def install(*responses):
        client = FakeClient(*responses)
        holder["client"] = client
        monkeypatch.setattr(testers, "_client", lambda **kwargs: client)
        return client

    return install


@pytest.fixture
def allow_any_host(monkeypatch):
    """Skip SSRF resolution, which needs real DNS."""
    monkeypatch.setattr(testers, "validate_server_url", lambda url: url)


# ── Registration ──────────────────────────────────────────────────────────────

class TestTesterRegistration:
    def test_builtin_types_arrive_with_a_tester(self):
        for type_key in ("jira", "heretto", *AI_PROVIDER_TYPES):
            assert CredentialTesterRegistry.is_testable(type_key)
            assert get_spec(type_key).testable is True

    def test_only_registered_types_get_testers(self):
        CredentialTypeRegistry.clear()
        CredentialTesterRegistry.clear()
        register_builtin_types("jira")

        assert CredentialTesterRegistry.is_testable("jira")
        assert not CredentialTesterRegistry.is_testable("heretto")

    def test_a_custom_type_is_not_testable_until_it_registers_one(self):
        CredentialTypeRegistry.register("zendesk", label="Zendesk", fields=[])
        assert get_spec("zendesk").testable is False

        async def tester(payload):
            return CredentialTestResult(success=True, message="ok")

        CredentialTesterRegistry.register("zendesk", tester)
        assert get_spec("zendesk").testable is True


# ── run_test ──────────────────────────────────────────────────────────────────

class TestRunTest:
    async def test_unknown_type_is_a_failed_result(self):
        result = await run_test("nope", {})
        assert result.success is False
        assert "cannot be tested" in result.message

    async def test_a_raising_tester_becomes_a_failed_result(self):
        async def boom(payload):
            raise RuntimeError("upstream exploded with secret sk-123")

        CredentialTesterRegistry.register("boom", boom)
        result = await run_test("boom", {})

        assert result.success is False
        # The exception text could hold anything; it must not reach the user.
        assert "sk-123" not in result.message

    async def test_a_value_error_message_is_shown(self):
        """Validation messages are written for whoever filled in the form."""
        async def invalid(payload):
            raise ValueError("URL must use https")

        CredentialTesterRegistry.register("invalid", invalid)
        result = await run_test("invalid", {})

        assert result.success is False
        assert result.message == "URL must use https"


# ── Built-in testers ──────────────────────────────────────────────────────────

class TestJiraTester:
    async def test_success_names_the_account(self, fake_http, allow_any_host):
        fake_http(FakeResponse(200, {"displayName": "Ada Lovelace"}))

        result = await testers.test_jira(JIRA)

        assert result.success is True
        assert "Ada Lovelace" in result.message

    async def test_sends_basic_auth_to_the_myself_endpoint(self, fake_http, allow_any_host):
        client = fake_http(FakeResponse(200, {"displayName": "Ada"}))

        await testers.test_jira(JIRA)

        request = client.requests[0]
        assert request["url"] == "https://acme.atlassian.net/rest/api/3/myself"
        assert request["headers"]["Authorization"].startswith("Basic ")

    async def test_401_explains_what_to_check(self, fake_http, allow_any_host):
        fake_http(FakeResponse(401))
        result = await testers.test_jira(JIRA)

        assert result.success is False
        assert "email and API token" in result.message

    async def test_403_is_distinguished_from_bad_credentials(self, fake_http, allow_any_host):
        fake_http(FakeResponse(403))
        result = await testers.test_jira(JIRA)

        assert "permissions" in result.message

    async def test_redirect_is_a_failure_not_a_followed_hop(self, fake_http, allow_any_host):
        """Following a redirect is how a validated host reaches an internal one."""
        fake_http(FakeResponse(302))
        result = await testers.test_jira(JIRA)

        assert result.success is False
        assert "redirected" in result.message

    async def test_missing_field_reported_before_any_request(self, fake_http, allow_any_host):
        client = fake_http(FakeResponse(200))

        with pytest.raises(ValueError, match="api_token"):
            await testers.test_jira({"server_url": "https://acme.atlassian.net",
                                     "email": "me@acme.com"})

        assert client.requests == []

    async def test_private_address_is_refused(self, fake_http):
        """SSRF guard: no request is made at all."""
        client = fake_http(FakeResponse(200))

        with pytest.raises(ValueError):
            await testers.test_jira({**JIRA, "server_url": "http://127.0.0.1:8000"})

        assert client.requests == []


class TestHerettoTester:
    async def test_success(self, fake_http, allow_any_host):
        fake_http(FakeResponse(200, {}))

        result = await testers.test_heretto(
            {"server_url": "https://acme.heretto.com", "username": "me", "token": "t"}
        )

        assert result.success is True
        assert "me" in result.message

    async def test_401_is_a_credentials_problem(self, fake_http, allow_any_host):
        fake_http(FakeResponse(401))
        result = await testers.test_heretto(
            {"server_url": "https://acme.heretto.com", "username": "me", "token": "t"}
        )

        assert result.success is False
        assert "username and API token" in result.message


class TestAiProviderTesters:
    async def test_anthropic_success_reports_the_model(self, fake_http):
        fake_http(FakeResponse(200, {}))
        result = await testers.test_anthropic(ANTHROPIC)

        assert result.success is True
        assert "claude-opus-5" in result.message

    async def test_anthropic_sends_the_key_as_a_header(self, fake_http):
        client = fake_http(FakeResponse(200, {}))
        await testers.test_anthropic(ANTHROPIC)

        request = client.requests[0]
        assert request["headers"]["x-api-key"] == "sk-ant-secret"
        assert request["json"]["model"] == "claude-opus-5"

    async def test_401_is_a_key_problem(self, fake_http):
        fake_http(FakeResponse(401))
        result = await testers.test_anthropic(ANTHROPIC)

        assert result.success is False
        assert "rejected the API key" in result.message

    async def test_404_names_the_unknown_model(self, fake_http):
        fake_http(FakeResponse(404))
        result = await testers.test_anthropic(ANTHROPIC)

        assert "claude-opus-5" in result.message

    async def test_429_suggests_retrying(self, fake_http):
        fake_http(FakeResponse(429))
        result = await testers.test_anthropic(ANTHROPIC)

        assert "rate-limited" in result.message

    async def test_openai_retries_with_max_tokens(self, fake_http):
        """Older models reject max_completion_tokens."""
        client = fake_http(
            FakeResponse(400, text="Unsupported parameter: max_completion_tokens"),
            FakeResponse(200, {}),
        )

        result = await testers.test_openai({"api_key": "sk-oai", "model": "gpt-4"})

        assert result.success is True
        assert "max_completion_tokens" in client.requests[0]["json"]
        assert "max_tokens" in client.requests[1]["json"]

    async def test_gemini_keeps_the_key_out_of_the_url(self, fake_http):
        """A key in a query string lands in every intermediary's access log."""
        client = fake_http(FakeResponse(200, {}))

        await testers.test_gemini({"api_key": "goog-secret", "model": "gemini-2.5-pro"})

        request = client.requests[0]
        assert "goog-secret" not in request["url"]
        assert request["headers"]["x-goog-api-key"] == "goog-secret"

    async def test_model_defaults_when_not_set(self, fake_http):
        client = fake_http(FakeResponse(200, {}))
        result = await testers.test_anthropic({"api_key": "sk-ant"})

        assert result.success is True
        assert client.requests[0]["json"]["model"]


class TestExchangeDiagnostics:
    async def test_failure_records_what_was_sent_and_returned(self, fake_http, allow_any_host):
        """The dialog needs the status and body to be of any use on a failure."""
        fake_http(FakeResponse(401, {"errorMessages": ["Client must be authenticated"]}))

        result = await testers.test_jira(JIRA)

        assert result.exchange.method == "GET"
        assert result.exchange.url == "https://acme.atlassian.net/rest/api/3/myself"
        assert result.exchange.status_code == 401
        assert "Client must be authenticated" in result.exchange.response_body
        assert result.exchange.duration_ms is not None

    async def test_success_records_the_exchange_too(self, fake_http, allow_any_host):
        fake_http(FakeResponse(200, {"displayName": "Ada"}))
        result = await testers.test_jira(JIRA)

        assert result.exchange.status_code == 200

    async def test_no_exchange_when_nothing_was_sent(self):
        """A URL refused by validation never left the building."""
        result = await run_test("jira", {**JIRA, "server_url": "http://127.0.0.1"})

        assert result.success is False
        assert result.exchange is None

    async def test_long_body_is_truncated_and_flagged(self, fake_http, allow_any_host):
        fake_http(FakeResponse(500, text="x" * 10_000))

        result = await testers.test_jira(JIRA)

        assert result.exchange.body_truncated is True
        assert len(result.exchange.response_body) == 4000

    async def test_a_secret_echoed_in_the_body_is_redacted(self, fake_http, allow_any_host):
        """Some APIs echo the request back, key and all."""
        fake_http(FakeResponse(401, text='{"error": "bad token jira-secret-token"}'))

        result = await run_test("jira", JIRA)

        assert "jira-secret-token" not in result.exchange.response_body
        assert "***redacted***" in result.exchange.response_body

    async def test_short_values_are_not_redacted(self):
        """Redacting a 3-character value would blank out half the body."""
        from hop_core.credentials.testing import redact

        assert redact("the model is gpt-5 ok", ["gpt-5"]) == "the model is gpt-5 ok"
        assert redact("key sk-abcdefgh here", ["sk-abcdefgh"]) == "key ***redacted*** here"

    async def test_openai_retry_reports_the_second_exchange(self, fake_http):
        fake_http(
            FakeResponse(400, text="Unsupported parameter: max_completion_tokens"),
            FakeResponse(401, {"error": "bad key"}),
        )

        result = await testers.test_openai({"api_key": "sk-oai-key", "model": "gpt-4"})

        assert result.exchange.status_code == 401


# ── Endpoint ──────────────────────────────────────────────────────────────────

class TestTestCredentialEndpoint:
    @pytest.fixture
    def jira_credential(self, client, new_user):
        resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "jira", "name": unique_name("Jira"), "credentials": JIRA,
        })
        return {**new_user, "credential": resp.json()}

    def test_returns_the_testers_result(self, client, jira_credential, monkeypatch):
        async def tester(payload):
            return CredentialTestResult(success=True, message="Connected to Jira as Ada.",
                                        details={"account": "Ada"})

        CredentialTesterRegistry.register("jira", tester)
        resp = client.post(f"/api/v1/credentials/{jira_credential['credential']['id']}/test",
                           headers=jira_credential["headers"])

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["success"] is True
        assert body["message"] == "Connected to Jira as Ada."
        assert body["details"] == {"account": "Ada"}
        assert "tested_at" in body

    def test_tester_receives_the_decrypted_payload(self, client, jira_credential):
        seen = {}

        async def tester(payload):
            seen.update(payload)
            return CredentialTestResult(success=True, message="ok")

        CredentialTesterRegistry.register("jira", tester)
        client.post(f"/api/v1/credentials/{jira_credential['credential']['id']}/test",
                    headers=jira_credential["headers"])

        assert seen["api_token"] == "jira-secret-token"

    def test_a_failed_connection_is_200_not_an_error(self, client, jira_credential):
        """The request succeeded; the connection did not. The UI wants the why."""
        async def tester(payload):
            return CredentialTestResult(success=False, message="Jira rejected the credentials.")

        CredentialTesterRegistry.register("jira", tester)
        resp = client.post(f"/api/v1/credentials/{jira_credential['credential']['id']}/test",
                           headers=jira_credential["headers"])

        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_untestable_type_rejected(self, client, new_user):
        credential = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "mystery", "name": unique_name("Mystery"), "credentials": {"k": "v"},
        }).json()

        resp = client.post(f"/api/v1/credentials/{credential['id']}/test",
                           headers=new_user["headers"])

        assert resp.status_code == 400
        assert "cannot be tested" in resp.json()["detail"]

    def test_other_organizations_credential_is_404(self, client, jira_credential):
        other = register(client)
        token = login(client, other["email"], other["password"])

        resp = client.post(f"/api/v1/credentials/{jira_credential['credential']['id']}/test",
                           headers=auth_headers(token))

        assert resp.status_code == 404

    def test_unauthenticated_rejected(self, client, jira_credential):
        credential_id = jira_credential["credential"]["id"]
        # The fixture logged in, and the TestClient cookie jar is session-scoped.
        client.cookies.clear()

        resp = client.post(f"/api/v1/credentials/{credential_id}/test")

        assert resp.status_code == 401

    def test_cookie_session_without_a_csrf_token_rejected(self, client, jira_credential):
        """Testing a credential is state-changing enough to cost money."""
        credential_id = jira_credential["credential"]["id"]

        # Cookie auth is still in the jar from login; no X-CSRF-Token header.
        resp = client.post(f"/api/v1/credentials/{credential_id}/test")

        assert resp.status_code == 403

    def test_exchange_is_returned_for_the_dialog(self, client, jira_credential):
        from hop_core.credentials.testing import CredentialTestExchange

        async def tester(payload):
            return CredentialTestResult(
                success=False, message="Jira rejected the credentials.",
                exchange=CredentialTestExchange(
                    method="GET", url="https://acme.atlassian.net/rest/api/3/myself",
                    status_code=401, response_body='{"errorMessages":["Unauthorized"]}',
                    duration_ms=142,
                ),
            )

        CredentialTesterRegistry.register("jira", tester)
        resp = client.post(f"/api/v1/credentials/{jira_credential['credential']['id']}/test",
                           headers=jira_credential["headers"])

        exchange = resp.json()["exchange"]
        assert exchange["status_code"] == 401
        assert exchange["method"] == "GET"
        assert "Unauthorized" in exchange["response_body"]
        assert exchange["duration_ms"] == 142

    def test_result_never_carries_the_secret(self, client, jira_credential):
        CredentialTesterRegistry.register("jira", testers.test_jira)

        resp = client.post(f"/api/v1/credentials/{jira_credential['credential']['id']}/test",
                           headers=jira_credential["headers"])

        assert resp.status_code == 200
        assert "jira-secret-token" not in resp.text
