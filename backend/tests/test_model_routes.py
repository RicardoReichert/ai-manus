"""Integration tests for the model registry API and session model plumbing.

These hit a running server (see conftest.BASE_URL) — bring the stack up
first: ./dev.sh up -d mongodb redis backend
"""
import pytest
import logging
import requests
from conftest import BASE_URL

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.models


@pytest.fixture
def test_user_data():
    return {
        "fullname": "Model Routes Test User",
        "password": "password123",
        "email": "model-routes-test@example.com",
    }


@pytest.fixture
def authenticated_user(client, test_user_data):
    register_url = f"{BASE_URL}/auth/register"
    register_response = client.post(register_url, json=test_user_data)

    if register_response.status_code == 200:
        auth_data = register_response.json()["data"]
        return auth_data

    login_url = f"{BASE_URL}/auth/login"
    login_response = client.post(
        login_url,
        json={"email": test_user_data["email"], "password": test_user_data["password"]},
    )
    if login_response.status_code == 200:
        return login_response.json()["data"]

    raise Exception("Failed to authenticate test user")


@pytest.fixture
def auth_headers(authenticated_user):
    return {"Authorization": f"Bearer {authenticated_user['access_token']}"}


class TestGetModels:
    def test_unauthenticated_returns_401(self, client: requests.Session):
        response = client.get(f"{BASE_URL}/models")
        assert response.status_code == 401

    def test_authenticated_returns_models_without_base_url(self, client, auth_headers):
        response = client.get(f"{BASE_URL}/models", headers=auth_headers)
        assert response.status_code == 200
        models = response.json()["data"]
        # The registry is database-backed now, so there is no synthesized
        # "default" entry — only what an admin registered (or the importer
        # seeded). Any non-empty registry satisfies the contract.
        assert len(models) >= 1
        for m in models:
            # ModelSummary intentionally omits base_url/api_key_env — the
            # browser has no use for internal endpoint topology.
            assert "base_url" not in m
            assert "api_key_env" not in m


def _first_registered_model_id(client, auth_headers) -> str:
    """Pick a real model id from the registry.

    Nothing is guaranteed to be called "default" any more, so tests that need
    a valid id have to ask the registry for one.
    """
    response = client.get(f"{BASE_URL}/models", headers=auth_headers)
    assert response.status_code == 200
    models = response.json()["data"]
    if not models:
        pytest.skip("No models registered; run scripts.import_models first")
    return models[0]["id"]


class TestCreateSessionModelValidation:
    def test_unknown_model_name_is_rejected(self, client, auth_headers):
        response = client.put(
            f"{BASE_URL}/sessions",
            json={"model_name": "definitely-not-a-real-model-id"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_known_model_name_is_accepted(self, client, auth_headers):
        model_id = _first_registered_model_id(client, auth_headers)
        response = client.put(
            f"{BASE_URL}/sessions",
            json={"model_name": model_id},
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestUpdateSessionModel:
    def _create_session(self, client, auth_headers) -> str:
        response = client.put(f"{BASE_URL}/sessions", headers=auth_headers)
        assert response.status_code == 200
        return response.json()["data"]["session_id"]

    def test_unknown_model_is_rejected(self, client, auth_headers):
        session_id = self._create_session(client, auth_headers)
        response = client.patch(
            f"{BASE_URL}/sessions/{session_id}/model",
            json={"model_name": "definitely-not-a-real-model-id"},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_valid_model_persists_and_is_readable(self, client, auth_headers):
        session_id = self._create_session(client, auth_headers)

        model_id = _first_registered_model_id(client, auth_headers)
        patch_response = client.patch(
            f"{BASE_URL}/sessions/{session_id}/model",
            json={"model_name": model_id},
            headers=auth_headers,
        )
        assert patch_response.status_code == 200
        patch_data = patch_response.json()["data"]
        assert patch_data["model_name"] == model_id

        # GET /sessions/{id} must echo the persisted model (regression guard
        # for the field being dropped from the response).
        get_response = client.get(f"{BASE_URL}/sessions/{session_id}", headers=auth_headers)
        assert get_response.status_code == 200
        session_data = get_response.json()["data"]
        assert session_data["model_name"] == model_id
        assert session_data["model_provider"]
