"""Unit tests for BingWebSearchEngine's request construction.

Regression coverage for a real bug found live: the scraping request sent
no market/language signal at all, so Bing had no idea the query was
Portuguese and fell back to matching only the one word it recognized
confidently — a real query about "povos indígenas" (indigenous peoples) in
a small locality in Pará came back as nine Portuguese *dictionary
definitions* of the common word "problemas", ignoring "povos indígenas",
"Nova Repartição", "Pará" entirely. Query encoding itself was never the
bug (verified separately) — this covers the actual fix: a market/language
hint on the request.

Pure unit tests — the curl_cffi session is mocked, no real network call.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import get_settings
from app.infrastructure.external.search.bing_web_search import BingWebSearchEngine


def _mock_session(html: str = "<html></html>"):
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()

    session = MagicMock()
    session.get = AsyncMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


class TestMarketSignal:
    @pytest.mark.asyncio
    async def test_sends_configured_market_as_param_and_header(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "search_market", "pt-BR")
        session = _mock_session()

        with patch(
            "app.infrastructure.external.search.bing_web_search.AsyncSession",
            return_value=session,
        ):
            engine = BingWebSearchEngine()
            await engine.search("problemas povos indígenas Nova Repartição do Pará")

        _, kwargs = session.get.call_args
        assert kwargs["params"]["mkt"] == "pt-BR"
        assert kwargs["headers"]["Accept-Language"] == "pt-BR"

    @pytest.mark.asyncio
    async def test_query_itself_is_passed_through_unmodified(self, monkeypatch):
        """Confirms the query text is never the bug: full multi-word,
        accented query reaches the request params byte-for-byte."""
        monkeypatch.setattr(get_settings(), "search_market", "pt-BR")
        query = "problemas povos indígenas Nova Repartição do Pará contexto social ambiental"
        session = _mock_session()

        with patch(
            "app.infrastructure.external.search.bing_web_search.AsyncSession",
            return_value=session,
        ):
            engine = BingWebSearchEngine()
            await engine.search(query)

        _, kwargs = session.get.call_args
        assert kwargs["params"]["q"] == query

    @pytest.mark.asyncio
    async def test_no_market_configured_omits_param_and_header(self, monkeypatch):
        monkeypatch.setattr(get_settings(), "search_market", "")
        session = _mock_session()

        with patch(
            "app.infrastructure.external.search.bing_web_search.AsyncSession",
            return_value=session,
        ):
            engine = BingWebSearchEngine()
            await engine.search("test")

        _, kwargs = session.get.call_args
        assert "mkt" not in kwargs["params"]
        assert kwargs["headers"] == {}
