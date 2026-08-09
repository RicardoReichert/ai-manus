"""
OpenAI-compatible API proxy for manus-claw.
All LLM requests from OpenClaw containers go through this endpoint,
authenticated using per-user API keys.

Requests are served via the same LangChain-backed gateway
(:mod:`app.infrastructure.external.llm.langchain_llm`) and model registry
(:mod:`app.infrastructure.external.llm.model_registry`) the rest of the app
uses, rather than forwarding raw HTTP to ``settings.api_base``. The previous
implementation assumed ``api_base`` was always an OpenAI-compatible
``/chat/completions`` endpoint, which breaks for any other provider (e.g. the
default here is Gemini/``google_genai``, which speaks a different protocol
entirely) — Claw would 200 with a synthetic SSE error and its agent runtime
would surface "agent lifecycle error".
"""
import json
import logging
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.application.services.claw_service import ClawService
from app.core.config import get_settings
from app.domain.models.message import LLMMessage, Role, ToolCall
from app.infrastructure.external.llm.langchain_llm import get_langchain_llm
from app.infrastructure.external.llm.model_registry import (
    api_key_for,
    get_default_model,
    resolve_model,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["openai-proxy"])


def _extract_bearer_token(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


async def _get_claw_service() -> ClawService:
    from app.interfaces.dependencies import get_claw_service
    return get_claw_service()


def _openai_error_response(status_code: int, message: str, error_type: str) -> JSONResponse:
    """Return an OpenAI-compatible error JSON response directly, bypassing the global handler."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type}},
    )


# ----------------------------------------------------------------------
# OpenAI wire format <-> domain LLMMessage
# ----------------------------------------------------------------------

def _openai_content_to_text(content: Any) -> str:
    """OpenAI content is either a string or a list of content parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "".join(parts)
    return str(content)


def _openai_tool_calls_to_domain(tool_calls: Optional[List[dict]]) -> List[ToolCall]:
    result = []
    for tc in tool_calls or []:
        fn = tc.get("function", {}) or {}
        raw_args = fn.get("arguments", "{}")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except json.JSONDecodeError:
            args = {}
        result.append(ToolCall(id=tc.get("id") or "", name=fn.get("name") or "", args=args))
    return result


def _openai_messages_to_domain(messages: List[dict]) -> List[LLMMessage]:
    domain_messages: List[LLMMessage] = []
    for m in messages:
        role = m.get("role")
        content = _openai_content_to_text(m.get("content"))
        if role == "system":
            domain_messages.append(LLMMessage.system(content))
        elif role == "user":
            domain_messages.append(LLMMessage.user(content))
        elif role == "assistant":
            domain_messages.append(
                LLMMessage.assistant(content, tool_calls=_openai_tool_calls_to_domain(m.get("tool_calls")))
            )
        elif role == "tool":
            domain_messages.append(
                LLMMessage.tool(
                    tool_call_id=m.get("tool_call_id") or "",
                    name=m.get("name") or "",
                    content=content,
                )
            )
        else:
            logger.warning(f"[openai-proxy] Skipping message with unknown role: {role!r}")
    return domain_messages


def _domain_tool_calls_to_openai(tool_calls: List[ToolCall]) -> List[dict]:
    return [
        {
            "id": tc.id or f"call_{uuid.uuid4().hex[:24]}",
            "type": "function",
            "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
        }
        for tc in tool_calls
    ]


def _domain_message_to_openai(message: LLMMessage, model: str) -> dict:
    """Build a non-streaming OpenAI chat.completion response."""
    msg: Dict[str, Any] = {"role": "assistant", "content": message.content or None}
    finish_reason = "stop"
    if message.tool_calls:
        msg["tool_calls"] = _domain_tool_calls_to_openai(message.tool_calls)
        finish_reason = "tool_calls"
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": msg, "finish_reason": finish_reason}],
    }


def _domain_message_to_openai_stream_chunks(message: LLMMessage, model: str) -> List[dict]:
    """The gateway's ask() is not token-streaming, so the whole reply is
    delivered as a single delta chunk followed by a finish chunk — still a
    valid OpenAI SSE stream, just not incremental."""
    chat_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())
    delta: Dict[str, Any] = {"role": "assistant", "content": message.content or None}
    finish_reason = "stop"
    if message.tool_calls:
        delta["tool_calls"] = _domain_tool_calls_to_openai(message.tool_calls)
        finish_reason = "tool_calls"
    base = {"id": chat_id, "object": "chat.completion.chunk", "created": created, "model": model}
    return [
        {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}]},
    ]


async def _resolve_llm_target(requested_model: Optional[str], api_key: Optional[str] = None):
    """Resolve which registry model this Claw request should run against.

    Claw's openclaw.json hardcodes the alias ``manus-proxy/default`` (baked in
    at container build time), so the alias cannot carry the session's choice.
    Resolution order: the model pinned to the session that owns this api_key,
    then (only when every session shares one physical container — see below)
    the most recently updated session, then the literal requested id if it
    happens to name a real registry entry, then the first enabled model.
    This is what lets switching models (via session restart) take effect
    without regenerating config.

    Resolving by api_key rather than user_id matters now that a user can
    have several concurrent sessions, each potentially on a different
    model — the api_key IS the session, one-to-one, so it's the only
    correct way to know which session's container is actually calling in.

    That breaks down when ``settings.claw_address`` is set (development's
    ``FixedClawRuntime``): every session shares the one physical container,
    which is started once with a single fixed system API key baked into its
    openclaw.json — never a session's own key — so ``get_by_api_key`` above
    can never match, and every call would silently fall back to the first
    enabled model regardless of what was chosen in the UI. In that mode
    only, once the caller is confirmed to be that fixed system key, fall
    back to the most recently updated session instead: with one shared
    container there is no way to attribute a call to a specific session, so
    "whichever session the operator most recently touched" is the best
    available signal of intent. Never consulted in production, where each
    session's own container makes the exact api_key match above authoritative.
    """
    desc = None
    claw_service = None

    if api_key:
        claw_service = await _get_claw_service()
        session = await claw_service.claw_repository.get_by_api_key(api_key)
        if session and session.model_id:
            desc = await resolve_model(session.model_id)

    if desc is None and api_key:
        settings = get_settings()
        if settings.claw_address and settings.claw_api_key and api_key == settings.claw_api_key:
            claw_service = claw_service or await _get_claw_service()
            session = await claw_service.claw_repository.get_most_recently_updated()
            if session and session.model_id:
                desc = await resolve_model(session.model_id)

    if desc is None:
        candidate = (requested_model or "").removeprefix("manus-proxy/")
        if candidate and candidate != "default":
            desc = await resolve_model(candidate)

    if desc is None:
        desc = await get_default_model()

    if desc is None:
        raise RuntimeError(
            "No models are registered. Add one in Settings > Models."
        )

    return get_langchain_llm(
        model=desc.model,
        provider=desc.provider,
        base_url=desc.base_url,
        api_key=await api_key_for(desc),
        capabilities=desc.capabilities,
    )


async def _stream_llm_response(body: dict, api_key: Optional[str] = None) -> AsyncIterator[bytes]:
    try:
        llm = await _resolve_llm_target(body.get("model"), api_key)
        messages = _openai_messages_to_domain(body.get("messages") or [])
        reply = await llm.ask(
            messages,
            tools=body.get("tools"),
            tool_choice=body.get("tool_choice") if isinstance(body.get("tool_choice"), str) else None,
        )
        for chunk in _domain_message_to_openai_stream_chunks(reply, body.get("model") or "default"):
            yield f"data: {json.dumps(chunk)}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"
    except Exception as e:
        logger.exception(f"[openai-proxy] LLM request failed: {e}")
        sse_error = (
            f'data: {json.dumps({"error": {"message": f"LLM backend error: {e}", "type": "api_error"}})}\n\n'
            f"data: [DONE]\n\n"
        )
        yield sse_error.encode("utf-8")


async def _get_llm_response(body: dict, api_key: Optional[str] = None) -> dict:
    llm = await _resolve_llm_target(body.get("model"), api_key)
    messages = _openai_messages_to_domain(body.get("messages") or [])
    reply = await llm.ask(
        messages,
        tools=body.get("tools"),
        tool_choice=body.get("tool_choice") if isinstance(body.get("tool_choice"), str) else None,
    )
    return _domain_message_to_openai(reply, body.get("model") or "default")


@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible chat completions proxy.
    Authenticates using per-user manus API keys and forwards to the configured LLM backend.
    """
    api_key = _extract_bearer_token(request)
    if not api_key:
        return _openai_error_response(status.HTTP_401_UNAUTHORIZED, "Missing API key", "auth_error")

    # Verify API key and get user
    claw_service = await _get_claw_service()
    user_id = await claw_service.verify_api_key(api_key)
    if not user_id:
        return _openai_error_response(status.HTTP_401_UNAUTHORIZED, "Invalid API key", "auth_error")

    try:
        body = await request.json()
    except Exception:
        return _openai_error_response(status.HTTP_400_BAD_REQUEST, "Invalid request body", "invalid_request_error")

    is_stream = body.get("stream", False)

    logger.info(f"[openai-proxy] user={user_id} model={body.get('model')} stream={is_stream}")

    try:
        if is_stream:
            return StreamingResponse(
                _stream_llm_response(body, api_key),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )
        else:
            result = await _get_llm_response(body, api_key)
            return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"[openai-proxy] Unexpected error: {str(e)}")
        return _openai_error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e), "api_error")
