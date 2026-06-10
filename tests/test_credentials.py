"""Tests for /api/v1/credentials/* endpoints."""

import uuid
import pytest
from tests.conftest import register, login, auth_headers, make_email


@pytest.fixture
def user_with_cred(client, new_user):
    """User who already has one credential in their org."""
    resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
        "type": "api_key",
        "name": "My Test Credential",
        "credentials": {"api_key": "sk-test-1234567890abcdef"},
    })
    assert resp.status_code == 200, resp.text
    return {**new_user, "credential": resp.json()}


class TestListCredentials:
    def test_returns_list(self, client, new_user):
        resp = client.get("/api/v1/credentials", headers=new_user["headers"])
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_created_credentials_appear(self, client, user_with_cred):
        resp = client.get("/api/v1/credentials", headers=user_with_cred["headers"])
        assert resp.status_code == 200
        cred_ids = [c["id"] for c in resp.json()]
        assert user_with_cred["credential"]["id"] in cred_ids

    def test_unauthenticated_rejected(self, client):
        resp = client.get("/api/v1/credentials")
        assert resp.status_code == 401


class TestCreateCredential:
    def test_creates_with_metadata(self, client, new_user):
        cred_name = f"OpenAI Key {make_email()[:6]}"
        resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "openai",
            "name": cred_name,
            "credentials": {"api_key": "sk-test-abc123"},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "id" in body
        assert body["type"] == "openai"
        assert body["name"] == cred_name
        assert "created_at" in body

    def test_does_not_return_raw_secrets(self, client, new_user):
        resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "secret_check",
            "name": f"Secret Check {make_email()[:6]}",
            "credentials": {"api_key": "super-secret-value"},
        })
        assert resp.status_code == 200
        body = resp.json()
        # The raw credentials dict should not appear in the response
        assert "credentials" not in body or "super-secret-value" not in str(body)

    def test_duplicate_name_and_type_rejected(self, client, user_with_cred):
        resp = client.post("/api/v1/credentials", headers=user_with_cred["headers"], json={
            "type": "api_key",
            "name": "My Test Credential",
            "credentials": {"api_key": "different-key"},
        })
        assert resp.status_code == 400

    def test_same_name_different_type_allowed(self, client, user_with_cred):
        resp = client.post("/api/v1/credentials", headers=user_with_cred["headers"], json={
            "type": "openai",
            "name": "My Test Credential",
            "credentials": {"api_key": "sk-openai-key"},
        })
        assert resp.status_code == 200

    def test_unauthenticated_rejected(self, client):
        resp = client.post("/api/v1/credentials", json={
            "type": "api_key", "name": "Test", "credentials": {},
        })
        assert resp.status_code == 401


class TestGetCredential:
    def test_get_by_id(self, client, user_with_cred):
        cred_id = user_with_cred["credential"]["id"]
        resp = client.get(f"/api/v1/credentials/{cred_id}", headers=user_with_cred["headers"])
        assert resp.status_code == 200
        assert resp.json()["id"] == cred_id

    def test_nonexistent_returns_404(self, client, new_user):
        resp = client.get(f"/api/v1/credentials/{uuid.uuid4()}", headers=new_user["headers"])
        assert resp.status_code == 404

    def test_other_orgs_credential_not_accessible(self, client, user_with_cred):
        other = register(client)
        other_token = login(client, other["email"], other["password"])
        other_headers = auth_headers(other_token)

        cred_id = user_with_cred["credential"]["id"]
        resp = client.get(f"/api/v1/credentials/{cred_id}", headers=other_headers)
        assert resp.status_code == 404


class TestUpdateCredential:
    def test_rename(self, client, user_with_cred):
        cred_id = user_with_cred["credential"]["id"]
        new_name = f"Renamed Cred {make_email()[:6]}"
        resp = client.put(f"/api/v1/credentials/{cred_id}", headers=user_with_cred["headers"],
                          json={"name": new_name})
        assert resp.status_code == 200
        assert resp.json()["name"] == new_name

    def test_update_credentials_data(self, client, user_with_cred):
        cred_id = user_with_cred["credential"]["id"]
        resp = client.put(f"/api/v1/credentials/{cred_id}", headers=user_with_cred["headers"],
                          json={"credentials": {"api_key": "sk-updated-key-xyz"}})
        assert resp.status_code == 200

    def test_nonexistent_returns_404(self, client, new_user):
        resp = client.put(f"/api/v1/credentials/{uuid.uuid4()}", headers=new_user["headers"],
                          json={"name": "Updated"})
        assert resp.status_code == 404


class TestDeleteCredential:
    def test_delete_removes_credential(self, client, new_user):
        create_resp = client.post("/api/v1/credentials", headers=new_user["headers"], json={
            "type": "delete_test",
            "name": f"Delete Me {make_email()[:6]}",
            "credentials": {"token": "abc"},
        })
        cred_id = create_resp.json()["id"]

        del_resp = client.delete(f"/api/v1/credentials/{cred_id}", headers=new_user["headers"])
        assert del_resp.status_code == 200

        get_resp = client.get(f"/api/v1/credentials/{cred_id}", headers=new_user["headers"])
        assert get_resp.status_code == 404

    def test_nonexistent_returns_404(self, client, new_user):
        resp = client.delete(f"/api/v1/credentials/{uuid.uuid4()}", headers=new_user["headers"])
        assert resp.status_code == 404
