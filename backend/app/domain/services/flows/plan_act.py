import logging
from enum import Enum
from typing import AsyncGenerator, List, Optional

from app.domain.external.browser import Browser
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.models.event import (
    BaseEvent,
    DoneEvent,
    MessageEvent,
    PlanEvent,
    PlanStatus,
    TitleEvent,
    WaitEvent,
)
from app.domain.models.message import Message
from app.domain.models.plan import ExecutionStatus, Step
from app.domain.models.session import SessionStatus
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.project_repository import ProjectRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.flows.base import BaseFlow
from app.domain.services.plan_progress import mark_first_step_running
from app.domain.services.prompts.execution import can_skip_summarize
from app.domain.services.tools.browser import BrowserToolkit
from app.domain.services.tools.file import FileToolkit
from app.domain.services.tools.mcp import MCPToolkit
from app.domain.services.tools.message import MessageToolkit
from app.domain.services.tools.search import SearchToolkit
from app.domain.services.tools.shell import ShellToolkit
from app.domain.services.tools.skill import SkillToolkit
from app.domain.services.tools.delegation import DelegationToolkit
from app.domain.services.tools.profiles import toolkits_for_profile, select_tool_names
from app.domain.services.agents.web import WebAgent

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    UPDATING = "updating"


def step_needs_replan(step: Step) -> bool:
    """Only failed / unsuccessful steps ask Planner to rewrite remaining work."""
    if step.status == ExecutionStatus.FAILED:
        return True
    if step.status == ExecutionStatus.COMPLETED and step.success is False:
        return True
    return False


class PlanActFlow(BaseFlow):
    """Plan-Act state machine: Planner creates/updates plan; Executor runs one step at a time.

    Successful steps are marked locally (no Planner round-trip). Planner.update_plan
    runs only when the finished step failed or reported success=false.
    """

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        session_id: str,
        session_repository: SessionRepository,
        sandbox: Sandbox,
        browser: Browser,
        mcp_tool: MCPToolkit,
        llm: LLM,
        search_engine: Optional[SearchEngine] = None,
        project_repository: Optional[ProjectRepository] = None,
        tool_profile: str = "full",
        enabled_tools: Optional[List[str]] = None,
        max_tools: Optional[int] = None,
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._session_id = session_id
        self._session_repository = session_repository
        self._project_repository = project_repository
        self._llm = llm
        self.status = AgentStatus.IDLE
        self.plan = None
        self._done = False
        self._resume_waiting = False

        self._skill_toolkit = SkillToolkit()
        all_toolkits = {
            "shell": ShellToolkit(sandbox),
            "browser": BrowserToolkit(browser),
            "file": FileToolkit(sandbox),
            "message": MessageToolkit(),
            "skill": self._skill_toolkit,
            "mcp": mcp_tool,
        }
        if search_engine:
            all_toolkits["search"] = SearchToolkit(search_engine)

        # None (the "full" profile) means no restriction, so a model with no
        # configured profile — or one running on the global default — gets
        # exactly the toolset the system always had. mcp is never gated by a
        # profile: it is already opt-in per-deployment via mcp.json.
        allowed = toolkits_for_profile(tool_profile)
        if allowed is None:
            tools = list(all_toolkits.values())
        else:
            tools = [
                toolkit for key, toolkit in all_toolkits.items()
                if key in allowed or key in ("mcp", "skill")
            ]
            if "browser" not in allowed:
                # Browsing isn't dropped, it's delegated: an isolated
                # WebAgent (own toolkit, own memory namespace) takes the 12
                # browser tools instead, so the supervisor's own tool count
                # stays within the profile's budget regardless of how many
                # steps a browsing task needs.
                web_agent = WebAgent(
                    agent_id=agent_id,
                    agent_repository=agent_repository,
                    llm=llm,
                    tools=[all_toolkits["browser"]],
                )
                tools.append(DelegationToolkit(web_agent))

        # enabled_tools narrows within the resolved toolkits, and max_tools
        # trims the profile's own default set when the admin hasn't picked
        # explicit tools — both go through select_tool_names, the single
        # source of truth for "which tool names survive a profile" (this
        # used to be a bespoke filter duplicating that function's contract;
        # see domain/services/tools/profiles.py). mcp is excluded from the
        # dict below (not merely skipped in the loop), so it is never a
        # candidate for either enabled_tools or max_tools: its tools are
        # discovered asynchronously after this constructor returns
        # (MCPToolkit.initialized()), so filtering here would just be
        # overwritten later, and MCP access is already opt-in per-deployment
        # via mcp.json.
        toolkits_by_name = {toolkit.name: toolkit for toolkit in tools if toolkit.name != "mcp"}
        available_by_toolkit = {
            name: [t.name for t in toolkit.get_tools()]
            for name, toolkit in toolkits_by_name.items()
        }
        allowed_names = set(
            select_tool_names(
                available_by_toolkit,
                tool_profile,
                enabled_tools=enabled_tools,
                max_tools=max_tools,
            )
        )
        for toolkit in toolkits_by_name.values():
            toolkit.tools = [t for t in toolkit.get_tools() if t.name in allowed_names]

        self.planner = PlannerAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=self._llm,
            capability_toolkits=tools,
        )
        self.executor = ExecutionAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=self._llm,
            tools=tools,
        )

    async def _apply_project_instruction(self, project_id: Optional[str]) -> None:
        instruction: Optional[str] = None
        if project_id and self._project_repository:
            project = await self._project_repository.find_by_id(project_id)
            if project and project.instruction:
                instruction = project.instruction
        self.planner.set_project_instruction(instruction)
        self.executor.set_project_instruction(instruction)

    def set_skill_catalog(self, catalog: Optional[str]) -> None:
        """Inject L1 skill metadata into planner and executor system prompts."""
        self.planner.set_skill_catalog(catalog)
        self.executor.set_skill_catalog(catalog)

    def set_enabled_skills(
        self,
        skills: Optional[list[tuple[str, str]]] = None,
        bodies: Optional[dict[str, str]] = None,
    ) -> None:
        """Refresh ``load_skill`` catalog + bodies from the user's enabled skills."""
        self._skill_toolkit.set_skills(list(skills or []))
        self._skill_toolkit.set_bodies(dict(bodies or {}))

    async def _apply_skill_context(self, message: Message) -> None:
        from app.domain.services.prompts.system import (
            format_skill_context,
            format_skill_planner_context,
        )

        if not message.skill:
            self.planner.set_skill_context(None)
            self.executor.set_skill_context(None)
            return

        # Planner: activation only — must schedule a first load_skill step.
        # Executor: soft MUST call load_skill before other work.
        self.planner.set_skill_context(
            format_skill_planner_context(
                name=message.skill.name,
                task=message.message,
            )
        )
        self.executor.set_skill_context(
            format_skill_context(
                name=message.skill.name,
                task=message.message,
            )
        )

    async def _sync_agent_prompts(self) -> None:
        await self.planner.sync_system_prompt()
        await self.executor.sync_system_prompt()

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        self._done = False
        session = await self._session_repository.find_by_id(self._session_id)
        if not session:
            raise ValueError(f"Session {self._session_id} not found")

        await self._apply_project_instruction(session.project_id)
        await self._apply_skill_context(message)
        await self._sync_agent_prompts()

        if session.status != SessionStatus.PENDING:
            await self.executor.roll_back(message)
            await self.planner.roll_back(message)

        self._resume_waiting = session.status == SessionStatus.WAITING
        if self._resume_waiting:
            self.status = AgentStatus.EXECUTING
        elif session.status == SessionStatus.RUNNING:
            self.status = AgentStatus.PLANNING
        else:
            self.status = AgentStatus.IDLE

        await self._session_repository.update_status(
            self._session_id, SessionStatus.RUNNING
        )
        self.plan = session.get_last_plan()

        step = None
        while True:
            if self.status == AgentStatus.IDLE:
                self.status = AgentStatus.PLANNING

            elif self.status == AgentStatus.PLANNING:
                async for event in self.planner.create_plan(message):
                    if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                        plan = event.plan
                        if message.skill and plan:
                            from app.domain.services.skills.plan_steps import (
                                ensure_skill_read_first_step,
                            )

                            ensure_skill_read_first_step(plan, message.skill.name)
                        self.plan = (
                            mark_first_step_running(plan)
                            if plan and plan.steps
                            else plan
                        )
                        event = PlanEvent(status=PlanStatus.CREATED, plan=self.plan)
                        if self.plan.title and self.plan.title.strip():
                            yield TitleEvent(title=self.plan.title)
                        if self.plan.message and self.plan.message.strip():
                            yield MessageEvent(
                                role="assistant",
                                message=self.plan.message,
                            )
                    yield event

                if not self.plan or not self.plan.steps:
                    self.status = AgentStatus.COMPLETED
                else:
                    self.status = AgentStatus.EXECUTING

            elif self.status == AgentStatus.EXECUTING:
                if not self.plan:
                    self.status = AgentStatus.COMPLETED
                    continue

                self.plan.status = ExecutionStatus.RUNNING
                step = self.plan.get_next_step()
                if not step:
                    self.status = AgentStatus.SUMMARIZING
                    continue

                waited = False
                if self._resume_waiting:
                    self._resume_waiting = False
                    events = self.executor.resume_step(self.plan, step)
                else:
                    events = self.executor.execute_step(self.plan, step, message)

                async for event in events:
                    if isinstance(event, WaitEvent):
                        waited = True
                    yield event

                if waited:
                    self._done = False
                    return

                await self.executor.compact_memory()

                if step_needs_replan(step):
                    logger.info(
                        "Agent %s step %s needs replan (status=%s success=%s)",
                        self._agent_id,
                        step.id,
                        step.status,
                        step.success,
                    )
                    self.status = AgentStatus.UPDATING
                else:
                    # Local progress only — keep Plan panel in sync without Planner LLM.
                    yield PlanEvent(status=PlanStatus.UPDATED, plan=self.plan)
                    self.status = AgentStatus.EXECUTING

            elif self.status == AgentStatus.UPDATING:
                async for event in self.planner.update_plan(self.plan, step):
                    yield event
                self.status = AgentStatus.EXECUTING

            elif self.status == AgentStatus.SUMMARIZING:
                if can_skip_summarize(self.plan):
                    logger.info(
                        "Agent %s skipping summarize for single successful step",
                        self._agent_id,
                    )
                    self.status = AgentStatus.COMPLETED
                    continue
                async for event in self.executor.summarize():
                    yield event
                self.status = AgentStatus.COMPLETED

            elif self.status == AgentStatus.COMPLETED:
                if self.plan:
                    self.plan.status = ExecutionStatus.COMPLETED
                    yield PlanEvent(status=PlanStatus.COMPLETED, plan=self.plan)
                self.status = AgentStatus.IDLE
                break

        self._done = True
        yield DoneEvent()

    def is_done(self) -> bool:
        return self._done
