import json
import logging
import asyncio
import re
import uuid
from abc import ABC
from typing import Any, List, Literal, Optional, AsyncGenerator
from app.domain.models.memory import estimate_tokens
from app.domain.models.message import Message, LLMMessage, Role, ToolCall
from app.domain.services.tools.base import BaseToolkit, OutputTool, Tool, ValidationError
from app.domain.models.event import (
    BaseEvent,
    ToolEvent,
    ToolStatus,
    ErrorEvent,
    MessageEvent,
    TerminalUpdateEvent,
)
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.external.llm import LLM
from app.domain.models.model_capabilities import ModelCapabilities


logger = logging.getLogger(__name__)


class StructuredOutputEvent(BaseEvent):
    """Internal event carrying validated structured output.

    Emitted when the model submits its result through an :class:`OutputTool`.
    Consumed by the concrete agents; never part of the public
    ``AgentEvent`` union streamed to clients.
    """

    type: Literal["structured_output"] = "structured_output"
    output: Any


class BaseAgent(ABC):
    """
    Base agent class, defining the basic behavior of the agent
    """

    name: str = ""
    max_iterations: int = 100
    max_retries: int = 3
    retry_interval: float = 1.0
    tool_choice: Optional[str] = None
    # Context engineering budgets: tool results are truncated at ingestion
    # (max_tool_result_chars, scaled by context window — see the property
    # below), and memory is compacted before each model call when over
    # budget (effective_context_tokens).
    max_context_tokens: int = 100000
    # effective_context_tokens floor/reserve knobs — see that property.
    min_context_tokens: int = 2000
    default_output_reserve_tokens: int = 4096
    context_safety_margin_tokens: int = 1000
    # max_tool_result_chars floor/ceiling/scale — see that property. A
    # single result at the ceiling (16000 chars ≈ 4k tokens) is already
    # ~17% of a 32K window; scaling down for small windows keeps one big
    # shell/browser dump from dominating a small model's whole budget.
    min_tool_result_chars: int = 2000
    max_tool_result_chars_ceiling: int = 16000
    tool_result_char_fraction_of_window: float = 0.05
    # A structured run nudges the model to call the output tool when it
    # answers in plain text instead. Past this many consecutive nudges, the
    # step fails cleanly instead of silently burning the rest of
    # max_iterations on a model that isn't going to comply (e.g. one that
    # keeps re-emitting the call as prose/markdown rather than a native
    # tool_call — see robust_json_parser's text-recovery stage, which
    # prevents most of these from ever reaching this counter).
    max_consecutive_no_tool_call_nudges: int = 3

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        tools: List[BaseToolkit] = []
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self._llm = llm
        self.toolkits = tools
        self.memory = None
        self._output_tool: Optional[OutputTool] = None
        self._project_instruction: Optional[str] = None

    def set_project_instruction(self, instruction: Optional[str]) -> None:
        """Bind project-level guidance used when assembling the system prompt."""
        text = (instruction or "").strip()
        self._project_instruction = text or None

    def build_system_prompt(self) -> str:
        """Assemble the system prompt for this agent; overridden by subclasses."""
        return ""

    async def sync_system_prompt(self) -> None:
        """Insert or refresh the leading system message so project edits apply."""
        await self._ensure_memory()
        prompt = self.build_system_prompt()
        if self.memory.empty:
            self.memory.add_message(LLMMessage.system(prompt))
            await self._repository.save_memory(self._agent_id, self.name, self.memory)
            return
        first = self.memory.messages[0]
        if first.role == Role.SYSTEM and first.content != prompt:
            first.content = prompt
            await self._repository.save_memory(self._agent_id, self.name, self.memory)

    def get_tool(self, name: str) -> Optional[Tool]:
        """Get specified tool"""
        for toolkit in self.toolkits:
            tool = toolkit.get_tool(name)
            if tool:
                return tool
        return None

    def get_tool_schemas(self) -> List[dict]:
        """Get OpenAI function schemas for all available tools.

        Includes the active output tool, if any, so the model can submit
        structured results through native function calling.
        """
        schemas = [schema for toolkit in self.toolkits for schema in toolkit.get_tool_schemas()]
        if self._output_tool:
            schemas.append(self._output_tool.to_openai_schema())
        return schemas

    @property
    def max_tool_result_chars(self) -> int:
        """Cap on a single tool result before it enters memory.

        Scaled to the model's context window (chars-per-token ratio matches
        Memory's own estimator) rather than a flat constant, so a 32K local
        model isn't handed the same 16000-char allowance as a 1M-context one
        — the ceiling below is exactly today's unchanged behavior for any
        model with no known window.
        """
        window = self.capabilities.context_window
        if not window:
            return self.max_tool_result_chars_ceiling
        chars_per_token = 4
        scaled = int(window * self.tool_result_char_fraction_of_window * chars_per_token)
        return max(self.min_tool_result_chars, min(self.max_tool_result_chars_ceiling, scaled))

    def _truncate_tool_result(self, content: str) -> str:
        """Cap a tool result before it enters memory, to bound context growth.

        Keeps a head *and* a tail slice rather than only the head: a shell
        command's error or final result is usually at the end of its
        output, and a head-only cap would silently discard exactly that.
        """
        limit = self.max_tool_result_chars
        if len(content) <= limit:
            return content
        omitted = len(content) - limit
        head_chars = limit * 2 // 3
        tail_chars = limit - head_chars
        return (
            content[:head_chars]
            + f"\n... [{omitted} chars truncated to save context] ...\n"
            + content[-tail_chars:]
        )

    async def invoke_tool(self, tool: Tool, tool_call: ToolCall) -> LLMMessage:
        """Invoke specified tool, with retry mechanism."""
        retries = 0
        last_error = ""
        while retries <= self.max_retries:
            try:
                raw_result = await tool.invoke(tool_call.args)
                content = (
                    raw_result.model_dump_json()
                    if hasattr(raw_result, "model_dump_json")
                    else str(raw_result)
                )
                return LLMMessage.tool(
                    tool_call_id=tool_call.id,
                    name=tool.name,
                    content=self._truncate_tool_result(content),
                    artifact=raw_result,
                )
            except Exception as e:
                last_error = str(e)
                retries += 1
                if retries <= self.max_retries:
                    await asyncio.sleep(self.retry_interval)
                else:
                    logger.exception(f"Tool execution failed, {tool_call.name}, {tool_call.args}")
                    break

        return LLMMessage.tool(tool_call_id=tool_call.id, name=tool.name, content=last_error)

    def _handle_output_call(self, tool_call: ToolCall) -> tuple[LLMMessage, Optional[Any]]:
        """Validate a structured-output tool call.

        Returns the tool response message to append to memory and, on
        success, the validated output model. On validation failure the
        response carries the error so the model can self-repair on the next
        iteration.
        """
        try:
            output = self._output_tool.validate(tool_call.args)
            response = LLMMessage.tool(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content='{"success": true}',
            )
            return response, output
        except ValidationError as e:
            logger.warning(f"Structured output validation failed for {tool_call.name}: {e}")
            response = LLMMessage.tool(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Invalid arguments, please correct and call {tool_call.name} again: {e}",
            )
            return response, None

    async def execute(
        self,
        request: str,
        output_tool: Optional[OutputTool] = None,
        request_tag: Optional[str] = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Run the agent loop.

        The model works with native tool calling. When ``output_tool`` is
        provided, the loop finishes when the model calls it with valid
        arguments, yielding a :class:`StructuredOutputEvent`. Otherwise a
        plain assistant message ends the loop with a :class:`MessageEvent`.

        ``request_tag`` marks the initial request message for compaction
        (see :attr:`~app.domain.models.message.LLMMessage.tag` and
        :meth:`~app.domain.models.memory.Memory.compact`) — e.g. the
        planner's full plan-JSON dump, which fully supersedes every earlier
        one. It is never applied to the later output-tool nudge messages.
        """
        self._output_tool = output_tool
        no_tool_call_streak = 0
        try:
            message = await self.ask(request, tag=request_tag)
            for _ in range(self.max_iterations):
                if not message.tool_calls:
                    # Plain message: final answer for unstructured runs; for
                    # structured runs, nudge the model to use the output tool.
                    if not output_tool:
                        break
                    no_tool_call_streak += 1
                    if no_tool_call_streak > self.max_consecutive_no_tool_call_nudges:
                        # A bounded, legible failure instead of exhausting
                        # max_iterations on a model that isn't going to
                        # comply — see the class attribute's docstring.
                        yield ErrorEvent(
                            error=(
                                f"Model did not call `{output_tool.name}` after "
                                f"{no_tool_call_streak - 1} nudges; giving up on "
                                "this step instead of exhausting the iteration budget."
                            )
                        )
                        return
                    # A model that needs guided decoding tends to answer in
                    # prose instead of calling the tool, and a plain nudge
                    # just burns iterations. Forcing a tool call converts an
                    # eventual max-iterations failure into a usable result.
                    forced = "required" if self.capabilities.needs_guided_decoding else None
                    message = await self.ask(
                        f"Submit your result by calling the `{output_tool.name}` tool.",
                        tool_choice=forced,
                    )
                    continue
                no_tool_call_streak = 0

                tool_responses = []
                structured_output: Optional[Any] = None
                for tool_call in message.tool_calls:
                    function_name = tool_call.name
                    if not tool_call.id:
                        tool_call.id = str(uuid.uuid4())
                    tool_call_id = tool_call.id
                    function_args = tool_call.args

                    if output_tool and function_name == output_tool.name:
                        response, structured_output = self._handle_output_call(tool_call)
                        tool_responses.append(response)
                        continue

                    tool = self.get_tool(function_name)
                    if not tool:
                        yield ErrorEvent(error=f"Unknown tool: {function_name}")
                        tool_responses.append(LLMMessage.tool(
                            tool_call_id=tool_call_id,
                            name=function_name,
                            content=f"Unknown tool: {function_name}",
                        ))
                        continue

                    # Generate event before tool call
                    yield ToolEvent(
                        status=ToolStatus.CALLING,
                        tool_call_id=tool_call_id,
                        tool_name=tool.toolkit.name,
                        function_name=function_name,
                        function_args=function_args
                    )

                    # Official terminalUpdate: poll shell console while the tool runs
                    shell_id = (
                        function_args.get("id")
                        if tool.toolkit.name == "shell" and isinstance(function_args, dict)
                        else None
                    )
                    # Delegation: drain the sub-agent's own events while its
                    # browse_web call is in flight, same shape as the shell
                    # console poll below — otherwise the UI sees one tool call
                    # that silently takes as long as the whole sub-task.
                    event_queue = getattr(tool.toolkit, "event_queue", None)
                    if tool.toolkit.name == "delegation" and event_queue is not None:
                        invoke_task = asyncio.create_task(self.invoke_tool(tool, tool_call))
                        while not invoke_task.done():
                            done, _ = await asyncio.wait({invoke_task}, timeout=0.5)
                            while not event_queue.empty():
                                yield event_queue.get_nowait()
                            if done:
                                break
                        while not event_queue.empty():
                            yield event_queue.get_nowait()
                        tool_result = await invoke_task
                    elif shell_id and hasattr(tool.toolkit, "sandbox"):
                        invoke_task = asyncio.create_task(self.invoke_tool(tool, tool_call))
                        last_fingerprint: Optional[str] = None

                        def _console_fingerprint(console: Any) -> str:
                            """Cheap change detector — avoid repr() on large consoles."""
                            if console is None:
                                return "0:"
                            if isinstance(console, str):
                                return f"s:{len(console)}:{console[-80:]}"
                            if isinstance(console, list):
                                if not console:
                                    return "0:"
                                last = console[-1]
                                if isinstance(last, dict):
                                    tail = f"{last.get('command', '')}|{str(last.get('output', ''))[-60:]}"
                                else:
                                    tail = str(last)[-80:]
                                return f"l:{len(console)}:{tail}"
                            return f"o:{type(console).__name__}:{str(console)[-80:]}"

                        while not invoke_task.done():
                            done, _ = await asyncio.wait({invoke_task}, timeout=1.0)
                            if done:
                                break
                            try:
                                view = await tool.toolkit.sandbox.view_shell(
                                    shell_id, console=True
                                )
                                console = (
                                    view.data.get("console", [])
                                    if view and getattr(view, "data", None)
                                    else []
                                )
                                fingerprint = _console_fingerprint(console)
                                if fingerprint != last_fingerprint:
                                    last_fingerprint = fingerprint
                                    yield TerminalUpdateEvent(
                                        shell_id=shell_id,
                                        output=console,
                                    )
                            except Exception:
                                logger.debug(
                                    "Shell live poll failed for %s",
                                    shell_id,
                                    exc_info=True,
                                )
                        tool_result = await invoke_task
                    else:
                        tool_result = await self.invoke_tool(tool, tool_call)

                    # Generate event after tool call
                    yield ToolEvent(
                        status=ToolStatus.CALLED,
                        tool_call_id=tool_call_id,
                        tool_name=tool.toolkit.name,
                        function_name=function_name,
                        function_args=function_args,
                        function_result=tool_result.artifact
                    )

                    tool_responses.append(tool_result)

                if structured_output is not None:
                    # Persist the tool responses so the tool-call pairing in
                    # memory stays consistent, then finish.
                    await self._add_to_memory(tool_responses)
                    yield StructuredOutputEvent(output=structured_output)
                    return

                message = await self.ask_with_messages(tool_responses)
            else:
                yield ErrorEvent(error="Maximum iteration count reached, failed to complete the task")

            yield MessageEvent(message=message.content)
        finally:
            self._output_tool = None

    async def _ensure_memory(self):
        if not self.memory:
            self.memory = await self._repository.get_memory(self._agent_id, self.name)
    
    # Matches both <think>...</think> and <thinking>...</thinking>, either
    # tag spelling, so this covers models using either convention.
    _THINK_BLOCK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.IGNORECASE | re.DOTALL)

    def _strip_thinking(self, message: LLMMessage) -> LLMMessage:
        """Drop prior reasoning blocks from a plain assistant turn's content.

        Only applies when ``capabilities.strip_thinking_from_history`` is
        set (Gemma 4 documents this explicitly) and only to turns with *no*
        tool calls — Gemma 4's own documentation calls out that thinking on
        tool-call turns must be preserved, since dropping it there
        measurably hurts tool-call quality.
        """
        if message.role != Role.ASSISTANT or message.tool_calls or not message.content:
            return message
        stripped = self._THINK_BLOCK_RE.sub("", message.content).strip()
        if stripped != message.content:
            message.content = stripped
        return message

    async def _add_to_memory(self, messages: List[LLMMessage]) -> None:
        """Update memory and save to repository"""
        await self._ensure_memory()
        if self.memory.empty:
            self.memory.add_message(LLMMessage.system(self.build_system_prompt()))
        if self.capabilities.strip_thinking_from_history:
            messages = [self._strip_thinking(m) for m in messages]
        self.memory.add_messages(messages)
        await self._repository.save_memory(self._agent_id, self.name, self.memory)
    
    async def _roll_back_memory(self) -> None:
        await self._ensure_memory()
        self.memory.roll_back()
        await self._repository.save_memory(self._agent_id, self.name, self.memory)

    @property
    def capabilities(self) -> "ModelCapabilities":
        """Capability profile of the model actually backing this agent.

        Read off the LLM gateway rather than passed in, so every construction
        path (session model, Celery worker, global default) gets the right
        profile without threading it through each agent constructor.
        """
        caps = getattr(self._llm, "capabilities", None)
        return caps if caps is not None else ModelCapabilities()

    @property
    def effective_context_tokens(self) -> int:
        """Compaction budget for this model.

        Built by construction — window minus what actually has to share it
        — rather than a flat fraction: the tool schemas sent on *every* call
        were previously uncounted entirely (they can be ~3k tokens on their
        own for a small model's full toolset), and the model's own reply
        needs headroom too. A 32K local model would otherwise be handed the
        100K class default and overflow.
        """
        window = self.capabilities.context_window
        if not window:
            return self.max_context_tokens

        schema_tokens = estimate_tokens(json.dumps(self.get_tool_schemas(), default=str))
        output_reserve = self.capabilities.max_output_tokens or self.default_output_reserve_tokens
        budget = window - schema_tokens - output_reserve - self.context_safety_margin_tokens
        return min(self.max_context_tokens, max(self.min_context_tokens, budget))

    async def ask_with_messages(
        self,
        messages: List[LLMMessage],
        tool_choice: Optional[str] = None,
    ) -> LLMMessage:
        await self._add_to_memory(messages)

        # Token-aware guard: reclaim budget from old tool results before the
        # context is sent to the model.
        budget = self.effective_context_tokens
        if self.memory.estimate_tokens() > budget:
            self.memory.compact(max_tokens=budget)
            await self._repository.save_memory(self._agent_id, self.name, self.memory)

        context = list(self.memory.get_messages())
        message = await self._llm.ask(
            messages=context,
            tools=self.get_tool_schemas(),
            tool_choice=tool_choice or self.tool_choice,
        )
        logger.debug(f"Response from model: {message}")

        if not self.capabilities.supports_parallel_tool_calls and len(message.tool_calls) > 1:
            # Defensive: the gateway already asks the provider not to emit
            # more than one (see langchain_llm._parallel_tool_calls_kwargs),
            # but a local model can ignore that hint. Keeping only the first
            # here, before it enters memory, is what actually enforces the
            # capability regardless of provider.
            logger.debug(
                "Model capabilities disallow parallel tool calls; keeping only "
                "the first of %d returned by this turn.",
                len(message.tool_calls),
            )
            message.tool_calls = message.tool_calls[:1]

        await self._add_to_memory([message])
        return message

    async def ask(
        self,
        request: str,
        tool_choice: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> LLMMessage:
        return await self.ask_with_messages(
            [LLMMessage.user(request, tag=tag)],
            tool_choice=tool_choice,
        )
    
    async def roll_back(self, message: Message):
        await self._ensure_memory()
        last_message = self.memory.get_last_message()
        if not last_message:
            return
        if last_message.role != Role.ASSISTANT:
            return
        if not last_message.tool_calls:
            return
        tool_call = last_message.tool_calls[0]
        function_name = tool_call.name
        tool_call_id = tool_call.id
        if function_name == "message_ask_user":
            self.memory.add_message(LLMMessage.tool(tool_call_id=tool_call_id, name=function_name, content=message.message))
        else:
            self.memory.roll_back()
        await self._repository.save_memory(self._agent_id, self.name, self.memory)
    
    async def compact_memory(self) -> None:
        await self._ensure_memory()
        self.memory.compact()
        await self._repository.save_memory(self._agent_id, self.name, self.memory)
