# User Profile Photo (Avatar) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user upload, crop-to-circle, and remove a profile photo from Settings → Account, replacing the initials-circle avatar everywhere it appears.

**Architecture:** Backend reuses the existing GridFS-backed `FileService` for storage but adds a dedicated, non-expiring `GET /auth/avatar/{user_id}` endpoint (unlike the 30-min signed-URL flow chat attachments use) plus `POST`/`DELETE /auth/avatar`. `User` gains `avatar_file_id`; `UserResponse` gains a pre-built `avatar_url`. Frontend adds a hand-rolled canvas crop dialog (drag to pan, slider to zoom, no new dependency) and a shared `UserAvatar.vue` that four existing components swap in for their duplicated initials-circle markup.

**Tech Stack:** FastAPI + Beanie/MongoDB (GridFS) on the backend; Vue 3 `<script setup>` + Canvas API on the frontend. No new dependencies either side.

## Global Constraints

- Accepted avatar file types: `image/jpeg`, `image/png`, `image/webp` only.
- Max upload size: 5MB, enforced both client-side (before the crop step) and server-side.
- Cropped output is always 512×512, exported as `image/jpeg` quality 0.9.
- `GET /auth/avatar/{user_id}` requires any authenticated session (`get_current_user`) — not owner-restricted; viewing another user's avatar is allowed by design.
- Reference spec: `docs/superpowers/specs/2026-08-06-user-avatar-design.md`.

---

## Task 1: Backend — `avatar_file_id` field on `User` and `UserDocument`

**Files:**
- Modify: `backend/app/domain/models/user.py`
- Modify: `backend/app/infrastructure/models/documents.py:48-66` (`UserDocument`)
- Test: `backend/tests/test_avatar_routes.py` (new file, created in this task)

**Interfaces:**
- Produces: `User.avatar_file_id: Optional[str]` (default `None`), same field name on `UserDocument`. Every later task reads/writes this exact attribute name on both classes.

**Context:** `BaseDocument.update_from_domain`/`to_domain` round-trip domain ↔ document objects by matching field names via `model_dump()`/`model_validate()` — a field present on only one side is silently dropped on every read (this bit a previous feature on this branch; see `2281750`'s commit message). Both classes must get the field in this same task.

- [ ] **Step 1: Add the field to the domain model**

In `backend/app/domain/models/user.py`, add `avatar_file_id` right after `password_hash`:

```python
class User(BaseModel):
    """User domain model"""
    id: str
    fullname: str
    email: str  # Now required field for login
    password_hash: Optional[str] = None
    avatar_file_id: Optional[str] = None
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime = datetime.now(UTC)
    updated_at: datetime = datetime.now(UTC)
    last_login_at: Optional[datetime] = None
```

- [ ] **Step 2: Add the matching field to the Mongo document**

In `backend/app/infrastructure/models/documents.py`, inside `UserDocument` (currently lines 48-66), add the same field after `password_hash`:

```python
class UserDocument(BaseDocument[User], id_field="user_id", domain_model_class=User):
    """MongoDB document for User"""
    user_id: str
    fullname: str
    email: str  # Now required field for login
    password_hash: Optional[str] = None
    avatar_file_id: Optional[str] = None
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)
    last_login_at: Optional[datetime] = None
```

- [ ] **Step 3: Write a failing round-trip test**

Create `backend/tests/test_avatar_routes.py`:

```python
"""Integration tests for profile photo (avatar) upload/remove/serve.

Hits a running server (see conftest.BASE_URL), same style as
test_auth_routes.py.
"""
import io
import logging

import pytest
import requests
from conftest import BASE_URL

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
        "0000102771 00102030004110521310612415107617113022032418191a10"
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
```

This whole file will fail to collect/run meaningfully yet because none of the
routes exist. That's expected — the remaining steps in this task just prove
the *domain field* round-trips; the rest of this test file is exercised
task-by-task as the routes are built (Tasks 3-4).

- [ ] **Step 4: Run the new test file to confirm it fails for the right reason**

Requires the dev stack up: `./dev.sh up -d mongodb redis backend`, then:

Run: `cd backend && uv run pytest tests/test_avatar_routes.py -v`
Expected: every test FAILs with a connection/404 error hitting `/auth/avatar` (route doesn't exist yet) — not an import error, not a Python exception. If you see a Python traceback instead (e.g. `AttributeError`), fix that first.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domain/models/user.py backend/app/infrastructure/models/documents.py backend/tests/test_avatar_routes.py
git commit -m "feat(auth): add avatar_file_id field to User and UserDocument"
```

---

## Task 2: Backend — `AuthService.set_avatar` + `UserResponse.avatar_url`

**Files:**
- Modify: `backend/app/application/services/auth_service.py` (near `change_fullname`, ~line 396)
- Modify: `backend/app/interfaces/schemas/auth.py` (`UserResponse`, ~line 145)

**Interfaces:**
- Consumes: `User.avatar_file_id` (Task 1), `self.user_repository.get_user_by_id`/`update_user` (existing, used identically by `change_fullname`).
- Produces: `AuthService.set_avatar(user_id: str, avatar_file_id: Optional[str]) -> User`. `UserResponse.avatar_url: Optional[str]`, built as `/api/v1/auth/avatar/{user.id}?v=<int(user.updated_at.timestamp())>` when `avatar_file_id` is set, else `None`. Task 4's routes call `set_avatar`; Task 4's routes and Task 5's frontend both read `avatar_url` off `UserResponse`.

- [ ] **Step 1: Add `set_avatar` to `AuthService`**

In `backend/app/application/services/auth_service.py`, add this right after `change_fullname` (after its `return updated_user` at line 409):

```python
    async def set_avatar(self, user_id: str, avatar_file_id: Optional[str]) -> User:
        logger.info(f"Setting avatar for user: {user_id} -> {avatar_file_id}")
        user = await self.user_repository.get_user_by_id(user_id)
        if not user:
            raise ValidationError("User not found")
        user.avatar_file_id = avatar_file_id
        user.updated_at = datetime.utcnow()
        updated_user = await self.user_repository.update_user(user)
        logger.info(f"Avatar set successfully for user: {user_id}")
        return updated_user
```

(`ValidationError` and `datetime` are already imported at the top of this file — same ones `change_fullname` uses.)

- [ ] **Step 2: Add `avatar_url` to `UserResponse`**

In `backend/app/interfaces/schemas/auth.py`, replace the `UserResponse` class (currently lines 145-168):

```python
class UserResponse(BaseModel):
    """User response schema"""
    id: str
    fullname: str
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None
    avatar_url: Optional[str] = None

    @staticmethod
    def from_domain(user) -> 'UserResponse':
        """Convert user domain model to response schema"""
        avatar_url = None
        if getattr(user, 'avatar_file_id', None):
            avatar_url = f"/api/v1/auth/avatar/{user.id}?v={int(user.updated_at.timestamp())}"
        return UserResponse(
            id=user.id,
            fullname=user.fullname,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login_at=user.last_login_at,
            avatar_url=avatar_url,
        )
```

- [ ] **Step 3: Write a unit test for `avatar_url` construction**

Add to `backend/tests/test_avatar_routes.py`, at module scope (no server needed — pure schema logic):

```python
from datetime import datetime, UTC

from app.domain.models.user import User, UserRole
from app.interfaces.schemas.auth import UserResponse


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
```

- [ ] **Step 4: Run the unit test**

Run: `cd backend && uv run pytest tests/test_avatar_routes.py::TestUserResponseAvatarUrl -v`
Expected: both PASS (this test needs no live server — it's pure Python).

- [ ] **Step 5: Commit**

```bash
git add backend/app/application/services/auth_service.py backend/app/interfaces/schemas/auth.py backend/tests/test_avatar_routes.py
git commit -m "feat(auth): AuthService.set_avatar and UserResponse.avatar_url"
```

---

## Task 3: Backend — `GET /auth/avatar/{user_id}` (serve)

**Files:**
- Modify: `backend/app/interfaces/api/auth_routes.py`

**Interfaces:**
- Consumes: `AuthService.get_user_by_id` (existing, line 411), `FileService.download_file(file_id, user_id=None)` (existing, returns `Tuple[BinaryIO, FileInfo]`), `get_file_service` dependency (existing, used by `file_routes.py`).
- Produces: nothing new consumed elsewhere — this is the route Task 5's `UserAvatar.vue` points its `<img>` at via `avatar_url` from Task 2.

- [ ] **Step 1: Add the imports this route needs**

In `backend/app/interfaces/api/auth_routes.py`, the top already imports `NotFoundError`/`BadRequestError` (line 8-10). Add two more imports right after the existing `from app.application.services.auth_service import AuthService` line:

```python
from app.application.services.file_service import FileService
from fastapi.responses import StreamingResponse
```

And add `get_file_service` to the existing dependencies import (currently `from app.interfaces.dependencies import get_auth_service, get_current_user, get_email_service`):

```python
from app.interfaces.dependencies import get_auth_service, get_current_user, get_email_service, get_file_service
```

- [ ] **Step 2: Add the route**

Add this after `get_current_user_info` (after its `return APIResponse.success(...)` at line 150):

```python
@router.get("/avatar/{user_id}")
async def get_avatar(
    user_id: str,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    file_service: FileService = Depends(get_file_service),
):
    """Serve a user's profile photo. Any authenticated user may view any
    other user's avatar — not owner-restricted, same as a display name."""
    target_user = await auth_service.get_user_by_id(user_id)
    if not target_user or not target_user.avatar_file_id:
        raise NotFoundError("Avatar not found")
    try:
        file_data, file_info = await file_service.download_file(target_user.avatar_file_id)
    except (FileNotFoundError, PermissionError):
        raise NotFoundError("Avatar not found")
    headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    return StreamingResponse(
        file_data,
        media_type=file_info.content_type or "image/jpeg",
        headers=headers,
    )
```

- [ ] **Step 3: Run the "404 for user with no avatar" and "401 without auth" tests**

Run: `cd backend && uv run pytest tests/test_avatar_routes.py::TestServeAvatar::test_401_without_auth tests/test_avatar_routes.py::TestServeAvatar::test_404_for_user_with_no_avatar -v`
Expected: both PASS. (`test_serves_image_bytes_to_the_owner` and `test_visible_to_a_different_authenticated_user` still FAIL — they depend on `POST /auth/avatar` from Task 4.)

- [ ] **Step 4: Commit**

```bash
git add backend/app/interfaces/api/auth_routes.py
git commit -m "feat(auth): GET /auth/avatar/{user_id} serves the profile photo"
```

---

## Task 4: Backend — `POST /auth/avatar` and `DELETE /auth/avatar`

**Files:**
- Modify: `backend/app/interfaces/api/auth_routes.py`

**Interfaces:**
- Consumes: `AuthService.set_avatar` (Task 2), `FileService.upload_file`/`delete_file` (existing, same signatures `file_routes.py` already uses), `UserResponse.avatar_url` (Task 2).
- Produces: the two endpoints Task 6's `api/auth.ts` (`uploadAvatar`/`removeAvatar`) call.

- [ ] **Step 1: Add the multipart-upload imports**

Add to the existing `from fastapi import APIRouter, Depends, Request, Response` line in `auth_routes.py`:

```python
from fastapi import APIRouter, Depends, Request, Response, UploadFile, File
```

- [ ] **Step 2: Add the mime/size constants and both routes**

Add near the top of `auth_routes.py`, right after `router = APIRouter(prefix="/auth", tags=["auth"])`:

```python
_AVATAR_MIME_WHITELIST = {"image/jpeg", "image/png", "image/webp"}
_AVATAR_MAX_BYTES = 5 * 1024 * 1024  # 5MB
```

Add the two routes right after `get_avatar` (from Task 3):

```python
@router.post("/avatar", response_model=APIResponse[UserResponse])
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[UserResponse]:
    if file.content_type not in _AVATAR_MIME_WHITELIST:
        raise BadRequestError("Avatar must be a JPEG, PNG, or WebP image")
    contents = await file.read()
    if len(contents) > _AVATAR_MAX_BYTES:
        raise BadRequestError("Avatar image must be 5MB or smaller")

    import io
    file_info = await file_service.upload_file(
        file_data=io.BytesIO(contents),
        filename=file.filename or "avatar",
        user_id=current_user.id,
        content_type=file.content_type,
    )

    old_avatar_file_id = current_user.avatar_file_id
    updated_user = await auth_service.set_avatar(current_user.id, file_info.file_id)

    if old_avatar_file_id:
        try:
            await file_service.delete_file(old_avatar_file_id, current_user.id)
        except Exception as e:
            logger.warning(f"Failed to delete previous avatar file {old_avatar_file_id}: {e}")

    return APIResponse.success(UserResponse.from_domain(updated_user))


@router.delete("/avatar", response_model=APIResponse[UserResponse])
async def remove_avatar(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[UserResponse]:
    if current_user.avatar_file_id:
        try:
            await file_service.delete_file(current_user.avatar_file_id, current_user.id)
        except Exception as e:
            logger.warning(f"Failed to delete avatar file {current_user.avatar_file_id}: {e}")
    updated_user = await auth_service.set_avatar(current_user.id, None)
    return APIResponse.success(UserResponse.from_domain(updated_user))
```

- [ ] **Step 3: Run the full avatar test file**

Run: `cd backend && uv run pytest tests/test_avatar_routes.py -v`
Expected: every test in the file PASSes now.

- [ ] **Step 4: Run the full backend suite to confirm no regressions**

Run: `cd backend && uv run pytest`
Expected: same pass/fail counts as the pre-existing baseline (16 known pre-existing failures unrelated to auth/avatar — see any recent commit message on this branch for the exact count) plus all-new avatar tests passing. If the failure count grew, something in this task broke an existing route — investigate before continuing.

- [ ] **Step 5: Commit**

```bash
git add backend/app/interfaces/api/auth_routes.py
git commit -m "feat(auth): POST/DELETE /auth/avatar upload and remove the profile photo"
```

---

## Task 5: Frontend — crop geometry pure functions + tests

**Files:**
- Create: `frontend/src/utils/avatarCrop.ts`
- Test: `frontend/src/utils/__tests__/avatarCrop.spec.ts`

**Interfaces:**
- Produces: `fitCoverScale(imageWidth, imageHeight, viewportSize): number`, `clampOffset(params): { x: number; y: number }`, `computeCropSourceRect(params): { sx: number; sy: number; sSize: number }`. Task 6's `AvatarCropDialog.vue` imports and uses all three by these exact names.

This task has zero DOM/canvas dependency — pure math, fully unit-testable in isolation. Follow TDD: write the test file first, watch it fail (module doesn't exist), then implement.

- [ ] **Step 1: Write the failing test file**

Create `frontend/src/utils/__tests__/avatarCrop.spec.ts`:

```typescript
import { describe, it, expect } from 'vitest';
import { fitCoverScale, clampOffset, computeCropSourceRect } from '../avatarCrop';

describe('fitCoverScale', () => {
  it('scales a wider-than-viewport image so its height fills the viewport', () => {
    // 400x200 image, 100x100 viewport -> must scale by 0.5 (100/200) to cover height
    expect(fitCoverScale(400, 200, 100)).toBeCloseTo(0.5);
  });

  it('scales a taller-than-viewport image so its width fills the viewport', () => {
    // 200x400 image, 100x100 viewport -> must scale by 0.5 (100/200) to cover width
    expect(fitCoverScale(200, 400, 100)).toBeCloseTo(0.5);
  });

  it('a square image at viewport size scales to exactly 1', () => {
    expect(fitCoverScale(100, 100, 100)).toBeCloseTo(1);
  });
});

describe('clampOffset', () => {
  it('keeps the displayed image covering the viewport (no blank edges), clamping each axis independently', () => {
    // displayedWidth 150, displayedHeight 250, 100 viewport:
    // x must stay within [-50, 0], y must stay within [-150, 0]
    const result = clampOffset({
      offsetX: 10, offsetY: -200, displayedWidth: 150, displayedHeight: 250, viewportSize: 100,
    });
    expect(result.x).toBe(0);    // clamped up from 10 (would show blank left/top edge)
    expect(result.y).toBe(-150); // clamped down from -200 (would show blank bottom edge)
  });

  it('passes through an offset that is already within bounds', () => {
    const result = clampOffset({
      offsetX: -20, offsetY: -30, displayedWidth: 150, displayedHeight: 150, viewportSize: 100,
    });
    expect(result).toEqual({ x: -20, y: -30 });
  });
});

describe('computeCropSourceRect', () => {
  it('computes the full image as the source rect at zoom=1, no pan, square image', () => {
    // 200x200 image, 100 viewport, baseScale=0.5 (cover), zoom=1, no offset
    const rect = computeCropSourceRect({
      imageWidth: 200, imageHeight: 200, viewportSize: 100,
      offsetX: 0, offsetY: 0, zoom: 1,
    });
    expect(rect.sx).toBeCloseTo(0);
    expect(rect.sy).toBeCloseTo(0);
    expect(rect.sSize).toBeCloseTo(200); // whole image is the source at scale 0.5
  });

  it('zooming in shrinks the source rect (crops in tighter)', () => {
    const rect = computeCropSourceRect({
      imageWidth: 200, imageHeight: 200, viewportSize: 100,
      offsetX: 0, offsetY: 0, zoom: 2,
    });
    expect(rect.sSize).toBeCloseTo(100); // 2x zoom -> half the source region
  });

  it('a pan offset shifts the source rect origin', () => {
    // scale = baseScale(0.5) * zoom(1) = 0.5; offsetX -20 CSS px -> source shifts by 20/0.5 = 40
    const rect = computeCropSourceRect({
      imageWidth: 200, imageHeight: 200, viewportSize: 100,
      offsetX: -20, offsetY: 0, zoom: 1,
    });
    expect(rect.sx).toBeCloseTo(40);
    expect(rect.sy).toBeCloseTo(0);
  });
});
```

- [ ] **Step 2: Run the test to confirm it fails on the missing module**

Run: `cd frontend && npx vitest run src/utils/__tests__/avatarCrop.spec.ts`
Expected: FAIL — `Cannot find module '../avatarCrop'`.

- [ ] **Step 3: Implement `avatarCrop.ts`**

Create `frontend/src/utils/avatarCrop.ts`:

```typescript
/**
 * Pure geometry for the avatar crop dialog. No DOM/canvas access here —
 * kept separate so the math is unit-testable without mounting a component.
 *
 * Model: a square "viewport" of CSS px `viewportSize` shows a circular crop
 * guide. The source image is displayed inside it at `fitCoverScale * zoom`,
 * offset by (offsetX, offsetY) CSS px from the viewport's top-left. Zoom
 * ranges from 1 (image just covers the viewport) upward.
 */

/** Scale factor so the image's shorter dimension exactly fills the viewport
 * (cover behavior — same as CSS `object-fit: cover`). */
export function fitCoverScale(imageWidth: number, imageHeight: number, viewportSize: number): number {
  return Math.max(viewportSize / imageWidth, viewportSize / imageHeight);
}

/** Clamp a pan offset so the displayed image always fully covers the
 * viewport (no blank space at any edge). `displayedWidth`/`displayedHeight`
 * are the image's rendered CSS px size at the current zoom — kept separate
 * (rather than a single `displayedSize`) because at `fitCoverScale` only
 * one axis is exactly viewport-sized; the other is typically larger, so
 * each axis needs its own clamp range. */
export function clampOffset(params: {
  offsetX: number;
  offsetY: number;
  displayedWidth: number;
  displayedHeight: number;
  viewportSize: number;
}): { x: number; y: number } {
  const clampAxis = (offset: number, displayedSize: number) => {
    const min = params.viewportSize - displayedSize; // negative or zero
    return Math.min(0, Math.max(min, offset));
  };
  return {
    x: clampAxis(params.offsetX, params.displayedWidth),
    y: clampAxis(params.offsetY, params.displayedHeight),
  };
}

/** Given the current pan/zoom state, compute the square source rectangle
 * (in original image pixel coordinates) that the viewport is showing —
 * this is what gets drawn into the output canvas. */
export function computeCropSourceRect(params: {
  imageWidth: number;
  imageHeight: number;
  viewportSize: number;
  offsetX: number;
  offsetY: number;
  zoom: number;
}): { sx: number; sy: number; sSize: number } {
  const scale = fitCoverScale(params.imageWidth, params.imageHeight, params.viewportSize) * params.zoom;
  return {
    sx: -params.offsetX / scale,
    sy: -params.offsetY / scale,
    sSize: params.viewportSize / scale,
  };
}
```

- [ ] **Step 4: Run the test to confirm it passes**

Run: `cd frontend && npx vitest run src/utils/__tests__/avatarCrop.spec.ts`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/utils/avatarCrop.ts frontend/src/utils/__tests__/avatarCrop.spec.ts
git commit -m "feat(avatar): pure crop geometry functions"
```

---

## Task 6: Frontend — `api/auth.ts` additions

**Files:**
- Modify: `frontend/src/api/auth.ts`

**Interfaces:**
- Consumes: backend `POST/DELETE /auth/avatar` (Task 4).
- Produces: `uploadAvatar(blob: Blob): Promise<User>`, `removeAvatar(): Promise<User>`. `User.avatar_url?: string | null`. Task 8 (`AccountSettings.vue`) and Task 7 (`UserAvatar.vue`) both depend on `User.avatar_url` existing with this exact name.

- [ ] **Step 1: Add `avatar_url` to the `User` interface**

In `frontend/src/api/auth.ts`, update the `User` interface (currently lines 12-21):

```typescript
export interface User {
  id: string;
  fullname: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string;
  avatar_url?: string | null;
}
```

- [ ] **Step 2: Add `uploadAvatar` and `removeAvatar`**

Add these functions right after `changeFullname` (after its closing `}` around line 184):

```typescript
/**
 * Upload (or replace) the current user's profile photo
 * @param blob Cropped image blob (JPEG)
 * @returns Updated user data
 */
export async function uploadAvatar(blob: Blob): Promise<User> {
  const formData = new FormData();
  formData.append('file', blob, 'avatar.jpg');
  const response = await apiClient.post<ApiResponse<User>>('/auth/avatar', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data.data;
}

/**
 * Remove the current user's profile photo
 * @returns Updated user data
 */
export async function removeAvatar(): Promise<User> {
  const response = await apiClient.delete<ApiResponse<User>>('/auth/avatar');
  return response.data.data;
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/auth.ts
git commit -m "feat(avatar): uploadAvatar/removeAvatar API calls"
```

---

## Task 7: Frontend — shared `UserAvatar.vue` component

**Files:**
- Create: `frontend/src/components/UserAvatar.vue`

**Interfaces:**
- Consumes: nothing external — pure presentational component.
- Produces: `<UserAvatar :avatar-url="..." :fallback-letter="..." :size="64" />`. Task 9 swaps this into all four existing avatar call sites with these exact prop names.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/UserAvatar.vue`:

```vue
<template>
  <div
    class="relative flex items-center justify-center font-bold flex-shrink-0 rounded-full overflow-hidden"
    :style="circleStyle"
  >
    <img
      v-if="avatarUrl && !imageFailed"
      :src="avatarUrl"
      :alt="fallbackLetter"
      class="w-full h-full object-cover"
      @error="imageFailed = true"
    >
    <template v-else>{{ fallbackLetter }}</template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';

const props = defineProps<{
  avatarUrl?: string | null;
  fallbackLetter: string;
  size: number;
}>();

// Reset the failed-image fallback whenever the URL itself changes (e.g. the
// user uploads a new photo after a previous one 404'd for some reason).
const imageFailed = ref(false);
watch(() => props.avatarUrl, () => { imageFailed.value = false; });

const circleStyle = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  fontSize: `${Math.round(props.size / 2)}px`,
  color: 'rgba(255, 255, 255, 0.9)',
  backgroundColor: 'rgb(59, 130, 246)',
}));
</script>
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/UserAvatar.vue
git commit -m "feat(avatar): shared UserAvatar component with initials fallback"
```

---

## Task 8: Frontend — swap `UserAvatar` into the four existing call sites

**Files:**
- Modify: `frontend/src/components/settings/AccountSettings.vue:6-11`
- Modify: `frontend/src/components/settings/SettingsTabs.vue:174-179`
- Modify: `frontend/src/components/UserMenu.vue:9-11`
- Modify: `frontend/src/components/SessionSidebar.vue:415-419`

**Interfaces:**
- Consumes: `UserAvatar.vue` (Task 7), `currentUser.value.avatar_url` (Task 6's `User` type).

Each of these four already has an `avatarLetter` computed and a `currentUser` from `useAuth()`. Only the template markup changes — the `avatarLetter` computed can stay (it's now the `fallback-letter` prop) or be removed if unused elsewhere in that file; check each file for other uses before deleting it.

- [ ] **Step 1: `AccountSettings.vue`**

Add the import (near the other component/composable imports in `<script setup>`):

```typescript
import UserAvatar from '@/components/UserAvatar.vue'
```

Replace lines 6-11:

```vue
<UserAvatar :avatar-url="currentUser?.avatar_url" :fallback-letter="avatarLetter" :size="64" />
```

- [ ] **Step 2: `SettingsTabs.vue`**

Add the import next to its other component imports, then replace lines 174-179:

```vue
<UserAvatar :avatar-url="currentUser?.avatar_url" :fallback-letter="avatarLetter" :size="28" />
```

- [ ] **Step 3: `UserMenu.vue`**

Add the import, then replace lines 9-11:

```vue
<UserAvatar :avatar-url="currentUser?.avatar_url" :fallback-letter="avatarLetter" :size="48" />
```

- [ ] **Step 4: `SessionSidebar.vue`**

Add the import, then replace lines 415-419:

```vue
<UserAvatar :avatar-url="currentUser?.avatar_url" :fallback-letter="avatarLetter" :size="28" />
```

- [ ] **Step 5: Verify everything still builds and type-checks**

Run: `cd frontend && npx vue-tsc --noEmit && npm run lint`
Expected: no new errors/warnings beyond the pre-existing `no-explicit-any` warnings already in these files.

- [ ] **Step 6: Manual visual check in the browser**

With the dev stack running (`./dev.sh up -d`), open `http://localhost:5173`, and confirm the initials circle still renders correctly (no `avatar_url` set yet) in: the sidebar bottom-left user row, the user menu popup (click it), Settings → the sidebar user card, and Settings → Account's large circle. All four should look pixel-identical to before this task (same size, same letter, same blue background) — this task is a pure refactor, not a behavior change, until Task 9 adds real photos.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/settings/AccountSettings.vue frontend/src/components/settings/SettingsTabs.vue frontend/src/components/UserMenu.vue frontend/src/components/SessionSidebar.vue
git commit -m "refactor(avatar): use shared UserAvatar component in all 4 call sites"
```

---

## Task 9: Frontend — `AvatarCropDialog.vue`

**Files:**
- Create: `frontend/src/components/settings/AvatarCropDialog.vue`

**Interfaces:**
- Consumes: `fitCoverScale`, `clampOffset`, `computeCropSourceRect` (Task 5, exact names).
- Produces: `<AvatarCropDialog :file="pickedFile" @saved="(blob: Blob) => ..." @cancel="..." />`. Task 10 (`AccountSettings.vue`) mounts this with these exact prop/event names.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/settings/AvatarCropDialog.vue`:

```vue
<template>
  <div class="absolute inset-0 z-[1000] pointer-events-auto">
    <div class="w-full h-full bg-black/60 backdrop-blur-[4px] fixed inset-0" @click="emit('cancel')" />
    <div
      role="dialog"
      class="shadow-menu pointer-events-auto fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[360px] max-w-[95%] flex flex-col rounded-[20px] bg-[var(--background-menu-white)]"
    >
      <h3 class="flex items-center justify-between border-b border-b-[var(--border-main)] pt-5 pe-3 pb-[18px] ps-5 shrink-0">
        <span class="text-[16px] font-medium text-[var(--text-primary)]">{{ t('Adjust photo') }}</span>
        <button
          type="button"
          class="flex h-7 w-7 items-center justify-center cursor-pointer rounded-md hover:bg-[var(--fill-tsp-white-light)]"
          @click="emit('cancel')"
        >
          <X class="size-5 text-[var(--icon-tertiary)]" />
        </button>
      </h3>

      <div class="p-5 flex flex-col items-center gap-4">
        <div
          ref="viewportRef"
          class="relative overflow-hidden rounded-full bg-black cursor-grab active:cursor-grabbing"
          :style="{ width: `${VIEWPORT_SIZE}px`, height: `${VIEWPORT_SIZE}px` }"
          @mousedown="startDrag"
        >
          <img
            v-if="imageUrl"
            ref="imageRef"
            :src="imageUrl"
            class="absolute select-none pointer-events-none"
            :style="imageStyle"
            @load="onImageLoad"
            draggable="false"
          >
        </div>

        <div class="w-full flex items-center gap-3">
          <span class="text-[13px] text-[var(--text-tertiary)]">{{ t('Zoom') }}</span>
          <input
            type="range"
            min="1"
            max="3"
            step="0.01"
            v-model.number="zoom"
            class="flex-1"
            @input="onZoomChange"
          >
        </div>

        <div class="w-full flex justify-end gap-2">
          <button
            type="button"
            class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 outline outline-1 -outline-offset-1 hover:bg-[var(--fill-tsp-white-light)] text-[var(--text-primary)] outline-[var(--border-btn-main)] bg-transparent h-[32px]"
            @click="emit('cancel')"
          >
            {{ t('Cancel') }}
          </button>
          <button
            type="button"
            :disabled="!imageLoaded"
            class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 bg-[var(--text-primary)] text-[var(--background-gray-main)] h-[32px] disabled:opacity-50"
            @click="save"
          >
            {{ t('Save') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue';
import { useI18n } from 'vue-i18n';
import { X } from 'lucide-vue-next';
import { fitCoverScale, clampOffset, computeCropSourceRect } from '@/utils/avatarCrop';

const props = defineProps<{ file: File }>();
const emit = defineEmits<{ saved: [blob: Blob]; cancel: [] }>();

const { t } = useI18n();

const VIEWPORT_SIZE = 280;
const OUTPUT_SIZE = 512;

const imageUrl = ref<string>('');
const imageRef = ref<HTMLImageElement | null>(null);
const viewportRef = ref<HTMLDivElement | null>(null);
const imageLoaded = ref(false);
const naturalWidth = ref(0);
const naturalHeight = ref(0);
const zoom = ref(1);
const offsetX = ref(0);
const offsetY = ref(0);

imageUrl.value = URL.createObjectURL(props.file);
onBeforeUnmount(() => URL.revokeObjectURL(imageUrl.value));

const baseScale = computed(() =>
  naturalWidth.value ? fitCoverScale(naturalWidth.value, naturalHeight.value, VIEWPORT_SIZE) : 1,
);
const displayedWidth = computed(() => naturalWidth.value * baseScale.value * zoom.value);
const displayedHeight = computed(() => naturalHeight.value * baseScale.value * zoom.value);

const imageStyle = computed(() => ({
  width: `${displayedWidth.value}px`,
  height: `${displayedHeight.value}px`,
  transform: `translate(${offsetX.value}px, ${offsetY.value}px)`,
}));

const onImageLoad = () => {
  const img = imageRef.value;
  if (!img) return;
  naturalWidth.value = img.naturalWidth;
  naturalHeight.value = img.naturalHeight;
  // Center the image in the viewport at zoom=1.
  offsetX.value = (VIEWPORT_SIZE - naturalWidth.value * baseScale.value) / 2;
  offsetY.value = (VIEWPORT_SIZE - naturalHeight.value * baseScale.value) / 2;
  imageLoaded.value = true;
};

const clampCurrentOffset = () => {
  const clamped = clampOffset({
    offsetX: offsetX.value,
    offsetY: offsetY.value,
    displayedWidth: displayedWidth.value,
    displayedHeight: displayedHeight.value,
    viewportSize: VIEWPORT_SIZE,
  });
  offsetX.value = clamped.x;
  offsetY.value = clamped.y;
};

const onZoomChange = () => clampCurrentOffset();

let dragging = false;
let dragStartX = 0;
let dragStartY = 0;
let dragOriginX = 0;
let dragOriginY = 0;

const startDrag = (e: MouseEvent) => {
  dragging = true;
  dragStartX = e.clientX;
  dragStartY = e.clientY;
  dragOriginX = offsetX.value;
  dragOriginY = offsetY.value;
  window.addEventListener('mousemove', onDrag);
  window.addEventListener('mouseup', stopDrag);
};

const onDrag = (e: MouseEvent) => {
  if (!dragging) return;
  offsetX.value = dragOriginX + (e.clientX - dragStartX);
  offsetY.value = dragOriginY + (e.clientY - dragStartY);
  clampCurrentOffset();
};

const stopDrag = () => {
  dragging = false;
  window.removeEventListener('mousemove', onDrag);
  window.removeEventListener('mouseup', stopDrag);
};

onBeforeUnmount(stopDrag);

const save = () => {
  const img = imageRef.value;
  if (!img || !imageLoaded.value) return;
  const rect = computeCropSourceRect({
    imageWidth: naturalWidth.value,
    imageHeight: naturalHeight.value,
    viewportSize: VIEWPORT_SIZE,
    offsetX: offsetX.value,
    offsetY: offsetY.value,
    zoom: zoom.value,
  });
  const canvas = document.createElement('canvas');
  canvas.width = OUTPUT_SIZE;
  canvas.height = OUTPUT_SIZE;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.drawImage(img, rect.sx, rect.sy, rect.sSize, rect.sSize, 0, 0, OUTPUT_SIZE, OUTPUT_SIZE);
  canvas.toBlob((blob) => {
    if (blob) emit('saved', blob);
  }, 'image/jpeg', 0.9);
};
</script>
```

- [ ] **Step 2: Type-check and lint**

Run: `cd frontend && npx vue-tsc --noEmit && npm run lint`
Expected: no new errors. (`lucide-vue-next`'s `X` icon is already used elsewhere in the codebase, e.g. `LibraryPickerDialog.vue` — confirm the import path matches what that file uses if `vue-tsc` complains.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/settings/AvatarCropDialog.vue
git commit -m "feat(avatar): crop dialog (drag to pan, slider to zoom)"
```

---

## Task 10: Frontend — wire upload/remove into `AccountSettings.vue`

**Files:**
- Modify: `frontend/src/components/settings/AccountSettings.vue`

**Interfaces:**
- Consumes: `uploadAvatar`, `removeAvatar` (Task 6), `AvatarCropDialog.vue` (Task 9), `useAuth().loadCurrentUser` (existing — already used by `updateFullname`).

- [ ] **Step 1: Add file-picker + change/remove buttons next to the avatar**

Replace the avatar block (currently lines 6-11, already updated to `<UserAvatar>` in Task 8) with:

```vue
<div class="flex flex-col items-start gap-2">
  <UserAvatar :avatar-url="currentUser?.avatar_url" :fallback-letter="avatarLetter" :size="64" />
  <div class="flex gap-2">
    <button
      type="button"
      class="text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] clickable"
      @click="triggerFilePicker"
    >
      {{ t('Change photo') }}
    </button>
    <button
      v-if="currentUser?.avatar_url"
      type="button"
      class="text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] clickable"
      @click="handleRemoveAvatar"
    >
      {{ t('Remove photo') }}
    </button>
  </div>
  <input
    ref="fileInputRef"
    type="file"
    accept="image/jpeg,image/png,image/webp"
    class="hidden"
    @change="onFilePicked"
  >
</div>

<AvatarCropDialog
  v-if="pickedFile"
  :file="pickedFile"
  @saved="handleCropSaved"
  @cancel="pickedFile = null"
/>
```

- [ ] **Step 2: Add the script logic**

Add these imports to the existing `<script setup>` import block:

```typescript
import UserAvatar from '@/components/UserAvatar.vue'
import AvatarCropDialog from './AvatarCropDialog.vue'
import { uploadAvatar, removeAvatar } from '@/api/auth'
```

Add these refs and handlers, near the other refs (`localFullname`, `copied`):

```typescript
const fileInputRef = ref<HTMLInputElement | null>(null)
const pickedFile = ref<File | null>(null)

const MAX_AVATAR_BYTES = 5 * 1024 * 1024
const ALLOWED_AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp']

const triggerFilePicker = () => {
  fileInputRef.value?.click()
}

const onFilePicked = (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // allow picking the same file again later
  if (!file) return
  if (!ALLOWED_AVATAR_TYPES.includes(file.type)) {
    showErrorToast(t('Please choose a JPEG, PNG, or WebP image.'))
    return
  }
  if (file.size > MAX_AVATAR_BYTES) {
    showErrorToast(t('Image must be 5MB or smaller.'))
    return
  }
  pickedFile.value = file
}

const handleCropSaved = async (blob: Blob) => {
  pickedFile.value = null
  try {
    await uploadAvatar(blob)
    await loadCurrentUser()
    showSuccessToast(t('Profile photo updated'))
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    showErrorToast(err?.response?.data?.message || err?.message || t('Failed to update profile photo'))
  }
}

const handleRemoveAvatar = async () => {
  try {
    await removeAvatar()
    await loadCurrentUser()
    showSuccessToast(t('Profile photo removed'))
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    showErrorToast(err?.response?.data?.message || err?.message || t('Failed to remove profile photo'))
  }
}
```

- [ ] **Step 3: Add the new i18n keys**

In `frontend/src/locales/en.ts`, add these right after the existing `'Full name updated successfully': 'Full name updated successfully',` line (line 397):

```typescript
  'Change photo': 'Change photo',
  'Remove photo': 'Remove photo',
  'Adjust photo': 'Adjust photo',
  'Zoom': 'Zoom',
  'Profile photo updated': 'Profile photo updated',
  'Profile photo removed': 'Profile photo removed',
  'Failed to update profile photo': 'Failed to update profile photo',
  'Failed to remove profile photo': 'Failed to remove profile photo',
  'Please choose a JPEG, PNG, or WebP image.': 'Please choose a JPEG, PNG, or WebP image.',
  'Image must be 5MB or smaller.': 'Image must be 5MB or smaller.',
```

In `frontend/src/locales/pt.ts`, add after the equivalent `'Full name updated successfully'` line:

```typescript
  'Change photo': 'Trocar foto',
  'Remove photo': 'Remover foto',
  'Adjust photo': 'Ajustar foto',
  'Zoom': 'Zoom',
  'Profile photo updated': 'Foto de perfil atualizada',
  'Profile photo removed': 'Foto de perfil removida',
  'Failed to update profile photo': 'Falha ao atualizar a foto de perfil',
  'Failed to remove profile photo': 'Falha ao remover a foto de perfil',
  'Please choose a JPEG, PNG, or WebP image.': 'Escolha uma imagem JPEG, PNG ou WebP.',
  'Image must be 5MB or smaller.': 'A imagem deve ter no máximo 5MB.',
```

In `frontend/src/locales/zh.ts`, add after the equivalent line:

```typescript
  'Change photo': '更换照片',
  'Remove photo': '移除照片',
  'Adjust photo': '调整照片',
  'Zoom': '缩放',
  'Profile photo updated': '头像已更新',
  'Profile photo removed': '头像已移除',
  'Failed to update profile photo': '更新头像失败',
  'Failed to remove profile photo': '移除头像失败',
  'Please choose a JPEG, PNG, or WebP image.': '请选择 JPEG、PNG 或 WebP 格式的图片。',
  'Image must be 5MB or smaller.': '图片大小不能超过 5MB。',
```

- [ ] **Step 4: Run the locale consistency test**

Run: `cd frontend && npx vitest run src/locales/__tests__/locales.spec.ts`
Expected: PASS (this test asserts all three locale files have identical key sets — see `frontend/src/locales/__tests__/locales.spec.ts` for what it checks).

- [ ] **Step 5: Type-check, lint, full test suite, build**

Run: `cd frontend && npx vue-tsc --noEmit && npm run lint && npm run test -- --run && npm run build`
Expected: no new type errors, no new lint errors, all tests pass, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/settings/AccountSettings.vue frontend/src/locales/en.ts frontend/src/locales/pt.ts frontend/src/locales/zh.ts
git commit -m "feat(avatar): wire upload/crop/remove into Settings > Account"
```

---

## Task 11: End-to-end manual verification

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite**

Run: `cd backend && uv run pytest`
Expected: same baseline pass/fail counts as before this feature, plus all new avatar tests passing.

- [ ] **Step 2: Full frontend suite**

Run: `cd frontend && npm run test -- --run && npm run type-check && npm run lint && npm run build`
Expected: all green.

- [ ] **Step 3: Live browser walkthrough**

With `./dev.sh up -d`, open `http://localhost:5173`, log in, go to Settings → Account:

1. Click "Change photo", pick a JPEG/PNG. The crop dialog opens with the image centered.
2. Drag the image around — it should never show blank space inside the circle.
3. Move the zoom slider — the image should scale up smoothly, still clamped so it always covers the circle.
4. Click "Save". The dialog closes, a success toast appears, and the 64px circle in Account settings now shows the cropped photo.
5. Check the other three locations without reloading: open the user menu (bottom-left), open Settings again and look at the sidebar user card — both should already show the new photo (no refresh needed, since `loadCurrentUser()` updates the shared `currentUser` ref every avatar-rendering component reads).
6. Reload the page fully. The photo should still be there (persisted, not just optimistic local state).
7. Click "Remove photo". All four locations revert to the initials circle immediately.
8. Try uploading a non-image file (e.g. a `.txt` renamed to `.jpg` won't trigger this — actually pick a real non-image via the file picker if your OS allows `accept` override, or temporarily comment out the `accept` attribute to test the server-side 400 path) and confirm a clear error toast appears, not a silent failure or crash.

- [ ] **Step 4: Confirm no regressions in existing avatar-adjacent UI**

Reconfirm from Task 8 Step 6 that a user with NO avatar still renders the plain initials circle correctly, pixel-identical to before this feature, in all four locations.
