"""Unit tests for filtering OpenClaw's "NO_REPLY" sentinel.

OpenClaw emits the literal string "NO_REPLY" as the entire assistant
message when the agent deliberately chooses not to respond (e.g. small
talk it judges doesn't warrant a reply) — not an error, but never meant to
reach the user verbatim. Reported as a real bug: a Claw session showed the
literal text "NO_REPLY" as the assistant's chat bubble after saying "oi".

Pure unit tests — no server, no Mongo, no Docker.
"""
from typing import AsyncIterator, List, Optional

import pytest

from app.domain.models.claw import ClawSession, ClawStatus, ClawMessage, ClawAttachment
from app.domain.services.claw_domain_service import ClawDomainService


class FakeClawSessionRepository:
    def __init__(self, session: Optional[ClawSession] = None, db_messages: Optional[List[ClawMessage]] = None):
        self.session = session
        self.db_messages = db_messages or []
        self.appended: list[tuple] = []

    async def get_by_id(self, session_id: str) -> Optional[ClawSession]:
        return self.session if self.session and self.session.id == session_id else None

    async def list_by_user_id(self, user_id: str) -> List[ClawSession]:
        return [self.session] if self.session and self.session.user_id == user_id else []

    async def get_by_api_key(self, api_key: str) -> Optional[ClawSession]:
        return None

    async def create(self, session: ClawSession) -> ClawSession:
        self.session = session
        return session

    async def update(self, session: ClawSession) -> ClawSession:
        self.session = session
        return session

    async def delete_by_id(self, session_id: str) -> bool:
        return False

    async def get_messages(self, session_id: str) -> List[ClawMessage]:
        return self.db_messages

    async def append_message(
        self, session_id: str, role: str, content: str = "",
        attachments: Optional[List[ClawAttachment]] = None,
    ) -> None:
        self.appended.append((session_id, role, content))

    async def clear_messages(self, session_id: str) -> None:
        pass


class FakeClawClient:
    def __init__(self, native_history: Optional[List[ClawMessage]] = None, chunks: Optional[List[dict]] = None):
        self.native_history = native_history or []
        self.chunks = chunks or []

    async def get_history(self, base_url, session_id, limit=200):
        return self.native_history

    async def get_file(self, base_url, filename):
        return b"", "application/octet-stream"

    async def chat_stream(self, base_url, message, session_id) -> AsyncIterator[dict]:
        for chunk in self.chunks:
            yield chunk


class FakeClawRuntime:
    creates_immediately = False

    async def create(self, session_id, api_key, volume_name):
        raise NotImplementedError

    async def destroy(self, instance_name):
        pass

    async def destroy_volume(self, volume_name):
        pass

    async def wait_for_ready(self, base_url):
        return True


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


class TestIsNoReply:
    def test_exact_match(self):
        assert ClawDomainService._is_no_reply("NO_REPLY") is True

    def test_match_with_surrounding_whitespace(self):
        assert ClawDomainService._is_no_reply("  NO_REPLY\n") is True

    def test_real_reply_is_not_flagged(self):
        assert ClawDomainService._is_no_reply("Hello there!") is False

    def test_reply_that_merely_contains_the_sentinel_is_not_flagged(self):
        assert ClawDomainService._is_no_reply("NO_REPLY, actually here's your answer") is False

    def test_empty_and_none_are_not_flagged(self):
        assert ClawDomainService._is_no_reply("") is False
        assert ClawDomainService._is_no_reply(None) is False


class TestProcessChatStreamFiltersNoReply:
    async def test_no_reply_is_not_persisted(self):
        repo = FakeClawSessionRepository()
        client = FakeClawClient(chunks=[{"type": "text", "content": "NO_REPLY"}, {"type": "done"}])
        service = ClawDomainService(repo, FakeClawRuntime(), client)

        chunks = [c async for c in service.process_chat_stream("sess-1", "http://x", "oi")]

        assert chunks == [{"type": "text", "content": "NO_REPLY"}, {"type": "done"}]
        assert repo.appended == []  # streamed to the client, but never persisted

    async def test_no_reply_split_across_chunks_is_still_caught(self):
        repo = FakeClawSessionRepository()
        client = FakeClawClient(chunks=[
            {"type": "text", "content": "NO_"},
            {"type": "text", "content": "REPLY"},
            {"type": "done"},
        ])
        service = ClawDomainService(repo, FakeClawRuntime(), client)

        [c async for c in service.process_chat_stream("sess-1", "http://x", "oi")]

        assert repo.appended == []

    async def test_real_reply_is_still_persisted(self):
        repo = FakeClawSessionRepository()
        client = FakeClawClient(chunks=[{"type": "text", "content": "Hi there!"}, {"type": "done"}])
        service = ClawDomainService(repo, FakeClawRuntime(), client)

        [c async for c in service.process_chat_stream("sess-1", "http://x", "oi")]

        assert repo.appended == [("sess-1", "assistant", "Hi there!")]


class TestGetHistoryFiltersNoReply:
    async def test_no_reply_dropped_from_db_messages(self):
        session = _make_session()
        db_msgs = [
            ClawMessage(role="user", content="oi", timestamp=100),
            ClawMessage(role="assistant", content="NO_REPLY", timestamp=101),
        ]
        repo = FakeClawSessionRepository(session=session, db_messages=db_msgs)
        service = ClawDomainService(repo, FakeClawRuntime(), FakeClawClient())

        history = await service.get_history("user-1", session.id)

        assert [m.content for m in history] == ["oi"]

    async def test_no_reply_dropped_from_native_claw_history(self, monkeypatch):
        # get_session live health-checks a RUNNING session's http_base_url;
        # stub it out so the fake in-memory session isn't marked STOPPED
        # (which would skip the native-history fetch this test exercises).
        monkeypatch.setattr(ClawDomainService, "_health_check", staticmethod(lambda base_url: _true()))

        session = _make_session()
        db_msgs = [ClawMessage(role="user", content="oi", timestamp=100)]
        native = [
            ClawMessage(role="user", content="oi", timestamp=100),
            ClawMessage(role="assistant", content="NO_REPLY", timestamp=101),
            ClawMessage(role="assistant", content="Hey!", timestamp=102),
        ]
        repo = FakeClawSessionRepository(session=session, db_messages=db_msgs)
        client = FakeClawClient(native_history=native)
        service = ClawDomainService(repo, FakeClawRuntime(), client)

        history = await service.get_history("user-1", session.id)

        assert [m.content for m in history] == ["oi", "Hey!"]


async def _true() -> bool:
    return True
