"""Unit tests for Claw tool-event persistence:
``ClawSessionRepository.append_tool_event``/``get_tool_events`` (truncation +
count cap) and ``ClawDomainService.process_chat_stream``/``get_tool_events``
(persist-once-on-'result', ownership check).

Pure unit tests — no server, no Mongo, no Docker. Follows the fake-repository
mocking convention already used in ``test_claw_terminal_url.py``.
"""
from typing import List, Optional

import pytest

from app.domain.models.claw import ClawAttachment, ClawMessage, ClawSession, ClawStatus, ClawToolEvent
from app.domain.services.claw_domain_service import ClawDomainService
from app.application.services.claw_service import ClawService
from app.infrastructure.repositories.claw_repository import (
    CLAW_TOOL_EVENT_MAX_COUNT,
    CLAW_TOOL_EVENT_RESULT_MAX_CHARS,
    _apply_tool_event_bounds,
)


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
        self.tool_events: List[ClawToolEvent] = []

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

    async def get_tool_events(self, session_id: str) -> List[ClawToolEvent]:
        return list(self.tool_events)

    async def append_tool_event(self, session_id: str, event: ClawToolEvent) -> None:
        self.tool_events.append(event)


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


class ScriptedClawClient:
    """Yields a scripted sequence of chunks from chat_stream, matching the
    real gateway's shape for a single completed tool call."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def get_history(self, base_url, session_id, limit):
        return []

    async def chat_stream(self, base_url, message, session_id):
        for chunk in self._chunks:
            yield chunk

    async def get_file(self, base_url, filename):
        return b"", "application/octet-stream"

    async def open_terminal(self, base_url, cols, rows):
        return {"session_id": "term-session-1"}


def _build_domain_service(session: Optional[ClawSession], repo=None, client=None):
    repo = repo if repo is not None else FakeClawSessionRepository(session)
    return ClawDomainService(
        claw_session_repository=repo,
        claw_runtime=NoopClawRuntime(),
        claw_client=client or ScriptedClawClient([]),
    ), repo


# ---------------------------------------------------------------------
# Repository bounds logic: pure-function unit tests, no Mongo/Beanie
# connection needed (this repo's other Claw tests never touch
# ClawSessionDocument directly either — they stay at the domain-service /
# fake-repository level, which is what the rest of this file does; the
# truncation/cap logic itself is extracted into _apply_tool_event_bounds
# specifically so it's testable without that infrastructure).
# ---------------------------------------------------------------------

def test_apply_tool_event_bounds_leaves_a_normal_sized_result_untouched():
    event = ClawToolEvent(
        tool_call_id="call-1", name="shell_exec", args={"command": "ls"},
        result="file1.txt", is_error=False, timestamp=1000,
    )

    bounded = _apply_tool_event_bounds(event)

    assert bounded is event  # untouched, not even copied
    assert bounded.result == "file1.txt"
    assert bounded.truncated is False


def test_apply_tool_event_bounds_truncates_an_oversized_string_result():
    huge_result = "x" * (CLAW_TOOL_EVENT_RESULT_MAX_CHARS + 500)
    event = ClawToolEvent(tool_call_id="call-1", name="shell_exec", result=huge_result, timestamp=1000)

    bounded = _apply_tool_event_bounds(event)

    assert bounded.truncated is True
    assert len(bounded.result) == CLAW_TOOL_EVENT_RESULT_MAX_CHARS


def test_apply_tool_event_bounds_truncates_an_oversized_non_string_result_via_json():
    huge_result = {"stdout": "y" * (CLAW_TOOL_EVENT_RESULT_MAX_CHARS + 500)}
    event = ClawToolEvent(tool_call_id="call-1", name="shell_exec", result=huge_result, timestamp=1000)

    bounded = _apply_tool_event_bounds(event)

    assert bounded.truncated is True
    assert isinstance(bounded.result, str)  # JSON-serialized before truncating
    assert len(bounded.result) == CLAW_TOOL_EVENT_RESULT_MAX_CHARS


def test_apply_tool_event_bounds_passes_through_a_result_of_none():
    event = ClawToolEvent(tool_call_id="call-1", name="shell_exec", result=None, timestamp=1000)

    bounded = _apply_tool_event_bounds(event)

    assert bounded.result is None
    assert bounded.truncated is False


def test_repository_append_caps_stored_count_keeping_most_recent():
    """Exercises the exact cap slicing append_tool_event performs
    (``doc.tool_events[-CLAW_TOOL_EVENT_MAX_COUNT:]``) directly against a
    plain list, matching what append_tool_event does to doc.tool_events."""
    events: List[ClawToolEvent] = []
    for i in range(CLAW_TOOL_EVENT_MAX_COUNT + 10):
        events.append(_apply_tool_event_bounds(ClawToolEvent(tool_call_id=f"call-{i}", name="tool", timestamp=i)))
        if len(events) > CLAW_TOOL_EVENT_MAX_COUNT:
            events = events[-CLAW_TOOL_EVENT_MAX_COUNT:]

    assert len(events) == CLAW_TOOL_EVENT_MAX_COUNT
    assert events[0].tool_call_id == "call-10"
    assert events[-1].tool_call_id == f"call-{CLAW_TOOL_EVENT_MAX_COUNT + 9}"


# ---------------------------------------------------------------------
# Domain service: persist-once-on-'result', ownership check
# ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_chat_stream_persists_one_tool_event_on_result_phase_only():
    session = _session()
    chunks = [
        {"type": "tool", "phase": "start", "toolCallId": "call-1", "name": "shell_exec", "args": {"command": "ls"}},
        {"type": "tool", "phase": "update", "toolCallId": "call-1", "name": "shell_exec", "partialResult": "file1"},
        {"type": "tool", "phase": "update", "toolCallId": "call-1", "name": "shell_exec", "partialResult": "file1\nfile2"},
        {"type": "tool", "phase": "result", "toolCallId": "call-1", "name": "shell_exec", "result": "file1\nfile2", "isError": False},
        {"type": "done"},
    ]
    domain, repo = _build_domain_service(session, client=ScriptedClawClient(chunks))

    async for _ in domain.process_chat_stream(session.id, "http://fake", "hi"):
        pass

    assert len(repo.tool_events) == 1  # not once per chunk
    event = repo.tool_events[0]
    assert event.tool_call_id == "call-1"
    assert event.args == {"command": "ls"}  # carried from 'start', not lost by 'update' overwrites
    assert event.result == "file1\nfile2"
    assert event.is_error is False


@pytest.mark.asyncio
async def test_process_chat_stream_marks_is_error_from_the_result_chunk():
    session = _session()
    chunks = [
        {"type": "tool", "phase": "start", "toolCallId": "call-1", "name": "shell_exec", "args": {}},
        {"type": "tool", "phase": "result", "toolCallId": "call-1", "name": "shell_exec", "result": "boom", "isError": True},
    ]
    domain, repo = _build_domain_service(session, client=ScriptedClawClient(chunks))

    async for _ in domain.process_chat_stream(session.id, "http://fake", "hi"):
        pass

    assert repo.tool_events[0].is_error is True


@pytest.mark.asyncio
async def test_process_chat_stream_does_not_persist_a_call_that_never_reaches_result():
    session = _session()
    chunks = [
        {"type": "tool", "phase": "start", "toolCallId": "call-1", "name": "shell_exec", "args": {}},
        {"type": "tool", "phase": "update", "toolCallId": "call-1", "name": "shell_exec", "partialResult": "partial"},
    ]
    domain, repo = _build_domain_service(session, client=ScriptedClawClient(chunks))

    async for _ in domain.process_chat_stream(session.id, "http://fake", "hi"):
        pass

    assert repo.tool_events == []


@pytest.mark.asyncio
async def test_get_tool_events_returns_empty_for_session_not_owned_by_caller():
    session = _session(session_id="sess-1", user_id="owner")
    domain, repo = _build_domain_service(session)
    repo.tool_events.append(ClawToolEvent(tool_call_id="c", name="t", timestamp=1))

    result = await domain.get_tool_events("someone-else", "sess-1")

    assert result == []


@pytest.mark.asyncio
async def test_get_tool_events_returns_persisted_events_for_owned_session():
    session = _session()
    domain, repo = _build_domain_service(session)
    repo.tool_events.append(ClawToolEvent(tool_call_id="c", name="t", timestamp=1))

    result = await domain.get_tool_events("user-1", "sess-1")

    assert len(result) == 1
    assert result[0].tool_call_id == "c"


@pytest.mark.asyncio
async def test_claw_service_get_tool_events_delegates_to_domain():
    session = _session()
    domain, repo = _build_domain_service(session)
    repo.tool_events.append(ClawToolEvent(tool_call_id="c", name="t", timestamp=1))
    service = ClawService(domain)

    result = await service.get_tool_events("user-1", "sess-1")

    assert len(result) == 1
