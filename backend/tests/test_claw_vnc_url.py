"""Unit tests for ``ClawService.get_vnc_url`` / ``ClawDomainService.get_vnc_url``.

Mirrors the main Manus sandbox's ``AgentService.get_vnc_url`` (see
``backend/app/application/services/agent_service.py``): builds a
``ws://<host>:5901`` URL from the session's container address, and never
returns another user's session.

Pure unit tests — no server, no Mongo, no Docker. Follows the fake-repository
mocking convention already used in ``test_claw_lifecycle.py`` and
``test_claw_shared_container_model_resolution.py``.
"""
from typing import List, Optional

import pytest

from app.domain.models.claw import ClawAttachment, ClawMessage, ClawSession, ClawStatus
from app.domain.services.claw_domain_service import ClawDomainService
from app.application.services.claw_service import ClawService


def _session(
    session_id: str = "sess-1",
    user_id: str = "user-1",
    container_ip: Optional[str] = "10.0.0.5",
    status: ClawStatus = ClawStatus.RUNNING,
) -> ClawSession:
    return ClawSession(
        id=session_id,
        user_id=user_id,
        model_id="some-model",
        volume_name=f"claw-session-vol-{session_id}",
        container_ip=container_ip,
        api_key="session-key",
        status=status,
    )


class FakeClawSessionRepository:
    def __init__(self, session: Optional[ClawSession] = None):
        self.session = session

    async def get_by_id(self, session_id: str) -> Optional[ClawSession]:
        return self.session if self.session and self.session.id == session_id else None

    async def list_by_user_id(self, user_id: str) -> List[ClawSession]:
        return [self.session] if self.session and self.session.user_id == user_id else []

    async def get_by_api_key(self, api_key: str) -> Optional[ClawSession]:
        return self.session if self.session and self.session.api_key == api_key else None

    async def create(self, session: ClawSession) -> ClawSession:
        self.session = session
        return session

    async def update(self, session: ClawSession) -> ClawSession:
        self.session = session
        return session

    async def delete_by_id(self, session_id: str) -> bool:
        return False

    async def get_messages(self, session_id: str) -> List[ClawMessage]:
        return []

    async def append_message(
        self, session_id: str, role: str, content: str = "",
        attachments: Optional[List[ClawAttachment]] = None,
    ) -> None:
        pass

    async def clear_messages(self, session_id: str) -> None:
        pass


class NoopClawRuntime:
    creates_immediately = False

    async def create(self, session_id, api_key, volume_name):
        raise NotImplementedError

    async def destroy(self, instance_name):
        pass

    async def destroy_volume(self, volume_name):
        pass

    async def wait_for_ready(self, base_url):
        return True


class NoopClawClient:
    async def get_history(self, base_url, session_id, limit):
        return []

    async def chat_stream(self, base_url, message, session_id):
        if False:
            yield {}

    async def get_file(self, base_url, filename):
        return b"", "application/octet-stream"


def _build_domain_service(session: Optional[ClawSession]) -> ClawDomainService:
    return ClawDomainService(
        claw_session_repository=FakeClawSessionRepository(session),
        claw_runtime=NoopClawRuntime(),
        claw_client=NoopClawClient(),
    )


@pytest.mark.asyncio
async def test_get_vnc_url_returns_ws_url_for_owned_session():
    session = _session(container_ip="10.0.0.5")
    domain = _build_domain_service(session)

    url = await domain.get_vnc_url("user-1", "sess-1")

    assert url == "ws://10.0.0.5:5901"


@pytest.mark.asyncio
async def test_get_vnc_url_via_application_service_matches_documented_signature():
    """``ClawService.get_vnc_url(session_id, user_id)`` — the exact order
    Task 5's WS proxy route is expected to call directly."""
    session = _session(container_ip="10.0.0.5")
    domain = _build_domain_service(session)
    service = ClawService(domain)

    url = await service.get_vnc_url("sess-1", "user-1")

    assert url == "ws://10.0.0.5:5901"


@pytest.mark.asyncio
async def test_get_vnc_url_raises_for_session_not_owned_by_caller():
    session = _session(session_id="sess-1", user_id="owner", container_ip="10.0.0.5")
    domain = _build_domain_service(session)

    with pytest.raises(ValueError):
        await domain.get_vnc_url("someone-else", "sess-1")


@pytest.mark.asyncio
async def test_get_vnc_url_raises_for_missing_session():
    domain = _build_domain_service(None)

    with pytest.raises(ValueError):
        await domain.get_vnc_url("user-1", "does-not-exist")


@pytest.mark.asyncio
async def test_get_vnc_url_raises_when_container_not_yet_provisioned():
    """A session that exists but has no container_ip yet (still CREATING)
    has no vnc_url — mirrors http_base_url's same-shaped None case."""
    session = _session(container_ip=None, status=ClawStatus.CREATING)
    domain = _build_domain_service(session)

    with pytest.raises(ValueError):
        await domain.get_vnc_url("user-1", "sess-1")
