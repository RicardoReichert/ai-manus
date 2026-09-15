"""RobustJsonParser

A layered JSON repair pipeline for tool call arguments, implemented as a
LangChain Runnable[AIMessage, AIMessage] so it can be composed with a model
using the | operator:

    chain = model_with_tools | RobustJsonParser.from_llm(llm)

Stage 0 — text tool-call recovery: some small local models, when the
runtime's chat template doesn't map their native tool-call format into the
API's tool_calls channel, emit the call as plain text instead — the model
picked the right tool and arguments, it just never touched the tool-call
channel at all (so both ``tool_calls`` and ``invalid_tool_calls`` come back
empty; this is a different failure from stages 1-3's malformed-JSON case).
Recognized text shapes, in the order tried:

  - ``<tool_call>{"name": ..., "arguments": {...}}</tool_call>``
  - `` ```tool_name\\n{...}``` `` — a fenced block whose language/name slot
    is the tool name and whose body is the raw arguments.
  - `` ```json\\n{"name": ..., "arguments": {...}}``` `` — generic fenced form.

A recovered call is only promoted when its name matches a tool the caller
actually offered this turn (``known_tools``); an unrecognized name is left
as plain text rather than guessed at.

Repair stages applied in order when invalid_tool_calls are detected:

  Stage 1 — parse_partial_json   : repair truncated / incomplete JSON locally.
  Stage 2 — parse_json_markdown  : repair JSON wrapped in markdown code fences.
  Stage 3 — OutputFixingParser   : ask the LLM to rewrite only the broken JSON
                                   string (wraps JsonOutputParser, cheap call).

When stages 1-3 are all insufficient, a ToolCallParseError is raised.  The
caller can catch it and implement model-level retries (stages 4-5):

  Stage 4 — silent model retry   : re-invoke the chain without extra context
                                   (mirrors RetryOutputParser).
  Stage 5 — error model retry    : re-invoke with the failed AIMessage and
                                   error details appended (mirrors
                                   RetryWithErrorOutputParser).

Stages 4-5 are intentionally left to the caller so that the Runnable stays
composable and stateless.  ToolCallParseError exposes a make_retry_context()
helper to build the stage-5 context without duplicating the template.
"""
import asyncio
import json
import logging
import re
from typing import Any, Optional, Sequence, Tuple

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.tool import tool_call as create_tool_call
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.utils.json import parse_json_markdown, parse_partial_json
from langchain_classic.output_parsers.fix import OutputFixingParser

logger = logging.getLogger(__name__)

# Stage 0 lead-ins: where a text-embedded tool call can start. Matched
# case-sensitively on purpose — these are literal protocol tokens/fences,
# not prose that happens to contain the words.
_TOOL_CALL_TAG_START_RE = re.compile(r"<tool_call>\s*")
_FENCE_START_RE = re.compile(r"```\s*([a-zA-Z_][a-zA-Z0-9_]*)?\s*")


def _extract_balanced_json_object(text: str, start: int) -> Optional[str]:
    """Return the first balanced ``{...}`` object starting at ``start``.

    ``start`` must index a ``{``. Tolerates an object left unterminated at
    end-of-string (a truncated generation) by returning everything from
    ``start`` onward — the caller feeds that to ``parse_partial_json``,
    which already handles truncated JSON elsewhere in this module.
    """
    if start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _parse_json_object(raw: str) -> Optional[dict]:
    """Strict parse first, falling back to the module's own tolerant parser
    for a truncated object (see ``_extract_balanced_json_object``)."""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    try:
        parsed = parse_partial_json(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return None


def _extract_text_tool_call(text: str) -> Optional[Tuple[str, dict, str]]:
    """Find a tool call embedded as text. Returns ``(name, args, matched)``,
    where ``matched`` is the exact substring to remove from the message
    content, or ``None`` if no recognizable shape is present."""
    tag_match = _TOOL_CALL_TAG_START_RE.search(text)
    if tag_match:
        obj_text = _extract_balanced_json_object(text, tag_match.end())
        if obj_text is not None:
            payload = _parse_json_object(obj_text)
            if isinstance(payload, dict):
                name, args = payload.get("name"), payload.get("arguments")
                if isinstance(name, str) and isinstance(args, dict):
                    matched = text[tag_match.start() : tag_match.end() + len(obj_text)]
                    # Absorb a trailing </tool_call> if present, so it isn't
                    # left dangling in the remaining prose.
                    tail = text[tag_match.end() + len(obj_text) :]
                    close = re.match(r"\s*</tool_call>", tail)
                    if close:
                        matched += close.group(0)
                    return name, args, matched

    fence_match = _FENCE_START_RE.search(text)
    if fence_match:
        label = (fence_match.group(1) or "").strip()
        obj_text = _extract_balanced_json_object(text, fence_match.end())
        if obj_text is not None:
            body = _parse_json_object(obj_text)
            if isinstance(body, dict):
                matched = text[fence_match.start() : fence_match.end() + len(obj_text)]
                tail = text[fence_match.end() + len(obj_text) :]
                close = re.match(r"\s*```", tail)
                if close:
                    matched += close.group(0)
                if label and label != "json":
                    # ```tool_name\n{...}``` — the fence's own label slot is
                    # the tool name; the object is the raw arguments.
                    return label, body, matched
                # ```json\n{"name": ..., "arguments": {...}}``` — generic.
                name, args = body.get("name"), body.get("arguments")
                if isinstance(name, str) and isinstance(args, dict):
                    return name, args, matched

    return None

_RETRY_WITH_ERROR_TEMPLATE = (
    "Your previous response contained invalid JSON in the tool call arguments.\n"
    "Error details:\n{error}\n\n"
    "Please resend the tool call with correctly formatted JSON arguments."
)


class ToolCallParseError(OutputParserException):
    """Raised when stages 1-3 cannot repair all invalid_tool_calls.

    Carries the partially-repaired AIMessage and per-call error details so
    callers can implement stages 4-5 (model-level retries) without
    re-discovering the errors.
    """

    def __init__(
        self,
        message: str,
        invalid_message: AIMessage,
        error_details: list[str],
    ) -> None:
        super().__init__(message)
        self.invalid_message = invalid_message
        self.error_details = error_details

    def make_retry_context(self, context: list[Any]) -> list[Any]:
        """Build a stage-5 context by appending error feedback to *context*.

        Args:
            context: Current conversation messages.

        Returns:
            A new list with the failed AIMessage and a corrective HumanMessage
            appended, ready to be passed back to the model.
        """
        error_str = "\n\n".join(self.error_details)
        return context + [
            self.invalid_message,
            HumanMessage(content=_RETRY_WITH_ERROR_TEMPLATE.format(error=error_str)),
        ]


class RobustJsonParser(Runnable[AIMessage, AIMessage]):
    """Layered JSON repair for tool call arguments (stages 1-3).

    Implements Runnable[AIMessage, AIMessage] so it composes cleanly with a
    bound model via the | operator::

        chain = (
            model
            .bind(response_format=..., tool_choice=...)
            .bind_tools(tools)
            | RobustJsonParser.from_llm(llm)
        )
        message = await chain.ainvoke(messages)

    Combines parse_partial_json, parse_json_markdown, JsonOutputParser, and
    OutputFixingParser into an escalating repair pipeline.  Raises
    ToolCallParseError (a subclass of OutputParserException) when all three
    stages are exhausted, so callers can add model-level retries (stages 4-5)
    on top — e.g. via chain.with_retry() or a manual loop.
    """

    def __init__(self, llm: BaseChatModel, known_tools: Optional[Sequence[str]] = None) -> None:
        self._llm = llm
        # Stage 0 only ever promotes a recovered call whose name is in this
        # set — an unrecognized name is left as plain text rather than
        # guessed at. None/empty disables stage 0 entirely (e.g. a call with
        # no tools bound has nothing to recover into).
        self._known_tools = set(known_tools) if known_tools else None
        # Stage 3: OutputFixingParser wraps JsonOutputParser.
        # JsonOutputParser validates the fixed string is well-formed JSON;
        # OutputFixingParser drives one LLM repair call on failure.
        self._fixing_parser: OutputFixingParser = OutputFixingParser.from_llm(
            llm=llm,
            parser=JsonOutputParser(),
            max_retries=1,
        )

    @classmethod
    def from_llm(cls, llm: BaseChatModel, known_tools: Optional[Sequence[str]] = None) -> "RobustJsonParser":
        """Create a RobustJsonParser from a chat model.

        Args:
            llm: Chat model used for Stage 3 (OutputFixingParser) repair.
            known_tools: Tool names offered this turn, used to validate a
                stage-0 text-recovered call's name before promoting it.

        Returns:
            A RobustJsonParser instance ready for use in a chain.
        """
        return cls(llm=llm, known_tools=known_tools)

    # ------------------------------------------------------------------
    # Stage 1: parse_partial_json
    # ------------------------------------------------------------------

    def _stage1_partial_json(self, raw: str) -> Optional[dict]:
        """Stage 1: tolerates truncated / incomplete JSON."""
        try:
            result = parse_partial_json(raw)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Stage 2: parse_json_markdown
    # ------------------------------------------------------------------

    def _stage2_json_markdown(self, raw: str) -> Optional[dict]:
        """Stage 2: strips markdown code fences before parsing."""
        try:
            result = parse_json_markdown(raw)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Stage 3: OutputFixingParser(JsonOutputParser)
    # ------------------------------------------------------------------

    async def _stage3_output_fixing(self, raw: str) -> Optional[dict]:
        """Stage 3: asks LLM to rewrite the broken JSON string."""
        try:
            result = await self._fixing_parser.aparse(raw)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Per-message repair (Stages 1-3)
    # ------------------------------------------------------------------

    async def _repair_invalid_tool_calls(self, message: AIMessage) -> AIMessage:
        """Attempt to repair each invalid_tool_call through stages 1-3.

        Repaired calls are promoted from invalid_tool_calls to tool_calls.
        Calls that cannot be repaired remain in invalid_tool_calls.
        """
        if not message.invalid_tool_calls:
            return message

        repaired_calls = list(message.tool_calls)
        still_invalid = []

        for itc in message.invalid_tool_calls:
            name: str = itc.get("name") or ""
            raw_args: str = itc.get("args") or ""

            fixed: Optional[dict] = (
                self._stage1_partial_json(raw_args)
                or self._stage2_json_markdown(raw_args)
                or await self._stage3_output_fixing(raw_args)
            )

            if fixed is not None:
                logger.info(
                    "Repaired invalid tool call '%s' (raw args length: %d)",
                    name,
                    len(raw_args),
                )
                repaired_calls.append(
                    create_tool_call(name=name, args=fixed, id=itc.get("id"))
                )
            else:
                still_invalid.append(itc)

        return message.model_copy(
            update={
                "tool_calls": repaired_calls,
                "invalid_tool_calls": still_invalid,
            }
        )

    # ------------------------------------------------------------------
    # Stage 0: text tool-call recovery
    # ------------------------------------------------------------------

    def _recover_tool_call_from_text(self, message: AIMessage) -> Optional[AIMessage]:
        """Recover a tool call the model emitted as text instead of using
        the native tool-call channel at all — see the module docstring.

        Only runs when there is nothing else to work with (no native and no
        malformed tool call already present), and only promotes a candidate
        whose name is a real, currently-offered tool.
        """
        if message.tool_calls or message.invalid_tool_calls:
            return None
        if not self._known_tools:
            return None
        content = message.content
        if not isinstance(content, str) or not content.strip():
            return None

        candidate = _extract_text_tool_call(content)
        if candidate is None:
            return None
        name, args, matched = candidate
        if name not in self._known_tools:
            logger.debug(
                "Text-embedded tool call named '%s' is not a known tool this turn; leaving as text",
                name,
            )
            return None

        logger.info(
            "Recovered tool call '%s' that the model emitted as text instead of a native tool_call",
            name,
        )
        remaining = content.replace(matched, "", 1).strip()
        return message.model_copy(
            update={
                "content": remaining,
                "tool_calls": [create_tool_call(name=name, args=args, id=None)],
            }
        )

    def _collect_errors(self, message: AIMessage) -> list[str]:
        return [
            f"Tool '{itc.get('name', 'unknown')}': "
            f"{itc.get('error', 'JSON parse error')}\n"
            f"Raw arguments: {itc.get('args', '')}"
            for itc in (message.invalid_tool_calls or [])
        ]

    # ------------------------------------------------------------------
    # Runnable interface
    # ------------------------------------------------------------------

    def invoke(
        self,
        input: AIMessage,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> AIMessage:
        return asyncio.get_event_loop().run_until_complete(
            self.ainvoke(input, config, **kwargs)
        )

    async def ainvoke(
        self,
        input: AIMessage,
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> AIMessage:
        """Repair invalid_tool_calls in *input* through stages 1-3.

        Args:
            input: The AIMessage produced by the model.
            config: Optional LangChain runnable config (unused but required by
                the Runnable interface).

        Returns:
            AIMessage with all tool call arguments successfully parsed.

        Raises:
            ToolCallParseError: If one or more tool calls cannot be repaired by
                stages 1-3.  The exception carries the partial-repaired
                AIMessage and per-call error details for the caller to use in
                stage-4/5 model retries.
        """
        recovered = self._recover_tool_call_from_text(input)
        message = await self._repair_invalid_tool_calls(recovered if recovered is not None else input)

        if message.invalid_tool_calls:
            errors = self._collect_errors(message)
            raise ToolCallParseError(
                message=(
                    f"Tool call JSON repair failed ({len(message.invalid_tool_calls)} "
                    f"call(s) unrepairable).\n" + "\n".join(errors)
                ),
                invalid_message=message,
                error_details=errors,
            )

        return message
