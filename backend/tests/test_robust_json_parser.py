"""Unit tests for RobustJsonParser's stage-0 text tool-call recovery.

Pure unit tests — AIMessage is constructed directly, no network call. This
is the fix for the observed failure mode where a small local model emits a
tool call as plain text/markdown instead of using the native tool_calls
channel, and the agent loop then nudges it in a loop until it exhausts
max_iterations (see domain/services/agents/base.py's
max_consecutive_no_tool_call_nudges for the companion bound on that loop).
"""
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage

from app.infrastructure.external.llm.robust_json_parser import (
    RobustJsonParser,
    ToolCallParseError,
    _extract_balanced_json_object,
    _extract_text_tool_call,
)


def _stub_llm() -> FakeListChatModel:
    """A real (minimal) Runnable chat model for OutputFixingParser's plumbing
    to bind to at construction time. Stage 0 recovers before stage 3 would
    ever call it, so its scripted response is never actually consumed by any
    of the tests below — if it were, that would itself be the bug."""
    return FakeListChatModel(responses=["stage 3 should not have been reached"])


def _parser(known_tools=("create_plan", "shell_exec")) -> RobustJsonParser:
    return RobustJsonParser.from_llm(_stub_llm(), known_tools=known_tools)


class TestExtractBalancedJsonObject:
    def test_simple_object(self):
        text = '{"a": 1}'
        assert _extract_balanced_json_object(text, 0) == '{"a": 1}'

    def test_nested_braces(self):
        text = '{"a": {"b": 1}} trailing'
        assert _extract_balanced_json_object(text, 0) == '{"a": {"b": 1}}'

    def test_braces_inside_string_values_are_ignored(self):
        text = '{"a": "text with } inside"} trailing'
        assert _extract_balanced_json_object(text, 0) == '{"a": "text with } inside"}'

    def test_escaped_quote_inside_string(self):
        text = r'{"a": "she said \"hi\""} trailing'
        result = _extract_balanced_json_object(text, 0)
        assert result == r'{"a": "she said \"hi\""}'

    def test_unterminated_object_returns_rest_of_string(self):
        text = '{"a": 1, "b": 2'
        assert _extract_balanced_json_object(text, 0) == '{"a": 1, "b": 2'

    def test_non_brace_start_returns_none(self):
        assert _extract_balanced_json_object("not a brace", 0) is None


class TestExtractTextToolCall:
    def test_tool_call_tag_format(self):
        text = '<tool_call>{"name": "create_plan", "arguments": {"title": "x"}}</tool_call>'
        result = _extract_text_tool_call(text)
        assert result is not None
        name, args, matched = result
        assert name == "create_plan"
        assert args == {"title": "x"}
        assert matched == text

    def test_tool_call_tag_with_surrounding_prose(self):
        text = 'Sure, calling it now.\n<tool_call>{"name": "shell_exec", "arguments": {"command": "ls"}}</tool_call>\nDone.'
        result = _extract_text_tool_call(text)
        assert result is not None
        name, args, matched = result
        assert name == "shell_exec"
        assert args == {"command": "ls"}
        remaining = text.replace(matched, "", 1).strip()
        assert remaining == "Sure, calling it now.\n\nDone."

    def test_named_fence_format(self):
        """The exact shape observed in production: ```tool_name {json}```"""
        text = '``` create_plan {"title": "Relatorio", "message": "Working on it"} ```'
        result = _extract_text_tool_call(text)
        assert result is not None
        name, args, matched = result
        assert name == "create_plan"
        assert args == {"title": "Relatorio", "message": "Working on it"}

    def test_named_fence_with_leading_indentation_and_prose(self):
        """Reproduces the captured session pattern: growing leading
        whitespace before the fence, across repeated nudge turns."""
        text = (
            '        ``` create_plan {"title": "Relatorio sobre X", '
            '"message": "Pesquisando..."}'
        )
        result = _extract_text_tool_call(text)
        assert result is not None
        name, args, _ = result
        assert name == "create_plan"
        assert args["title"] == "Relatorio sobre X"

    def test_generic_json_fence_format(self):
        text = '```json\n{"name": "shell_exec", "arguments": {"command": "pwd"}}\n```'
        result = _extract_text_tool_call(text)
        assert result is not None
        name, args, _ = result
        assert name == "shell_exec"
        assert args == {"command": "pwd"}

    def test_unterminated_fence_still_recovers(self):
        """No closing ``` at all (generation cut off) — still recoverable
        via the balanced-brace extractor plus the tolerant JSON parser."""
        text = '``` create_plan {"title": "Incomplete report'
        result = _extract_text_tool_call(text)
        # The object itself is truncated (unterminated string), so a plain
        # json.loads would fail — parse_partial_json is what makes this work.
        assert result is not None
        name, args, _ = result
        assert name == "create_plan"
        assert args.get("title") == "Incomplete report"

    def test_plain_prose_with_no_embedded_call_returns_none(self):
        assert _extract_text_tool_call("I'm still thinking about this.") is None

    def test_fence_without_json_object_returns_none(self):
        assert _extract_text_tool_call("```python\nprint('hi')\n```") is None

    def test_tag_format_takes_priority_over_a_fence(self):
        text = (
            '<tool_call>{"name": "create_plan", "arguments": {"title": "A"}}</tool_call>\n'
            '``` shell_exec {"command": "ls"} ```'
        )
        name, _, _ = _extract_text_tool_call(text)
        assert name == "create_plan"


class TestRobustJsonParserStage0Integration:
    async def test_recovers_and_promotes_a_known_tool(self):
        message = AIMessage(
            content='``` create_plan {"title": "Report", "message": "ok"} ```',
        )
        parser = _parser(known_tools=["create_plan"])
        result = await parser.ainvoke(message)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "create_plan"
        assert result.tool_calls[0]["args"] == {"title": "Report", "message": "ok"}

    async def test_matched_text_is_stripped_from_content(self):
        message = AIMessage(
            content='Sure!\n``` create_plan {"title": "Report"} ```\nDone.',
        )
        parser = _parser(known_tools=["create_plan"])
        result = await parser.ainvoke(message)
        assert "create_plan" not in result.content
        assert "{" not in result.content

    async def test_unknown_tool_name_is_left_as_plain_text(self):
        message = AIMessage(
            content='``` not_a_real_tool {"x": 1} ```',
        )
        parser = _parser(known_tools=["create_plan"])
        result = await parser.ainvoke(message)
        assert result.tool_calls == []
        assert result.content == message.content

    async def test_no_known_tools_disables_recovery(self):
        """A call with no tools bound has nothing to recover into."""
        message = AIMessage(content='``` create_plan {"title": "Report"} ```')
        parser = RobustJsonParser.from_llm(_stub_llm(), known_tools=None)
        result = await parser.ainvoke(message)
        assert result.tool_calls == []

    async def test_existing_native_tool_calls_are_left_alone(self):
        """Stage 0 must never run when the model already used the native
        channel correctly — nothing to recover."""
        message = AIMessage(
            content="",
            tool_calls=[{"name": "create_plan", "args": {"title": "x"}, "id": "c1", "type": "tool_call"}],
        )
        parser = _parser()
        result = await parser.ainvoke(message)
        assert result.tool_calls == message.tool_calls

    async def test_plain_prose_with_no_recoverable_call_raises_nothing(self):
        """No tool_calls, no invalid_tool_calls, no embedded call: passes
        through unchanged (the agent loop's nudge/streak limit handles this
        case, not the parser)."""
        message = AIMessage(content="I'm still thinking about this.")
        parser = _parser()
        result = await parser.ainvoke(message)
        assert result.tool_calls == []
        assert result.content == "I'm still thinking about this."
