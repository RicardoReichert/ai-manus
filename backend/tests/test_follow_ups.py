"""Unit tests for TAREFA 5.2 — follow-up suggestions on the final message.

Pure unit tests against the domain/schema layer, no running server needed
(unlike most of this suite — see conftest.BASE_URL for the integration
tests).
"""
from app.domain.models.agent_output import FinalResult
from app.domain.models.event import MessageEvent
from app.interfaces.schemas.event import EventMapper, MessageStreamEvent


class TestFinalResultFollowUps:
    def test_defaults_to_empty_list(self):
        result = FinalResult(message="done")
        assert result.follow_ups == []

    def test_round_trips_provided_suggestions(self):
        result = FinalResult(message="done", follow_ups=["Add a chart", "Deploy it"])
        assert result.follow_ups == ["Add a chart", "Deploy it"]


class TestMessageEventFollowUps:
    def test_defaults_to_none(self):
        event = MessageEvent(message="done")
        assert event.follow_ups is None


class TestEventMapperFollowUps:
    async def test_follow_ups_pass_through_to_wire_format(self):
        event = MessageEvent(
            role="assistant", message="done", follow_ups=["Add a chart", "Deploy it"]
        )
        stream_event = await EventMapper.event_to_stream_event(event)
        assert isinstance(stream_event, MessageStreamEvent)
        assert stream_event.data.follow_ups == ["Add a chart", "Deploy it"]

    async def test_no_follow_ups_serializes_as_none(self):
        event = MessageEvent(role="assistant", message="done")
        stream_event = await EventMapper.event_to_stream_event(event)
        assert isinstance(stream_event, MessageStreamEvent)
        assert stream_event.data.follow_ups is None

    async def test_intermediate_step_messages_are_unaffected(self):
        """Only the final summarize() message ever sets follow_ups — a plain
        role='assistant' MessageEvent mid-task (e.g. message_ask_user) must
        not accidentally pick one up from somewhere."""
        event = MessageEvent(role="assistant", message="Which format do you prefer?")
        stream_event = await EventMapper.event_to_stream_event(event)
        assert stream_event.data.follow_ups is None
