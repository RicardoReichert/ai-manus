import asyncio
import logging
from typing import Optional

import httpx

from app.domain.external.claw import ClawInstanceInfo
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DockerClawRuntime:
    """Creates claw instances as local Docker containers."""

    creates_immediately = False

    def __init__(self):
        self.settings = get_settings()

    async def create(self, session_id: str, api_key: str, volume_name: str) -> ClawInstanceInfo:
        import docker
        docker_client = docker.from_env()

        claw_network = self.settings.claw_network
        manus_api_base_url = self.settings.manus_api_base_url
        container_name = f"{self.settings.claw_name_prefix}-{session_id[:8]}"

        # Remove a stale container left over from a previous provisioning
        # attempt for *this session specifically* — scoped to this exact
        # name, not the whole shared prefix. Sweeping every container
        # sharing the prefix (the previous behavior) would force-remove
        # other sessions' — possibly other users' — live containers on every
        # new create() call, which matters a lot more now that many sessions
        # run concurrently instead of at most one globally.
        try:
            docker_client.containers.get(container_name).remove(force=True)
            logger.warning(f"Removed stale claw container before recreate: {container_name}")
        except docker.errors.NotFound:
            pass
        except Exception as e:
            logger.warning(f"Failed to remove stale claw container {container_name}: {e}")

        # Idempotent: reusing an existing volume (a restart within the same
        # session) is exactly what preserves OpenClaw's native memory across
        # container recreation — this must never recreate/wipe the volume.
        try:
            docker_client.volumes.get(volume_name)
        except docker.errors.NotFound:
            docker_client.volumes.create(name=volume_name)
            logger.info(f"Created claw session volume: {volume_name}")

        container_config = {
            "image": self.settings.claw_image,
            "name": container_name,
            "detach": True,
            "remove": True,
            "environment": {
                "CLAW_TTL_SECONDS": str(self.settings.claw_ttl_seconds),
                "MANUS_API_KEY": api_key,
                "MANUS_API_BASE_URL": manus_api_base_url,
            },
            "volumes": {
                volume_name: {"bind": "/home/node/.openclaw", "mode": "rw"},
            },
        }
        if claw_network:
            container_config["network"] = claw_network

        container = docker_client.containers.run(**container_config)
        container.reload()

        network_settings = container.attrs["NetworkSettings"]
        ip_address = network_settings.get("IPAddress", "")
        if not ip_address and "Networks" in network_settings:
            for _, nc in network_settings["Networks"].items():
                if nc.get("IPAddress"):
                    ip_address = nc["IPAddress"]
                    break

        logger.info(
            f"Claw container started: {container_name} ip={ip_address} volume={volume_name}"
        )
        return ClawInstanceInfo(address=ip_address, instance_name=container_name)

    async def destroy(self, instance_name: Optional[str]) -> None:
        if not instance_name:
            return
        try:
            import docker
            docker_client = docker.from_env()
            try:
                container = docker_client.containers.get(instance_name)
            except docker.errors.NotFound:
                # Already gone (e.g. the container's TTL expired and it
                # removed itself) — nothing to do.
                return
            logger.info(f"Removing claw container: {instance_name}")
            container.remove(force=True)
        except Exception as e:
            logger.warning(f"Failed to remove container {instance_name}: {e}")

    async def destroy_volume(self, volume_name: Optional[str]) -> None:
        """Remove a session's persistent volume — only on explicit session delete."""
        if not volume_name:
            return
        try:
            import docker
            docker_client = docker.from_env()
            try:
                volume = docker_client.volumes.get(volume_name)
            except docker.errors.NotFound:
                return
            logger.info(f"Removing claw session volume: {volume_name}")
            volume.remove(force=True)
        except Exception as e:
            logger.warning(f"Failed to remove volume {volume_name}: {e}")

    async def wait_for_ready(self, base_url: str) -> bool:
        timeout = self.settings.claw_ready_timeout
        interval = 2.0
        max_retries = int(timeout / interval)
        async with httpx.AsyncClient(timeout=5.0) as client:
            for _ in range(max_retries):
                try:
                    resp = await client.get(f"{base_url}/health")
                    if resp.status_code == 200:
                        logger.info(f"Claw instance ready: {base_url}")
                        return True
                except Exception:
                    pass
                await asyncio.sleep(interval)
        logger.warning(f"Claw instance not ready after {timeout}s: {base_url}")
        return False
