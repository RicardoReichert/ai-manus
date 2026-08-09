from typing import Optional, List, AsyncIterator, Protocol
from dataclasses import dataclass

from app.domain.models.claw import ClawMessage


@dataclass
class ClawInstanceInfo:
    """Connection info returned after creating a claw instance."""
    address: str
    instance_name: Optional[str] = None


class ClawRuntime(Protocol):
    """Manages the lifecycle of claw instances.

    Implementations may use Docker (local), a remote HTTP API,
    Kubernetes, SSH, or any other provisioning mechanism.
    """

    creates_immediately: bool

    async def create(self, session_id: str, api_key: str, volume_name: str) -> ClawInstanceInfo:
        """Create a new claw container, attached to a persistent volume.

        ``volume_name`` is mounted at OpenClaw's home directory inside the
        container — reusing the same name across calls (e.g. on restart with
        a different model) is what lets OpenClaw's own native session memory
        survive the container being destroyed and recreated. The volume
        itself is never created here on destroy; only ``destroy_volume``
        removes it, so a container restart never touches memory.
        """
        ...

    async def destroy(self, instance_name: Optional[str]) -> None:
        """Destroy a claw container (best-effort, should not raise).

        Never removes the backing volume — that's ``destroy_volume``,
        called only when a session itself is deleted.
        """
        ...

    async def destroy_volume(self, volume_name: Optional[str]) -> None:
        """Remove a session's persistent volume (best-effort, should not raise).

        Only called on explicit session deletion — this is the one operation
        that actually discards a session's memory for good.
        """
        ...

    async def wait_for_ready(self, base_url: str) -> bool:
        """Wait until the claw instance is healthy. Returns True if ready."""
        ...


class ClawClient(Protocol):
    """Communicates with a running claw instance.

    Implementations may use HTTP, gRPC, or any other protocol.
    """

    def chat_stream(
        self, base_url: str, message: str, session_id: str,
    ) -> AsyncIterator[dict]:
        """Stream chat response chunks from a claw instance.
        Yields dicts with at minimum a 'type' key ('text', 'file', 'done', 'error')."""
        ...

    async def get_history(
        self, base_url: str, session_id: str, limit: int = 200,
    ) -> List[ClawMessage]:
        """Fetch native session history from a claw instance."""
        ...

    async def get_file(self, base_url: str, filename: str) -> tuple[bytes, str]:
        """Download a file. Returns (content_bytes, content_type)."""
        ...

    async def open_terminal(
        self, base_url: str, cols: int = 80, rows: int = 24,
    ) -> dict:
        """POST /terminal/open on the claw instance's plugin server.

        Returns the plugin's JSON response
        (``{"session_id", "agent_id", "shell", "cwd", "confined"}``)."""
        ...
