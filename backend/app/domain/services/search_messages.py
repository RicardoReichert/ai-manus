"""TAREFA 16.1 — server-side global search over a user's message history.

Pure aggregation over already-fetched Session domain objects (the caller
is responsible for the DB round trip — see AgentService.search_messages).

Performance note (tracked as a known debt in docs/backlog/paridade-manus.md
TAREFA 16.1): events live embedded in each session document, so this scans
every message of every session the user owns on every search. Fine at the
scale this product runs at today; a Mongo text index or a derived messages
collection is the fix if that stops being true — not built here.
"""
from typing import Any, Dict, List

from app.domain.models.event import MessageEvent
from app.domain.models.session import Session


def build_snippet(text: str, query_lower: str, context: int = 60) -> str:
    """A window of `text` centered on the first match of query_lower."""
    idx = text.lower().find(query_lower)
    if idx < 0:
        return text[: context * 2]
    start = max(0, idx - context)
    end = min(len(text), idx + len(query_lower) + context)
    snippet = text[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def search_messages(sessions: List[Session], query: str, limit: int = 30) -> List[Dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return []

    results: List[Dict[str, Any]] = []
    for session in sessions:
        for event in session.events:
            if not isinstance(event, MessageEvent) or not event.message:
                continue
            if q not in event.message.lower():
                continue
            results.append({
                "session_id": session.id,
                "session_title": session.title,
                "snippet": build_snippet(event.message, q),
                "message_at": int(event.timestamp.timestamp()) if event.timestamp else None,
            })

    results.sort(key=lambda r: r["message_at"] or 0, reverse=True)
    return results[:limit]
