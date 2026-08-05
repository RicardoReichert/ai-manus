import json
import logging
import os
import time
from typing import Dict, List, Optional

from app.core.config import ModelDescriptor, get_settings

logger = logging.getLogger(__name__)

# The registry file is re-read at most once per window, so editing
# models.json takes effect without a restart but costs no I/O per request.
_CACHE_TTL_SECONDS = 30.0

_cache: Optional[List[ModelDescriptor]] = None
_cache_at: float = 0.0


def invalidate_registry_cache() -> None:
    """Drop the cached registry. Used by tests and after config changes."""
    global _cache, _cache_at
    _cache = None
    _cache_at = 0.0


def _default_model() -> ModelDescriptor:
    """The globally configured model, always offered as ``id="default"``.

    Guarantees there is at least one selectable model even with no registry
    file present, so the app works with zero extra configuration.
    """
    settings = get_settings()
    return ModelDescriptor(
        id="default",
        name=settings.model_name,
        provider=settings.model_provider,
        model=settings.model_name,
        base_url=settings.api_base,
        is_local=False,
        description="Model configured via MODEL_NAME / MODEL_PROVIDER",
    )


def _load_file_models() -> List[ModelDescriptor]:
    """Load registry entries from ``models_config_path``.

    A missing file is normal (zero-config deployments). A malformed file is
    logged and ignored rather than crashing boot, matching how EXTRA_HEADERS
    is handled in core.config.
    """
    path = get_settings().models_config_path
    if not path or not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Could not read model registry at {path}, ignoring: {e}")
        return []

    entries = raw.get("models") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        logger.warning(
            f"Model registry at {path} must be a list or {{\"models\": [...]}}, ignoring"
        )
        return []

    models: List[ModelDescriptor] = []
    for entry in entries:
        try:
            models.append(ModelDescriptor(**entry))
        except Exception as e:
            logger.warning(f"Skipping invalid model registry entry {entry!r}: {e}")
    return models


async def get_all_available_models() -> List[ModelDescriptor]:
    """All selectable models: the global default first, then registry entries.

    Deduplicated by ``id``, so a file entry with ``id="default"`` deliberately
    overrides the synthesized one.
    """
    global _cache, _cache_at

    now = time.monotonic()
    if _cache is not None and (now - _cache_at) < _CACHE_TTL_SECONDS:
        return _cache

    models_by_id: Dict[str, ModelDescriptor] = {"default": _default_model()}
    for desc in _load_file_models():
        models_by_id[desc.id] = desc

    _cache = list(models_by_id.values())
    _cache_at = now
    return _cache


async def resolve_model(model_id: str) -> Optional[ModelDescriptor]:
    """Look up a registry entry by id, or None if it is not (or no longer) known."""
    if not model_id:
        return None
    for desc in await get_all_available_models():
        if desc.id == model_id:
            return desc
    return None


def api_key_for(desc: ModelDescriptor) -> Optional[str]:
    """Resolve the credential for a model.

    Without this, switching a session from e.g. google_genai to an OpenAI
    model would send the globally configured key to the wrong provider.
    """
    if desc.api_key_env:
        key = os.environ.get(desc.api_key_env)
        if key:
            return key
        logger.warning(
            f"Model {desc.id!r} declares api_key_env={desc.api_key_env!r} "
            f"but it is unset; falling back to the global API key"
        )
    return get_settings().api_key
