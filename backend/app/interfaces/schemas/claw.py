from typing import Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from app.domain.models.claw import ClawStatus, ClawMessage, ClawAttachment, ClawToolEvent


class ClawSessionResponse(BaseModel):
    """A Manus Claw session, as returned to the frontend."""
    id: str
    user_id: str
    name: Optional[str] = None
    model_id: str
    status: ClawStatus
    container_name: Optional[str] = None
    error_message: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    last_active_at: datetime

    @staticmethod
    def from_domain(session) -> 'ClawSessionResponse':
        return ClawSessionResponse(
            id=session.id,
            user_id=session.user_id,
            name=session.name,
            model_id=session.model_id,
            status=session.status,
            container_name=session.container_name,
            error_message=session.error_message,
            expires_at=session.expires_at,
            created_at=session.created_at,
            updated_at=session.updated_at,
            last_active_at=session.last_active_at,
        )


class ListClawSessionsResponse(BaseModel):
    sessions: List[ClawSessionResponse]


class CreateClawSessionRequest(BaseModel):
    """Body for POST /claw/sessions. model_id is mandatory — a session
    always starts pinned to a specific model, never "pick later"."""
    model_id: str = Field(min_length=1)
    name: Optional[str] = None


class RestartClawSessionRequest(BaseModel):
    """Body for POST /claw/sessions/{id}/restart. The only way to change a
    session's model — never a silent runtime swap."""
    model_id: str = Field(min_length=1)


class ClawChatRequest(BaseModel):
    """Chat request schema"""
    message: str


class ClawChatChunk(BaseModel):
    """Chat chunk event schema"""
    type: str
    content: Optional[str] = None
    stop_reason: Optional[str] = None
    error: Optional[str] = None


class ClawAttachmentSchema(BaseModel):
    """File attachment in a chat message"""
    file_id: str
    filename: str
    content_type: Optional[str] = None
    size: int = 0
    file_url: Optional[str] = None

    @staticmethod
    def from_domain(att: ClawAttachment) -> 'ClawAttachmentSchema':
        return ClawAttachmentSchema(
            file_id=att.file_id,
            filename=att.filename,
            content_type=att.content_type,
            size=att.size,
            file_url=att.file_url,
        )


class ClawMessageSchema(BaseModel):
    """A single chat message"""
    role: str
    content: str = ""
    timestamp: int
    attachments: Optional[List[ClawAttachmentSchema]] = None

    @staticmethod
    def from_domain(msg: ClawMessage) -> 'ClawMessageSchema':
        return ClawMessageSchema(
            role=msg.role,
            content=msg.content,
            timestamp=msg.timestamp,
            attachments=[ClawAttachmentSchema.from_domain(a) for a in msg.attachments] if msg.attachments else None,
        )


class ClawHistoryResponse(BaseModel):
    """Chat history response"""
    messages: List[ClawMessageSchema]


class ClawToolEventSchema(BaseModel):
    """A single persisted tool-call event"""
    tool_call_id: str
    name: str
    args: Optional[dict] = None
    result: Optional[Any] = None
    is_error: bool = False
    truncated: bool = False
    timestamp: int

    @staticmethod
    def from_domain(event: ClawToolEvent) -> 'ClawToolEventSchema':
        return ClawToolEventSchema(
            tool_call_id=event.tool_call_id,
            name=event.name,
            args=event.args,
            result=event.result,
            is_error=event.is_error,
            truncated=event.truncated,
            timestamp=event.timestamp,
        )


class ClawToolEventsResponse(BaseModel):
    """Tool-call history response"""
    tool_events: List[ClawToolEventSchema]
