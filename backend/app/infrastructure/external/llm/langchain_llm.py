"""LangChain implementation of the domain :class:`LLM` gateway.

Keeps all LangChain-specific concerns — model instantiation, message
translation, tool binding, the JSON-repair chain and model-level retries —
inside the infrastructure layer, so the domain agents depend only on the
:class:`app.domain.external.llm.LLM` Protocol and domain message types.
"""
import logging
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from langchain.chat_models import init_chat_model
from langchain.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_classic.output_parsers.retry import RetryWithErrorOutputParser
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from app.core.config import Settings, get_settings
from app.domain.models.message import LLMMessage, Role, ToolCall
from app.domain.models.model_capabilities import ModelCapabilities
from app.infrastructure.external.llm.robust_json_parser import (
    RobustJsonParser,
    ToolCallParseError,
)

logger = logging.getLogger(__name__)

# Distinguishes "caller did not specify a base_url, inherit API_BASE" from
# "caller specified no base_url, use the provider default". Registry models
# rely on the latter: a Gemini or DeepSeek entry must not silently inherit an
# API_BASE that points at some other provider's endpoint.
_INHERIT_API_BASE = object()


def _tool_names(tools: Optional[List[Dict[str, Any]]]) -> List[str]:
    """Extract ``function.name`` from each OpenAI-shaped tool schema.

    Feeds ``RobustJsonParser``'s stage-0 text-recovery, which only promotes
    a recovered call whose name was actually offered this turn.
    """
    if not tools:
        return []
    names = []
    for t in tools:
        name = (t.get("function") or {}).get("name") if isinstance(t, dict) else None
        if name:
            names.append(name)
    return names


def _parallel_tool_calls_kwargs(capabilities: ModelCapabilities, provider: Optional[str]) -> Dict[str, Any]:
    """``bind_tools()`` kwargs enforcing ``supports_parallel_tool_calls=False``.

    Only the OpenAI-compatible ``bind_tools()`` signature is known to accept
    ``parallel_tool_calls`` across the providers ``init_chat_model`` supports;
    other providers could error on an unrecognized bind kwarg, so this stays
    scoped to where local models are actually routed (``provider="openai"``
    with a ``base_url`` override, e.g. LM Studio). ``base.py``'s execute loop
    also defensively keeps only the first tool call for these models,
    regardless of provider, in case the model ignores this hint anyway.
    """
    if not capabilities.supports_parallel_tool_calls and provider == "openai":
        return {"parallel_tool_calls": False}
    return {}


def _sanitize_json_schema(node: Any, *, properties_depth: int = 0) -> Any:
    """Recursively rewrite a tool JSON Schema into a shape every provider's
    schema-to-grammar compiler can handle.

    Tool definitions come from the caller (e.g. OpenClaw's own built-in
    tools, forwarded verbatim by the Claw proxy) and are outside our
    control, so callers can't be relied on to only use constructs every
    engine supports. Every rewrite below was found by reproducing a real
    "agent lifecycle error"/"failed to parse grammar" against LM
    Studio/llama.cpp with a real tool payload (bisecting the actual failing
    request down to the exact schema fragment, not guessed) — each is,
    individually, enough to fail the *entire* request (not just the one
    offending tool), so this always runs before ``bind_tools``, for every
    provider, not just local ones:

    - Anchor unanchored regex ``pattern`` keys. JSON Schema itself treats an
      unanchored pattern as a substring match, but llama.cpp's grammar
      compiler rejects anything not wrapped in ``^...$`` outright ("Pattern
      must start with '^' and end with '$'"). Wrapping in ``^(?:...)$`` is a
      strictly narrower match, safe everywhere.
    - Drop ``pattern``, ``minLength`` and ``maxLength`` entirely once they
      sit two or more ``properties`` levels below the tool's root schema
      (e.g. ``parameters.properties.job.properties.declarationKey.pattern``,
      or ``...job.properties.trigger.properties.script.maxLength`` one
      level deeper still) — confirmed live against LM Studio, by bisecting
      OpenClaw's real ``cron`` tool schema down to single-key repros, that
      llama.cpp's grammar compiler fails ("failed to parse grammar") on
      *any* string this deep constrained by pattern OR length, regardless
      of the constraint's own value, while the identical constraint one
      level up (a direct property of the root schema) works fine. The
      field's ``description`` still reaches the model; only the format
      constraint is lost, and only when nested this deep.
    - Replace ``patternProperties`` with ``additionalProperties``.
      llama.cpp's converter doesn't support ``patternProperties`` at all
      ("failed to parse grammar" — OpenClaw's ``exec`` tool, whose ``env``
      parameter is ``{"patternProperties": {"^.*$": {...}}}``, i.e. "any
      string key"). Merging every pattern-keyed schema into one
      ``additionalProperties`` schema is the closest equivalent every
      engine (including llama.cpp) does support; in practice there is
      always exactly one pattern here and it's already "match anything", so
      this loses no real constraint.
    """
    if isinstance(node, dict):
        out: Dict[str, Any] = {}
        for key, value in node.items():
            if key == "pattern" and isinstance(value, str) and value:
                if properties_depth >= 2:
                    continue  # drop: unsupported this deep, regardless of content
                if not (value.startswith("^") and value.endswith("$")):
                    value = f"^(?:{value})$"
                out[key] = value
                continue
            if key in ("minLength", "maxLength") and properties_depth >= 2:
                continue  # drop: unsupported this deep, regardless of value
            if key == "patternProperties":
                continue
            if key == "properties" and isinstance(value, dict):
                out[key] = {
                    prop_name: _sanitize_json_schema(prop_schema, properties_depth=properties_depth + 1)
                    for prop_name, prop_schema in value.items()
                }
                continue
            out[key] = _sanitize_json_schema(value, properties_depth=properties_depth)
        pattern_properties = node.get("patternProperties")
        if isinstance(pattern_properties, dict) and "additionalProperties" not in out:
            merged: Dict[str, Any] = {}
            for sub_schema in pattern_properties.values():
                if isinstance(sub_schema, dict):
                    merged.update(_sanitize_json_schema(sub_schema, properties_depth=properties_depth))
            if merged:
                out["additionalProperties"] = merged
        return out
    if isinstance(node, list):
        return [_sanitize_json_schema(item, properties_depth=properties_depth) for item in node]
    return node


class LangchainLLM:
    """Concrete :class:`LLM` gateway backed by LangChain chat models."""

    _JSON_PARSE_PROMPT = PromptTemplate.from_template(
        "Extract or repair the JSON from the following LLM output.\n\n{input}"
    )

    def __init__(
        self,
        settings: Optional[Settings] = None,
        max_retries: int = 3,
        model_name: Optional[str] = None,
        model_provider: Optional[str] = None,
        base_url: Any = _INHERIT_API_BASE,
        api_key: Optional[str] = None,
        capabilities: Optional[ModelCapabilities] = None,
    ):
        settings = settings or get_settings()
        self._max_retries = max_retries
        self.capabilities = capabilities or ModelCapabilities()

        target_model = model_name or settings.model_name
        target_provider = model_provider or settings.model_provider
        self._provider = target_provider
        target_base_url = settings.api_base if base_url is _INHERIT_API_BASE else base_url
        # The global API_KEY is only for the bare default gateway (no model
        # named). A registry-resolved model (model_name/model_provider given)
        # must use exactly its own stored credential, even if that's none —
        # a local LM Studio/Ollama model with no key must never silently
        # inherit a different provider's secret (e.g. Gemini's key sent to an
        # OpenAI-compatible endpoint, which is a real credential leak, not
        # just a wrong-provider error).
        is_named_model = model_name is not None or model_provider is not None
        target_api_key = api_key if is_named_model else (api_key or settings.api_key)

        kwargs: Dict[str, Any] = dict(
            model=target_model,
            model_provider=target_provider,
            # A local/small model tends to need a lower temperature for
            # reliable tool calling than a hosted frontier default.
            temperature=(
                self.capabilities.temperature
                if self.capabilities.temperature is not None
                else settings.temperature
            ),
            # A small model's own output limit is lower than the global
            # default; exceeding it is a hard provider error, not a truncation.
            max_tokens=self.capabilities.max_output_tokens or settings.max_tokens,
        )
        if target_base_url and target_provider != "google_genai":
            kwargs["base_url"] = target_base_url
        if target_api_key:
            kwargs["api_key"] = target_api_key
        if settings.extra_headers:
            kwargs["default_headers"] = settings.extra_headers
        if self.capabilities.request_timeout is not None:
            # "timeout" is the cross-provider alias LangChain's chat model
            # constructors accept (e.g. ChatOpenAI's `request_timeout` field).
            # There is otherwise no client-side timeout anywhere in this call
            # chain, so a hung local endpoint would block the session forever.
            kwargs["timeout"] = self.capabilities.request_timeout
        self._model = init_chat_model(**kwargs)

        self._json_output_parser = RetryWithErrorOutputParser.from_llm(
            parser=JsonOutputParser(),
            llm=self._model,
            max_retries=self._max_retries,
        )

    # ------------------------------------------------------------------
    # Message translation (domain <-> LangChain)
    # ------------------------------------------------------------------

    def _to_langchain(self, messages: List[LLMMessage]) -> List[Any]:
        lc_messages: List[Any] = []
        for m in messages:
            additional_kwargs = getattr(m, "additional_kwargs", {}) or {}
            if m.role == Role.SYSTEM:
                lc_messages.append(SystemMessage(content=m.content, additional_kwargs=additional_kwargs))
            elif m.role == Role.USER:
                lc_messages.append(HumanMessage(content=m.content, additional_kwargs=additional_kwargs))
            elif m.role == Role.ASSISTANT:
                tool_calls = [
                    {
                        "name": tc.name,
                        "args": tc.args,
                        "id": tc.id or None,
                        "type": "tool_call",
                    }
                    for tc in m.tool_calls
                ]
                lc_messages.append(
                    AIMessage(content=m.content, tool_calls=tool_calls, additional_kwargs=additional_kwargs)
                )
            elif m.role == Role.TOOL:
                lc_messages.append(
                    ToolMessage(
                        tool_call_id=m.tool_call_id or "",
                        name=m.name,
                        content=m.content,
                        additional_kwargs=additional_kwargs,
                    )
                )
        return lc_messages

    @staticmethod
    def _extract_text_content(raw: Any) -> str:
        """Flatten LangChain's ``AIMessage.content`` to plain text.

        Some providers (e.g. Gemini 2.5 with extended thinking) return
        content as a list of typed blocks — ``[{"type": "text", "text": "…",
        "extras": {"signature": "…"}}]`` — instead of a plain string. Without
        this, ``str(raw)`` on the list leaked the raw Python repr (including
        the opaque thinking-signature blob) straight into the chat bubble.
        """
        if isinstance(raw, str):
            return raw
        if raw is None:
            return ""
        if isinstance(raw, list):
            parts: List[str] = []
            for block in raw:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                    # Non-text blocks (e.g. thinking-only, signatures) carry
                    # no user-visible text — silently omitted, not stringified.
            return "".join(parts)
        return str(raw)

    def _from_langchain(self, message: AIMessage) -> LLMMessage:
        tool_calls = [
            ToolCall(
                id=tc.get("id") or "",
                name=tc.get("name") or "",
                args=tc.get("args") or {},
            )
            for tc in (message.tool_calls or [])
        ]
        content = self._extract_text_content(message.content)
        additional_kwargs = getattr(message, "additional_kwargs", {}) or {}
        return LLMMessage.assistant(
            content=content,
            tool_calls=tool_calls,
            additional_kwargs=additional_kwargs,
        )

    # ------------------------------------------------------------------
    # LLM Protocol
    # ------------------------------------------------------------------

    async def ask(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[str] = None,
        tool_choice: Optional[str] = None,
    ) -> LLMMessage:
        rf = {"type": response_format} if response_format else None

        bind_kwargs: Dict[str, Any] = {}
        if rf is not None:
            bind_kwargs["response_format"] = rf
        if tool_choice is not None:
            bind_kwargs["tool_choice"] = tool_choice
        model = self._model.bind(**bind_kwargs) if bind_kwargs else self._model
        if tools:
            bind_tools_kwargs = _parallel_tool_calls_kwargs(self.capabilities, self._provider)
            model = model.bind_tools(_sanitize_json_schema(tools), **bind_tools_kwargs)

        # Stage 0: recovers a tool call a model emitted as text instead of
        # the native channel (known_tools validates the recovered name).
        # Stages 1-3: RobustJsonParser repairs invalid tool call JSON locally
        # and via a cheap fixing call. Stages 4-5: this outer loop retries the
        # model, silently first then with error feedback.
        chain = model | RobustJsonParser.from_llm(self._model, known_tools=_tool_names(tools))

        context = self._to_langchain(messages)
        message: Optional[AIMessage] = None
        for attempt in range(self._max_retries):
            try:
                message = await chain.ainvoke(context)
                break
            except ToolCallParseError as e:
                if attempt == self._max_retries - 1:
                    raise
                logger.warning(
                    "Attempt %d/%d: tool call JSON repair failed, retrying model",
                    attempt + 1,
                    self._max_retries,
                )
                if attempt > 0:
                    # Stage 5: append the failed message and error feedback.
                    context = e.make_retry_context(context)

        logger.debug("Response from model: %s", message)
        return self._from_langchain(message)

    async def parse_json(self, text: str) -> Dict[str, Any]:
        """Extract/repair a JSON object from raw model output."""
        prompt_value = self._JSON_PARSE_PROMPT.format_prompt(input=text)
        return await self._json_output_parser.aparse_with_prompt(text, prompt_value)


# Constructing a LangchainLLM builds an HTTP client and a retrying output
# parser, so gateways are cached per distinct target rather than per call.
# The registry bounds the key space in practice; the cap is a safety net.
_MAX_CACHED_GATEWAYS = 32
_gateway_cache: "OrderedDict[Tuple[Optional[str], Optional[str], Any, Optional[str]], LangchainLLM]" = OrderedDict()


def get_langchain_llm(
    model: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Any = _INHERIT_API_BASE,
    api_key: Optional[str] = None,
    capabilities: Optional[ModelCapabilities] = None,
) -> LangchainLLM:
    """Return a LangChain LLM gateway for a target, cached per target.

    Called with no arguments it yields the globally configured gateway, which
    is what the DI container and the Celery worker use. Pass ``base_url=None``
    explicitly to mean "no base_url" rather than "inherit API_BASE".
    """
    # Capabilities affect construction (max_tokens) and per-call behavior
    # (guided decoding), so they must be part of the cache key — otherwise an
    # admin editing a model's capabilities would keep getting the old gateway.
    caps_key = capabilities.model_dump_json() if capabilities else None
    key = (provider, model, base_url, caps_key)
    cached = _gateway_cache.get(key)
    if cached is not None:
        _gateway_cache.move_to_end(key)
        return cached

    logger.info(
        "Creating LangchainLLM gateway (provider=%s, model=%s, base_url=%s)",
        provider or "default", model or "default", base_url or "default",
    )
    gateway = LangchainLLM(
        model_name=model,
        model_provider=provider,
        base_url=base_url,
        api_key=api_key,
        capabilities=capabilities,
    )
    _gateway_cache[key] = gateway
    while len(_gateway_cache) > _MAX_CACHED_GATEWAYS:
        _gateway_cache.popitem(last=False)
    return gateway
