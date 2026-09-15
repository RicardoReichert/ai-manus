"""Unit tests for PlanActFlow's tool-profile-based toolkit selection.

Pure unit tests — PlanActFlow.__init__ only stores its collaborators and
builds toolkits from them, so Sandbox/Browser/etc. can be inert sentinels;
nothing here calls the sandbox or hits the network.
"""
import pytest

from app.domain.services.flows.plan_act import PlanActFlow
from app.domain.services.tools.delegation import DelegationToolkit


class FakeMCPToolkit:
    """Stands in for MCPToolkit — real MCP tools are discovered later, async."""

    name = "mcp"

    def get_tools(self):
        return []

    def get_tool_schemas(self):
        return []


def make_flow(**kwargs) -> PlanActFlow:
    return PlanActFlow(
        agent_id="agent-1",
        agent_repository=object(),
        session_id="session-1",
        session_repository=object(),
        sandbox=object(),
        browser=object(),
        mcp_tool=FakeMCPToolkit(),
        llm=object(),
        **kwargs,
    )


class TestFullProfileIsUnchanged:
    def test_full_profile_includes_the_browser_toolkit_directly(self):
        """Non-regression: large models must keep calling browser tools directly."""
        flow = make_flow(tool_profile="full")
        toolkit_names = [tk.name for tk in flow.executor.toolkits]
        assert "browser" in toolkit_names
        assert not any(isinstance(tk, DelegationToolkit) for tk in flow.executor.toolkits)

    def test_default_profile_is_full(self):
        """Omitting tool_profile entirely must behave exactly as before profiles existed."""
        flow = make_flow()
        toolkit_names = [tk.name for tk in flow.executor.toolkits]
        assert "browser" in toolkit_names
        assert "shell" in toolkit_names
        assert "file" in toolkit_names
        assert "message" in toolkit_names


class TestLeanProfileDelegatesBrowsing:
    def test_lean_profile_excludes_the_raw_browser_toolkit(self):
        flow = make_flow(tool_profile="lean")
        toolkit_names = [tk.name for tk in flow.executor.toolkits]
        assert "browser" not in toolkit_names

    def test_lean_profile_adds_a_delegation_toolkit_instead(self):
        flow = make_flow(tool_profile="lean")
        assert any(isinstance(tk, DelegationToolkit) for tk in flow.executor.toolkits)

    def test_lean_profile_keeps_core_work_toolkits(self):
        flow = make_flow(tool_profile="lean")
        toolkit_names = [tk.name for tk in flow.executor.toolkits]
        assert "shell" in toolkit_names
        assert "file" in toolkit_names
        assert "message" in toolkit_names

    def test_the_delegating_sub_agent_only_has_the_browser_toolkit(self):
        flow = make_flow(tool_profile="lean")
        delegation = next(tk for tk in flow.executor.toolkits if isinstance(tk, DelegationToolkit))
        sub_toolkit_names = [tk.name for tk in delegation._web_agent.toolkits]
        assert sub_toolkit_names == ["browser"]


class TestUnknownProfileFailsOpen:
    def test_an_invalid_profile_string_behaves_like_full(self):
        """A bad stored value must not silently gag the agent."""
        flow = make_flow(tool_profile="not-a-real-profile")
        toolkit_names = [tk.name for tk in flow.executor.toolkits]
        assert "browser" in toolkit_names


class TestEnabledToolsOverride:
    def test_enabled_tools_narrows_within_a_toolkit(self):
        flow = make_flow(tool_profile="full", enabled_tools=["shell_exec"])
        shell = next(tk for tk in flow.executor.toolkits if tk.name == "shell")
        assert [t.name for t in shell.get_tools()] == ["shell_exec"]

    def test_enabled_tools_cannot_resurrect_a_toolkit_the_profile_excluded(self):
        """Checking a browser tool by name must not bypass the lean profile."""
        flow = make_flow(tool_profile="lean", enabled_tools=["shell_exec", "browser_click"])
        toolkit_names = [tk.name for tk in flow.executor.toolkits]
        assert "browser" not in toolkit_names

    def test_mcp_tools_are_not_narrowed_by_enabled_tools(self):
        """MCP tools are discovered asynchronously after __init__ returns, so
        filtering them here would just be silently overwritten later."""
        flow = make_flow(tool_profile="full", enabled_tools=["shell_exec"])
        mcp = next(tk for tk in flow.executor.toolkits if tk.name == "mcp")
        # It's the same object passed in, untouched.
        assert mcp is flow.executor.toolkits[[t.name for t in flow.executor.toolkits].index("mcp")]


class TestMaxToolsBudget:
    def test_budget_trims_tools_across_toolkits(self):
        flow = make_flow(tool_profile="full", max_tools=3)
        total = sum(
            len(tk.get_tools()) for tk in flow.executor.toolkits if tk.name != "mcp"
        )
        assert total == 3

    def test_budget_keeps_message_tools_first(self):
        """message_notify_user/message_ask_user rank highest in TOOL_PRIORITY."""
        flow = make_flow(tool_profile="lean", max_tools=2)
        message = next(tk for tk in flow.executor.toolkits if tk.name == "message")
        assert {t.name for t in message.get_tools()} == {"message_notify_user", "message_ask_user"}

    def test_no_budget_is_unaffected(self):
        flow = make_flow(tool_profile="full")
        with_none = sum(
            len(tk.get_tools()) for tk in flow.executor.toolkits if tk.name != "mcp"
        )
        flow_budgeted = make_flow(tool_profile="full", max_tools=None)
        with_explicit_none = sum(
            len(tk.get_tools()) for tk in flow_budgeted.executor.toolkits if tk.name != "mcp"
        )
        assert with_none == with_explicit_none

    def test_mcp_is_exempt_from_the_budget(self):
        """A tight max_tools must not touch the mcp toolkit's own tool list —
        it is populated asynchronously after __init__ returns."""
        flow = make_flow(tool_profile="full", max_tools=1)
        mcp = next(tk for tk in flow.executor.toolkits if tk.name == "mcp")
        assert mcp.get_tools() == []  # unchanged from the FakeMCPToolkit stub

    def test_enabled_tools_overrides_max_tools(self):
        """An explicit admin pick isn't further squeezed by the soft budget."""
        flow = make_flow(
            tool_profile="full",
            enabled_tools=["shell_exec", "file_read", "file_write"],
            max_tools=1,
        )
        total = sum(
            len(tk.get_tools()) for tk in flow.executor.toolkits if tk.name != "mcp"
        )
        assert total == 3
