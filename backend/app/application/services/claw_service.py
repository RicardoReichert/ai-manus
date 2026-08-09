import logging
import asyncio
from collections import defaultdict
from typing import Optional, List

from app.domain.models.claw import ClawSession, ClawMessage, ClawStatus, ClawToolEvent
from app.domain.services.claw_domain_service import ClawDomainService
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ClawEventBus:
    """Simple in-memory pub/sub per session for broadcasting Claw stream events.

    Keyed by session_id (not user_id): a user can have several sessions
    chatting concurrently, and events must never cross between them.
    """

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[session_id].append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue):
        subs = self._subscribers.get(session_id)
        if subs:
            self._subscribers[session_id] = [q for q in subs if q is not queue]

    async def publish(self, session_id: str, event: dict):
        for queue in self._subscribers.get(session_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass


class _ChatState:
    """Tracks an in-progress response so new WebSocket clients can catch up."""
    __slots__ = ("pending_text",)

    def __init__(self):
        self.pending_text = ""


class ClawService:
    """Application service for managing OpenClaw sessions.

    Thin orchestration layer: delegates core business logic to
    ``ClawDomainService`` and adds application-level concerns such as
    the Claw event bus, background task scheduling, and chat state tracking.
    """

    def __init__(self, claw_domain_service: ClawDomainService):
        self.domain = claw_domain_service
        self.claw_repository = claw_domain_service.claw_repository
        self.settings = get_settings()
        self.event_bus = ClawEventBus()
        self._bg_tasks: set[asyncio.Task] = set()
        self._chat_states: dict[str, _ChatState] = {}

    # ------------------------------------------------------------------
    # Delegates to domain service
    # ------------------------------------------------------------------

    async def list_sessions(self, user_id: str) -> List[ClawSession]:
        return await self.domain.list_sessions(user_id)

    async def get_session(self, user_id: str, session_id: str) -> Optional[ClawSession]:
        return await self.domain.get_session(user_id, session_id)

    async def get_history(self, user_id: str, session_id: str) -> List[ClawMessage]:
        return await self.domain.get_history(user_id, session_id)

    async def get_tool_events(self, user_id: str, session_id: str) -> List[ClawToolEvent]:
        return await self.domain.get_tool_events(user_id, session_id)

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        return await self.domain.delete_session(user_id, session_id)

    async def get_file(self, user_id: str, session_id: str, filename: str) -> tuple[bytes, str]:
        return await self.domain.get_file(user_id, session_id, filename)

    async def open_terminal(
        self, user_id: str, session_id: str, cols: int = 80, rows: int = 24,
    ) -> tuple[str, str]:
        """Open an Operator Terminal PTY for a session. Returns
        ``(terminal_ws_url, terminal_session_id)``, enforcing ownership
        before returning a URL to connect to."""
        return await self.domain.open_terminal(user_id, session_id, cols, rows)

    async def verify_api_key(self, api_key: str) -> Optional[str]:
        return await self.domain.verify_api_key(api_key, self.settings.claw_api_key)

    # ------------------------------------------------------------------
    # Session creation / restart – background provisioning
    # ------------------------------------------------------------------

    async def create_session(self, user_id: str, model_id: str, name: Optional[str] = None) -> ClawSession:
        session = await self.domain.create_session(user_id, model_id, name)
        task = asyncio.create_task(self._provision_in_background(session))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return session

    async def restart_session(self, user_id: str, session_id: str, model_id: str) -> Optional[ClawSession]:
        """Kill the current container and start a fresh one with a new model,
        on the same volume — preserves the session's OpenClaw-native memory."""
        session = await self.domain.restart_session(user_id, session_id, model_id)
        if not session:
            return None
        task = asyncio.create_task(self._provision_in_background(session))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return session

    async def _provision_in_background(self, session: ClawSession) -> None:
        await self.domain.provision_session(session, self.settings.claw_ttl_seconds)

    # ------------------------------------------------------------------
    # Chat  – fire-and-forget + event bus
    # ------------------------------------------------------------------

    async def send_message(self, user_id: str, session_id: str, message: str) -> None:
        """Accept a user message and kick off background processing."""
        session = await self.domain.validate_session_for_chat(user_id, session_id)

        await self.claw_repository.append_message(session_id, "user", message)

        task = asyncio.create_task(
            self._process_chat(session_id, session.http_base_url, message)
        )
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _process_chat(self, session_id: str, base_url: str, message: str) -> None:
        """Background task: stream from claw, broadcast events, persist."""
        state = _ChatState()
        self._chat_states[session_id] = state

        try:
            async for chunk in self.domain.process_chat_stream(session_id, base_url, message):
                if chunk.get("type") == "text" and chunk.get("content"):
                    state.pending_text += chunk["content"]

                if chunk.get("type") != "done":
                    await self.event_bus.publish(session_id, chunk)

        except Exception as e:
            logger.error(f"[claw-chat] background processing error for session={session_id}: {e}")
            await self.event_bus.publish(session_id, {"type": "error", "error": str(e)})
        finally:
            await self.event_bus.publish(session_id, {"type": "done", "stop_reason": "end_turn"})
            self._chat_states.pop(session_id, None)

    def get_pending_content(self, session_id: str) -> Optional[str]:
        """Return accumulated text for an in-progress response (for WS catch-up)."""
        state = self._chat_states.get(session_id)
        if state and state.pending_text:
            return state.pending_text
        return None

    def is_processing(self, session_id: str) -> bool:
        return session_id in self._chat_states
