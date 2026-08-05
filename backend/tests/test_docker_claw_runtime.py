"""Unit tests for DockerClawRuntime's volume-per-session mounting and the
cross-session container cleanup fix.

Pure unit tests — the ``docker`` SDK client is mocked, no real Docker daemon
needed. What matters here: create() mounts the given volume_name at
OpenClaw's home dir, reuses an existing volume rather than recreating it (the
whole point — recreating would wipe memory), the stale-container cleanup is
scoped to this session's own container name (not a prefix sweep that could
hit other sessions/users), and destroy_volume only ever runs on the volume
the caller names, never as a side effect of destroy()/create().
"""
from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.external.claw.docker_claw_runtime import DockerClawRuntime


class FakeDockerNotFound(Exception):
    pass


def make_docker_client(container_exists: bool = False, volume_exists: bool = False):
    client = MagicMock()
    client.errors = MagicMock()
    client.containers.get.side_effect = (
        None if container_exists else FakeDockerNotFound()
    )
    client.volumes.get.side_effect = (
        None if volume_exists else FakeDockerNotFound()
    )
    container = MagicMock()
    container.attrs = {"NetworkSettings": {"IPAddress": "172.18.0.9"}}
    client.containers.run.return_value = container
    return client


@pytest.fixture
def mock_docker():
    with patch("docker.from_env") as from_env, patch("docker.errors") as errors_mod:
        errors_mod.NotFound = FakeDockerNotFound
        client = make_docker_client()
        from_env.return_value = client
        yield client


class TestVolumeMounting:
    @pytest.mark.asyncio
    async def test_create_mounts_the_given_volume_at_openclaw_home(self, mock_docker):
        runtime = DockerClawRuntime()
        await runtime.create("session-abc123", "api-key-1", "claw-session-vol-abc")

        _, kwargs = mock_docker.containers.run.call_args
        assert kwargs["volumes"] == {
            "claw-session-vol-abc": {"bind": "/home/node/.openclaw", "mode": "rw"}
        }

    @pytest.mark.asyncio
    async def test_reuses_an_existing_volume_instead_of_recreating_it(self, mock_docker):
        """The whole point: a restart within the same session must not wipe
        the volume that carries OpenClaw's native memory."""
        mock_docker.volumes.get.side_effect = None  # volume already exists
        runtime = DockerClawRuntime()
        await runtime.create("session-abc123", "api-key-1", "claw-session-vol-abc")

        mock_docker.volumes.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_the_volume_when_it_does_not_exist_yet(self, mock_docker):
        runtime = DockerClawRuntime()
        await runtime.create("session-abc123", "api-key-1", "claw-session-vol-abc")

        mock_docker.volumes.create.assert_called_once_with(name="claw-session-vol-abc")


class TestCleanupScoping:
    @pytest.mark.asyncio
    async def test_stale_cleanup_targets_only_this_sessions_container_name(self, mock_docker):
        """Regression guard for the cross-session/cross-user bug: creating a
        session must never sweep-remove containers by shared prefix."""
        runtime = DockerClawRuntime()
        await runtime.create("session-abc123", "api-key-1", "claw-session-vol-abc")

        # containers.list() (the old prefix-sweep mechanism) must not be used.
        mock_docker.containers.list.assert_not_called()
        # Only a lookup by this exact container's own name.
        mock_docker.containers.get.assert_any_call("manus-claw-session-")

    @pytest.mark.asyncio
    async def test_removes_its_own_stale_container_before_recreating(self, mock_docker):
        mock_docker.containers.get.side_effect = None  # a stale one exists
        stale_container = MagicMock()
        mock_docker.containers.get.return_value = stale_container

        runtime = DockerClawRuntime()
        await runtime.create("session-abc123", "api-key-1", "claw-session-vol-abc")

        stale_container.remove.assert_called_once_with(force=True)


class TestDestroy:
    @pytest.mark.asyncio
    async def test_destroy_never_touches_the_volume(self, mock_docker):
        runtime = DockerClawRuntime()
        await runtime.destroy("manus-claw-session-abc123")

        mock_docker.volumes.get.assert_not_called()
        mock_docker.volumes.remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_destroy_volume_removes_only_the_named_volume(self, mock_docker):
        mock_docker.volumes.get.side_effect = None
        volume = MagicMock()
        mock_docker.volumes.get.return_value = volume

        runtime = DockerClawRuntime()
        await runtime.destroy_volume("claw-session-vol-abc")

        mock_docker.volumes.get.assert_called_once_with("claw-session-vol-abc")
        volume.remove.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_destroy_volume_is_a_noop_for_a_missing_volume(self, mock_docker):
        runtime = DockerClawRuntime()
        # Must not raise even though the volume doesn't exist.
        await runtime.destroy_volume("does-not-exist")

    @pytest.mark.asyncio
    async def test_destroy_with_no_instance_name_is_a_noop(self, mock_docker):
        runtime = DockerClawRuntime()
        await runtime.destroy(None)
        mock_docker.containers.get.assert_not_called()
