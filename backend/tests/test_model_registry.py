"""Unit tests for the file-backed model registry.

No running server needed — these exercise model_registry.py directly, the
same style as test_llm_gateway.py.
"""
import json
import os

import pytest

from app.core.config import get_settings
from app.infrastructure.external.llm import model_registry as registry


@pytest.fixture(autouse=True)
def _reset_registry_state(monkeypatch, tmp_path):
    """Isolate each test: fresh cache, fresh models_config_path, no env leakage."""
    registry.invalidate_registry_cache()
    monkeypatch.setattr(get_settings(), "models_config_path", str(tmp_path / "models.json"))
    yield
    registry.invalidate_registry_cache()


def _write_registry(tmp_path, models: list[dict]) -> None:
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"models": models}))


class TestFileLoading:
    @pytest.mark.asyncio
    async def test_missing_file_yields_default_only(self):
        models = await registry.get_all_available_models()
        assert [m.id for m in models] == ["default"]
        assert models[0].name == get_settings().model_name

    @pytest.mark.asyncio
    async def test_malformed_json_is_ignored_not_raised(self, tmp_path):
        (tmp_path / "models.json").write_text("{not valid json")
        models = await registry.get_all_available_models()
        assert [m.id for m in models] == ["default"]

    @pytest.mark.asyncio
    async def test_invalid_entry_is_skipped_not_raised(self, tmp_path):
        _write_registry(tmp_path, [{"id": "bad"}])  # missing required fields
        models = await registry.get_all_available_models()
        assert [m.id for m in models] == ["default"]

    @pytest.mark.asyncio
    async def test_valid_file_merges_and_default_stays_first(self, tmp_path):
        _write_registry(
            tmp_path,
            [
                {"id": "gemini", "name": "Gemini", "provider": "google_genai", "model": "gemini-2.5-flash"},
            ],
        )
        models = await registry.get_all_available_models()
        assert [m.id for m in models] == ["default", "gemini"]

    @pytest.mark.asyncio
    async def test_file_entry_can_override_default(self, tmp_path):
        _write_registry(
            tmp_path,
            [{"id": "default", "name": "Custom Default", "provider": "openai", "model": "gpt-4o-mini"}],
        )
        models = await registry.get_all_available_models()
        assert len(models) == 1
        assert models[0].name == "Custom Default"


class TestResolveModel:
    @pytest.mark.asyncio
    async def test_resolve_known_id(self):
        desc = await registry.resolve_model("default")
        assert desc is not None and desc.id == "default"

    @pytest.mark.asyncio
    async def test_resolve_unknown_id_returns_none(self):
        assert await registry.resolve_model("does-not-exist") is None

    @pytest.mark.asyncio
    async def test_resolve_empty_id_returns_none(self):
        assert await registry.resolve_model("") is None

    @pytest.mark.asyncio
    async def test_discovered_id_maps_to_real_wire_model_name(self, tmp_path):
        # Registry entries may use an opaque id distinct from the provider's
        # own model name — resolve_model must expose both.
        _write_registry(
            tmp_path,
            [{
                "id": "lmstudio:qwen-local",
                "name": "Qwen (local)",
                "provider": "openai",
                "model": "qwen-local",
                "base_url": "http://host.docker.internal:1234/v1",
                "is_local": True,
            }],
        )
        desc = await registry.resolve_model("lmstudio:qwen-local")
        assert desc is not None
        assert desc.id == "lmstudio:qwen-local"
        assert desc.model == "qwen-local"


class TestApiKeyFor:
    @pytest.mark.asyncio
    async def test_prefers_api_key_env_over_global_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_MODEL_KEY", "specific-key")
        _write_registry(
            tmp_path,
            [{
                "id": "custom",
                "name": "Custom",
                "provider": "openai",
                "model": "gpt-4o",
                "api_key_env": "MY_MODEL_KEY",
            }],
        )
        desc = await registry.resolve_model("custom")
        assert registry.api_key_for(desc) == "specific-key"

    @pytest.mark.asyncio
    async def test_falls_back_to_global_key_when_env_unset(self, tmp_path, monkeypatch):
        monkeypatch.delenv("UNSET_MODEL_KEY", raising=False)
        _write_registry(
            tmp_path,
            [{
                "id": "custom",
                "name": "Custom",
                "provider": "openai",
                "model": "gpt-4o",
                "api_key_env": "UNSET_MODEL_KEY",
            }],
        )
        desc = await registry.resolve_model("custom")
        assert registry.api_key_for(desc) == get_settings().api_key

    def test_falls_back_to_global_key_when_no_api_key_env(self):
        desc = registry._default_model()
        assert registry.api_key_for(desc) == get_settings().api_key


class TestCache:
    @pytest.mark.asyncio
    async def test_reads_file_once_within_ttl(self, tmp_path, monkeypatch):
        _write_registry(tmp_path, [])
        calls = {"n": 0}
        real_load = registry._load_file_models

        def counting_load():
            calls["n"] += 1
            return real_load()

        monkeypatch.setattr(registry, "_load_file_models", counting_load)

        await registry.get_all_available_models()
        await registry.get_all_available_models()
        await registry.get_all_available_models()

        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_invalidate_forces_reload(self, tmp_path, monkeypatch):
        _write_registry(tmp_path, [])
        calls = {"n": 0}
        real_load = registry._load_file_models

        def counting_load():
            calls["n"] += 1
            return real_load()

        monkeypatch.setattr(registry, "_load_file_models", counting_load)

        await registry.get_all_available_models()
        registry.invalidate_registry_cache()
        await registry.get_all_available_models()

        assert calls["n"] == 2
