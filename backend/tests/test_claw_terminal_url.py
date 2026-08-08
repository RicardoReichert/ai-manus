"""Unit tests for ``ClawService.open_terminal`` / ``ClawDomainService.open_terminal``.

Pure unit tests — no server, no Mongo, no Docker. Follows the fake-repository
mocking convention already used in ``test_claw_lifecycle.py`` and
``test_claw_shared_container_model_resolution.py``.
"""
from typing import List, Optional
from unittest.mock import AsyncMock, patch

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

    async def open_terminal(self, base_url, cols, rows):
        return {"session_id": "term-session-1"}


def _build_domain_service(session: Optional[ClawSession]) -> ClawDomainService:
    return ClawDomainService(
        claw_session_repository=FakeClawSessionRepository(session),
        claw_runtime=NoopClawRuntime(),
        claw_client=NoopClawClient(),
    )


@pytest.mark.asyncio
async def test_open_terminal_returns_ws_url_and_session_id_for_owned_running_session():
    session = _session(container_ip="10.0.0.5")
    domain = _build_domain_service(session)

    # get_session()'s _check_expiry health-checks a RUNNING session's
    # http_base_url over real httpx before returning it; stub that out so
    # the test doesn't depend on 10.0.0.5:18788 being reachable (it isn't,
    # in CI or locally), which would otherwise flip the session to STOPPED
    # and mask the very case this test is meant to cover.
    with patch.object(ClawDomainService, "_health_check", AsyncMock(return_value=True)):
        ws_url, terminal_session_id = await domain.open_terminal("user-1", "sess-1")

    assert terminal_session_id == "term-session-1"
    assert ws_url == "ws://10.0.0.5:18788/terminal/term-session-1"


@pytest.mark.asyncio
async def test_open_terminal_via_application_service_matches_documented_signature():
    """``ClawService.open_terminal(user_id, session_id, cols, rows)`` — the
    exact order the terminal WS proxy route is expected to call directly."""
    session = _session(container_ip="10.0.0.5")
    domain = _build_domain_service(session)
    service = ClawService(domain)

    with patch.object(ClawDomainService, "_health_check", AsyncMock(return_value=True)):
        ws_url, terminal_session_id = await service.open_terminal("user-1", "sess-1")

    assert terminal_session_id == "term-session-1"
    assert ws_url == "ws://10.0.0.5:18788/terminal/term-session-1"


@pytest.mark.asyncio
async def test_open_terminal_raises_for_session_not_owned_by_caller():
    session = _session(session_id="sess-1", user_id="owner", container_ip="10.0.0.5")
    domain = _build_domain_service(session)

    with pytest.raises(ValueError):
        await domain.open_terminal("someone-else", "sess-1")


@pytest.mark.asyncio
async def test_open_terminal_raises_for_stopped_session_with_stale_container_ip():
    """``_check_expiry`` marks a session STOPPED on a failed health check but
    only the expiry-timeout branch clears ``container_ip``, so a session
    whose container just died can still carry a non-None
    ``container_ip``/``terminal_ws_base_url``."""
    session = _session(container_ip="10.0.0.5", status=ClawStatus.STOPPED)
    domain = _build_domain_service(session)

    with pytest.raises(ValueError):
        await domain.open_terminal("user-1", "sess-1")
