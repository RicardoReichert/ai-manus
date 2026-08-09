from typing import List
from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.domain.models.user import User
from app.infrastructure.external.llm.model_registry import get_all_available_models
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.config import ClientConfigResponse, ModelSummary

router = APIRouter(tags=["config"])


@router.get("/config/frontend", response_model=APIResponse[ClientConfigResponse])
async def get_frontend_config() -> APIResponse[ClientConfigResponse]:
    """Get frontend runtime config."""
    settings = get_settings()

    return APIResponse.success(
        ClientConfigResponse(
            auth_provider=settings.auth_provider,
            show_github_button=settings.show_github_button,
            github_repository_url=settings.github_repository_url,
            google_analytics_id=settings.google_analytics_id,
            claw_enabled=settings.claw_enabled,
        )
    )


@router.get("/models", response_model=APIResponse[List[ModelSummary]])
async def get_models(
    current_user: User = Depends(get_current_user),
) -> APIResponse[List[ModelSummary]]:
    """List the models a session can be assigned to."""
    models = await get_all_available_models()
    return APIResponse.success(
        [
            ModelSummary(
                id=m.id,
                name=m.name,
                provider=m.provider,
                is_local=m.is_local,
                description=m.description,
            )
            for m in models
        ]
    )
