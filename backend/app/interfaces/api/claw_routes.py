"""
Claw management API routes.
Endpoints for creating, managing, and chatting with OpenClaw sessions.

A user may own several sessions (``/claw/sessions``) — each pinned to a
model chosen at creation, each backed by its own persistent Docker volume
so restarting its container (e.g. to switch models) never loses OpenClaw's
native conversational memory. See ``ClawDomainService`` for the lifecycle.
"""
import logging
from fastapi import APIRouter, Depends, Header, UploadFile, File, HTTPException, status
from fastapi.responses import Response

from app.application.services.claw_service import ClawService
from app.application.services.file_service import FileService
from app.application.errors.exceptions import BadRequestError, NotFoundError
from app.interfaces.dependencies import get_current_user, get_claw_service, get_file_service
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.claw import (
    ClawSessionResponse, ListClawSessionsResponse,
    CreateClawSessionRequest, RestartClawSessionRequest,
    ClawHistoryResponse, ClawMessageSchema,
    ClawToolEventsResponse, ClawToolEventSchema,
)
from app.interfaces.schemas.file import FileInfoResponse
from app.domain.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/claw", tags=["claw"])


async def _resolve_model_id(model_id: str) -> str:
    """Validate a model id against the live registry; raise if unknown."""
    from app.infrastructure.external.llm.model_registry import resolve_model
    if not await resolve_model(model_id):
        raise BadRequestError(f"Unknown model: {model_id}")
    return model_id


@router.get("/sessions", response_model=APIResponse[ListClawSessionsResponse])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    claw_service: ClawService = Depends(get_claw_service),
) -> APIResponse[ListClawSessionsResponse]:
    """List the current user's claw sessions, most recently active first"""
    sessions = await claw_service.list_sessions(current_user.id)
    return APIResponse.success(ListClawSessionsResponse(
        sessions=[ClawSessionResponse.from_domain(s) for s in sessions]
    ))


@router.post("/sessions", response_model=APIResponse[ClawSessionResponse])
async def create_session(
    request: CreateClawSessionRequest,
    current_user: User = Depends(get_current_user),
    claw_service: ClawService = Depends(get_claw_service),
) -> APIResponse[ClawSessionResponse]:
    """Create a new claw session, pinned to the given model.

    Starts with a fresh, empty-memory volume — for a "start over" session,
    just create a new one rather than restarting an existing session.
    """
    await _resolve_model_id(request.model_id)
    session = await claw_service.create_session(current_user.id, request.model_id, request.name)
    return APIResponse.success(ClawSessionResponse.from_domain(session))


@router.get("/sessions/{session_id}", response_model=APIResponse[ClawSessionResponse])
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    claw_service: ClawService = Depends(get_claw_service),
) -> APIResponse[ClawSessionResponse]:
    """Get one of the current user's claw sessions"""
    session = await claw_service.get_session(current_user.id, session_id)
    if not session:
        raise NotFoundError("Claw session not found")
    return APIResponse.success(ClawSessionResponse.from_domain(session))


@router.post("/sessions/{session_id}/restart", response_model=APIResponse[ClawSessionResponse])
async def restart_session(
    session_id: str,
    request: RestartClawSessionRequest,
    current_user: User = Depends(get_current_user),
    claw_service: ClawService = Depends(get_claw_service),
) -> APIResponse[ClawSessionResponse]:
    """Kill the session's current container and start a fresh one on a
    (possibly different) model — the only way to change a session's model.

    The session's volume is untouched, so OpenClaw's native memory for this
    session survives the restart; only deleting the session discards it.
    """
    await _resolve_model_id(request.model_id)
    session = await claw_service.restart_session(current_user.id, session_id, request.model_id)
    if not session:
        raise NotFoundError("Claw session not found")
    return APIResponse.success(ClawSessionResponse.from_domain(session))


@router.delete("/sessions/{session_id}", response_model=APIResponse[dict])
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    claw_service: ClawService = Depends(get_claw_service),
) -> APIResponse[dict]:
    """Delete a claw session — destroys its container AND its volume.

    This is the only operation that actually discards a session's memory;
    restarting (even with a different model) preserves it.
    """
    deleted = await claw_service.delete_session(current_user.id, session_id)
    if not deleted:
        raise NotFoundError("Claw session not found")
    return APIResponse.success({})


@router.get("/sessions/{session_id}/history", response_model=APIResponse[ClawHistoryResponse])
async def get_session_history(
    session_id: str,
    current_user: User = Depends(get_current_user),
    claw_service: ClawService = Depends(get_claw_service),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[ClawHistoryResponse]:
    """Get chat history for one of the current user's claw sessions"""
    raw_messages = await claw_service.get_history(current_user.id, session_id)
    schemas = []
    for m in raw_messages:
        schema = ClawMessageSchema.from_domain(m)
        if schema.attachments:
            for att in schema.attachments:
                try:
                    att.file_url = await file_service.create_signed_url(att.file_id)
                except Exception:
                    pass
        schemas.append(schema)
    return APIResponse.success(ClawHistoryResponse(messages=schemas))


@router.get("/sessions/{session_id}/tool-events", response_model=APIResponse[ClawToolEventsResponse])
async def get_session_tool_events(
    session_id: str,
    current_user: User = Depends(get_current_user),
    claw_service: ClawService = Depends(get_claw_service),
) -> APIResponse[ClawToolEventsResponse]:
    """Get persisted tool-call history for one of the current user's claw
    sessions (Computer panel Tools tab restore)."""
    raw_events = await claw_service.get_tool_events(current_user.id, session_id)
    schemas = [ClawToolEventSchema.from_domain(e) for e in raw_events]
    return APIResponse.success(ClawToolEventsResponse(tool_events=schemas))


@router.get("/sessions/{session_id}/files/{filename}")
async def download_session_file(
    session_id: str,
    filename: str,
    current_user: User = Depends(get_current_user),
    claw_service: ClawService = Depends(get_claw_service),
):
    """Proxy a file download from a session's claw workspace"""
    try:
        content, content_type = await claw_service.get_file(current_user.id, session_id, filename)
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"[claw-file] Failed to proxy file {filename}: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch file from claw")


# ----------------------------------------------------------------------
# Container -> backend callbacks, authenticated by the session's own
# per-session API key (X-Claw-Api-Key), not the user's cookie/token.
# ----------------------------------------------------------------------

@router.post("/upload", response_model=APIResponse[FileInfoResponse])
async def upload_claw_file(
    file: UploadFile = File(...),
    x_claw_api_key: str = Header(..., alias="X-Claw-Api-Key"),
    claw_service: ClawService = Depends(get_claw_service),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[FileInfoResponse]:
    """Upload a file from a claw workspace to Manus storage (authenticated by claw API key)"""
    user_id = await claw_service.verify_api_key(x_claw_api_key)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid claw API key")
    result = await file_service.upload_file(
        file_data=file.file,
        filename=file.filename or "file",
        user_id=user_id,
        content_type=file.content_type,
    )
    return APIResponse.success(await FileInfoResponse.from_domain(result))


@router.get("/resolve/{file_id}")
async def resolve_claw_file_meta(
    file_id: str,
    x_claw_api_key: str = Header(..., alias="X-Claw-Api-Key"),
    claw_service: ClawService = Depends(get_claw_service),
    file_service: FileService = Depends(get_file_service),
) -> APIResponse[FileInfoResponse]:
    """Get file metadata for manus-file:// resolution (authenticated by claw API key)"""
    user_id = await claw_service.verify_api_key(x_claw_api_key)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid claw API key")
    file_info = await file_service.get_file_info(file_id)
    if not file_info:
        raise NotFoundError("File not found")
    return APIResponse.success(await FileInfoResponse.from_domain(file_info))


@router.get("/resolve/{file_id}/download")
async def resolve_claw_file_download(
    file_id: str,
    x_claw_api_key: str = Header(..., alias="X-Claw-Api-Key"),
    claw_service: ClawService = Depends(get_claw_service),
    file_service: FileService = Depends(get_file_service),
):
    """Download file content for manus-file:// resolution (authenticated by claw API key)"""
    user_id = await claw_service.verify_api_key(x_claw_api_key)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid claw API key")
    try:
        file_data, file_info = await file_service.download_file(file_id)
    except (FileNotFoundError, PermissionError):
        raise NotFoundError("File not found")
    import urllib.parse
    encoded_filename = urllib.parse.quote(file_info.filename, safe='')
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        file_data,
        media_type=file_info.content_type or 'application/octet-stream',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"},
    )
