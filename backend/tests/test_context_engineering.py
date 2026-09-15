"""Unit tests for the redesigned context engineering.

Covers the composable system prompt, structured output via native function
calling (OutputTool + self-repair), token-aware memory compaction, tool
result truncation, and the dynamic MCP tool bridge. Pure unit tests — no
running backend required.
"""
import json
from typing import List, Optional

from app.domain.models.agent_output import PlanOutput, StepReport
from app.domain.models.memory import Memory, estimate_tokens
from app.domain.models.message import LLMMessage, Role, ToolCall
from app.domain.models.model_capabilities import ModelCapabilities
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base import BaseAgent, StructuredOutputEvent
from app.domain.models.event import ErrorEvent
from app.domain.services.prompts.system import build_system_prompt
from app.domain.services.tools.base import (
    BaseToolkit,
    OutputTool,
    Tool,
    describe_toolkits,
    tool,
)

from tests.harness import FakeAgentRepository, ScriptedLLM, StubAgent, collect


class EchoToolkit(BaseToolkit):
    name = "echo"
    instructions = "- Echo things back verbatim"

    @tool
    async def echo(self, text: str) -> ToolResult:
        """Echo the given text back.

        Args:
            text: Text to echo
        """
        return ToolResult(success=True, data=text)


class SilentToolkit(BaseToolkit):
    """Toolkit without instructions — must not add a prompt section."""

    name = "silent"

    @tool
    async def noop(self) -> ToolResult:
        """Do nothing."""
        return ToolResult(success=True)


class TestSystemPromptBuilder:
    def test_core_prompt_always_present(self):
        prompt = build_system_prompt()
        assert "You are Manus" in prompt
        assert "<sandbox_environment>" in prompt

    def test_bound_toolkit_contributes_section(self):
        prompt = build_system_prompt(toolkits=[EchoToolkit()])
        assert "<echo_rules>" in prompt
        assert "Echo things back verbatim" in prompt

    def test_toolkit_without_instructions_adds_no_section(self):
        prompt = build_system_prompt(toolkits=[SilentToolkit()])
        assert "<silent_rules>" not in prompt

    def test_role_prompt_appended(self):
        prompt = build_system_prompt(role_prompt="<role>planner</role>")
        assert prompt.endswith("<role>planner</role>")

    def test_project_instruction_section(self):
        prompt = build_system_prompt(project_instruction="Always reply in Chinese.")
        assert "<project_instructions>" in prompt
        assert "Always reply in Chinese." in prompt

    def test_blank_project_instruction_omitted(self):
        prompt = build_system_prompt(project_instruction="   ")
        assert "<project_instructions>" not in prompt

    def test_describe_toolkits_compact_overview(self):
        overview = describe_toolkits([EchoToolkit(), SilentToolkit()])
        assert overview == "- echo: echo\n- silent: noop"


class TestOutputTool:
    def test_schema_shape(self):
        out = OutputTool("create_plan", "Submit the plan.", PlanOutput)
        schema = out.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "create_plan"
        props = schema["function"]["parameters"]["properties"]
        assert set(props) == {"message", "language", "title", "goal", "steps"}

    def test_validate_success_and_failure(self):
        out = OutputTool("complete_step", "Report step.", StepReport)
        report = out.validate({"success": True, "result": "done"})
        assert report.success is True and report.attachments == []

        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            out.validate({"result": "missing success"})


class TestMemoryCompaction:
    def _memory_with_tool_results(self, n: int, size: int = 400) -> Memory:
        m = Memory()
        m.add_message(LLMMessage.system("sys"))
        for i in range(n):
            m.add_message(LLMMessage.assistant(
                "", tool_calls=[ToolCall(id=f"c{i}", name="echo", args={})]
            ))
            m.add_message(LLMMessage.tool(
                tool_call_id=f"c{i}", name="echo", content="x" * size
            ))
        return m

    def test_estimate_tokens_counts_content_and_calls(self):
        assert estimate_tokens("") == 0
        assert estimate_tokens("abcd" * 100) == 100
        m = self._memory_with_tool_results(2)
        assert m.estimate_tokens() > 0

    def test_unconditional_compact_elides_old_tool_results(self):
        m = self._memory_with_tool_results(10)
        m.compact(keep_recent=4)
        elided = [msg for msg in m.messages if "elided" in msg.content]
        assert elided, "old tool results should be elided"
        # The most recent messages are untouched.
        assert m.messages[-1].content == "x" * 400

    def test_budgeted_compact_stops_at_budget(self):
        m = self._memory_with_tool_results(10)
        before = m.estimate_tokens()
        m.compact(max_tokens=before + 1)  # already under budget: no-op
        assert all("elided" not in msg.content for msg in m.messages if msg.role == Role.TOOL)

        m.compact(max_tokens=before // 2, keep_recent=2)
        assert m.estimate_tokens() <= before // 2

    def test_compact_preserves_message_skeleton(self):
        m = self._memory_with_tool_results(5)
        count = len(m.messages)
        m.compact(keep_recent=0)
        assert len(m.messages) == count
        assert all(msg.role in (Role.SYSTEM, Role.ASSISTANT, Role.TOOL) for msg in m.messages)

    def _memory_with_long_assistant_turns(self, n: int, size: int = 2000) -> Memory:
        m = Memory()
        m.add_message(LLMMessage.system("sys"))
        for i in range(n):
            m.add_message(LLMMessage.user(f"do step {i}"))
            m.add_message(LLMMessage.assistant("y" * size))
        return m

    def test_unconditional_compact_never_truncates_assistant_prose(self):
        """The historical unconditional per-step call (max_tokens=0) must
        not start discarding a large-context model's own reasoning just
        because a step boundary was reached — only tool-result elision and
        (lossless) tag elision run unconditionally."""
        m = self._memory_with_long_assistant_turns(10)
        m.compact(keep_recent=2)
        assert all(len(msg.content) == 2000 for msg in m.messages if msg.role == Role.ASSISTANT)

    def test_budgeted_compact_truncates_old_assistant_prose_as_a_last_resort(self):
        m = self._memory_with_long_assistant_turns(10)
        before = m.estimate_tokens()
        # A reachable target: keep_recent=2 always protects one full 2000-char
        # assistant turn, so the floor here is well above zero.
        m.compact(max_tokens=before // 2, keep_recent=2)
        assert m.estimate_tokens() < before
        truncated = [
            msg for msg in m.messages[:-2]
            if msg.role == Role.ASSISTANT and "elided to save context" in msg.content
        ]
        assert truncated

    def test_budgeted_compact_never_truncates_recent_assistant_turns(self):
        m = self._memory_with_long_assistant_turns(10)
        before = m.estimate_tokens()
        m.compact(max_tokens=before // 4, keep_recent=2)
        recent_assistant = [msg for msg in m.messages[-2:] if msg.role == Role.ASSISTANT]
        assert recent_assistant and all(len(msg.content) == 2000 for msg in recent_assistant)

    def test_assistant_truncation_is_idempotent(self):
        """Running compact twice must not re-truncate an already-truncated
        turn down to nothing."""
        m = self._memory_with_long_assistant_turns(10)
        before = m.estimate_tokens()
        m.compact(max_tokens=before // 4, keep_recent=2)
        first_pass = [msg.content for msg in m.messages if msg.role == Role.ASSISTANT]
        m.compact(max_tokens=before // 4, keep_recent=2)
        second_pass = [msg.content for msg in m.messages if msg.role == Role.ASSISTANT]
        assert first_pass == second_pass

    def _memory_with_tagged_dumps(self, n: int, tag: str = "plan_dump") -> Memory:
        m = Memory()
        m.add_message(LLMMessage.system("sys"))
        for i in range(n):
            m.add_message(LLMMessage.user(f"plan snapshot #{i}" * 50, tag=tag))
        return m

    def test_tagged_messages_keep_only_the_latest(self):
        m = self._memory_with_tagged_dumps(5)
        m.compact(keep_recent=0)
        tagged = [msg for msg in m.messages if msg.tag == "plan_dump"]
        superseded = [msg for msg in tagged if "superseded" in msg.content]
        assert len(superseded) == 4
        assert "plan snapshot #4" in tagged[-1].content

    def test_tag_elision_runs_even_without_a_budget(self):
        """Unlike assistant truncation, tag elision is lossless (the older
        message is fully redundant), so it runs on every compact() call."""
        m = self._memory_with_tagged_dumps(5)
        m.compact(keep_recent=0)  # max_tokens=0, the unconditional per-step call
        superseded = [msg for msg in m.messages if msg.tag == "plan_dump" and "superseded" in msg.content]
        assert len(superseded) == 4

    def test_tag_elision_respects_keep_recent(self):
        m = self._memory_with_tagged_dumps(5)
        m.compact(keep_recent=2)
        # The last 2 messages are protected regardless of tag/superseding.
        untouched_by_recency = m.messages[-2:]
        assert all("superseded" not in msg.content for msg in untouched_by_recency)

    def test_untagged_messages_are_unaffected_by_tag_elision(self):
        m = self._memory_with_tool_results(3)
        system_before = [msg.content for msg in m.messages if msg.role == Role.SYSTEM]
        m.compact(keep_recent=0)
        assert all(msg.tag is None for msg in m.messages)
        system_after = [msg.content for msg in m.messages if msg.role == Role.SYSTEM]
        # Untagged, non-tool content (here: the system message) is never
        # touched by the tag-elision pass.
        assert system_after == system_before


def _agent(llm: ScriptedLLM, toolkits: Optional[list] = None) -> StubAgent:
    return StubAgent(
        agent_id="a1",
        agent_repository=FakeAgentRepository(),
        llm=llm,
        tools=toolkits or [],
    )


class _FakeRepository:
    def __init__(self):
        self.memory = Memory()

    async def get_memory(self, agent_id: str, name: str) -> Memory:
        return self.memory

    async def save_memory(self, agent_id: str, name: str, memory: Memory) -> None:
        self.memory = memory


class _ScriptedLLM:
    """LLM stub returning scripted assistant messages in order, with a
    configurable ``capabilities`` (unlike harness.ScriptedLLM, which always
    defaults it) — needed by the context-budget tests below."""

    def __init__(self, responses: List[LLMMessage], capabilities: Optional[ModelCapabilities] = None):
        self._responses = list(responses)
        self.requests = []
        self.capabilities = capabilities or ModelCapabilities()

    async def ask(self, messages, tools=None, response_format=None, tool_choice=None):
        self.requests.append({"messages": list(messages), "tools": tools, "tool_choice": tool_choice})
        return self._responses.pop(0)

    async def parse_json(self, text: str):
        raise AssertionError("parse_json must not be used by the agent loop anymore")


class _TestAgent(BaseAgent):
    name = "test"

    def build_system_prompt(self) -> str:
        return "test system prompt"


def _local_agent(llm: _ScriptedLLM, toolkits: Optional[list] = None) -> _TestAgent:
    return _TestAgent(
        agent_id="a1",
        agent_repository=_FakeRepository(),
        llm=llm,
        tools=toolkits or [],
    )


REPORT_TOOL = OutputTool("complete_step", "Report the step outcome.", StepReport)


async def _collect(gen):
    return [event async for event in gen]


class TestAgentLoopStructuredOutput:
    async def test_output_tool_call_yields_structured_output(self):
        llm = ScriptedLLM([
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c1", name="complete_step",
                         args={"success": True, "result": "done", "attachments": []}),
            ]),
        ])
        agent = _agent(llm)
        events = await collect(agent.execute("do it", output_tool=REPORT_TOOL))

        outputs = [e for e in events if isinstance(e, StructuredOutputEvent)]
        assert len(outputs) == 1
        assert outputs[0].output.result == "done"

        # Output tool schema was offered to the model.
        offered = [t["function"]["name"] for t in llm.requests[0]["tools"]]
        assert "complete_step" in offered

        # Memory stays consistent: the output call received a tool response.
        last = agent.memory.get_last_message()
        assert last.role == Role.TOOL and last.tool_call_id == "c1"

    async def test_invalid_output_args_trigger_self_repair(self):
        llm = ScriptedLLM([
            # First attempt: missing required fields.
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c1", name="complete_step", args={"success": True}),
            ]),
            # Second attempt: valid.
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c2", name="complete_step",
                         args={"success": True, "result": "fixed"}),
            ]),
        ])
        agent = _agent(llm)
        events = await collect(agent.execute("do it", output_tool=REPORT_TOOL))

        outputs = [e for e in events if isinstance(e, StructuredOutputEvent)]
        assert len(outputs) == 1 and outputs[0].output.result == "fixed"

        # The validation error was fed back as the tool response.
        error_feedback = [
            m for m in agent.memory.get_messages()
            if m.role == Role.TOOL and "Invalid arguments" in m.content
        ]
        assert len(error_feedback) == 1

    async def test_plain_message_is_nudged_to_output_tool(self):
        llm = ScriptedLLM([
            LLMMessage.assistant("I think I'm done."),
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c1", name="complete_step",
                         args={"success": True, "result": "ok"}),
            ]),
        ])
        agent = _agent(llm)
        events = await collect(agent.execute("do it", output_tool=REPORT_TOOL))
        assert any(isinstance(e, StructuredOutputEvent) for e in events)
        # The nudge mentions the output tool by name.
        nudge = llm.requests[1]["messages"][-1]
        assert "complete_step" in nudge.content

    async def test_regular_tools_still_execute(self):
        llm = ScriptedLLM([
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c1", name="echo", args={"text": "hello"}),
            ]),
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c2", name="complete_step",
                         args={"success": True, "result": "echoed"}),
            ]),
        ])
        agent = _agent(llm, toolkits=[EchoToolkit()])
        events = await collect(agent.execute("echo hello", output_tool=REPORT_TOOL))
        assert any(isinstance(e, StructuredOutputEvent) for e in events)
        tool_msgs = [m for m in agent.memory.get_messages() if m.role == Role.TOOL and m.name == "echo"]
        assert len(tool_msgs) == 1
        assert json.loads(tool_msgs[0].content)["data"] == "hello"

    async def test_unknown_tool_gets_error_response(self):
        llm = ScriptedLLM([
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c1", name="not_a_tool", args={}),
            ]),
            LLMMessage.assistant("all done"),
        ])
        agent = _agent(llm)
        events = await collect(agent.execute("do it"))
        # The dangling tool call was answered so the history stays valid.
        unknown = [
            m for m in agent.memory.get_messages()
            if m.role == Role.TOOL and "Unknown tool" in m.content
        ]
        assert len(unknown) == 1


class TestToolResultTruncation:
    async def test_oversized_tool_result_truncated(self):
        class BigToolkit(BaseToolkit):
            name = "big"

            @tool
            async def big(self) -> ToolResult:
                """Return something huge."""
                return ToolResult(success=True, data="y" * 100000)

        llm = ScriptedLLM([
            LLMMessage.assistant("", tool_calls=[ToolCall(id="c1", name="big", args={})]),
            LLMMessage.assistant("done"),
        ])
        agent = _agent(llm, toolkits=[BigToolkit()])
        await collect(agent.execute("go"))

        tool_msg = [m for m in agent.memory.get_messages() if m.role == Role.TOOL][0]
        assert len(tool_msg.content) <= agent.max_tool_result_chars + 100
        assert "truncated" in tool_msg.content

    def test_no_known_window_keeps_the_historical_ceiling(self):
        agent = _local_agent(_ScriptedLLM([]))
        assert agent.max_tool_result_chars == agent.max_tool_result_chars_ceiling == 16000

    def test_small_window_scales_the_cap_down(self):
        agent = _local_agent(_ScriptedLLM([], capabilities=ModelCapabilities(context_window=32000)))
        assert agent.max_tool_result_chars == 6400

    def test_huge_window_is_clamped_to_the_ceiling(self):
        agent = _local_agent(_ScriptedLLM([], capabilities=ModelCapabilities(context_window=1000000)))
        assert agent.max_tool_result_chars == agent.max_tool_result_chars_ceiling

    def test_tiny_window_is_clamped_to_the_floor(self):
        agent = _local_agent(_ScriptedLLM([], capabilities=ModelCapabilities(context_window=1000)))
        assert agent.max_tool_result_chars == agent.min_tool_result_chars

    def test_truncation_keeps_head_and_tail(self):
        agent = _local_agent(_ScriptedLLM([], capabilities=ModelCapabilities(context_window=32000)))
        content = "HEAD" * 1000 + "MIDDLE" * 1000 + "TAIL_END_MARKER" * 200
        truncated = agent._truncate_tool_result(content)
        assert truncated.startswith("HEAD")
        assert truncated.endswith("TAIL_END_MARKER")
        assert "truncated" in truncated
        assert len(truncated) < len(content)


class TestEffectiveContextTokens:
    def test_no_known_window_uses_the_flat_default(self):
        agent = _local_agent(_ScriptedLLM([]))
        assert agent.effective_context_tokens == agent.max_context_tokens

    def test_small_window_reserves_schema_and_output_headroom(self):
        agent = _agent(
            _ScriptedLLM([], capabilities=ModelCapabilities(context_window=32000, max_output_tokens=4000)),
        )
        schema_tokens = estimate_tokens(json.dumps(agent.get_tool_schemas(), default=str))
        expected = 32000 - schema_tokens - 4000 - agent.context_safety_margin_tokens
        assert agent.effective_context_tokens == expected

    def test_missing_max_output_tokens_falls_back_to_a_default_reserve(self):
        agent = _local_agent(_ScriptedLLM([], capabilities=ModelCapabilities(context_window=32000)))
        schema_tokens = estimate_tokens(json.dumps(agent.get_tool_schemas(), default=str))
        expected = 32000 - schema_tokens - agent.default_output_reserve_tokens - agent.context_safety_margin_tokens
        assert agent.effective_context_tokens == expected

    def test_budget_never_drops_below_the_floor(self):
        agent = _local_agent(_ScriptedLLM([], capabilities=ModelCapabilities(context_window=100)))
        assert agent.effective_context_tokens == agent.min_context_tokens

    def test_budget_is_capped_at_the_global_ceiling(self):
        agent = _local_agent(_ScriptedLLM([], capabilities=ModelCapabilities(context_window=100_000_000)))
        assert agent.effective_context_tokens == agent.max_context_tokens

    def test_more_tools_reduce_the_effective_budget(self):
        """The whole point: tool schemas were previously uncounted."""
        bare = _local_agent(_ScriptedLLM([], capabilities=ModelCapabilities(context_window=32000)))
        with_tools = _agent(
            _ScriptedLLM([], capabilities=ModelCapabilities(context_window=32000)),
            toolkits=[EchoToolkit()],
        )
        assert with_tools.effective_context_tokens < bare.effective_context_tokens


class TestParallelToolCallEnforcement:
    async def test_extra_tool_calls_dropped_when_unsupported(self):
        llm = _ScriptedLLM(
            [
                LLMMessage.assistant("", tool_calls=[
                    ToolCall(id="c1", name="echo", args={"text": "a"}),
                    ToolCall(id="c2", name="echo", args={"text": "b"}),
                ]),
                LLMMessage.assistant("", tool_calls=[
                    ToolCall(id="c3", name="complete_step", args={"success": True, "result": "ok"}),
                ]),
            ],
            capabilities=ModelCapabilities(supports_parallel_tool_calls=False),
        )
        agent = _agent(llm, toolkits=[EchoToolkit()])
        await _collect(agent.execute("go", output_tool=REPORT_TOOL))

        # Only the first tool call's response made it into memory — the
        # second was dropped before it ever entered the loop.
        tool_msgs = [m for m in agent.memory.get_messages() if m.role == Role.TOOL and m.name == "echo"]
        assert len(tool_msgs) == 1
        assert json.loads(tool_msgs[0].content)["data"] == "a"

    async def test_multiple_tool_calls_kept_when_supported(self):
        llm = _ScriptedLLM([
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c1", name="echo", args={"text": "a"}),
                ToolCall(id="c2", name="echo", args={"text": "b"}),
            ]),
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c3", name="complete_step", args={"success": True, "result": "ok"}),
            ]),
        ])
        agent = _agent(llm, toolkits=[EchoToolkit()])
        await _collect(agent.execute("go", output_tool=REPORT_TOOL))
        tool_msgs = [m for m in agent.memory.get_messages() if m.role == Role.TOOL and m.name == "echo"]
        assert len(tool_msgs) == 2


class TestThinkingStripped:
    async def test_thinking_dropped_on_plain_turns_when_flagged(self):
        llm = _ScriptedLLM(
            [
                LLMMessage.assistant("<think>pondering...</think>I think I'm done."),
                LLMMessage.assistant("", tool_calls=[
                    ToolCall(id="c1", name="complete_step", args={"success": True, "result": "ok"}),
                ]),
            ],
            capabilities=ModelCapabilities(strip_thinking_from_history=True),
        )
        agent = _agent(llm)
        await _collect(agent.execute("do it", output_tool=REPORT_TOOL))
        plain_turn = next(m for m in agent.memory.get_messages() if m.role == Role.ASSISTANT)
        assert "<think>" not in plain_turn.content
        assert "I think I'm done." in plain_turn.content

    async def test_thinking_preserved_on_tool_call_turns(self):
        """Gemma 4's documented exception: dropping thinking on a tool-call
        turn measurably hurts tool-call quality."""
        llm = _ScriptedLLM(
            [
                LLMMessage.assistant("<think>plan the call</think>", tool_calls=[
                    ToolCall(id="c1", name="complete_step", args={"success": True, "result": "ok"}),
                ]),
            ],
            capabilities=ModelCapabilities(strip_thinking_from_history=True),
        )
        agent = _agent(llm)
        await _collect(agent.execute("do it", output_tool=REPORT_TOOL))
        turn = next(m for m in agent.memory.get_messages() if m.role == Role.ASSISTANT)
        assert turn.tool_calls
        assert "<think>" in turn.content

    async def test_thinking_kept_when_capability_not_flagged(self):
        llm = _ScriptedLLM([
            LLMMessage.assistant("<think>pondering...</think>done."),
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c1", name="complete_step", args={"success": True, "result": "ok"}),
            ]),
        ])
        agent = _agent(llm)
        await _collect(agent.execute("do it", output_tool=REPORT_TOOL))
        plain_turn = next(m for m in agent.memory.get_messages() if m.role == Role.ASSISTANT)
        assert "<think>" in plain_turn.content


class TestConsecutiveNoToolCallLimit:
    async def test_gives_up_after_max_consecutive_nudges_instead_of_exhausting_iterations(self):
        # The model never calls the output tool, no matter how many times
        # it's nudged — one more response than the limit allows.
        responses = [LLMMessage.assistant(f"still thinking #{i}") for i in range(10)]
        llm = _ScriptedLLM(responses)
        agent = _agent(llm)
        events = await _collect(agent.execute("do it", output_tool=REPORT_TOOL))

        errors = [e for e in events if isinstance(e, ErrorEvent)]
        assert len(errors) == 1
        assert "complete_step" in errors[0].error

        # Bounded: far fewer requests than max_iterations (100) or the full
        # scripted response list (10).
        assert len(llm.requests) <= agent.max_consecutive_no_tool_call_nudges + 1

    async def test_recovering_a_tool_call_resets_the_streak(self):
        """A model that goes quiet, then calls a regular tool, then goes
        quiet again should get the full nudge budget each time — one lapse
        elsewhere must not spend down the streak permanently."""
        responses = (
            [LLMMessage.assistant(f"thinking #{i}") for i in range(2)]
            + [LLMMessage.assistant("", tool_calls=[ToolCall(id="c1", name="echo", args={"text": "x"})])]
            + [LLMMessage.assistant(f"thinking again #{i}") for i in range(2)]
            + [LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c2", name="complete_step", args={"success": True, "result": "ok"}),
            ])]
        )
        llm = _ScriptedLLM(responses)
        agent = _agent(llm, toolkits=[EchoToolkit()])
        events = await _collect(agent.execute("do it", output_tool=REPORT_TOOL))
        assert any(isinstance(e, StructuredOutputEvent) for e in events)
        assert not any(isinstance(e, ErrorEvent) for e in events)


class TestRequestTagPropagation:
    async def test_request_tag_reaches_the_stored_user_message(self):
        llm = _ScriptedLLM([
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c1", name="complete_step", args={"success": True, "result": "ok"}),
            ]),
        ])
        agent = _agent(llm)
        await _collect(agent.execute("plan dump text", output_tool=REPORT_TOOL, request_tag="plan_dump"))
        tagged = [m for m in agent.memory.get_messages() if m.tag == "plan_dump"]
        assert len(tagged) == 1
        assert tagged[0].content == "plan dump text"

    async def test_no_tag_by_default(self):
        llm = _ScriptedLLM([
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c1", name="complete_step", args={"success": True, "result": "ok"}),
            ]),
        ])
        agent = _agent(llm)
        await _collect(agent.execute("do it", output_tool=REPORT_TOOL))
        assert all(m.tag is None for m in agent.memory.get_messages())

    async def test_output_tool_nudge_messages_are_never_tagged(self):
        """Only the initial request carries the tag — repeated nudges to use
        the output tool must not each be treated as a fresh 'latest dump'."""
        llm = _ScriptedLLM([
            LLMMessage.assistant("still thinking"),
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="c1", name="complete_step", args={"success": True, "result": "ok"}),
            ]),
        ])
        agent = _agent(llm)
        await _collect(agent.execute("plan dump text", output_tool=REPORT_TOOL, request_tag="plan_dump"))
        tagged = [m for m in agent.memory.get_messages() if m.tag == "plan_dump"]
        assert len(tagged) == 1
        assert tagged[0].content == "plan dump text"


class TestDynamicMcpTools:
    def test_mcp_schemas_become_invocable_tools(self):
        from app.domain.services.tools.mcp import MCPToolkit

        toolkit = MCPToolkit()
        tools = toolkit._build_tools([
            {
                "type": "function",
                "function": {
                    "name": "mcp_server_lookup",
                    "description": "[server] Look something up",
                    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                },
            }
        ])
        toolkit.tools = tools
        found = toolkit.get_tool("mcp_server_lookup")
        assert isinstance(found, Tool)
        assert found.toolkit is toolkit
        assert toolkit.get_tool_schemas()[0]["function"]["name"] == "mcp_server_lookup"
