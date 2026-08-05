"""Integration tests for the admin model registry API.

Hits a running server (see conftest.BASE_URL) — bring the stack up first:
./dev.sh up -d mongodb redis backend

Admin routes require role=admin, which "password" auth users don't get
through the public API. Promotion here goes straight to Mongo, the same
workaround test_auth_routes.py documents ("would need database manipulation")
but does not itself implement.
"""
import logging
import uuid

import pytest
import requests
from pymongo import MongoClient

from conftest import BASE_URL

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.models

MONGO_URL = "mongodb://localhost:27017"
MONGO_DB = "manus"


def _promote_to_admin(user_id: str) -> None:
    client = MongoClient(MONGO_URL)
    try:
        result = client[MONGO_DB]["users"].update_one(
            {"user_id": user_id}, {"$set": {"role": "admin"}}
        )
        if result.matched_count == 0:
            pytest.skip(f"Could not find user {user_id} in Mongo to promote (unexpected schema?)")
    finally:
        client.close()


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


# These tests run against the real dev database (see module docstring), and
# the registry's default-model selection (model_registry.get_default_model)
# picks the first enabled entry by (sort_order, name) — so a model left behind
# by a previous run can silently become "the" default for Claw and real chat
# traffic. Everything this file creates carries this prefix, and it is swept
# after every test regardless of outcome.
TEST_MODEL_ID_PREFIX = "pytest-model-config-"


@pytest.fixture(autouse=True)
def _cleanup_test_models():
    yield
    client = MongoClient(MONGO_URL)
    try:
        client[MONGO_DB]["model_configs"].delete_many(
            {"model_config_id": {"$regex": f"^{TEST_MODEL_ID_PREFIX}"}}
        )
        client[MONGO_DB]["users"].delete_many(
            {"email": {"$regex": r"^model-(admin|nonadmin)-"}}
        )
    finally:
        client.close()


@pytest.fixture
def admin_headers(client):
    """A freshly registered user, promoted to admin directly in Mongo."""
    email = _unique_email("model-admin")
    resp = client.post(
        f"{BASE_URL}/auth/register",
        json={"fullname": "Model Admin", "password": "password123", "email": email},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    _promote_to_admin(data["user"]["id"])

    # Role is baked into the JWT at login, so re-authenticate after promotion.
    login = client.post(
        f"{BASE_URL}/auth/login", json={"email": email, "password": "password123"}
    )
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_headers(client):
    """A regular, non-admin authenticated user."""
    email = _unique_email("model-nonadmin")
    resp = client.post(
        f"{BASE_URL}/auth/register",
        json={"fullname": "Regular User", "password": "password123", "email": email},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _unique_model_id(suffix: str = "test-model") -> str:
    return f"{TEST_MODEL_ID_PREFIX}{suffix}-{uuid.uuid4().hex[:8]}"


class TestAuthorization:
    def test_unauthenticated_is_rejected(self, client):
        response = client.get(f"{BASE_URL}/admin/models")
        assert response.status_code == 401

    def test_non_admin_cannot_list(self, client, user_headers):
        # Matches the existing admin-guard convention (auth_routes.py):
        # UnauthorizedError -> 401, not 403.
        response = client.get(f"{BASE_URL}/admin/models", headers=user_headers)
        assert response.status_code == 401

    def test_non_admin_cannot_create(self, client, user_headers):
        response = client.post(
            f"{BASE_URL}/admin/models",
            json={"id": _unique_model_id(), "name": "X", "provider": "openai", "model": "gpt-4o"},
            headers=user_headers,
        )
        assert response.status_code == 401


class TestCreateModel:
    def test_admin_can_create_a_model(self, client, admin_headers):
        model_id = _unique_model_id()
        response = client.post(
            f"{BASE_URL}/admin/models",
            json={
                "id": model_id, "name": "Test GPT-4o", "provider": "openai",
                "model": "gpt-4o", "api_key": "sk-test-abcdefgh1234",
            },
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert body["id"] == model_id
        assert body["has_api_key"] is True
        assert body["api_key_hint"] == "…1234"

    def test_response_never_contains_the_plaintext_key(self, client, admin_headers):
        model_id = _unique_model_id()
        response = client.post(
            f"{BASE_URL}/admin/models",
            json={
                "id": model_id, "name": "X", "provider": "openai",
                "model": "gpt-4o", "api_key": "sk-super-secret-value",
            },
            headers=admin_headers,
        )
        assert "sk-super-secret-value" not in response.text

    def test_duplicate_id_is_rejected(self, client, admin_headers):
        model_id = _unique_model_id()
        payload = {"id": model_id, "name": "X", "provider": "openai", "model": "gpt-4o"}
        first = client.post(f"{BASE_URL}/admin/models", json=payload, headers=admin_headers)
        assert first.status_code == 200
        second = client.post(f"{BASE_URL}/admin/models", json=payload, headers=admin_headers)
        assert second.status_code == 400

    def test_capabilities_are_auto_detected_from_the_catalog(self, client, admin_headers):
        model_id = _unique_model_id("qwen3-4b")
        response = client.post(
            f"{BASE_URL}/admin/models",
            json={"id": model_id, "name": "Qwen3 4B", "provider": "ollama", "model": "qwen3-4b", "is_local": True},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert body["capabilities_auto_detected"] is True
        assert body["capabilities"]["max_tools"] is not None

    def test_a_model_with_no_credential_is_accepted(self, client, admin_headers):
        """Correct for local runtimes (LM Studio / Ollama) needing no auth."""
        model_id = _unique_model_id("local")
        response = client.post(
            f"{BASE_URL}/admin/models",
            json={"id": model_id, "name": "Local", "provider": "ollama", "model": "llama3", "is_local": True},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["has_api_key"] is False

    def test_an_id_containing_a_slash_is_rejected(self, client, admin_headers):
        """A '/' in the id makes it two URL path segments on every follow-up
        route (test/edit/delete), so creation must reject it up front rather
        than let a model be created and then be unreachable by every other
        action."""
        response = client.post(
            f"{BASE_URL}/admin/models",
            json={
                "id": f"{TEST_MODEL_ID_PREFIX}google/gemma-4-e4b",
                "name": "Bad", "provider": "openai", "model": "google/gemma-4-e4b",
            },
            headers=admin_headers,
        )
        assert response.status_code == 422

    def test_a_model_name_containing_a_slash_is_fine(self, client, admin_headers):
        """The restriction is on the id (URL segment), not the provider's
        real model name — "google/gemma-4-e4b", "anthropic/claude-3.5-sonnet"
        style names are exactly what admins need to type here."""
        model_id = _unique_model_id("gemma")
        response = client.post(
            f"{BASE_URL}/admin/models",
            json={"id": model_id, "name": "Gemma", "provider": "openai", "model": "google/gemma-4-e4b"},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text


class TestUpdateModel:
    def _create(self, client, admin_headers, **overrides):
        model_id = _unique_model_id()
        payload = {
            "id": model_id, "name": "Original Name", "provider": "openai",
            "model": "gpt-4o", "api_key": "sk-original-key-1234",
        }
        payload.update(overrides)
        resp = client.post(f"{BASE_URL}/admin/models", json=payload, headers=admin_headers)
        assert resp.status_code == 200
        return model_id

    def test_updating_name_does_not_touch_the_key(self, client, admin_headers):
        model_id = self._create(client, admin_headers)
        response = client.patch(
            f"{BASE_URL}/admin/models/{model_id}",
            json={"name": "Renamed"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["name"] == "Renamed"
        assert body["has_api_key"] is True
        assert body["api_key_hint"] == "…1234"

    def test_explicit_clear_removes_the_key(self, client, admin_headers):
        model_id = self._create(client, admin_headers)
        response = client.patch(
            f"{BASE_URL}/admin/models/{model_id}",
            json={"clear_api_key": True},
            headers=admin_headers,
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["has_api_key"] is False
        assert body["api_key_hint"] == ""

    def test_sending_a_new_key_replaces_the_old_one(self, client, admin_headers):
        model_id = self._create(client, admin_headers)
        response = client.patch(
            f"{BASE_URL}/admin/models/{model_id}",
            json={"api_key": "sk-brand-new-key-9999"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["api_key_hint"] == "…9999"

    def test_unknown_model_is_404(self, client, admin_headers):
        response = client.patch(
            f"{BASE_URL}/admin/models/does-not-exist-{uuid.uuid4().hex}",
            json={"name": "X"},
            headers=admin_headers,
        )
        assert response.status_code == 404


class TestDeleteModel:
    def test_admin_can_delete(self, client, admin_headers):
        model_id = _unique_model_id()
        client.post(
            f"{BASE_URL}/admin/models",
            json={"id": model_id, "name": "X", "provider": "openai", "model": "gpt-4o"},
            headers=admin_headers,
        )
        response = client.delete(f"{BASE_URL}/admin/models/{model_id}", headers=admin_headers)
        assert response.status_code == 200

        listing = client.get(f"{BASE_URL}/admin/models", headers=admin_headers)
        assert model_id not in [m["id"] for m in listing.json()["data"]["models"]]

    def test_deleting_unknown_model_is_404(self, client, admin_headers):
        response = client.delete(
            f"{BASE_URL}/admin/models/does-not-exist-{uuid.uuid4().hex}",
            headers=admin_headers,
        )
        assert response.status_code == 404


class TestPublicListingReflectsRegistry:
    def test_a_newly_created_model_appears_in_the_public_dropdown(self, client, admin_headers, user_headers):
        model_id = _unique_model_id()
        client.post(
            f"{BASE_URL}/admin/models",
            json={"id": model_id, "name": "Dropdown Test", "provider": "openai", "model": "gpt-4o"},
            headers=admin_headers,
        )
        response = client.get(f"{BASE_URL}/models", headers=user_headers)
        assert response.status_code == 200
        assert model_id in [m["id"] for m in response.json()["data"]]

    def test_a_disabled_model_does_not_appear_in_the_public_dropdown(self, client, admin_headers, user_headers):
        model_id = _unique_model_id()
        client.post(
            f"{BASE_URL}/admin/models",
            json={"id": model_id, "name": "Disabled", "provider": "openai", "model": "gpt-4o", "enabled": False},
            headers=admin_headers,
        )
        response = client.get(f"{BASE_URL}/models", headers=user_headers)
        assert model_id not in [m["id"] for m in response.json()["data"]]
