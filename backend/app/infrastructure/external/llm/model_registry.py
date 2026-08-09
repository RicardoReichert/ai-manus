"""Database-backed registry of selectable models.

Formerly parsed ``models.json`` and resolved credentials through per-model
environment variables. Both are gone: models are registered by an admin
through the API and stored in MongoDB (``ModelConfigDocument``) with their
credentials encrypted at rest.

The short read-through cache is kept — the registry is consulted on every
model resolution (chat, Claw proxy, session validation) and changes only when
an admin edits it, so a few seconds of staleness is a good trade. Admin
mutations call :func:`invalidate_registry_cache` directly, making edits take
effect immediately rather than after the TTL.
"""
import logging
import time
from typing import List, Optional

from app.domain.models.model_config import ModelConfig

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 30.0

_cache: Optional[List[ModelConfig]] = None
_cache_at: float = 0.0
# Last successful read, kept separately from the TTL cache so that a database
# blip degrades to stale-but-working instead of "no models available" — which
# would surface to users as chat being broken. Deliberately survives
# invalidation, since an admin edit is exactly when the TTL cache is empty and
# a failed re-read would otherwise leave nothing to serve.
_last_good: Optional[List[ModelConfig]] = None


def invalidate_registry_cache(drop_last_good: bool = False) -> None:
    """Drop the cached registry. Called after admin edits, and by tests.

    ``drop_last_good`` also clears the resilience copy; tests use it to assert
    on a genuinely cold registry.
    """
    global _cache, _cache_at, _last_good
    _cache = None
    _cache_at = 0.0
    if drop_last_good:
        _last_good = None


def _repository():
    # Imported lazily: the DI container imports this module, so a module-level
    # import would be circular.
    from app.interfaces.dependencies import get_model_config_repository
    return get_model_config_repository()


async def get_all_available_models() -> List[ModelConfig]:
    """Every enabled model, in admin-defined order.

    Returns an empty list on a fresh install. Callers must handle that — see
    ``scripts/import_models.py`` for seeding an existing deployment, and the
    admin UI's empty state.
    """
    global _cache, _cache_at, _last_good

    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < _CACHE_TTL_SECONDS:
        return _cache

    try:
        models = await _repository().list_all(enabled_only=True)
    except Exception as e:
        # A registry read failure must not take down chat entirely; serve the
        # last known good list if we have one.
        logger.error(
            "Could not read the model registry (%s); %s",
            e,
            "serving the last known list" if _last_good else "no cached list to fall back on",
        )
        return _last_good if _last_good is not None else []

    if not models:
        logger.warning(
            "No models are registered. Add one in Settings > Models, or seed "
            "an existing deployment with: uv run python -m scripts.import_models"
        )

    _cache = models
    _cache_at = now
    _last_good = models
    return _cache


async def resolve_model(model_id: str) -> Optional[ModelConfig]:
    """Look up an enabled model by registry id, or None if unknown."""
    if not model_id:
        return None
    for desc in await get_all_available_models():
        if desc.id == model_id:
            return desc
    return None


async def get_default_model() -> Optional[ModelConfig]:
    """The model to use when none was explicitly selected.

    The first enabled entry in admin-defined order, so an operator controls
    the default by ordering rather than by a magic id.
    """
    models = await get_all_available_models()
    return models[0] if models else None


async def api_key_for(desc: Optional[ModelConfig]) -> Optional[str]:
    """Decrypt the credential registered for a model.

    Returns None when the model has no stored credential — correct for local
    runtimes (LM Studio, Ollama) that need no authentication.
    """
    if desc is None:
        return None
    return await _repository().get_api_key(desc.id)
