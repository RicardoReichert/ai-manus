"""Delegation toolkit: stands in for the browser toolkit's 12 tools.

Bound onto a supervisor agent instead of ``BrowserToolkit`` when a model's
tool profile excludes browsing (see ``domain/services/tools/profiles.py``),
this exposes a single ``browse_web`` tool that hands a self-contained task to
an isolated :class:`~app.domain.services.agents.web.WebAgent` and returns its
final report as plain text.

Sub-agent events (tool calls, browser actions) are pushed onto ``event_queue``
as they happen rather than returned — ``browse_web`` itself only returns once
the sub-agent finishes. The queue is drained by the delegating agent's own
``execute()`` loop while the tool call is in flight (the same
poll-while-awaiting shape already used for shell's live console updates), so
the UI keeps seeing what the browsing sub-agent is doing instead of a single
tool call that silently takes a long time.
"""
import asyncio
import logging
from typing import Optional

from app.domain.models.agent_output import WebFindings
from app.domain.models.event import BaseEvent, ToolEvent, ToolStatus
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.web import REPORT_FINDINGS_TOOL, WebAgent
from app.domain.services.agents.base import StructuredOutputEvent
from app.domain.services.tools.base import BaseToolkit, tool

logger = logging.getLogger(__name__)


class DelegationToolkit(BaseToolkit):
    """Exposes `browse_web` and forwards the sub-agent's events to a queue."""

    name: str = "delegation"
    instructions: str = """
- Use browse_web to accomplish anything requiring a web browser (navigating, clicking, reading a page)
- Give it the complete, self-contained task in one call — it has no access to this conversation
- It returns a text report; if it reports failure, adjust the task and try again rather than repeating the same request
"""

    def __init__(self, web_agent: WebAgent):
        super().__init__()
        self._web_agent = web_agent
        # Unbounded: a sub-agent step producing events faster than the
        # supervisor drains them (e.g. between poll ticks) must not block the
        # sub-agent's own progress.
        self.event_queue: "asyncio.Queue[BaseEvent]" = asyncio.Queue()

    @tool
    async def browse_web(self, task: str) -> ToolResult:
        """Delegate a browsing task to a specialized web sub-agent and get its report.

        Args:
            task: The complete, self-contained browsing task to perform — include
                everything the sub-agent needs, since it has no memory of this
                conversation.
        """
        findings: Optional[WebFindings] = None
        try:
            async for event in self._web_agent.execute(task, output_tool=REPORT_FINDINGS_TOOL):
                if isinstance(event, StructuredOutputEvent) and isinstance(event.output, WebFindings):
                    findings = event.output
                    continue
                await self.event_queue.put(event)
        except Exception as e:
            logger.exception("Web sub-agent failed for task: %s", task)
            return ToolResult(success=False, message=f"Web sub-agent failed: {e}")

        if findings is None:
            return ToolResult(
                success=False,
                message="Web sub-agent ended without reporting findings (likely hit its iteration limit).",
            )
        return ToolResult(success=findings.success, message=findings.result)
