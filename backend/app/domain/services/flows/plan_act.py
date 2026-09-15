import logging
from app.domain.services.flows.base import BaseFlow
from app.domain.models.message import Message
from typing import AsyncGenerator, List, Optional
from enum import Enum
from app.domain.models.event import (
    BaseEvent,
    PlanEvent,
    PlanStatus,
    MessageEvent,
    DoneEvent,
    TitleEvent,
)
from app.domain.models.plan import ExecutionStatus
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.agents.execution import ExecutionAgent
from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser
from app.domain.external.search import SearchEngine
from app.domain.external.llm import LLM
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.repositories.project_repository import ProjectRepository
from app.domain.models.session import SessionStatus
from app.domain.services.tools.mcp import MCPToolkit
from app.domain.services.tools.shell import ShellToolkit
from app.domain.services.tools.browser import BrowserToolkit
from app.domain.services.tools.file import FileToolkit
from app.domain.services.tools.message import MessageToolkit
from app.domain.services.tools.search import SearchToolkit
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

class PlanActFlow(BaseFlow):
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

        all_toolkits = {
            "shell": ShellToolkit(sandbox),
            "browser": BrowserToolkit(browser),
            "file": FileToolkit(sandbox),
            "message": MessageToolkit(),
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
                if key in allowed or key == "mcp"
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

        # Create planner and execution agents. The planner only receives a
        # compact capability overview instead of full tool schemas.
        self.planner = PlannerAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=self._llm,
            capability_toolkits=tools,
        )
        logger.debug(f"Created planner agent for Agent {self._agent_id}")
            
        self.executor = ExecutionAgent(
            agent_id=self._agent_id,
            agent_repository=self._repository,
            llm=self._llm,
            tools=tools,
        )
        logger.debug(f"Created execution agent for Agent {self._agent_id}")

    async def _apply_project_instruction(self, project_id: Optional[str]) -> None:
        instruction: Optional[str] = None
        if project_id and self._project_repository:
            project = await self._project_repository.find_by_id(project_id)
            if project and project.instruction:
                instruction = project.instruction
        self.planner.set_project_instruction(instruction)
        self.executor.set_project_instruction(instruction)
        await self.planner.sync_system_prompt()
        await self.executor.sync_system_prompt()

    async def run(self, message: Message) -> AsyncGenerator[BaseEvent, None]:

        # TODO: move to task runner
        session = await self._session_repository.find_by_id(self._session_id)
        if not session:
            raise ValueError(f"Session {self._session_id} not found")

        await self._apply_project_instruction(session.project_id)

        if session.status != SessionStatus.PENDING:
            logger.debug(f"Session {self._session_id} is not in PENDING status, rolling back")
            await self.executor.roll_back(message)
            await self.planner.roll_back(message)
        
        if session.status == SessionStatus.RUNNING:
            logger.debug(f"Session {self._session_id} is in RUNNING status")
            self.status = AgentStatus.PLANNING

        if session.status == SessionStatus.WAITING:
            logger.debug(f"Session {self._session_id} is in WAITING status")
            self.status = AgentStatus.EXECUTING

        await self._session_repository.update_status(self._session_id, SessionStatus.RUNNING)  
        self.plan = session.get_last_plan()

        logger.info(f"Agent {self._agent_id} started processing message: {message.message[:50]}...")
        step = None
        while True:
            if self.status == AgentStatus.IDLE:
                logger.info(f"Agent {self._agent_id} state changed from {AgentStatus.IDLE} to {AgentStatus.PLANNING}")
                self.status = AgentStatus.PLANNING
            elif self.status == AgentStatus.PLANNING:
                # Create plan
                logger.info(f"Agent {self._agent_id} started creating plan")
                async for event in self.planner.create_plan(message):
                    if isinstance(event, PlanEvent) and event.status == PlanStatus.CREATED:
                        self.plan = event.plan
                        logger.info(f"Agent {self._agent_id} created plan successfully with {len(event.plan.steps)} steps")
                        if event.plan.title and event.plan.title.strip():
                            yield TitleEvent(title=event.plan.title)
                        # Skip empty planner acknowledgements (bad LLM stubs)
                        if event.plan.message and event.plan.message.strip():
                            yield MessageEvent(role="assistant", message=event.plan.message)
                    yield event
                logger.info(f"Agent {self._agent_id} state changed from {AgentStatus.PLANNING} to {AgentStatus.EXECUTING}")
                self.status = AgentStatus.EXECUTING
                if len(event.plan.steps) == 0:
                    logger.info(f"Agent {self._agent_id} created plan successfully with no steps")
                    self.status = AgentStatus.COMPLETED
                    
            elif self.status == AgentStatus.EXECUTING:
                # Execute plan
                self.plan.status = ExecutionStatus.RUNNING
                step = self.plan.get_next_step()
                if not step:
                    logger.info(f"Agent {self._agent_id} has no more steps, state changed from {AgentStatus.EXECUTING} to {AgentStatus.COMPLETED}")
                    self.status = AgentStatus.SUMMARIZING
                    continue
                # Execute step
                logger.info(f"Agent {self._agent_id} started executing step {step.id}: {step.description[:50]}...")
                async for event in self.executor.execute_step(self.plan, step, message):
                    yield event
                logger.info(f"Agent {self._agent_id} completed step {step.id}, state changed from {AgentStatus.EXECUTING} to {AgentStatus.UPDATING}")
                await self.executor.compact_memory()
                logger.debug(f"Agent {self._agent_id} compacted memory")
                self.status = AgentStatus.UPDATING
            elif self.status == AgentStatus.UPDATING:
                # Update plan
                logger.info(f"Agent {self._agent_id} started updating plan")
                async for event in self.planner.update_plan(self.plan, step):
                    yield event
                logger.info(f"Agent {self._agent_id} plan update completed, state changed from {AgentStatus.UPDATING} to {AgentStatus.EXECUTING}")
                self.status = AgentStatus.EXECUTING
            elif self.status == AgentStatus.SUMMARIZING:
                # Conclusion
                logger.info(f"Agent {self._agent_id} started summarizing")
                async for event in self.executor.summarize():
                    yield event
                logger.info(f"Agent {self._agent_id} summarizing completed, state changed from {AgentStatus.SUMMARIZING} to {AgentStatus.COMPLETED}")
                self.status = AgentStatus.COMPLETED
            elif self.status == AgentStatus.COMPLETED:
                self.plan.status = ExecutionStatus.COMPLETED
                logger.info(f"Agent {self._agent_id} plan has been completed")
                yield PlanEvent(status=PlanStatus.COMPLETED, plan=self.plan)
                self.status = AgentStatus.IDLE
                break
        yield DoneEvent()
        
        logger.info(f"Agent {self._agent_id} message processing completed")
    
    def is_done(self) -> bool:
        return self.status == AgentStatus.IDLE