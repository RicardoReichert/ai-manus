"""Admin API for the model registry.

Every route requires an admin: these manage shared, global configuration and
handle provider credentials. Regular users read the resulting list through
``GET /api/v1/models`` (config_routes) and never touch this surface.
"""
import asyncio
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends

from app.application.errors.exceptions import BadRequestError, NotFoundError, UnauthorizedError
from app.domain.models.model_config import ModelConfig
from app.domain.models.user import User
from app.domain.repositories.model_config_repository import ModelConfigRepository
from app.infrastructure.external.llm.model_catalog import is_known_model, lookup_capabilities
from app.infrastructure.external.llm.model_registry import invalidate_registry_cache
from app.infrastructure.security import secret_box
from app.interfaces.dependencies import get_current_user, get_model_config_repository
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.model_config import (
    CreateModelConfigRequest,
    ListModelConfigsResponse,
    ModelConfigResponse,
    TestModelConnectionResponse,
    UpdateModelConfigRequest,
    capabilities_from_schema,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/models", tags=["admin-models"])

# An unreachable local endpoint (LM Studio, Ollama, a typo'd base_url) hangs
# a plain HTTP client indefinitely — there is no default client-side timeout
# anywhere in this call chain. Without a cap, one bad test-connection request
# ties up a worker forever instead of reporting the failure it's meant to catch.
#
# 60s rather than something shorter: this probe runs a real chat completion,
# not just a reachability check, and a local runtime (LM Studio, Ollama) that
# hasn't loaded the model into memory yet pays a real cold-load cost — often
# well past 20s for anything above a few billion parameters — before it can
# answer at all. A reachable-but-cold local model must not read as "broken".
_TEST_CONNECTION_TIMEOUT_SECONDS = 60.0


def _require_admin(user: User) -> None:
    if user.role != "admin":
        raise UnauthorizedError("Admin access required")


def _require_encryption_configured(api_key: Optional[str]) -> None:
    """Refuse to accept a credential we cannot protect.

    Failing here beats storing a key in plaintext or silently dropping it.
    """
    if api_key and not secret_box.is_configured():
        raise BadRequestError(
            "MODEL_ENCRYPTION_KEY is not configured, so an API key cannot be "
            "stored securely. Set it in the server environment and restart. "
            "Models without a credential (e.g. local LM Studio/Ollama) can "
            "still be saved."
        )


@router.get("", response_model=APIResponse[ListModelConfigsResponse])
async def list_models(
    current_user: User = Depends(get_current_user),
    repo: ModelConfigRepository = Depends(get_model_config_repository),
) -> APIResponse[ListModelConfigsResponse]:
    _require_admin(current_user)
    models = await repo.list_all()
    return APIResponse.success(
        ListModelConfigsResponse(models=[ModelConfigResponse.from_domain(m) for m in models])
    )


@router.post("", response_model=APIResponse[ModelConfigResponse])
async def create_model(
    request: CreateModelConfigRequest,
    current_user: User = Depends(get_current_user),
    repo: ModelConfigRepository = Depends(get_model_config_repository),
) -> APIResponse[ModelConfigResponse]:
    _require_admin(current_user)
    _require_encryption_configured(request.api_key)

    if await repo.find_by_id(request.id):
        raise BadRequestError(f"A model with id {request.id!r} already exists")

    # Auto-fill capabilities from the catalog unless the admin sent explicit
    # ones — the whole point is that nobody has to know a model's quirks.
    if request.capabilities is not None:
        capabilities = capabilities_from_schema(request.capabilities)
        auto_detected = False
    else:
        capabilities = lookup_capabilities(request.model, is_local=request.is_local)
        auto_detected = is_known_model(request.model)

    config = ModelConfig(
        id=request.id,
        name=request.name,
        provider=request.provider,
        model=request.model,
        base_url=request.base_url,
        is_local=request.is_local,
        description=request.description,
        enabled=request.enabled,
        sort_order=request.sort_order,
        capabilities=capabilities,
        capabilities_auto_detected=auto_detected,
        tool_profile=request.tool_profile,
        enabled_tools=request.enabled_tools,
    )
    created = await repo.create(config, request.api_key)
    invalidate_registry_cache()
    return APIResponse.success(ModelConfigResponse.from_domain(created))


@router.patch("/{model_config_id}", response_model=APIResponse[ModelConfigResponse])
async def update_model(
    model_config_id: str,
    request: UpdateModelConfigRequest,
    current_user: User = Depends(get_current_user),
    repo: ModelConfigRepository = Depends(get_model_config_repository),
) -> APIResponse[ModelConfigResponse]:
    _require_admin(current_user)
    _require_encryption_configured(request.api_key)

    existing = await repo.find_by_id(model_config_id)
    if not existing:
        raise NotFoundError(f"Model {model_config_id!r} not found")

    merged = existing.model_copy(deep=True)
    for field in (
        "name", "provider", "model", "base_url", "is_local",
        "description", "enabled", "sort_order", "tool_profile",
    ):
        value = getattr(request, field)
        if value is not None:
            setattr(merged, field, value)
    if request.enabled_tools is not None:
        merged.enabled_tools = request.enabled_tools

    if request.capabilities is not None:
        merged.capabilities = capabilities_from_schema(request.capabilities)
        merged.capabilities_auto_detected = False
    elif request.model is not None and request.model != existing.model:
        # The model changed but capabilities weren't sent — re-detect rather
        # than keep the old model's profile, which could be wildly wrong.
        merged.capabilities = lookup_capabilities(request.model, is_local=merged.is_local)
        merged.capabilities_auto_detected = is_known_model(request.model)

    updated = await repo.update(
        model_config_id,
        merged,
        api_key=request.api_key,
        clear_api_key=request.clear_api_key,
    )
    invalidate_registry_cache()
    return APIResponse.success(ModelConfigResponse.from_domain(updated))


@router.delete("/{model_config_id}", response_model=APIResponse[None])
async def delete_model(
    model_config_id: str,
    current_user: User = Depends(get_current_user),
    repo: ModelConfigRepository = Depends(get_model_config_repository),
) -> APIResponse[None]:
    _require_admin(current_user)
    if not await repo.delete(model_config_id):
        raise NotFoundError(f"Model {model_config_id!r} not found")
    invalidate_registry_cache()
    return APIResponse.success()


@router.post("/{model_config_id}/test", response_model=APIResponse[TestModelConnectionResponse])
async def test_model_connection(
    model_config_id: str,
    current_user: User = Depends(get_current_user),
    repo: ModelConfigRepository = Depends(get_model_config_repository),
) -> APIResponse[TestModelConnectionResponse]:
    """Probe a registered model with a trivial prompt.

    Catches a wrong key, unreachable base_url or bad model name at
    registration time instead of when a user's first task silently fails.
    """
    _require_admin(current_user)

    config = await repo.find_by_id(model_config_id)
    if not config:
        raise NotFoundError(f"Model {model_config_id!r} not found")

    from app.domain.models.message import LLMMessage
    from app.infrastructure.external.llm.langchain_llm import get_langchain_llm

    started = time.monotonic()
    try:
        llm = get_langchain_llm(
            model=config.model,
            provider=config.provider,
            base_url=config.base_url,
            api_key=await repo.get_api_key(model_config_id),
            capabilities=config.capabilities,
        )
        await asyncio.wait_for(
            llm.ask([LLMMessage.user("Reply with the single word: ok")]),
            timeout=_TEST_CONNECTION_TIMEOUT_SECONDS,
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        return APIResponse.success(TestModelConnectionResponse(ok=True, latency_ms=latency_ms))
    except asyncio.TimeoutError:
        logger.warning("Connection test timed out for model %s", model_config_id)
        return APIResponse.success(TestModelConnectionResponse(
            ok=False,
            error=(
                f"No response within {int(_TEST_CONNECTION_TIMEOUT_SECONDS)}s. "
                f"Check that base_url is reachable from the backend container, or — for a "
                f"local model — that it isn't still loading into memory for the first time."
            ),
        ))
    except Exception as e:
        logger.warning("Connection test failed for model %s: %s", model_config_id, e)
        # Surfaced to the admin verbatim: provider errors ("invalid api key",
        # "connection refused") are exactly the diagnostic they need.
        return APIResponse.success(TestModelConnectionResponse(ok=False, error=str(e)))
