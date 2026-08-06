"""Unit tests for ``openai_routes._resolve_llm_target``'s shared-container
fallback.

In development, ``settings.claw_address`` points every Claw session at one
physical container (``FixedClawRuntime``), so every proxied LLM call
authenticates with the same fixed system API key — no per-session key
survives to identify which session a call belongs to, and the model chosen
in the UI (persisted on the session record) can never take effect. This
covers the fallback: when the system key is used, resolve via the most
recently updated session instead of silently defaulting to the first
enabled model.

Pure unit tests — no server, no Mongo, no Docker.
"""
from typing import Optional

import pytest

from app.domain.models.claw import ClawSession, ClawStatus
from app.domain.models.model_config import ModelConfig

SYSTEM_KEY = "manus-dev-api-key-changeme"


def _session(model_id: str, api_key: str = "session-specific-key") -> ClawSession:
    return ClawSession(
        id="sess-1",
        user_id="user-1",
        model_id=model_id,
        volume_name="claw-session-vol-sess-1",
        api_key=api_key,
        status=ClawStatus.RUNNING,
    )


class FakeClawSessionRepository:
    def __init__(self, most_recent: Optional[ClawSession] = None):
        self._most_recent = most_recent
        self.by_api_key: dict[str, ClawSession] = {}
        if most_recent:
            self.by_api_key[most_recent.api_key] = most_recent

    async def get_by_api_key(self, api_key: str) -> Optional[ClawSession]:
        return self.by_api_key.get(api_key)

    async def get_most_recently_updated(self) -> Optional[ClawSession]:
        return self._most_recent


class FakeClawService:
    def __init__(self, claw_repository: FakeClawSessionRepository):
        self.claw_repository = claw_repository


def _model(model_id: str) -> ModelConfig:
    return ModelConfig(id=model_id, name=model_id, provider="openai", model=model_id)


@pytest.fixture
def patched_registry(monkeypatch):
    """Stand in a tiny two-model registry: 'first-enabled' is what a naive
    default-model fallback would pick; 'chosen-by-user' is what the test
    expects to win once the shared-container fallback is wired in."""
    from app.interfaces.api import openai_routes as routes

    models = {
        "first-enabled": _model("first-enabled"),
        "chosen-by-user": _model("chosen-by-user"),
    }

    async def fake_resolve_model(model_id: str):
        return models.get(model_id)

    async def fake_get_default_model():
        return models["first-enabled"]

    async def fake_api_key_for(desc):
        return None

    captured = {}

    def fake_get_langchain_llm(model, provider, base_url, api_key, capabilities):
        captured["model"] = model
        return object()

    monkeypatch.setattr(routes, "resolve_model", fake_resolve_model)
    monkeypatch.setattr(routes, "get_default_model", fake_get_default_model)
    monkeypatch.setattr(routes, "api_key_for", fake_api_key_for)
    monkeypatch.setattr(routes, "get_langchain_llm", fake_get_langchain_llm)
    return captured


@pytest.mark.asyncio
async def test_exact_session_api_key_match_wins(monkeypatch, patched_registry):
    """Baseline (production shape): a session's own api_key resolves its own model."""
    from app.interfaces.api import openai_routes as routes

    session = _session("chosen-by-user", api_key="session-owns-this-key")
    fake_service = FakeClawService(FakeClawSessionRepository(most_recent=session))

    async def fake_get_claw_service():
        return fake_service

    monkeypatch.setattr(routes, "_get_claw_service", fake_get_claw_service)

    await routes._resolve_llm_target("manus-proxy/default", api_key="session-owns-this-key")

    assert patched_registry["model"] == "chosen-by-user"


@pytest.mark.asyncio
async def test_shared_container_system_key_falls_back_to_most_recent_session(
    monkeypatch, patched_registry,
):
    """Reproduces the reported bug: dev's shared FixedClawRuntime container
    always calls in with the fixed system key, which never matches any
    session's own api_key. Before the fix this fell straight through to
    get_default_model() ('first-enabled') regardless of what the user
    picked in the UI. It should resolve via the most recently updated
    session instead.
    """
    from app.core.config import get_settings
    from app.interfaces.api import openai_routes as routes

    most_recent_session = _session("chosen-by-user", api_key="some-other-sessions-key")
    fake_service = FakeClawService(FakeClawSessionRepository(most_recent=most_recent_session))

    async def fake_get_claw_service():
        return fake_service

    settings = get_settings()
    monkeypatch.setattr(settings, "claw_address", "claw", raising=False)
    monkeypatch.setattr(settings, "claw_api_key", SYSTEM_KEY, raising=False)
    monkeypatch.setattr(routes, "_get_claw_service", fake_get_claw_service)

    # The physical container always authenticates with the fixed system key,
    # never the DB-side session's own generated api_key.
    await routes._resolve_llm_target("manus-proxy/default", api_key=SYSTEM_KEY)

    assert patched_registry["model"] == "chosen-by-user"


@pytest.mark.asyncio
async def test_unrecognized_api_key_still_falls_back_to_default(
    monkeypatch, patched_registry,
):
    """A key that is neither a real session's nor the configured system key
    must not trigger the shared-container fallback — falls through to the
    plain default-model behavior, unchanged."""
    from app.core.config import get_settings
    from app.interfaces.api import openai_routes as routes

    most_recent_session = _session("chosen-by-user", api_key="some-other-sessions-key")
    fake_service = FakeClawService(FakeClawSessionRepository(most_recent=most_recent_session))

    async def fake_get_claw_service():
        return fake_service

    settings = get_settings()
    monkeypatch.setattr(settings, "claw_address", "claw", raising=False)
    monkeypatch.setattr(settings, "claw_api_key", SYSTEM_KEY, raising=False)
    monkeypatch.setattr(routes, "_get_claw_service", fake_get_claw_service)

    await routes._resolve_llm_target("manus-proxy/default", api_key="totally-unknown-key")

    assert patched_registry["model"] == "first-enabled"
