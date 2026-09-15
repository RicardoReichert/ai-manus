from fastapi import APIRouter, Depends, Query
from app.application.services.agent_service import AgentService
from app.interfaces.dependencies import get_current_user, get_agent_service
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.search import SearchResponse, SearchResultItem
from app.domain.models.user import User

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=APIResponse[SearchResponse])
async def search(
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
) -> APIResponse[SearchResponse]:
    results = await agent_service.search_messages(current_user.id, q, limit=limit)
    return APIResponse.success(
        SearchResponse(results=[SearchResultItem(**r) for r in results])
    )
