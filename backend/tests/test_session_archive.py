"""Integration tests for TAREFA 1.5 — archive/unarchive a session.

Hits a running server (see conftest.BASE_URL) — bring the stack up first:
./dev.sh up -d mongodb redis backend
"""
import uuid
import pytest
import logging
import requests
from conftest import BASE_URL

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.archive


@pytest.fixture
def test_user_data():
    return {
        "fullname": "Archive Test User",
        "password": "password123",
        "email": f"archive-test-{uuid.uuid4().hex[:8]}@example.com",
    }


@pytest.fixture
def authenticated_user(client, test_user_data):
    register_url = f"{BASE_URL}/auth/register"
    response = client.post(register_url, json=test_user_data)
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.fixture
def auth_headers(authenticated_user):
    return {"Authorization": f"Bearer {authenticated_user['access_token']}"}


def create_session(client: requests.Session, auth_headers: dict) -> str:
    response = client.put(f"{BASE_URL}/sessions", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["session_id"]


class TestArchiveSession:
    def test_new_session_is_not_archived(self, client, auth_headers):
        session_id = create_session(client, auth_headers)
        response = client.get(f"{BASE_URL}/sessions/{session_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["is_archived"] is False

    def test_archive_then_unarchive_round_trip(self, client, auth_headers):
        session_id = create_session(client, auth_headers)

        archived = client.post(f"{BASE_URL}/sessions/{session_id}/archive", headers=auth_headers)
        assert archived.status_code == 200
        assert archived.json()["data"] == {"session_id": session_id, "is_archived": True}

        detail = client.get(f"{BASE_URL}/sessions/{session_id}", headers=auth_headers)
        assert detail.json()["data"]["is_archived"] is True

        unarchived = client.delete(f"{BASE_URL}/sessions/{session_id}/archive", headers=auth_headers)
        assert unarchived.status_code == 200
        assert unarchived.json()["data"] == {"session_id": session_id, "is_archived": False}

        detail = client.get(f"{BASE_URL}/sessions/{session_id}", headers=auth_headers)
        assert detail.json()["data"]["is_archived"] is False

    def test_archiving_someone_elses_session_is_rejected(self, client, auth_headers):
        session_id = create_session(client, auth_headers)

        other_user = {
            "fullname": "Other Archive User",
            "password": "password123",
            "email": f"archive-test-other-{uuid.uuid4().hex[:8]}@example.com",
        }
        other_response = client.post(f"{BASE_URL}/auth/register", json=other_user)
        assert other_response.status_code == 200
        other_headers = {
            "Authorization": f"Bearer {other_response.json()['data']['access_token']}"
        }

        response = client.post(f"{BASE_URL}/sessions/{session_id}/archive", headers=other_headers)
        assert response.status_code >= 400

        # Confirm it really wasn't archived under the owner's account
        detail = client.get(f"{BASE_URL}/sessions/{session_id}", headers=auth_headers)
        assert detail.json()["data"]["is_archived"] is False


class TestListSessionsArchivedFilter:
    def test_default_list_excludes_archived(self, client, auth_headers):
        session_id = create_session(client, auth_headers)
        client.post(f"{BASE_URL}/sessions/{session_id}/archive", headers=auth_headers)

        response = client.get(f"{BASE_URL}/sessions", headers=auth_headers)
        assert response.status_code == 200
        ids = [s["session_id"] for s in response.json()["data"]["sessions"]]
        assert session_id not in ids

    def test_archived_true_returns_only_archived(self, client, auth_headers):
        archived_id = create_session(client, auth_headers)
        client.post(f"{BASE_URL}/sessions/{archived_id}/archive", headers=auth_headers)
        active_id = create_session(client, auth_headers)

        response = client.get(f"{BASE_URL}/sessions?archived=true", headers=auth_headers)
        assert response.status_code == 200
        ids = [s["session_id"] for s in response.json()["data"]["sessions"]]
        assert archived_id in ids
        assert active_id not in ids
        assert all(s["is_archived"] for s in response.json()["data"]["sessions"])
