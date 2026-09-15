"""Integration tests for TAREFA 16.1 — GET /search endpoint wiring.

Hits a running server (see conftest.BASE_URL). Message-matching/snippet/
sort logic is covered by the pure unit tests in test_search_messages.py —
this only exercises auth, validation, and the empty-baseline round trip
(there's no REST endpoint to inject a synthetic chat message outside a real
WS agent run, which this suite doesn't drive anywhere else either).
"""
import uuid
import pytest
from conftest import BASE_URL

pytestmark = pytest.mark.search


@pytest.fixture
def test_user_data():
    return {
        "fullname": "Search Test User",
        "password": "password123",
        "email": f"search-test-{uuid.uuid4().hex[:8]}@example.com",
    }


@pytest.fixture
def authenticated_user(client, test_user_data):
    response = client.post(f"{BASE_URL}/auth/register", json=test_user_data)
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.fixture
def auth_headers(authenticated_user):
    return {"Authorization": f"Bearer {authenticated_user['access_token']}"}


class TestSearchRoute:
    def test_unauthenticated_returns_401(self, client):
        response = client.get(f"{BASE_URL}/search", params={"q": "anything"})
        assert response.status_code == 401

    def test_new_user_with_no_sessions_gets_empty_results(self, client, auth_headers):
        response = client.get(f"{BASE_URL}/search", params={"q": "anything"}, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["results"] == []

    def test_blank_query_returns_empty_results(self, client, auth_headers):
        response = client.get(f"{BASE_URL}/search", params={"q": ""}, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["results"] == []

    def test_limit_out_of_range_is_rejected(self, client, auth_headers):
        response = client.get(
            f"{BASE_URL}/search", params={"q": "x", "limit": 500}, headers=auth_headers
        )
        assert response.status_code == 422

    def test_default_limit_is_accepted(self, client, auth_headers):
        response = client.get(f"{BASE_URL}/search", params={"q": "x"}, headers=auth_headers)
        assert response.status_code == 200

    def test_search_only_covers_the_authenticated_users_own_sessions(self, client, auth_headers):
        """A session created by another user must never surface here."""
        other = client.post(f"{BASE_URL}/auth/register", json={
            "fullname": "Other Search User",
            "password": "password123",
            "email": f"search-test-other-{uuid.uuid4().hex[:8]}@example.com",
        })
        other_headers = {"Authorization": f"Bearer {other.json()['data']['access_token']}"}
        client.put(f"{BASE_URL}/sessions", headers=other_headers)

        response = client.get(f"{BASE_URL}/search", params={"q": "anything"}, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["results"] == []
