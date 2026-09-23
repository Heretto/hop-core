"""Tests for registered credential types and the field-spec behaviour they drive."""

import uuid
import pytest

from hop_core.credentials import (
    AI_PROVIDER_TYPES,
    BUILTIN_CREDENTIAL_TYPES,
    get_spec,
    register_builtin_types,
)
from hop_core.models.enums import CredentialTypeRegistry
from tests.conftest import register, login, auth_headers


def unique_name(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _registered_types():
    """Register the three Release Notes Agent credential types."""
    CredentialTypeRegistry.clear()
    register_builtin_types("jira", "heretto", *AI_PROVIDER_TYPES)
    yield
    CredentialTypeRegistry.clear()


JIRA = {"server_url": "https://acme.atlassian.net", "email": "me@acme.com",
        "api_token": "jira-secret-token"}
HERETTO = {"server_url": "https://acme.heretto.com", "username": "me",
           "token": "heretto-secret-token"}
ANTHROPIC = {"api_key": "sk-ant-secret", "model": "claude-opus-5"}


class TestBuiltinTypes:
    def test_ships_the_release_notes_agent_types(self):
        assert set(BUILTIN_CREDENTIAL_TYPES) == {
            "jira", "heretto", "anthropic", "openai", "gemini",
        }

    def test_apps_choose_which_types_to_register(self):
        CredentialTypeRegistry.clear()
        register_builtin_types("jira")

        assert CredentialTypeRegistry.get_types() == ["jira"]
        assert get_spec("heretto") is None

    def test_unknown_builtin_name_is_an_error(self):
        with pytest.raises(ValueError, match="Unknown built-in credential type"):
            register_builtin_types("jira", "zendesk")

    def test_ai_providers_share_a_group_and_are_ai_configurations(self):
        for provider in AI_PROVIDER_TYPES:
            spec = get_spec(provider)
            assert spec.group == "ai"
            assert spec.group_label == "AI Providers"
            assert spec.is_ai_configuration is True

    def test_jira_and_heretto_are_not_ai_configurations(self):
        assert get_spec("jira").is_ai_configuration is False
        assert get_spec("heretto").is_ai_configuration is False

    def test_secrets_are_marked_secret(self):
        assert [f.name for f in get_spec("jira").fields if f.secret] == ["api_token"]
        assert [f.name for f in get_spec("heretto").fields if f.secret] == ["token"]
        assert [f.name for f in get_spec("anthropic").fields if f.secret] == ["api_key"]

    def test_custom_types_register_alongside_builtins(self):
        CredentialTypeRegistry.register("zendesk", label="Zendesk", fields=[
            {"name": "subdomain", "label": "Subdomain", "summary": True},
            {"name": "api_token", "label": "API Token", "type": "password", "secret": True},
        ])

        spec = get_spec("zendesk")
        assert spec.label == "Zendesk"
        assert [f.name for f in spec.fields] == ["subdomain", "api_token"]


class TestListCredentialTypes:
    def test_lists_registered_types_with_their_fields(self, client, new_user):
        resp = client.get("/api/v1/credentials/types", headers=new_user["headers"])

        assert resp.status_code == 200, resp.text
        by_type = {spec["type"]: spec for spec in resp.json()}
        assert set(by_type) == {"jira", "heretto", "anthropic", "openai", "gemini"}
        assert [f["name"] for f in by_type["jira"]["fields"]] == [
            "server_url", "email", "api_token",
        ]
        assert by_type["jira"]["label"] == "Jira"

    def test_empty_when_nothing_registered(self, client, new_user):
        CredentialTypeRegistry.clear()
        resp = client.get("/api/v1/credentials/types", headers=new_user["headers"])

        assert resp.status_code == 200
        assert resp.json() == []

    def test_unauthenticated_rejected(self, client):
        assert client.get("/api/v1/credentials/types").status_code == 401


class TestCredentialValues:
    def test_returns_non_secret_values(self, client, new_user):
        resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "jira", "name": unique_name("Jira"), "credentials": JIRA,
        })

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["values"] == {
            "server_url": "https://acme.atlassian.net", "email": "me@acme.com",
        }

    def test_never_returns_the_secret(self, client, new_user):
        resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "jira", "name": unique_name("Jira"), "credentials": JIRA,
        })

        assert "jira-secret-token" not in resp.text
        assert "api_token" not in resp.json()["values"]

    def test_reports_which_secrets_are_set(self, client, new_user):
        resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "heretto", "name": unique_name("Heretto"), "credentials": HERETTO,
        })

        assert resp.json()["secrets_set"] == ["token"]

    def test_unregistered_type_discloses_nothing(self, client, new_user):
        """Without a spec there is no way to know what is secret, so echo nothing."""
        resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "mystery", "name": unique_name("Mystery"),
            "credentials": {"anything": "at-all", "api_key": "super-secret"},
        })

        assert resp.status_code == 200, resp.text
        assert resp.json()["values"] == {}
        assert resp.json()["secrets_set"] == []
        assert "super-secret" not in resp.text

    def test_values_appear_in_the_list(self, client, new_user):
        created = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "jira", "name": unique_name("Jira"), "credentials": JIRA,
        }).json()

        listed = client.get("/api/v1/credentials", headers=new_user["headers"]).json()
        row = next(c for c in listed if c["id"] == created["id"])
        assert row["values"]["email"] == "me@acme.com"


class TestRequiredFields:
    def test_missing_required_field_rejected(self, client, new_user):
        resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "jira", "name": unique_name("Jira"),
            "credentials": {"server_url": "https://acme.atlassian.net"},
        })

        assert resp.status_code == 400
        assert "email" in resp.json()["detail"]
        assert "api_token" in resp.json()["detail"]

    def test_optional_field_may_be_omitted(self, client, new_user):
        """An AI configuration without a model is still a valid credential."""
        resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "anthropic", "name": unique_name("Anthropic"),
            "credentials": {"api_key": "sk-ant-secret"},
        })

        assert resp.status_code == 200, resp.text
        assert resp.json()["values"] == {}

    def test_unregistered_type_is_not_validated(self, client, new_user):
        resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "mystery", "name": unique_name("Mystery"), "credentials": {},
        })
        assert resp.status_code == 200


class TestUpdatingSecrets:
    @pytest.fixture
    def jira_credential(self, client, new_user):
        resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "jira", "name": unique_name("Jira"), "credentials": JIRA,
        })
        return {**new_user, "credential": resp.json()}

    def test_blank_secret_keeps_the_stored_one(self, client, jira_credential):
        """The form never receives the secret, so blank must mean "keep"."""
        credential_id = jira_credential["credential"]["id"]

        resp = client.put(f"/api/v1/credentials/{credential_id}",
                          headers=jira_credential["headers"],
                          json={"credentials": {"email": "new@acme.com", "api_token": ""}})

        assert resp.status_code == 200, resp.text
        assert resp.json()["values"]["email"] == "new@acme.com"
        assert resp.json()["secrets_set"] == ["api_token"]

    def test_omitted_secret_keeps_the_stored_one(self, client, jira_credential):
        credential_id = jira_credential["credential"]["id"]

        resp = client.put(f"/api/v1/credentials/{credential_id}",
                          headers=jira_credential["headers"],
                          json={"credentials": {"email": "new@acme.com"}})

        assert resp.status_code == 200, resp.text
        assert resp.json()["secrets_set"] == ["api_token"]

    def test_a_supplied_secret_replaces_it(self, client, jira_credential):
        credential_id = jira_credential["credential"]["id"]

        resp = client.put(f"/api/v1/credentials/{credential_id}",
                          headers=jira_credential["headers"],
                          json={"credentials": {"api_token": "rotated-token"}})

        assert resp.status_code == 200, resp.text
        assert "rotated-token" not in resp.text
        assert resp.json()["secrets_set"] == ["api_token"]

    def test_update_cannot_blank_a_required_non_secret_field(self, client, jira_credential):
        credential_id = jira_credential["credential"]["id"]

        resp = client.put(f"/api/v1/credentials/{credential_id}",
                          headers=jira_credential["headers"],
                          json={"credentials": {"email": ""}})

        assert resp.status_code == 400
        assert "email" in resp.json()["detail"]


class TestAgentsUseRegisteredAiTypes:
    def test_ai_providers_are_offered_as_agent_configurations(self, client, new_user):
        """The same registration drives both the credentials UI and the agent picker."""
        created = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "anthropic", "name": unique_name("Anthropic"), "credentials": ANTHROPIC,
        }).json()

        resp = client.get("/api/v1/agents/ai-configurations", headers=new_user["headers"])

        assert resp.status_code == 200
        offered = next(c for c in resp.json() if c["id"] == created["id"])
        assert offered["provider_label"] == "Anthropic"
        assert offered["model"] == "claude-opus-5"

    def test_jira_is_not_offered(self, client, new_user):
        jira = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "jira", "name": unique_name("Jira"), "credentials": JIRA,
        }).json()

        resp = client.get("/api/v1/agents/ai-configurations", headers=new_user["headers"])

        assert jira["id"] not in [c["id"] for c in resp.json()]
