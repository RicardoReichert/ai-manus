"""WebSocket routes for realtime session list, chat, and Claw."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

import httpx
import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.domain.models.claw import ClawAttachment
from app.domain.models.file import FileInfo
from app.interfaces.dependencies import (
    resolve_ws_user,
    get_agent_service,
    get_claw_service,
    get_file_service,
)
from app.interfaces.schemas.event import EventMapper
from app.interfaces.schemas.session import ListSessionItem
from app.infrastructure.storage.redis import get_redis
from app.infrastructure.external.session_list import (
    channel_for_user,
    parse_notify_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["ws"])

SESSION_LIST_KEEPALIVE_SECONDS = 20.0
CHAT_WS_PING_SECONDS = 20.0
CLAW_HEARTBEAT_INTERVAL = 15

# Chat WS protocol (aligned with official Manus control-plane contract).
CHAT_WS_PROTOCOL_VERSION = 2
ERR_BAD_VERSION = 4000
ERR_BAD_REQUEST = 4002
ERR_NOT_FOUND = 4004
ERR_NOT_JOINED = 4009
ERR_INTERNAL = 5000


def _session_status_value(status: Any) -> str:
    return getattr(status, "value", status) if status is not None else "pending"


def _agent_status_from_session(status: Any) -> str:
    """Map SessionStatus → wire agent_status (pending|running|waiting|completed|error)."""
    value = _session_status_value(status)
    if value in ("pending", "running", "waiting", "completed"):
        return value
    return "completed"


def _events_after(events: list[Any], last_event_id: Optional[str]) -> list[Any]:
    """Return domain events strictly after last_event_id (Mongo catch-up)."""
    if not events:
        return []
    if not last_event_id:
        return list(events)
    idx = next((i for i, e in enumerate(events) if getattr(e, "id", None) == last_event_id), None)
    if idx is None:
        return list(events)
    return list(events[idx + 1 :])


@router.websocket("/sessions")
async def sessions_list_ws(websocket: WebSocket):
    """User session list channel.

    Auth: Cookie (browser) or Authorization Bearer (App). No ?token=.

    Server → Client JSON:
      {"op":"snapshot","sessions":[...]}
      {"op":"upsert","session":{...}}
      {"op":"remove","session_id":"..."}
      {"op":"ping"}
    """
    try:
        user = await resolve_ws_user(websocket)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    agent_service = get_agent_service()

    redis = get_redis()
    await redis.initialize()
    channel = channel_for_user(user.id)
    pubsub = redis.client.pubsub()
    await pubsub.subscribe(channel)

    try:
        summaries = await agent_service.get_all_sessions(user.id)
        await websocket.send_json({
            "op": "snapshot",
            "sessions": [
                ListSessionItem.from_domain(s).model_dump(mode="json")
                for s in summaries
            ],
        })

        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=SESSION_LIST_KEEPALIVE_SECONDS,
            )
            if message is None:
                await websocket.send_json({"op": "ping"})
                continue
            if message.get("type") != "message":
                continue
            raw = message.get("data", "")
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="replace")
            payload = parse_notify_payload(raw)
            if not payload:
                continue
            op = payload["op"]
            session_id = payload["session_id"]
            if op == "remove":
                await websocket.send_json({"op": "remove", "session_id": session_id})
                continue
            summary = await agent_service.get_session_summary(session_id, user.id)
            if summary:
                await websocket.send_json({
                    "op": "upsert",
                    "session": ListSessionItem.from_domain(summary).model_dump(mode="json"),
                })
    except WebSocketDisconnect:
        logger.debug("Session list WS disconnected for user %s", user.id)
    except Exception:
        logger.exception("Session list WS error for user %s", user.id)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception:
            logger.debug("Failed to close session list pubsub", exc_info=True)


@router.websocket("/chat")
async def chat_ws(websocket: WebSocket):
    """Chat channel — one connection per tab; switch sessions via join/leave.

    Auth: Cookie (browser) or Authorization Bearer (App). No ?token=.
    Protocol version: client frames must include ``version: 2``.

    Client → Server (envelope):
      {
        "id": "...", "timestamp": 1710000000, "version": 2,
        "type": "join_session|leave_session|chat|stop_session",
        "session_id": "...",
        "last_event_id": "...?", "message": "...?", "attachments": [],
        "conn_id": "...?"
      }

    Server → Client:
      {"type":"joined|left|stopped","session_id":"...","request_id":"...?"}
      {"type":"ack","request_id":"...","op":"chat","session_id":"...","ok":true}
      {"type":"event","session_id":"...","event":"message|status_update|...","data":{...}}
      {"type":"stream_end","session_id":"..."}
      {"type":"error","error":"...","code":4000,"session_id":"...?","request_id":"...?"}
      {"type":"ping"}
    """
    try:
        user = await resolve_ws_user(websocket)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    agent_service = get_agent_service()

    joined_session_id: Optional[str] = None
    stream_task: Optional[asyncio.Task] = None
    send_lock = asyncio.Lock()

    async def safe_send(payload: dict[str, Any]) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    async def send_error(
        error: str,
        *,
        code: int = ERR_INTERNAL,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        payload: dict[str, Any] = {"type": "error", "error": error, "code": code}
        if session_id:
            payload["session_id"] = session_id
        if request_id:
            payload["request_id"] = request_id
        await safe_send(payload)

    async def send_status_update(session_id: str, agent_status: str) -> None:
        await safe_send({
            "type": "event",
            "session_id": session_id,
            "event": "status_update",
            "data": {
                "event_id": f"status-{session_id}-{agent_status}-{int(datetime.now().timestamp())}",
                "timestamp": int(datetime.now().timestamp()),
                "agent_status": agent_status,
            },
        })

    async def send_agent_event(session_id: str, event: Any) -> None:
        stream_event = await EventMapper.event_to_stream_event(event)
        data = stream_event.data.model_dump(mode="json") if stream_event.data else {}
        await safe_send({
            "type": "event",
            "session_id": session_id,
            "event": stream_event.event,
            "data": data,
        })

    async def cancel_stream() -> None:
        nonlocal stream_task
        if stream_task and not stream_task.done():
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("Chat stream task ended with error", exc_info=True)
        stream_task = None

    async def stream_session(
        session_id: str,
        message: Optional[str] = None,
        last_event_id: Optional[str] = None,
        attachments: Optional[list[FileInfo]] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        saw_error = False
        try:
            async for event in agent_service.chat(
                session_id=session_id,
                user_id=user.id,
                message=message,
                timestamp=timestamp,
                event_id=last_event_id,
                attachments=attachments,
            ):
                if joined_session_id != session_id:
                    break
                if getattr(event, "type", None) == "error":
                    saw_error = True
                await send_agent_event(session_id, event)
                # Mid-stream phase: WaitEvent means Mongo is already WAITING — tell
                # clients immediately so phase UI does not depend on domain→phase fallbacks.
                if getattr(event, "type", None) == "wait":
                    await send_status_update(session_id, "waiting")
            if joined_session_id == session_id:
                session = await agent_service.get_session(session_id, user.id)
                final_status = _session_status_value(session.status) if session else "completed"
                # Prefer authoritative session status (e.g. waiting after message_ask_user)
                # over saw_error — early tool errors can coexist with a later WaitEvent.
                # Send status_update BEFORE stream_end: clients often clear handlers on
                # stream_end, which would drop a trailing status_update.
                if final_status == "waiting":
                    await send_status_update(session_id, "waiting")
                elif saw_error:
                    await send_status_update(session_id, "error")
                else:
                    await send_status_update(
                        session_id,
                        _agent_status_from_session(
                            session.status if session else "completed"
                        ),
                    )
                await safe_send({"type": "stream_end", "session_id": session_id})
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Chat stream failed for session %s", session_id)
            try:
                await send_error(str(e), code=ERR_INTERNAL, session_id=session_id)
                if joined_session_id == session_id:
                    await send_status_update(session_id, "error")
            except Exception:
                pass

    def start_stream(**kwargs: Any) -> None:
        nonlocal stream_task

        async def _run() -> None:
            nonlocal stream_task
            try:
                await stream_session(**kwargs)
            finally:
                stream_task = None

        stream_task = asyncio.create_task(_run())

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=CHAT_WS_PING_SECONDS,
                )
            except asyncio.TimeoutError:
                await safe_send({"type": "ping"})
                continue

            if not isinstance(raw, dict):
                await send_error("Invalid message", code=ERR_BAD_REQUEST)
                continue

            msg_type = raw.get("type")
            session_id = raw.get("session_id")
            request_id = raw.get("id")

            # leave_session: still accept missing version (tab-close races), but
            # clients should send version: 2 like other control frames.
            if msg_type != "leave_session" and raw.get("version") != CHAT_WS_PROTOCOL_VERSION:
                await send_error(
                    f"Unsupported protocol version (require {CHAT_WS_PROTOCOL_VERSION})",
                    code=ERR_BAD_VERSION,
                    session_id=session_id,
                    request_id=request_id,
                )
                continue

            if msg_type == "join_session":
                if not session_id:
                    await send_error(
                        "session_id required",
                        code=ERR_BAD_REQUEST,
                        request_id=request_id,
                    )
                    continue
                session = await agent_service.get_session(session_id, user.id)
                if not session:
                    await send_error(
                        "Session not found",
                        code=ERR_NOT_FOUND,
                        session_id=session_id,
                        request_id=request_id,
                    )
                    continue

                if joined_session_id and joined_session_id != session_id:
                    await cancel_stream()
                    prev = joined_session_id
                    joined_session_id = None
                    await safe_send({"type": "left", "session_id": prev})

                joined_session_id = session_id
                last_event_id = raw.get("last_event_id")
                joined_payload: dict[str, Any] = {
                    "type": "joined",
                    "session_id": session_id,
                }
                if request_id:
                    joined_payload["request_id"] = request_id
                await safe_send(joined_payload)

                status = _session_status_value(session.status)
                agent_status = _agent_status_from_session(session.status)

                # Idle/pending/completed/waiting: Mongo catch-up after cursor,
                # then authoritative status_update. Do NOT send stream_end —
                # a follow-up chat would otherwise clear client "thinking".
                if status == "running":
                    await send_status_update(session_id, "running")
                    await cancel_stream()
                    start_stream(
                        session_id=session_id,
                        message=None,
                        last_event_id=last_event_id,
                    )
                else:
                    if last_event_id:
                        for event in _events_after(session.events or [], last_event_id):
                            if joined_session_id != session_id:
                                break
                            await send_agent_event(session_id, event)
                    await send_status_update(session_id, agent_status)

            elif msg_type == "leave_session":
                target = session_id or joined_session_id
                if not target:
                    continue
                if joined_session_id == target:
                    await cancel_stream()
                    joined_session_id = None
                    left_payload: dict[str, Any] = {
                        "type": "left",
                        "session_id": target,
                    }
                    if request_id:
                        left_payload["request_id"] = request_id
                    await safe_send(left_payload)

            elif msg_type == "chat":
                if not session_id:
                    await send_error(
                        "session_id required",
                        code=ERR_BAD_REQUEST,
                        request_id=request_id,
                    )
                    continue
                if joined_session_id != session_id:
                    await send_error(
                        "Not joined to this session",
                        code=ERR_NOT_JOINED,
                        session_id=session_id,
                        request_id=request_id,
                    )
                    continue

                message = raw.get("message") or ""
                attachments_raw = raw.get("attachments") or []
                attachments: list[FileInfo] = []
                for item in attachments_raw:
                    if isinstance(item, dict) and item.get("file_id"):
                        attachments.append(
                            FileInfo(
                                file_id=item["file_id"],
                                filename=item.get("filename") or "",
                            )
                        )
                ts = raw.get("timestamp")
                timestamp = datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) else None

                if request_id:
                    await safe_send({
                        "type": "ack",
                        "request_id": request_id,
                        "op": "chat",
                        "session_id": session_id,
                        "ok": True,
                    })
                await send_status_update(session_id, "running")
                await cancel_stream()
                start_stream(
                    session_id=session_id,
                    message=message or None,
                    last_event_id=raw.get("last_event_id") or raw.get("event_id"),
                    attachments=attachments or None,
                    timestamp=timestamp,
                )

            elif msg_type == "stop_session":
                if not session_id:
                    await send_error(
                        "session_id required",
                        code=ERR_BAD_REQUEST,
                        request_id=request_id,
                    )
                    continue
                try:
                    await agent_service.stop_session(session_id, user.id)
                    stopped_payload: dict[str, Any] = {
                        "type": "stopped",
                        "session_id": session_id,
                    }
                    if request_id:
                        stopped_payload["request_id"] = request_id
                    await safe_send(stopped_payload)
                    await send_status_update(session_id, "completed")
                except Exception as e:
                    await send_error(
                        str(e),
                        code=ERR_INTERNAL,
                        session_id=session_id,
                        request_id=request_id,
                    )
            else:
                await send_error(
                    f"Unknown type: {msg_type}",
                    code=ERR_BAD_REQUEST,
                    request_id=request_id,
                )

    except WebSocketDisconnect:
        logger.debug("Chat WS disconnected for user %s", user.id)
    except Exception:
        logger.exception("Chat WS error for user %s", user.id)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        await cancel_stream()


@router.websocket("/claw/{session_id}")
async def claw_ws(websocket: WebSocket, session_id: str):
    """Claw chat channel, scoped to one session — same Cookie / Bearer
    resolve as /ws/sessions and /ws/chat.

    A user may have several sessions; each gets its own connection (one
    session per socket, matching /ws/vnc/{session_id}'s convention) so
    events from one session's chat can never leak into another's.

    Client → Server:
      {"type":"chat","message":"...","file_ids":[]}

    Server → Client:
      {"type":"text","content":"..."}
      {"type":"file",...}
      {"type":"tool","phase":"start"|"update"|"result","name":"...","toolCallId":"...",...}
      {"type":"done","stop_reason":"..."}
      {"type":"error","error":"..."}
      {"type":"catchup","content":"..."}
      {"type":"heartbeat"}
    """
    try:
        user = await resolve_ws_user(websocket)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    claw_service = get_claw_service()
    session = await claw_service.get_session(user.id, session_id)
    if not session:
        await websocket.close(code=4004, reason="Claw session not found")
        return

    await websocket.accept()

    queue = claw_service.event_bus.subscribe(session_id)

    async def _write_events() -> None:
        try:
            pending = claw_service.get_pending_content(session_id)
            if pending:
                await websocket.send_json({"type": "catchup", "content": pending})

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=CLAW_HEARTBEAT_INTERVAL)
                    await websocket.send_json(event)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "heartbeat"})
        except (WebSocketDisconnect, asyncio.CancelledError, Exception):
            pass

    file_service = get_file_service()

    async def _process_files(
        file_ids: list[str], uid: str
    ) -> tuple[str, list[ClawAttachment]]:
        current = await claw_service.get_session(uid, session_id)
        claw_base_url = current.http_base_url if current else None

        refs: list[str] = []
        attachments: list[ClawAttachment] = []
        for fid in file_ids:
            try:
                stream, info = await file_service.download_file(fid, uid)
                ct = info.content_type or ""
                filename = info.filename or fid
                raw = stream.read() if hasattr(stream, "read") else b""

                attachments.append(ClawAttachment(
                    file_id=fid, filename=filename,
                    content_type=ct, size=info.size or 0,
                ))

                if not claw_base_url:
                    refs.append(f'<MANUS_FILE name="{filename}" id="{fid}" status="no_claw" />')
                    continue

                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{claw_base_url}/workspace",
                        params={"file_id": fid, "filename": filename},
                        content=raw,
                        headers={"Content-Type": "application/octet-stream"},
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    local_path = result.get("path", "")

                refs.append(
                    f'<MANUS_FILE path="{local_path}" name="{filename}" '
                    f'id="{fid}" type="{ct}" size="{info.size}" />'
                )
                logger.info("[claw-ws] pushed %s to workspace: %s", filename, local_path)

            except Exception as e:
                logger.warning("[claw-ws] failed to process file %s: %s", fid, e)
                refs.append(
                    f'<MANUS_FILE name="{fid}" id="{fid}" status="download_failed" '
                    f'reason="{str(e)[:100]}" />'
                )

        return "\n".join(refs), attachments

    async def _read_messages() -> None:
        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type")
                if msg_type == "chat":
                    message = data.get("message", "").strip()
                    file_ids = data.get("file_ids", [])
                    user_attachments: list[ClawAttachment] = []

                    if file_ids:
                        file_refs, user_attachments = await _process_files(file_ids, user.id)
                        if file_refs:
                            message = f"{message}\n\n{file_refs}" if message else file_refs

                    if message:
                        try:
                            await claw_service.send_message(user.id, session_id, message)
                            if user_attachments:
                                await claw_service.claw_repository.append_message(
                                    session_id, "attachments", "user", attachments=user_attachments,
                                )
                        except Exception as e:
                            await websocket.send_json({"type": "error", "error": str(e)})
        except (WebSocketDisconnect, asyncio.CancelledError, Exception):
            pass

    write_task = asyncio.create_task(_write_events())
    read_task = asyncio.create_task(_read_messages())

    try:
        _done, pending = await asyncio.wait(
            [write_task, read_task], return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
    finally:
        claw_service.event_bus.unsubscribe(session_id, queue)


@router.websocket("/vnc/{session_id}")
async def vnc_ws(websocket: WebSocket, session_id: str):
    """Sandbox VNC proxy (binary) — Cookie / Bearer auth, no signed URL.

    Client should negotiate subprotocol ``binary`` (NoVNC default).
    """
    try:
        user = await resolve_ws_user(websocket)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    agent_service = get_agent_service()
    session = await agent_service.get_session(session_id, user.id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await websocket.accept(subprotocol="binary")
    logger.info("Accepted VNC WS for session %s user %s", session_id, user.id)

    try:
        sandbox_ws_url = await agent_service.get_vnc_url(session_id)
        logger.info("Connecting to sandbox VNC at %s", sandbox_ws_url)

        async with websockets.connect(sandbox_ws_url) as sandbox_ws:
            async def forward_to_sandbox() -> None:
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await sandbox_ws.send(data)
                except WebSocketDisconnect:
                    logger.info("Web -> VNC connection closed")
                except Exception as e:
                    logger.error("Error forwarding data to sandbox: %s", e)

            async def forward_from_sandbox() -> None:
                try:
                    while True:
                        data = await sandbox_ws.recv()
                        await websocket.send_bytes(data)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("VNC -> Web connection closed")
                except Exception as e:
                    logger.error("Error forwarding data from sandbox: %s", e)

            forward_task1 = asyncio.create_task(forward_to_sandbox())
            forward_task2 = asyncio.create_task(forward_from_sandbox())
            _done, pending = await asyncio.wait(
                [forward_task1, forward_task2],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
    except ConnectionError as e:
        logger.error("Unable to connect to sandbox environment: %s", e)
        try:
            await websocket.close(
                code=1011,
                reason=f"Unable to connect to sandbox environment: {str(e)}",
            )
        except Exception:
            pass
    except Exception as e:
        logger.error("VNC WebSocket error: %s", e)
        try:
            await websocket.close(code=1011, reason=f"WebSocket error: {str(e)}")
        except Exception:
            pass


@router.websocket("/claw/vnc/{session_id}")
async def claw_vnc_ws(websocket: WebSocket, session_id: str):
    """Claw sandbox VNC proxy (binary) — Cookie / Bearer auth, no signed URL.

    Mirrors ``vnc_ws`` above, but looks up the session via ``claw_service``
    (same ownership check as ``/claw/{session_id}``) and resolves the
    target VNC URL via ``claw_service.get_vnc_url``.

    Client should negotiate subprotocol ``binary`` (NoVNC default).
    """
    try:
        user = await resolve_ws_user(websocket)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    claw_service = get_claw_service()
    session = await claw_service.get_session(user.id, session_id)
    if not session:
        await websocket.close(code=4004, reason="Claw session not found")
        return

    await websocket.accept(subprotocol="binary")
    logger.info("Accepted Claw VNC WS for session %s user %s", session_id, user.id)

    try:
        claw_vnc_url = await claw_service.get_vnc_url(session_id, user.id)
        logger.info("Connecting to Claw VNC at %s", claw_vnc_url)

        async with websockets.connect(claw_vnc_url) as claw_ws:
            async def forward_to_claw() -> None:
                try:
                    while True:
                        data = await websocket.receive_bytes()
                        await claw_ws.send(data)
                except WebSocketDisconnect:
                    logger.info("Web -> Claw VNC connection closed")
                except Exception as e:
                    logger.error("Error forwarding data to Claw VNC: %s", e)

            async def forward_from_claw() -> None:
                try:
                    while True:
                        data = await claw_ws.recv()
                        await websocket.send_bytes(data)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("Claw VNC -> Web connection closed")
                except Exception as e:
                    logger.error("Error forwarding data from Claw VNC: %s", e)

            forward_task1 = asyncio.create_task(forward_to_claw())
            forward_task2 = asyncio.create_task(forward_from_claw())
            _done, pending = await asyncio.wait(
                [forward_task1, forward_task2],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
    except ValueError as e:
        logger.error("Claw VNC unavailable for session %s: %s", session_id, e)
        try:
            await websocket.close(code=4004, reason=str(e))
        except Exception:
            pass
    except ConnectionError as e:
        logger.error("Unable to connect to Claw environment: %s", e)
        try:
            await websocket.close(
                code=1011,
                reason=f"Unable to connect to Claw environment: {str(e)}",
            )
        except Exception:
            pass
    except Exception as e:
        logger.error("Claw VNC WebSocket error: %s", e)
        try:
            await websocket.close(code=1011, reason=f"WebSocket error: {str(e)}")
        except Exception:
            pass


@router.websocket("/claw/terminal/{session_id}")
async def claw_terminal_ws(websocket: WebSocket, session_id: str):
    """Claw Operator Terminal proxy — Cookie / Bearer auth, no signed URL.

    Unlike ``claw_vnc_ws`` (raw binary), this proxies JSON *text* frames:
    Task 5's plugin WS endpoint exchanges JSON messages, not raw bytes, so
    forwarding is ``receive_text``/``send_text`` in both directions rather
    than ``receive_bytes``/``send_bytes``. Frames are passed through
    unparsed — this route only needs to move bytes between the two sockets,
    not interpret the protocol.

    Optional query params ``?cols=&rows=`` size the initial PTY (defaults
    80x24, matching the plugin's own defaults per Task 5's report); resizing
    afterwards is a client -> server ``{"type":"resize",...}`` message,
    forwarded like any other frame.

    Client -> Server (forwarded as-is to the Claw container):
      {"type":"input","data":"..."}
      {"type":"resize","cols":100,"rows":30}

    Server -> Client (forwarded as-is from the Claw container):
      {"type":"data","seq":N,"data":"..."}
      {"type":"exit","exit_code":...,"signal":...,"reason":"..."}
      {"type":"error","error":"..."}
    """
    try:
        user = await resolve_ws_user(websocket)
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    claw_service = get_claw_service()
    session = await claw_service.get_session(user.id, session_id)
    if not session:
        await websocket.close(code=4004, reason="Claw session not found")
        return

    def _int_query_param(name: str, default: int) -> int:
        raw = websocket.query_params.get(name)
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    cols = _int_query_param("cols", 80)
    rows = _int_query_param("rows", 24)

    await websocket.accept()
    logger.info("Accepted Claw terminal WS for session %s user %s", session_id, user.id)

    try:
        terminal_ws_url, terminal_session_id = await claw_service.open_terminal(
            user.id, session_id, cols, rows,
        )
        logger.info(
            "Opened Claw terminal %s for session %s, connecting to %s",
            terminal_session_id, session_id, terminal_ws_url,
        )

        async with websockets.connect(terminal_ws_url) as terminal_ws:
            async def forward_to_terminal() -> None:
                try:
                    while True:
                        data = await websocket.receive_text()
                        await terminal_ws.send(data)
                except WebSocketDisconnect:
                    logger.info("Web -> Claw terminal connection closed")
                except Exception as e:
                    logger.error("Error forwarding data to Claw terminal: %s", e)

            async def forward_from_terminal() -> None:
                try:
                    while True:
                        data = await terminal_ws.recv()
                        if isinstance(data, bytes):
                            data = data.decode("utf-8", errors="replace")
                        await websocket.send_text(data)
                except websockets.exceptions.ConnectionClosed:
                    logger.info("Claw terminal -> Web connection closed")
                except Exception as e:
                    logger.error("Error forwarding data from Claw terminal: %s", e)

            forward_task1 = asyncio.create_task(forward_to_terminal())
            forward_task2 = asyncio.create_task(forward_from_terminal())
            _done, pending = await asyncio.wait(
                [forward_task1, forward_task2],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
    except ValueError as e:
        logger.error("Claw terminal unavailable for session %s: %s", session_id, e)
        try:
            await websocket.close(code=4004, reason=str(e))
        except Exception:
            pass
    except ConnectionError as e:
        logger.error("Unable to connect to Claw terminal: %s", e)
        try:
            await websocket.close(
                code=1011,
                reason=f"Unable to connect to Claw terminal: {str(e)}",
            )
        except Exception:
            pass
    except Exception as e:
        logger.error("Claw terminal WebSocket error: %s", e)
        try:
            await websocket.close(code=1011, reason=f"WebSocket error: {str(e)}")
        except Exception:
            pass
