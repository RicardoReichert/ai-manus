"""Unit tests for the database-backed model registry.

No running server and no real MongoDB — the repository is stubbed, so these
exercise the registry's own logic (caching, default selection, credential
delegation) rather than Beanie.
"""
from typing import List, Optional

import pytest

from app.domain.models.model_capabilities import ModelCapabilities
from app.domain.models.model_config import ModelConfig
from app.infrastructure.external.llm import model_registry as registry


class FakeRepository:
    """Minimal stand-in for ModelConfigRepository."""

    def __init__(self, models: Optional[List[ModelConfig]] = None):
        self.models = models or []
        self.api_keys = {}
        self.list_calls = 0
        self.fail_with: Optional[Exception] = None

    async def list_all(self, enabled_only: bool = False) -> List[ModelConfig]:
        self.list_calls += 1
        if self.fail_with:
            raise self.fail_with
        if enabled_only:
            return [m for m in self.models if m.enabled]
        return list(self.models)

    async def get_api_key(self, model_config_id: str) -> Optional[str]:
        return self.api_keys.get(model_config_id)


def make_model(model_id: str, **overrides) -> ModelConfig:
    defaults = dict(id=model_id, name=model_id, provider="openai", model=f"{model_id}-real")
    defaults.update(overrides)
    return ModelConfig(**defaults)


@pytest.fixture
def repo(monkeypatch):
    """Point the registry at a stub repository and start with a cold cache."""
    fake = FakeRepository()
    monkeypatch.setattr(registry, "_repository", lambda: fake)
    registry.invalidate_registry_cache(drop_last_good=True)
    yield fake
    registry.invalidate_registry_cache(drop_last_good=True)


class TestListing:
    async def test_empty_database_yields_no_models(self, repo):
        """A fresh install has nothing until an admin registers or imports."""
        assert await registry.get_all_available_models() == []

    async def test_returns_registered_models(self, repo):
        repo.models = [make_model("a"), make_model("b")]
        assert [m.id for m in await registry.get_all_available_models()] == ["a", "b"]

    async def test_disabled_models_are_excluded(self, repo):
        repo.models = [make_model("a"), make_model("b", enabled=False)]
        assert [m.id for m in await registry.get_all_available_models()] == ["a"]


class TestResolve:
    async def test_resolves_a_known_id(self, repo):
        repo.models = [make_model("a"), make_model("b")]
        assert (await registry.resolve_model("b")).model == "b-real"

    async def test_unknown_id_returns_none(self, repo):
        repo.models = [make_model("a")]
        assert await registry.resolve_model("nope") is None

    async def test_blank_id_returns_none(self, repo):
        repo.models = [make_model("a")]
        assert await registry.resolve_model("") is None

    async def test_a_disabled_model_cannot_be_resolved(self, repo):
        repo.models = [make_model("a", enabled=False)]
        assert await registry.resolve_model("a") is None


class TestDefaultModel:
    async def test_default_is_the_first_enabled_model(self, repo):
        """Ordering is the admin's lever — no magic 'default' id anymore."""
        repo.models = [make_model("first"), make_model("second")]
        assert (await registry.get_default_model()).id == "first"

    async def test_default_is_none_when_nothing_registered(self, repo):
        assert await registry.get_default_model() is None


class TestCache:
    async def test_reads_once_within_the_ttl(self, repo):
        repo.models = [make_model("a")]
        await registry.get_all_available_models()
        await registry.get_all_available_models()
        assert repo.list_calls == 1

    async def test_invalidate_forces_a_reload(self, repo):
        repo.models = [make_model("a")]
        await registry.get_all_available_models()
        registry.invalidate_registry_cache()
        await registry.get_all_available_models()
        assert repo.list_calls == 2

    async def test_admin_edits_are_visible_after_invalidation(self, repo):
        repo.models = [make_model("a")]
        await registry.get_all_available_models()
        repo.models.append(make_model("b"))
        registry.invalidate_registry_cache()
        assert [m.id for m in await registry.get_all_available_models()] == ["a", "b"]


class TestFailureHandling:
    async def test_a_database_error_does_not_raise(self, repo):
        """Chat must not hard-fail because the registry read blipped."""
        repo.fail_with = RuntimeError("mongo down")
        assert await registry.get_all_available_models() == []

    async def test_serves_the_last_known_list_when_the_database_fails(self, repo):
        repo.models = [make_model("a")]
        await registry.get_all_available_models()
        registry.invalidate_registry_cache()
        repo.fail_with = RuntimeError("mongo down")
        assert [m.id for m in await registry.get_all_available_models()] == ["a"]


class TestApiKey:
    async def test_returns_the_decrypted_credential(self, repo):
        model = make_model("a")
        repo.models = [model]
        repo.api_keys["a"] = "sk-secret"
        assert await registry.api_key_for(model) == "sk-secret"

    async def test_none_when_the_model_has_no_credential(self, repo):
        """Correct for local runtimes (LM Studio / Ollama) needing no auth."""
        model = make_model("a")
        repo.models = [model]
        assert await registry.api_key_for(model) is None

    async def test_none_model_is_tolerated(self, repo):
        assert await registry.api_key_for(None) is None


class TestCapabilitiesSurvive:
    async def test_capabilities_reach_the_caller(self, repo):
        """The gateway needs these to adapt; they must not be dropped."""
        repo.models = [make_model("small", capabilities=ModelCapabilities(max_tools=8))]
        resolved = await registry.resolve_model("small")
        assert resolved.capabilities.max_tools == 8
