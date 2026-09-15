from pydantic import BaseModel
from typing import List, Optional


class SearchResultItem(BaseModel):
    """One matching message, for grouping-by-date on the client (16.1)"""
    session_id: str
    session_title: Optional[str] = None
    snippet: str
    message_at: Optional[int] = None


class SearchResponse(BaseModel):
    results: List[SearchResultItem]
