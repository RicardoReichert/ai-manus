"""Integration tests for TAREFA 4.1 — GET /sessions/{id}/usage and
POST /sessions/{id}/rating.

Hits a running server (see conftest.BASE_URL) — bring the stack up first:
./dev.sh up -d mongodb redis backend
"""
import uuid
import pytest
import requests
from conftest import BASE_URL

pytestmark = pytest.mark.usage


@pytest.fixture
def test_user_data():
    return {
        "fullname": "Usage Test User",
        "password": "password123",
        "email": f"usage-test-{uuid.uuid4().hex[:8]}@example.com",
    }


@pytest.fixture
def authenticated_user(client, test_user_data):
    response = client.post(f"{BASE_URL}/auth/register", json=test_user_data)
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.fixture
def auth_headers(authenticated_user):
    return {"Authorization": f"Bearer {authenticated_user['access_token']}"}


def create_session(client: requests.Session, auth_headers: dict) -> str:
    response = client.put(f"{BASE_URL}/sessions", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["session_id"]


class TestSessionUsage:
    def test_new_session_usage_is_all_zeros_and_unrated(self, client, auth_headers):
        session_id = create_session(client, auth_headers)
        response = client.get(f"{BASE_URL}/sessions/{session_id}/usage", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data == {
            "session_id": session_id,
            "worked_ms": 0,
            "pages_viewed": 0,
            "commands_run": 0,
            "api_calls": 0,
            "files_created": 0,
            "rating": None,
        }

    def test_no_credit_field_anywhere_in_the_response(self, client, auth_headers):
        session_id = create_session(client, auth_headers)
        response = client.get(f"{BASE_URL}/sessions/{session_id}/usage", headers=auth_headers)
        body_text = response.text.lower()
        assert "credit" not in body_text

    def test_usage_for_someone_elses_session_is_rejected(self, client, auth_headers):
        session_id = create_session(client, auth_headers)
        other = client.post(f"{BASE_URL}/auth/register", json={
            "fullname": "Other Usage User",
            "password": "password123",
            "email": f"usage-test-other-{uuid.uuid4().hex[:8]}@example.com",
        })
        other_headers = {"Authorization": f"Bearer {other.json()['data']['access_token']}"}
        response = client.get(f"{BASE_URL}/sessions/{session_id}/usage", headers=other_headers)
        assert response.status_code >= 400


class TestSessionRating:
    def test_rate_then_clear_round_trip(self, client, auth_headers):
        session_id = create_session(client, auth_headers)

        rated = client.post(f"{BASE_URL}/sessions/{session_id}/rating", headers=auth_headers, json={"rating": 4})
        assert rated.status_code == 200
        assert rated.json()["data"] == {"session_id": session_id, "rating": 4}

        usage = client.get(f"{BASE_URL}/sessions/{session_id}/usage", headers=auth_headers)
        assert usage.json()["data"]["rating"] == 4

        cleared = client.post(f"{BASE_URL}/sessions/{session_id}/rating", headers=auth_headers, json={"rating": None})
        assert cleared.status_code == 200
        assert cleared.json()["data"]["rating"] is None

    @pytest.mark.parametrize("bad_rating", [0, 6, -1])
    def test_out_of_range_rating_is_rejected(self, client, auth_headers, bad_rating):
        session_id = create_session(client, auth_headers)
        response = client.post(
            f"{BASE_URL}/sessions/{session_id}/rating", headers=auth_headers, json={"rating": bad_rating}
        )
        assert response.status_code == 400
