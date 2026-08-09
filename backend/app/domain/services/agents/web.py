"""Web sub-agent: the browsing specialist behind delegation.

Exists so a supervisor running on a small model never holds the browser
toolkit's 12 tools in its own context alongside shell/file/message/search —
the documented degradation threshold (~10-20 tools) is crossed by the full
toolset alone. Delegation moves navigation into an isolated agent with only
the browser toolkit, so the supervisor's own tool surface stays small
regardless of how many steps a browsing task takes.

Memory is namespaced by ``self.name`` in the repository (see
``AgentRepository.get_memory``), so this gets an isolated history "for free"
— the supervisor's context is never polluted with click-by-click browser
tool calls, only the final report.
"""
from typing import List

from app.domain.models.agent_output import WebFindings
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.external.llm import LLM
from app.domain.services.agents.base import BaseAgent
from app.domain.services.prompts.system import build_system_prompt
from app.domain.services.tools.base import BaseToolkit, OutputTool

REPORT_FINDINGS_TOOL = OutputTool(
    name="report_findings",
    description="Report the outcome of the browsing task once it is complete or cannot proceed.",
    schema=WebFindings,
)

WEB_ROLE_PROMPT = """
<role>
You are a browsing specialist working on behalf of another agent. You will
be given a single, self-contained browsing task. Complete it using the
browser tools, then call `report_findings` with what you found or did.

- You do not talk to the end user directly — there is no one to ask
  clarifying questions of. Make reasonable assumptions and note them in your
  report instead of stalling.
- Be thorough enough that the delegating agent can act on your report
  without re-browsing, but do not pad it — state what was found, plainly.
- If the task cannot be completed (page unreachable, information not
  present, blocked by a login wall), say so in `report_findings` with
  `success=false` and explain what you tried.
</role>
"""


class WebAgent(BaseAgent):
    """A sub-agent scoped to only the browser toolkit."""

    name: str = "web"
    # Browsing can take many small steps (navigate, click, scroll, extract);
    # cap well below the supervisor's iteration budget so a stuck sub-agent
    # fails fast and reports back rather than silently consuming the parent's
    # own iteration budget indirectly.
    max_iterations: int = 30

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        tools: List[BaseToolkit],
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            tools=tools,
        )

    def build_system_prompt(self) -> str:
        return build_system_prompt(
            toolkits=self.toolkits,
            role_prompt=WEB_ROLE_PROMPT,
            project_instruction=self._project_instruction,
        )
