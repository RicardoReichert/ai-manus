"""Unit tests for the shell output cap.

Pure unit test on the bounded-append helper — no subprocess, no live shell
session. Guards against a long-running or highly verbose command growing
``active_shells[...]["output"]`` without bound.
"""
from app.services.shell import MAX_SHELL_OUTPUT_CHARS, _append_bounded


class TestAppendBounded:
    def test_under_limit_appends_normally(self):
        assert _append_bounded("hello ", "world") == "hello world"

    def test_empty_existing_appends_normally(self):
        assert _append_bounded("", "world") == "world"

    def test_over_limit_keeps_only_the_tail(self):
        result = _append_bounded("x" * 100, "y" * 50, limit=120)
        assert len(result) == 120
        assert result.endswith("y" * 50)

    def test_result_never_exceeds_the_limit(self):
        existing = ""
        for _ in range(500):
            existing = _append_bounded(existing, "chunk of output\n", limit=1000)
        assert len(existing) <= 1000

    def test_most_recent_output_is_preserved_over_oldest(self):
        """A live terminal scrollback keeps what just happened, not the
        earliest lines — matters most for a still-running command."""
        result = _append_bounded("OLDEST_DATA" * 100, "NEWEST_MARKER", limit=50)
        assert result.endswith("NEWEST_MARKER")

    def test_default_limit_matches_the_module_constant(self):
        result = _append_bounded("x" * (MAX_SHELL_OUTPUT_CHARS + 100), "y")
        assert len(result) == MAX_SHELL_OUTPUT_CHARS
