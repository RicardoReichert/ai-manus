from typing import Optional, List
from datetime import datetime, UTC
from app.infrastructure.models.documents import ClawSessionDocument
from app.domain.models.claw import ClawSession, ClawMessage, ClawAttachment, ClawToolEvent
import json
import logging

logger = logging.getLogger(__name__)

# Bounds on Mongo-persisted Claw tool-event history: a session document is a
# single BSON doc (16MB hard cap), and tool results can be arbitrarily large
# (e.g. reading a big file) or arbitrarily numerous over a long session.
CLAW_TOOL_EVENT_RESULT_MAX_CHARS = 16_000  # ~16KB per persisted result, after JSON-stringifying
CLAW_TOOL_EVENT_MAX_COUNT = 200  # keep only the most recent N events per session


def _apply_tool_event_bounds(event: ClawToolEvent) -> ClawToolEvent:
    """Truncate an oversized ``result`` to CLAW_TOOL_EVENT_RESULT_MAX_CHARS,
    marking ``truncated=True``. Pure function (no I/O) so it's directly unit
    testable without a live Mongo/Beanie connection.
    """
    if event.result is None:
        return event
    try:
        serialized = event.result if isinstance(event.result, str) else json.dumps(event.result)
    except (TypeError, ValueError):
        serialized = str(event.result)
    if len(serialized) <= CLAW_TOOL_EVENT_RESULT_MAX_CHARS:
        return event
    return event.model_copy(update={
        "result": serialized[:CLAW_TOOL_EVENT_RESULT_MAX_CHARS],
        "truncated": True,
    })


class ClawSessionRepository:
    """MongoDB repository for Claw sessions"""

    async def get_by_id(self, session_id: str) -> Optional[ClawSession]:
        """Get a session by its own ID"""
        doc = await ClawSessionDocument.find_one(ClawSessionDocument.claw_session_id == session_id)
        if not doc:
            return None
        return doc.to_domain()

    async def list_by_user_id(self, user_id: str) -> List[ClawSession]:
        """List all sessions owned by a user, most recently active first"""
        docs = await ClawSessionDocument.find(
            ClawSessionDocument.user_id == user_id
        ).sort("-last_active_at").to_list()
        return [doc.to_domain() for doc in docs]

    async def get_by_api_key(self, api_key: str) -> Optional[ClawSession]:
        """Get the session whose container authenticates with this API key"""
        doc = await ClawSessionDocument.find_one(ClawSessionDocument.api_key == api_key)
        if not doc:
            return None
        return doc.to_domain()

    async def get_most_recently_updated(self) -> Optional[ClawSession]:
        """The single most recently updated session across every user"""
        docs = await ClawSessionDocument.find_all().sort("-updated_at").limit(1).to_list()
        return docs[0].to_domain() if docs else None

    async def create(self, session: ClawSession) -> ClawSession:
        """Create a new session"""
        doc = ClawSessionDocument.from_domain(session)
        await doc.insert()
        return doc.to_domain()

    async def update(self, session: ClawSession) -> ClawSession:
        """Update an existing session"""
        doc = await ClawSessionDocument.find_one(ClawSessionDocument.claw_session_id == session.id)
        if not doc:
            raise ValueError(f"Claw session not found: {session.id}")
        doc.update_from_domain(session)
        await doc.save()
        return doc.to_domain()

    async def delete_by_id(self, session_id: str) -> bool:
        """Delete a session's record (caller destroys container/volume separately)"""
        doc = await ClawSessionDocument.find_one(ClawSessionDocument.claw_session_id == session_id)
        if not doc:
            return False
        await doc.delete()
        return True

    async def get_messages(self, session_id: str) -> List[ClawMessage]:
        """Get the display-transcript chat history for a session"""
        doc = await ClawSessionDocument.find_one(ClawSessionDocument.claw_session_id == session_id)
        if not doc:
            return []
        return doc.messages

    async def append_message(
        self, session_id: str, role: str, content: str = "",
        attachments: Optional[List[ClawAttachment]] = None,
    ) -> None:
        """Append a message to a session's chat history"""
        doc = await ClawSessionDocument.find_one(ClawSessionDocument.claw_session_id == session_id)
        if not doc:
            return
        msg = ClawMessage(
            role=role,
            content=content,
            timestamp=int(datetime.now(UTC).timestamp()),
            attachments=attachments,
        )
        doc.messages.append(msg)
        doc.updated_at = datetime.now(UTC)
        doc.last_active_at = datetime.now(UTC)
        await doc.save()

    async def clear_messages(self, session_id: str) -> None:
        """Clear all chat messages for a session"""
        doc = await ClawSessionDocument.find_one(ClawSessionDocument.claw_session_id == session_id)
        if not doc:
            return
        doc.messages = []
        doc.updated_at = datetime.now(UTC)
        await doc.save()

    async def get_tool_events(self, session_id: str) -> List[ClawToolEvent]:
        """Get the persisted tool-call history for a session (Tools tab restore)"""
        doc = await ClawSessionDocument.find_one(ClawSessionDocument.claw_session_id == session_id)
        if not doc:
            return []
        return doc.tool_events

    async def append_tool_event(self, session_id: str, event: ClawToolEvent) -> None:
        """Append a completed tool-call event to a session's history.

        Truncates an oversized ``result`` and caps the total stored count
        — see CLAW_TOOL_EVENT_RESULT_MAX_CHARS / CLAW_TOOL_EVENT_MAX_COUNT
        above.
        """
        doc = await ClawSessionDocument.find_one(ClawSessionDocument.claw_session_id == session_id)
        if not doc:
            return

        doc.tool_events.append(_apply_tool_event_bounds(event))
        if len(doc.tool_events) > CLAW_TOOL_EVENT_MAX_COUNT:
            doc.tool_events = doc.tool_events[-CLAW_TOOL_EVENT_MAX_COUNT:]
        doc.updated_at = datetime.now(UTC)
        doc.last_active_at = datetime.now(UTC)
        await doc.save()
