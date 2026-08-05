"""Integration tests for TAREFA 1.1 — GET /sessions/{id}/subtasks.

Hits a running server (see conftest.BASE_URL). A session only gets a plan
once a real agent run creates one (PlanEvent) — this suite doesn't drive a
live agent run anywhere (see test_search_routes.py's docstring for the same
constraint), so this covers the no-plan-yet baseline, auth, and isolation;
Session.get_last_plan() itself (which this endpoint is a thin wrapper
around) is exercised by whatever already relies on it in the live agent
loop.
"""
import uuid
import pytest
from conftest import BASE_URL

pytestmark = pytest.mark.subtasks


@pytest.fixture
def test_user_data():
    return {
        "fullname": "Subtasks Test User",
        "password": "password123",
        "email": f"subtasks-test-{uuid.uuid4().hex[:8]}@example.com",
    }


@pytest.fixture
def authenticated_user(client, test_user_data):
    response = client.post(f"{BASE_URL}/auth/register", json=test_user_data)
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.fixture
def auth_headers(authenticated_user):
    return {"Authorization": f"Bearer {authenticated_user['access_token']}"}


def create_session(client, auth_headers) -> str:
    response = client.put(f"{BASE_URL}/sessions", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["session_id"]


class TestSessionSubtasks:
    def test_unauthenticated_returns_401(self, client):
        response = client.get(f"{BASE_URL}/sessions/does-not-matter/subtasks")
        assert response.status_code == 401

    def test_new_session_has_no_plan_yet(self, client, auth_headers):
        session_id = create_session(client, auth_headers)
        response = client.get(f"{BASE_URL}/sessions/{session_id}/subtasks", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"] == {
            "session_id": session_id,
            "plan_title": None,
            "goal": None,
            "steps": [],
        }

    def test_someone_elses_session_is_rejected(self, client, auth_headers):
        session_id = create_session(client, auth_headers)
        other = client.post(f"{BASE_URL}/auth/register", json={
            "fullname": "Other Subtasks User",
            "password": "password123",
            "email": f"subtasks-test-other-{uuid.uuid4().hex[:8]}@example.com",
        })
        other_headers = {"Authorization": f"Bearer {other.json()['data']['access_token']}"}
        response = client.get(f"{BASE_URL}/sessions/{session_id}/subtasks", headers=other_headers)
        assert response.status_code >= 400

    def test_nonexistent_session_is_rejected(self, client, auth_headers):
        response = client.get(f"{BASE_URL}/sessions/does-not-exist/subtasks", headers=auth_headers)
        assert response.status_code >= 400
