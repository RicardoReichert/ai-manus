"""Unit tests for TAREFA 16.1 — search_messages() pure aggregation.

No running server needed — hits the domain function directly with
synthetic sessions. See test_search_routes.py for the integration-level
GET /search endpoint tests.
"""
from datetime import datetime, timedelta, timezone

from app.domain.models.event import MessageEvent
from app.domain.models.session import Session
from app.domain.services.search_messages import search_messages, build_snippet


def make_session(session_id: str, title: str, messages: list) -> Session:
    """messages: list of (role, text, minutes_ago) tuples."""
    now = datetime.now(timezone.utc)
    events = [
        MessageEvent(role=role, message=text, timestamp=now - timedelta(minutes=minutes_ago))
        for role, text, minutes_ago in messages
    ]
    return Session(id=session_id, user_id="u1", agent_id="a1", title=title, events=events)


class TestBuildSnippet:
    def test_returns_full_text_when_short(self):
        assert build_snippet("hello world", "world") == "hello world"

    def test_truncates_long_text_around_the_match_with_ellipses(self):
        text = "x" * 100 + "NEEDLE" + "y" * 100
        snippet = build_snippet(text, "needle", context=10)
        assert "NEEDLE" in snippet
        assert snippet.startswith("…")
        assert snippet.endswith("…")
        assert len(snippet) < len(text)

    def test_no_leading_ellipsis_when_match_is_at_the_start(self):
        text = "NEEDLE" + "y" * 200
        snippet = build_snippet(text, "needle", context=10)
        assert not snippet.startswith("…")
        assert snippet.endswith("…")


class TestSearchMessages:
    def test_empty_query_returns_nothing(self):
        sessions = [make_session("s1", "Trip planning", [("user", "Plan a trip to Japan", 5)])]
        assert search_messages(sessions, "   ") == []

    def test_matches_are_case_insensitive(self):
        sessions = [make_session("s1", "Trip planning", [("user", "Plan a Trip to Japan", 5)])]
        results = search_messages(sessions, "JAPAN")
        assert len(results) == 1
        assert results[0]["session_id"] == "s1"

    def test_no_match_returns_empty(self):
        sessions = [make_session("s1", "Trip planning", [("user", "Plan a trip to Japan", 5)])]
        assert search_messages(sessions, "quarterly report") == []

    def test_searches_across_multiple_sessions(self):
        sessions = [
            make_session("s1", "Trip", [("user", "Plan a trip to Japan", 10)]),
            make_session("s2", "Report", [("assistant", "Here is your quarterly report", 5)]),
        ]
        results = search_messages(sessions, "report")
        assert [r["session_id"] for r in results] == ["s2"]

    def test_results_sorted_newest_first(self):
        sessions = [
            make_session("s1", "Old", [("user", "budget review meeting", 100)]),
            make_session("s2", "New", [("user", "budget review notes", 5)]),
        ]
        results = search_messages(sessions, "budget")
        assert [r["session_id"] for r in results] == ["s2", "s1"]

    def test_respects_limit(self):
        sessions = [
            make_session(f"s{i}", f"Task {i}", [("user", "keyword match here", i)])
            for i in range(5)
        ]
        results = search_messages(sessions, "keyword", limit=2)
        assert len(results) == 2

    def test_each_result_has_session_title_snippet_and_message_at(self):
        sessions = [make_session("s1", "My Task", [("user", "find the treasure", 3)])]
        results = search_messages(sessions, "treasure")
        assert results[0]["session_title"] == "My Task"
        assert "treasure" in results[0]["snippet"].lower()
        assert isinstance(results[0]["message_at"], int)
