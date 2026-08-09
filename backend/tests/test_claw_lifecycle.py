"""Unit tests for Claw session lifecycle: container cleanup, expiry, restart.

Verifies that ``ClawDomainService`` destroys the underlying runtime instance
(the Docker container) when a session expires, is deleted, or fails to
provision — and, the core guarantee of the session model, that expiry and
restart never touch a session's volume or its Mongo record, only deletion
does. Sessions are durable; containers are disposable.
"""
from datetime import datetime, timedelta, UTC
from typing import Optional, List

import pytest

from app.domain.models.claw import ClawSession, ClawStatus, ClawMessage, ClawAttachment
from app.domain.external.claw import ClawInstanceInfo
from app.domain.services.claw_domain_service import ClawDomainService


class FakeClawSessionRepository:
    def __init__(self, session: Optional[ClawSession] = None):
        self.session = session
        self.deleted_ids: list[str] = []
        self.messages: list[tuple] = []

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
        if not self.session or self.session.id != session_id:
            return False
        self.deleted_ids.append(session_id)
        self.session = None
        return True

    async def get_messages(self, session_id: str) -> List[ClawMessage]:
        return []

    async def append_message(
        self, session_id: str, role: str, content: str = "",
        attachments: Optional[List[ClawAttachment]] = None,
    ) -> None:
        self.messages.append((session_id, role, content))

    async def clear_messages(self, session_id: str) -> None:
        pass


class FakeClawRuntime:
    creates_immediately = False

    def __init__(self, fail_create: bool = False, ready: bool = True):
        self.fail_create = fail_create
        self.ready = ready
        self.destroyed: list[Optional[str]] = []
        self.destroyed_volumes: list[Optional[str]] = []

    async def create(self, session_id: str, api_key: str, volume_name: str) -> ClawInstanceInfo:
        if self.fail_create:
            raise RuntimeError("boom")
        return ClawInstanceInfo(address="10.0.0.5", instance_name=f"manus-claw-{session_id[:8]}")

    async def destroy(self, instance_name: Optional[str]) -> None:
        self.destroyed.append(instance_name)

    async def destroy_volume(self, volume_name: Optional[str]) -> None:
        self.destroyed_volumes.append(volume_name)

    async def wait_for_ready(self, base_url: str) -> bool:
        return self.ready


class FakeClawClient:
    async def get_history(self, base_url, session_id, limit=200):
        return []

    async def get_file(self, base_url, filename):
        return b"", "application/octet-stream"

    def chat_stream(self, base_url, message, session_id):
        raise NotImplementedError


def _make_session(**overrides) -> ClawSession:
    defaults = dict(
        id="claw-1234-abcd",
        user_id="user-1",
        model_id="gpt-4o",
        volume_name="claw-session-vol-claw1234",
        api_key="manus-testkey",
        status=ClawStatus.RUNNING,
        container_name="manus-claw-claw1234",
        container_ip="10.0.0.5",
    )
    defaults.update(overrides)
    return ClawSession(**defaults)


class TestExpiry:
    async def test_expired_session_stops_the_container(self):
        session = _make_session(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        repo = FakeClawSessionRepository(session)
        runtime = FakeClawRuntime()
        service = ClawDomainService(repo, runtime, FakeClawClient())

        result = await service.get_session("user-1", "claw-1234-abcd")

        assert result.status == ClawStatus.STOPPED
        assert runtime.destroyed == ["manus-claw-claw1234"]

    async def test_expiry_never_deletes_the_record_or_the_volume(self):
        """The core session/container split: expiry is a container event,
        never a session event. Only explicit delete removes either."""
        session = _make_session(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        repo = FakeClawSessionRepository(session)
        runtime = FakeClawRuntime()
        service = ClawDomainService(repo, runtime, FakeClawClient())

        await service.get_session("user-1", "claw-1234-abcd")

        assert repo.deleted_ids == []
        assert runtime.destroyed_volumes == []
        assert repo.session is not None

    async def test_expired_session_still_appears_in_the_list(self):
        session = _make_session(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        repo = FakeClawSessionRepository(session)
        service = ClawDomainService(repo, FakeClawRuntime(), FakeClawClient())

        sessions = await service.list_sessions("user-1")

        assert len(sessions) == 1
        assert sessions[0].status == ClawStatus.STOPPED


class TestDelete:
    async def test_delete_session_destroys_container_and_volume(self):
        session = _make_session(container_ip=None)  # skip live health check
        repo = FakeClawSessionRepository(session)
        runtime = FakeClawRuntime()
        service = ClawDomainService(repo, runtime, FakeClawClient())

        deleted = await service.delete_session("user-1", "claw-1234-abcd")

        assert deleted is True
        assert runtime.destroyed == ["manus-claw-claw1234"]
        assert runtime.destroyed_volumes == ["claw-session-vol-claw1234"]
        assert repo.deleted_ids == ["claw-1234-abcd"]

    async def test_delete_without_a_matching_session_is_noop(self):
        repo = FakeClawSessionRepository(None)
        runtime = FakeClawRuntime()
        service = ClawDomainService(repo, runtime, FakeClawClient())

        deleted = await service.delete_session("user-1", "does-not-exist")

        assert deleted is False
        assert runtime.destroyed == []
        assert runtime.destroyed_volumes == []

    async def test_cannot_delete_another_users_session(self):
        session = _make_session(user_id="user-1", container_ip=None)
        repo = FakeClawSessionRepository(session)
        runtime = FakeClawRuntime()
        service = ClawDomainService(repo, runtime, FakeClawClient())

        deleted = await service.delete_session("someone-else", "claw-1234-abcd")

        assert deleted is False
        assert runtime.destroyed == []


class TestProvision:
    async def test_provision_failure_destroys_the_container(self):
        session = _make_session(status=ClawStatus.CREATING, container_name=None, container_ip=None)
        repo = FakeClawSessionRepository(session)
        runtime = FakeClawRuntime(ready=False)  # created but never becomes healthy
        service = ClawDomainService(repo, runtime, FakeClawClient())

        await service.provision_session(session, ttl_seconds=3600)

        assert session.status == ClawStatus.ERROR
        assert runtime.destroyed == ["manus-claw-claw-123"]
        assert session.container_name is None
        assert session.container_ip is None

    async def test_provision_success_sets_expiry_from_start_time(self):
        session = _make_session(status=ClawStatus.CREATING, container_name=None, container_ip=None)
        repo = FakeClawSessionRepository(session)
        runtime = FakeClawRuntime(ready=True)
        service = ClawDomainService(repo, runtime, FakeClawClient())

        before = datetime.now(UTC)
        await service.provision_session(session, ttl_seconds=3600)
        after = datetime.now(UTC)

        assert session.status == ClawStatus.RUNNING
        assert runtime.destroyed == []
        # expires_at must be anchored at provisioning start, not at readiness,
        # so the DB record never outlives the container's own TTL clock.
        assert before + timedelta(seconds=3600) <= session.expires_at <= after + timedelta(seconds=3600)


class TestRestart:
    async def test_restart_reuses_the_same_volume(self):
        """The whole point: switching models must never touch the volume
        that carries OpenClaw's native memory."""
        # No container_ip: skips the live health check inside get_session()
        # for a fake, otherwise-unreachable IP — irrelevant to what this
        # test verifies and would just add a real network timeout.
        session = _make_session(model_id="gpt-4o", container_ip=None)
        repo = FakeClawSessionRepository(session)
        runtime = FakeClawRuntime()
        service = ClawDomainService(repo, runtime, FakeClawClient())

        updated = await service.restart_session("user-1", "claw-1234-abcd", "gemini-2.5-flash")

        assert updated.volume_name == "claw-session-vol-claw1234"
        assert runtime.destroyed_volumes == []

    async def test_restart_destroys_the_old_container(self):
        session = _make_session(container_name="manus-claw-claw1234", container_ip=None)
        repo = FakeClawSessionRepository(session)
        runtime = FakeClawRuntime()
        service = ClawDomainService(repo, runtime, FakeClawClient())

        await service.restart_session("user-1", "claw-1234-abcd", "gemini-2.5-flash")

        assert runtime.destroyed == ["manus-claw-claw1234"]

    async def test_restart_updates_the_pinned_model(self):
        session = _make_session(model_id="gpt-4o", container_ip=None)
        repo = FakeClawSessionRepository(session)
        service = ClawDomainService(repo, FakeClawRuntime(), FakeClawClient())

        updated = await service.restart_session("user-1", "claw-1234-abcd", "gemini-2.5-flash")

        assert updated.model_id == "gemini-2.5-flash"
        assert repo.session.model_id == "gemini-2.5-flash"

    async def test_restart_without_a_matching_session_returns_none(self):
        repo = FakeClawSessionRepository(None)
        service = ClawDomainService(repo, FakeClawRuntime(), FakeClawClient())

        result = await service.restart_session("user-1", "does-not-exist", "gpt-4o")

        assert result is None

    async def test_restart_of_a_never_started_session_does_not_destroy_anything(self):
        """A CREATING session with no container yet — restart must not call
        destroy() with a None instance name in a way that breaks."""
        session = _make_session(status=ClawStatus.CREATING, container_name=None)
        repo = FakeClawSessionRepository(session)
        runtime = FakeClawRuntime()
        service = ClawDomainService(repo, runtime, FakeClawClient())

        await service.restart_session("user-1", "claw-1234-abcd", "gpt-4o")

        assert runtime.destroyed == []
