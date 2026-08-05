"""One-time importer: seed the database-backed model registry.

The registry used to be a JSON file plus ``MODEL_NAME``/``API_KEY`` env vars.
It is now a MongoDB collection managed through the admin UI, which means a
deployment upgrading across that change would otherwise boot with **no
selectable models at all**. This script carries the old configuration over.

Run once after upgrading::

    docker compose -f docker-compose-development.yml exec backend \\
        uv run python -m scripts.import_models

Idempotent: models whose id already exists are skipped, so re-running is safe.
Pass ``--dry-run`` to preview without writing.
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from typing import List, Optional, Tuple

from beanie import init_beanie

from app.core.config import get_settings
from app.domain.models.model_config import ModelConfig
from app.infrastructure.external.llm.model_catalog import (
    is_known_model,
    lookup_capabilities,
)
from app.infrastructure.models.documents import ModelConfigDocument
from app.infrastructure.repositories.mongo_model_config_repository import (
    MongoModelConfigRepository,
)
from app.infrastructure.security import secret_box
from app.infrastructure.storage.mongodb import get_mongodb

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("import_models")


def _load_legacy_file() -> List[dict]:
    """Read the legacy models.json, if one is present."""
    path = get_settings().models_config_path
    if not path or not os.path.exists(path):
        logger.info("No models.json at %s — nothing to import from file.", path)
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read %s (%s); skipping file import.", path, e)
        return []

    entries = raw.get("models") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        logger.warning("%s is not a list or {'models': [...]}; skipping.", path)
        return []
    return entries


def _legacy_api_key(entry: dict) -> Optional[str]:
    """Resolve a legacy entry's credential the way the old registry did.

    ``api_key_env`` named an environment variable; unset fell back to the
    global API_KEY. Both are read here so credentials survive the migration
    without anyone having to re-enter them.
    """
    env_name = entry.get("api_key_env")
    if env_name:
        value = os.environ.get(env_name)
        if value:
            return value
        logger.warning(
            "  entry %r declares api_key_env=%s but it is unset; "
            "falling back to the global API_KEY.",
            entry.get("id"), env_name,
        )
    return get_settings().api_key


def _entry_to_config(entry: dict, sort_order: int) -> Optional[Tuple[ModelConfig, Optional[str]]]:
    """Convert a legacy registry entry into a ModelConfig + its credential."""
    model_id = entry.get("id")
    model = entry.get("model")
    if not model_id or not model:
        logger.warning("  skipping entry without id/model: %r", entry)
        return None

    is_local = bool(entry.get("is_local", False))
    capabilities = lookup_capabilities(model, is_local=is_local)

    config = ModelConfig(
        id=model_id,
        name=entry.get("name") or model_id,
        provider=entry.get("provider") or "openai",
        model=model,
        base_url=entry.get("base_url"),
        is_local=is_local,
        description=entry.get("description"),
        enabled=True,
        sort_order=sort_order,
        capabilities=capabilities,
        capabilities_auto_detected=is_known_model(model),
        # Everything imported keeps the full tool surface it had before, so
        # the migration never silently changes agent behavior. Narrowing to a
        # lean profile is an explicit choice in the admin UI.
        tool_profile="full",
    )
    return config, _legacy_api_key(entry)


def _global_model_config(sort_order: int) -> Optional[Tuple[ModelConfig, Optional[str]]]:
    """The model formerly synthesized from MODEL_NAME/MODEL_PROVIDER.

    The old registry always offered this as ``id="default"``, so a deployment
    that never had a models.json still had exactly one working model.
    """
    settings = get_settings()
    if not settings.model_name:
        return None

    capabilities = lookup_capabilities(settings.model_name, is_local=False)
    config = ModelConfig(
        id="default",
        name=settings.model_name,
        provider=settings.model_provider,
        model=settings.model_name,
        base_url=settings.api_base,
        is_local=False,
        # None, not a migration note: this shows to end users under the
        # model name in the dropdown, and is editable from Settings > Models
        # afterward if an admin wants one.
        description=None,
        enabled=True,
        sort_order=sort_order,
        capabilities=capabilities,
        capabilities_auto_detected=is_known_model(settings.model_name),
        tool_profile="full",
    )
    return config, settings.api_key


async def _run(dry_run: bool) -> int:
    settings = get_settings()

    if not dry_run and not secret_box.is_configured():
        logger.error(
            "MODEL_ENCRYPTION_KEY is not set, so credentials cannot be stored.\n"
            "Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"\n'
            "then set it in .env and re-run."
        )
        return 1

    await get_mongodb().initialize()
    await init_beanie(
        database=get_mongodb().client[settings.mongodb_database],
        document_models=[ModelConfigDocument],
    )
    repo = MongoModelConfigRepository()

    # The global model goes first so it stays the default pick (the registry
    # treats the first enabled entry as the default).
    candidates: List[Tuple[ModelConfig, Optional[str]]] = []
    global_entry = _global_model_config(sort_order=0)
    if global_entry:
        candidates.append(global_entry)

    for i, entry in enumerate(_load_legacy_file(), start=1):
        converted = _entry_to_config(entry, sort_order=i)
        if converted:
            candidates.append(converted)

    if not candidates:
        logger.warning(
            "Nothing to import: no models.json entries and no MODEL_NAME set.\n"
            "Add a model through Settings > Models instead."
        )
        return 0

    imported = skipped = 0
    for config, api_key in candidates:
        existing = await repo.find_by_id(config.id)
        if existing:
            logger.info("  = %-28s already registered, skipping", config.id)
            skipped += 1
            continue

        caps = config.capabilities
        detail = "full capability" if not caps.is_constrained else (
            f"max_tools={caps.max_tools}, guided_decoding={caps.needs_guided_decoding}"
        )
        if dry_run:
            logger.info(
                "  + %-28s %s/%s  (%s)%s",
                config.id, config.provider, config.model, detail,
                "  [has credential]" if api_key else "",
            )
        else:
            await repo.create(config, api_key)
            logger.info(
                "  + %-28s %s/%s  (%s)%s",
                config.id, config.provider, config.model, detail,
                "  [credential encrypted]" if api_key else "",
            )
        imported += 1

    verb = "would import" if dry_run else "imported"
    logger.info("\n%s %d model(s), skipped %d already present.", verb.capitalize(), imported, skipped)
    if not dry_run and imported:
        logger.info("Review them in Settings > Models.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without writing to the database.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
