"""Unit tests for the web sub-agent and its delegation toolkit.

Pure unit tests — no server, no network. The LLM and agent repository are
faked so the WebAgent's tool-calling loop runs deterministically.
"""
from typing import Any, Dict, List, Optional

import pytest

from app.domain.models.memory import Memory
from app.domain.models.message import LLMMessage, ToolCall
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.web import WebAgent
from app.domain.services.tools.base import BaseToolkit, tool
from app.domain.services.tools.delegation import DelegationToolkit


class FakeBrowserToolkit(BaseToolkit):
    """A minimal single-tool toolkit standing in for BrowserToolkit."""

    name = "browser"

    def __init__(self):
        super().__init__()
        self.calls: List[str] = []

    @tool(parse_docstring=True)
    async def browser_navigate(self, url: str) -> ToolResult:
        """Navigate to a URL.

        Args:
            url: The URL to open.
        """
        self.calls.append(url)
        return ToolResult(success=True, message=f"navigated to {url}")


class FakeAgentRepository:
    """In-memory stand-in for AgentRepository — enough for one agent's memory."""

    def __init__(self):
        self._memories: Dict[str, Memory] = {}

    async def save(self, agent) -> None:
        pass

    async def find_by_id(self, agent_id: str):
        return None

    async def add_memory(self, agent_id: str, name: str, memory: Memory) -> None:
        self._memories[(agent_id, name)] = memory

    async def get_memory(self, agent_id: str, name: str) -> Memory:
        return self._memories.setdefault((agent_id, name), Memory())

    async def save_memory(self, agent_id: str, name: str, memory: Memory) -> None:
        self._memories[(agent_id, name)] = memory


class ScriptedLLM:
    """Returns queued responses in order, ignoring the actual prompt."""

    def __init__(self, responses: List[LLMMessage]):
        self._responses = list(responses)
        self.capabilities = None
        self.ask_calls: List[List[LLMMessage]] = []

    async def ask(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[str] = None,
        tool_choice: Optional[str] = None,
    ) -> LLMMessage:
        self.ask_calls.append(messages)
        if not self._responses:
            raise AssertionError("ScriptedLLM ran out of queued responses")
        return self._responses.pop(0)


def make_web_agent(llm: ScriptedLLM, browser: FakeBrowserToolkit) -> WebAgent:
    return WebAgent(
        agent_id="agent-1",
        agent_repository=FakeAgentRepository(),
        llm=llm,
        tools=[browser],
    )


class TestWebAgentIsolation:
    @pytest.mark.asyncio
    async def test_web_agent_only_has_the_browser_toolkit(self):
        browser = FakeBrowserToolkit()
        agent = make_web_agent(ScriptedLLM([]), browser)
        assert [tk.name for tk in agent.toolkits] == ["browser"]

    @pytest.mark.asyncio
    async def test_web_agent_has_its_own_memory_namespace(self):
        """Namespaced by agent.name, per AgentRepository.get_memory."""
        browser = FakeBrowserToolkit()
        agent = make_web_agent(ScriptedLLM([]), browser)
        assert agent.name == "web"


class TestBrowseWebTool:
    @pytest.mark.asyncio
    async def test_reports_findings_on_success(self):
        browser = FakeBrowserToolkit()
        llm = ScriptedLLM([
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="1", name="browser_navigate", args={"url": "https://example.com"})
            ]),
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="2", name="report_findings", args={
                    "success": True, "result": "The page says hello."
                })
            ]),
        ])
        web_agent = make_web_agent(llm, browser)
        toolkit = DelegationToolkit(web_agent)

        result = await toolkit.get_tool("browse_web").invoke({"task": "Go to example.com and summarize it"})

        assert result.success is True
        assert result.message == "The page says hello."
        assert browser.calls == ["https://example.com"]

    @pytest.mark.asyncio
    async def test_reports_failure_from_the_sub_agent(self):
        browser = FakeBrowserToolkit()
        llm = ScriptedLLM([
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="1", name="report_findings", args={
                    "success": False, "result": "Site required login; could not proceed."
                })
            ]),
        ])
        web_agent = make_web_agent(llm, browser)
        toolkit = DelegationToolkit(web_agent)

        result = await toolkit.get_tool("browse_web").invoke({"task": "Log in and check the dashboard"})

        assert result.success is False
        assert "login" in result.message

    @pytest.mark.asyncio
    async def test_missing_report_is_a_clear_failure_not_a_crash(self):
        """The sub-agent hit its iteration cap without calling report_findings."""
        browser = FakeBrowserToolkit()
        # One initial ask() plus one nudge per iteration — max_iterations=2
        # needs 3 scripted plain-message turns to exhaust without a tool call.
        web_agent = make_web_agent(
            ScriptedLLM([LLMMessage.assistant("x") for _ in range(3)]),
            browser,
        )
        web_agent.max_iterations = 2
        toolkit = DelegationToolkit(web_agent)

        result = await toolkit.get_tool("browse_web").invoke({"task": "An impossible task"})

        assert result.success is False
        assert "iteration" in result.message.lower() or "findings" in result.message.lower()


class TestEventForwarding:
    @pytest.mark.asyncio
    async def test_sub_agent_tool_events_land_on_the_queue(self):
        """This is what lets the UI see browsing progress during delegation."""
        browser = FakeBrowserToolkit()
        llm = ScriptedLLM([
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="1", name="browser_navigate", args={"url": "https://x.test"})
            ]),
            LLMMessage.assistant("", tool_calls=[
                ToolCall(id="2", name="report_findings", args={"success": True, "result": "done"})
            ]),
        ])
        web_agent = make_web_agent(llm, browser)
        toolkit = DelegationToolkit(web_agent)

        await toolkit.get_tool("browse_web").invoke({"task": "Visit x.test"})

        events = []
        while not toolkit.event_queue.empty():
            events.append(toolkit.event_queue.get_nowait())
        tool_names = [getattr(e, "function_name", None) for e in events]
        assert "browser_navigate" in tool_names
        # report_findings is consumed internally, not forwarded as a tool event.
        assert "report_findings" not in tool_names
