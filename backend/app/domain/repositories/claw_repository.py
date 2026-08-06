from typing import Optional, List, Protocol

from app.domain.models.claw import ClawSession, ClawMessage, ClawAttachment


class ClawSessionRepository(Protocol):
    """Repository interface for the ClawSession aggregate.

    Unlike the old 1:1-per-user Claw, a user may own several sessions —
    every lookup here is keyed by ``session_id``, with ``list_by_user_id``
    the one exception for populating a session list/switcher.
    """

    async def get_by_id(self, session_id: str) -> Optional[ClawSession]:
        """Get a session by its own ID"""
        ...

    async def list_by_user_id(self, user_id: str) -> List[ClawSession]:
        """List all sessions owned by a user, most recently active first"""
        ...

    async def get_by_api_key(self, api_key: str) -> Optional[ClawSession]:
        """Get the session whose container authenticates with this API key"""
        ...

    async def get_most_recently_updated(self) -> Optional[ClawSession]:
        """The single most recently updated session across every user.

        Only meaningful when every session shares one physical container
        (``settings.claw_address`` set — see ``FixedClawRuntime``): there,
        no per-session API key can identify which session a proxied LLM
        call belongs to, so the most recently touched session is the best
        available signal of "what the operator is currently using". Never
        consulted when sessions have their own containers (production).
        """
        ...

    async def create(self, session: ClawSession) -> ClawSession:
        """Create a new session"""
        ...

    async def update(self, session: ClawSession) -> ClawSession:
        """Update an existing session"""
        ...

    async def delete_by_id(self, session_id: str) -> bool:
        """Delete a session's record (caller destroys container/volume separately)"""
        ...

    async def get_messages(self, session_id: str) -> List[ClawMessage]:
        """Get the display-transcript chat history for a session"""
        ...

    async def append_message(
        self, session_id: str, role: str, content: str = "",
        attachments: Optional[List[ClawAttachment]] = None,
    ) -> None:
        """Append a message to a session's chat history"""
        ...

    async def clear_messages(self, session_id: str) -> None:
        """Clear all chat messages for a session"""
        ...
