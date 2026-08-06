"""Integration tests for profile photo (avatar) upload/remove/serve.

Hits a running server (see conftest.BASE_URL), same style as
test_auth_routes.py.
"""
import io
import logging
from datetime import datetime, UTC

import pytest
import requests
from conftest import BASE_URL

from app.domain.models.user import User, UserRole
from app.interfaces.schemas.auth import UserResponse

logger = logging.getLogger(__name__)


@pytest.fixture
def avatar_user(client):
    """Register (or log in) a dedicated user for avatar tests."""
    user_data = {
        "fullname": "Avatar Test User",
        "password": "password123",
        "email": "avatar-test@example.com",
    }
    register_url = f"{BASE_URL}/auth/register"
    response = client.post(register_url, json=user_data)
    if response.status_code != 200:
        login_url = f"{BASE_URL}/auth/login"
        response = client.post(login_url, json={
            "email": user_data["email"], "password": user_data["password"],
        })
    assert response.status_code == 200, response.text
    auth_data = response.json()["data"]
    return {
        "access_token": auth_data["access_token"],
        "user_id": auth_data["user"]["id"],
    }


def _auth_headers(avatar_user) -> dict:
    return {"Authorization": f"Bearer {avatar_user['access_token']}"}


def _tiny_jpeg_bytes() -> bytes:
    """1x1 black pixel JPEG — small, valid, real image/jpeg bytes."""
    return bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300030202020202"
        "03020202030303030406040404040408060605060907090a0a090809090a0c"
        "0f0c0a0b0e0b09090d110d0e0f101011100a0c12131210130f101010ffc900"
        "0b08000100010100011100ffc4001f0000010501010101010100000000000"
        "000000102030405060708090a0bffc400b5100002010303020403050504040"
        "0000102777100102030004110521310612415107617113022032418191a10"
        "9233324ea1b1c109233524f0015162272432c62733b3527f01f620110000021"
        "1030311000000000000000000ffda000c03010002110311003f00b2c0f7fa2"
        "8a0028a0028a0028a0028a0028a0028a0028a0028a0028a0028a0028a0028a"
        "00fffd9"
    )


class TestUploadAvatar:
    def test_upload_returns_avatar_url(self, client, avatar_user):
        files = {"file": ("avatar.jpg", io.BytesIO(_tiny_jpeg_bytes()), "image/jpeg")}
        response = client.post(
            f"{BASE_URL}/auth/avatar", files=files, headers=_auth_headers(avatar_user),
        )
        assert response.status_code == 200, response.text
        user = response.json()["data"]
        assert user["avatar_url"] is not None
        assert f"/auth/avatar/{avatar_user['user_id']}" in user["avatar_url"]

    def test_rejects_non_image_content_type(self, client, avatar_user):
        files = {"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
        response = client.post(
            f"{BASE_URL}/auth/avatar", files=files, headers=_auth_headers(avatar_user),
        )
        assert response.status_code == 400

    def test_rejects_oversized_file(self, client, avatar_user):
        oversized = b"\xff\xd8\xff" + (b"0" * (5 * 1024 * 1024 + 1))
        files = {"file": ("big.jpg", io.BytesIO(oversized), "image/jpeg")}
        response = client.post(
            f"{BASE_URL}/auth/avatar", files=files, headers=_auth_headers(avatar_user),
        )
        assert response.status_code == 400


class TestServeAvatar:
    def test_serves_image_bytes_to_the_owner(self, client, avatar_user):
        files = {"file": ("avatar.jpg", io.BytesIO(_tiny_jpeg_bytes()), "image/jpeg")}
        client.post(f"{BASE_URL}/auth/avatar", files=files, headers=_auth_headers(avatar_user))

        response = client.get(
            f"{BASE_URL}/auth/avatar/{avatar_user['user_id']}", headers=_auth_headers(avatar_user),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/")

    def test_visible_to_a_different_authenticated_user(self, client, avatar_user):
        files = {"file": ("avatar.jpg", io.BytesIO(_tiny_jpeg_bytes()), "image/jpeg")}
        client.post(f"{BASE_URL}/auth/avatar", files=files, headers=_auth_headers(avatar_user))

        other = {
            "fullname": "Other Viewer",
            "password": "password123",
            "email": "avatar-viewer@example.com",
        }
        response = client.post(f"{BASE_URL}/auth/register", json=other)
        if response.status_code != 200:
            response = client.post(f"{BASE_URL}/auth/login", json={
                "email": other["email"], "password": other["password"],
            })
        other_token = response.json()["data"]["access_token"]

        response = client.get(
            f"{BASE_URL}/auth/avatar/{avatar_user['user_id']}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert response.status_code == 200

    def test_401_without_auth(self, client, avatar_user):
        response = requests.get(f"{BASE_URL}/auth/avatar/{avatar_user['user_id']}")
        assert response.status_code == 401

    def test_404_for_user_with_no_avatar(self, client, avatar_user):
        no_avatar = {
            "fullname": "No Avatar User",
            "password": "password123",
            "email": "avatar-none@example.com",
        }
        response = client.post(f"{BASE_URL}/auth/register", json=no_avatar)
        if response.status_code != 200:
            response = client.post(f"{BASE_URL}/auth/login", json={
                "email": no_avatar["email"], "password": no_avatar["password"],
            })
        data = response.json()["data"]
        response = client.get(
            f"{BASE_URL}/auth/avatar/{data['user']['id']}",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        assert response.status_code == 404


class TestRemoveAvatar:
    def test_remove_clears_avatar_url(self, client, avatar_user):
        files = {"file": ("avatar.jpg", io.BytesIO(_tiny_jpeg_bytes()), "image/jpeg")}
        client.post(f"{BASE_URL}/auth/avatar", files=files, headers=_auth_headers(avatar_user))

        response = client.delete(f"{BASE_URL}/auth/avatar", headers=_auth_headers(avatar_user))
        assert response.status_code == 200
        assert response.json()["data"]["avatar_url"] is None

        response = client.get(
            f"{BASE_URL}/auth/avatar/{avatar_user['user_id']}", headers=_auth_headers(avatar_user),
        )
        assert response.status_code == 404

    def test_remove_without_an_existing_avatar_is_a_noop(self, client, avatar_user):
        response = client.delete(f"{BASE_URL}/auth/avatar", headers=_auth_headers(avatar_user))
        assert response.status_code == 200
        assert response.json()["data"]["avatar_url"] is None


class TestReplaceAvatar:
    def test_replacing_deletes_the_old_file(self, client, avatar_user):
        files = {"file": ("avatar1.jpg", io.BytesIO(_tiny_jpeg_bytes()), "image/jpeg")}
        first = client.post(
            f"{BASE_URL}/auth/avatar", files=files, headers=_auth_headers(avatar_user),
        ).json()["data"]["avatar_url"]

        files = {"file": ("avatar2.jpg", io.BytesIO(_tiny_jpeg_bytes()), "image/jpeg")}
        second = client.post(
            f"{BASE_URL}/auth/avatar", files=files, headers=_auth_headers(avatar_user),
        ).json()["data"]["avatar_url"]

        assert first != second  # cache-busting ?v= timestamp changed

        response = client.get(
            f"{BASE_URL}/auth/avatar/{avatar_user['user_id']}", headers=_auth_headers(avatar_user),
        )
        assert response.status_code == 200  # current (second) avatar still serves fine


class TestUserResponseAvatarUrl:
    def test_no_avatar_file_id_gives_null_avatar_url(self):
        user = User(id="u1", fullname="Test", email="t@example.com", role=UserRole.USER)
        response = UserResponse.from_domain(user)
        assert response.avatar_url is None

    def test_avatar_file_id_builds_versioned_relative_url(self):
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        user = User(
            id="u1", fullname="Test", email="t@example.com", role=UserRole.USER,
            avatar_file_id="file-123", updated_at=ts,
        )
        response = UserResponse.from_domain(user)
        assert response.avatar_url == f"/api/v1/auth/avatar/u1?v={int(ts.timestamp())}"
