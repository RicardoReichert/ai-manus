from typing import Optional, List
from datetime import datetime, UTC
from pydantic import BaseModel, Field
from enum import Enum


class ClawAttachment(BaseModel):
    """File attachment within a Claw chat message"""
    file_id: str
    filename: str
    content_type: Optional[str] = None
    size: int = 0
    file_url: Optional[str] = None


class ClawMessage(BaseModel):
    """A single chat message in a Claw conversation"""
    role: str  # 'user' | 'assistant' | 'attachments'
    content: str = ""
    timestamp: int  # Unix timestamp (seconds)
    attachments: Optional[List[ClawAttachment]] = None


class ClawStatus(str, Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class ClawSession(BaseModel):
    """A persistent Manus Claw conversation.

    A user may have several of these (unlike the old 1:1 ``Claw``). The
    session is the durable identity: its ``volume_name`` — a Docker volume
    mounted at OpenClaw's home directory (``/home/node/.openclaw``) inside
    the container — is what makes OpenClaw's own native conversational
    memory survive killing and recreating the *container*. A container is
    disposable; a session is not. Only an explicit delete removes a
    session's volume, so switching models (only possible by restarting with
    a fresh container attached to the same volume) never loses context, and
    a brand new session naturally starts with zero memory (no shared volume).

    ``model_id`` is required at creation and only changes via an explicit
    restart — never silently, and never while a container is live.
    """
    id: str
    user_id: str
    name: Optional[str] = None
    model_id: str
    volume_name: str
    container_name: Optional[str] = None
    container_ip: Optional[str] = None
    # Per-session now, not per-user: the backend resolves which model a
    # /v1/chat/completions proxy call should target by looking up the
    # session that owns the Bearer api_key, so each session needs its own.
    api_key: str
    status: ClawStatus = ClawStatus.CREATING
    error_message: Optional[str] = None
    expires_at: Optional[datetime] = None
    # Not carried on the domain object, same as the previous Claw model:
    # message history is large and accessed separately via
    # ClawSessionRepository.get_messages/append_message, not round-tripped
    # through every load/save of the session record itself.
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def http_base_url(self) -> Optional[str]:
        """HTTP base URL for the manus-claw plugin server"""
        if self.container_ip:
            return f"http://{self.container_ip}:18788"
        return None
