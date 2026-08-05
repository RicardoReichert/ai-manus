import re
import secrets
import uuid
import logging
from datetime import datetime, timedelta, UTC
from typing import Optional, List

import httpx

from app.domain.models.claw import ClawSession, ClawStatus, ClawMessage, ClawAttachment
from app.domain.external.claw import ClawRuntime, ClawClient
from app.domain.repositories.claw_repository import ClawSessionRepository

logger = logging.getLogger(__name__)


def _generate_api_key() -> str:
    """Generate a secure per-session API key for LLM proxy authentication"""
    return f"manus-{secrets.token_urlsafe(32)}"


def _generate_session_id() -> str:
    return str(uuid.uuid4())


def _volume_name_for(session_id: str) -> str:
    """Deterministic Docker volume name for a session's persistent state.

    Same session_id always maps to the same volume — that's what lets a
    restart (destroy container, create a new one) reattach to the exact
    volume that carries OpenClaw's native memory, instead of accidentally
    diverging.
    """
    return f"claw-session-vol-{session_id[:8]}"


class ClawDomainService:
    """Domain service for Claw session lifecycle, history merge, and auth logic.

    This service encapsulates pure business rules that are independent of
    application-level concerns (event bus, background task scheduling, etc.).

    A user may own several sessions (unlike the old 1:1 Claw). A session is
    the durable identity — its ``volume_name`` is what survives a container
    being destroyed and recreated; the container itself is disposable. The
    model is chosen at session creation and only ever changes via
    ``restart_session``, never silently.
    """

    def __init__(
        self,
        claw_session_repository: ClawSessionRepository,
        claw_runtime: ClawRuntime,
        claw_client: ClawClient,
    ):
        self.claw_repository = claw_session_repository
        self.claw_runtime = claw_runtime
        self.claw_client = claw_client

    # ------------------------------------------------------------------
    # Session CRUD / lifecycle
    # ------------------------------------------------------------------

    async def list_sessions(self, user_id: str) -> List[ClawSession]:
        sessions = await self.claw_repository.list_by_user_id(user_id)
        checked = [await self._check_expiry(s) for s in sessions]
        return [s for s in checked if s is not None]

    async def get_session(self, user_id: str, session_id: str) -> Optional[ClawSession]:
        """Get a session, scoped to its owner — never returns another user's session."""
        session = await self.claw_repository.get_by_id(session_id)
        if not session or session.user_id != user_id:
            return None
        return await self._check_expiry(session)

    async def _check_expiry(self, session: ClawSession) -> Optional[ClawSession]:
        """Lazily stop an expired session's container, or mark it stopped if
        unreachable. Unlike the old per-user Claw, expiry never deletes the
        record or its volume — only explicit deletion does that. A session
        must stay visible/restartable in the list after its container dies.
        """
        if session.status != ClawStatus.RUNNING:
            return session

        expires = session.expires_at
        if expires and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires and datetime.now(UTC) >= expires:
            logger.info(f"[claw] session {session.id} expired, stopping container")
            await self.claw_runtime.destroy(session.container_name)
            session.status = ClawStatus.STOPPED
            session.container_name = None
            session.container_ip = None
            return await self.claw_repository.update(session)

        if session.http_base_url and not await self._health_check(session.http_base_url):
            logger.warning(f"[claw] session {session.id} health check failed, marking stopped")
            session.status = ClawStatus.STOPPED
            return await self.claw_repository.update(session)

        return session

    @staticmethod
    async def _health_check(base_url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def create_session(
        self, user_id: str, model_id: str, name: Optional[str] = None,
    ) -> ClawSession:
        """Create a new session with a fresh (empty-memory) volume.

        ``model_id`` is required — there is no "pick later" path; a session
        always starts pinned to a specific model, per the product decision
        that model choice is mandatory at creation.
        """
        session_id = _generate_session_id()
        session = ClawSession(
            id=session_id,
            user_id=user_id,
            name=name,
            model_id=model_id,
            volume_name=_volume_name_for(session_id),
            api_key=_generate_api_key(),
            status=ClawStatus.CREATING,
        )
        return await self.claw_repository.create(session)

    async def provision_session(self, session: ClawSession, ttl_seconds: Optional[int] = None) -> None:
        """Provision (or reprovision) the container behind a session.

        Intended to be called in a background task after ``create_session``
        or ``restart_session``. Always reuses ``session.volume_name`` — never
        generates a new one — so OpenClaw's native memory for this session
        carries over regardless of how many times this runs.
        """
        try:
            started_at = datetime.now(UTC)
            info = await self.claw_runtime.create(session.id, session.api_key, session.volume_name)
            session.container_name = info.instance_name
            session.container_ip = info.address
            await self.claw_repository.update(session)
            if session.http_base_url:
                ready = await self.claw_runtime.wait_for_ready(session.http_base_url)
                if not ready:
                    raise RuntimeError(f"Claw service not ready: {session.http_base_url}")
            logger.info(f"Claw session provisioned: id={session.id} address={info.address}")
            session.status = ClawStatus.RUNNING
            session.error_message = None
            if ttl_seconds and ttl_seconds > 0:
                session.expires_at = started_at + timedelta(seconds=ttl_seconds)
            await self.claw_repository.update(session)
        except Exception as e:
            logger.error(f"Failed to provision claw session {session.id}: {e}")
            session.status = ClawStatus.ERROR
            session.error_message = str(e)
            await self.claw_runtime.destroy(session.container_name)
            session.container_name = None
            session.container_ip = None
            try:
                await self.claw_repository.update(session)
            except Exception:
                pass

    async def restart_session(
        self, user_id: str, session_id: str, model_id: str,
    ) -> Optional[ClawSession]:
        """Kill the current container (if any) and start a fresh one on the
        SAME volume, pointed at ``model_id``.

        This is the only way to change a session's model — the model is
        pinned while a container is live, matching the product requirement
        that switching models is a deliberate restart, not a silent runtime
        swap. Because the volume is untouched, OpenClaw's native memory for
        this session survives the restart in full, even across a model
        change — verified with a real container: a second, freshly-started
        container correctly recalled information only ever told to the
        first, now-destroyed one.
        """
        session = await self.get_session(user_id, session_id)
        if not session:
            return None

        if session.container_name:
            await self.claw_runtime.destroy(session.container_name)

        session.model_id = model_id
        session.status = ClawStatus.CREATING
        session.container_name = None
        session.container_ip = None
        session.error_message = None
        session = await self.claw_repository.update(session)
        return session

    async def delete_session(self, user_id: str, session_id: str) -> bool:
        """Delete a session's record, its container, AND its volume.

        This is the only operation that actually discards a session's
        memory — restarting (even with a different model) preserves the
        volume; only this removes it.
        """
        session = await self.get_session(user_id, session_id)
        if not session:
            return False
        await self.claw_runtime.destroy(session.container_name)
        await self.claw_runtime.destroy_volume(session.volume_name)
        return await self.claw_repository.delete_by_id(session_id)

    # ------------------------------------------------------------------
    # History merge
    # ------------------------------------------------------------------

    async def get_history(self, user_id: str, session_id: str) -> List[ClawMessage]:
        """Merge MongoDB messages with OpenClaw's native session history."""
        session = await self.get_session(user_id, session_id)
        if not session:
            return []

        db_msgs = await self.claw_repository.get_messages(session_id)

        claw_msgs: List[ClawMessage] = []
        try:
            if session.http_base_url and session.status == ClawStatus.RUNNING:
                claw_msgs = await self.claw_client.get_history(
                    session.http_base_url, session.id, 200,
                )
        except Exception as e:
            logger.warning(f"[claw-history] failed to fetch claw native history: {e}")

        if not claw_msgs:
            return db_msgs

        return self._merge_histories(db_msgs, claw_msgs)

    @staticmethod
    def _normalize_ts(ts: int) -> int:
        """Normalize timestamp to seconds (Claw uses ms, MongoDB uses seconds)."""
        if ts > 1_000_000_000_000:
            return ts // 1000
        return ts

    @staticmethod
    def _strip_openclaw_prefix(text: str) -> str:
        """Strip OpenClaw's timestamp prefix like '[Sat 2026-03-21 11:11 UTC] '."""
        return re.sub(r'^\[.*?\]\s*', '', text)

    @classmethod
    def _normalize_content(cls, text: str) -> str:
        """Normalize message text for dedup comparison."""
        text = cls._strip_openclaw_prefix(text)
        text = re.sub(r'<MANUS_FILE\b[^>]*/>', '', text)
        return text.strip()

    @classmethod
    def _merge_histories(
        cls, db_msgs: List[ClawMessage], claw_msgs: List[ClawMessage],
    ) -> List[ClawMessage]:
        """Merge two message lists, dedup, return sorted by timestamp.

        DB messages are authoritative; Claw messages fill gaps.
        Uses (role, timestamp proximity, content prefix) for cross-source dedup
        so that identical messages sent at different times are kept distinct.
        Attachment messages are deduped by file_id.
        """

        TS_WINDOW = 5  # seconds tolerance between DB and Claw timestamps

        seen_file_ids: set[str] = set()
        for m in db_msgs:
            if m.role == "attachments" and m.attachments:
                for att in m.attachments:
                    if att.file_id:
                        seen_file_ids.add(att.file_id)

        db_fingerprints: list[tuple[str, int, str, bool]] = []
        for m in db_msgs:
            if m.role != "attachments":
                norm = cls._normalize_content(m.content or "")
                db_fingerprints.append((m.role, m.timestamp or 0, norm[:120], False))

        merged: List[ClawMessage] = list(db_msgs)

        for m in claw_msgs:
            ts = cls._normalize_ts(m.timestamp or 0)
            content = cls._normalize_content(m.content or "")

            if m.attachments:
                new_atts = [a for a in m.attachments if a.file_id and a.file_id not in seen_file_ids]
                if new_atts:
                    for a in new_atts:
                        seen_file_ids.add(a.file_id)
                    att_role = "user" if m.role == "user" else "assistant"
                    merged.append(ClawMessage(
                        role="attachments", content=att_role,
                        timestamp=ts, attachments=new_atts,
                    ))

            if not content:
                continue

            prefix = content[:120]
            matched = False
            for idx, (fp_role, fp_ts, fp_prefix, fp_used) in enumerate(db_fingerprints):
                if fp_used:
                    continue
                if fp_role != m.role:
                    continue
                if abs(fp_ts - ts) > TS_WINDOW:
                    continue
                if fp_prefix == prefix:
                    db_fingerprints[idx] = (fp_role, fp_ts, fp_prefix, True)
                    matched = True
                    break

            if not matched:
                merged.append(ClawMessage(
                    role=m.role, content=content, timestamp=ts,
                ))

        merged.sort(key=lambda m: m.timestamp or 0)
        return merged

    # ------------------------------------------------------------------
    # Chat processing (core streaming logic)
    # ------------------------------------------------------------------

    async def process_chat_stream(
        self, session_id: str, base_url: str, message: str,
    ):
        """Stream chat from the claw client, persisting messages.

        Yields raw chunk dicts from the claw client. The caller is responsible
        for broadcasting chunks to WebSocket consumers. The OpenClaw-native
        session key sent to the container is always this session's own id —
        there is no separate user-suppliable session_id anymore, since the
        session *is* the resource now.
        """
        assistant_content: list[str] = []
        file_attachments: list[ClawAttachment] = []

        try:
            async for chunk in self.claw_client.chat_stream(base_url, message, session_id):
                if chunk.get("type") == "text" and chunk.get("content"):
                    assistant_content.append(chunk["content"])

                if chunk.get("type") == "file" and chunk.get("file_id"):
                    file_attachments.append(ClawAttachment(
                        file_id=chunk["file_id"],
                        filename=chunk.get("filename", chunk["file_id"]),
                        content_type=chunk.get("content_type"),
                        size=chunk.get("size", 0),
                        file_url=chunk.get("file_url"),
                    ))

                yield chunk

        finally:
            if file_attachments:
                await self.claw_repository.append_message(
                    session_id, "attachments", "assistant", attachments=file_attachments,
                )
            if assistant_content:
                await self.claw_repository.append_message(
                    session_id, "assistant", "".join(assistant_content),
                )

    async def validate_session_for_chat(self, user_id: str, session_id: str) -> ClawSession:
        """Validate that a session is running and ready for chat.

        Returns the session or raises ValueError.
        """
        session = await self.get_session(user_id, session_id)
        if not session or not session.http_base_url:
            raise ValueError("No running claw session found")
        if session.status != ClawStatus.RUNNING:
            raise ValueError(f"Claw session is not running (status: {session.status})")
        return session

    # ------------------------------------------------------------------
    # File proxy
    # ------------------------------------------------------------------

    async def get_file(self, user_id: str, session_id: str, filename: str) -> tuple[bytes, str]:
        session = await self.get_session(user_id, session_id)
        if not session or not session.http_base_url:
            raise ValueError("No running claw session found")
        if session.status != ClawStatus.RUNNING:
            raise ValueError(f"Claw session is not running (status: {session.status})")
        return await self.claw_client.get_file(session.http_base_url, filename)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def verify_api_key(self, api_key: str, system_api_key: Optional[str] = None) -> Optional[str]:
        """Verify a claw API key and return the associated user ID.

        ``system_api_key`` is an optional global key (from settings) that
        bypasses per-session lookup and returns a fixed service account ID
        (used by the dev-mode fixed/shared container).
        """
        if system_api_key and api_key == system_api_key:
            return "claw-service-account"
        session = await self.claw_repository.get_by_api_key(api_key)
        if session:
            return session.user_id
        return None
