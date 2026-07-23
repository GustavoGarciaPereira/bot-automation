"""Tests for AI enrichment service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.enrichment import EnrichmentService


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.generate = AsyncMock(
        return_value='{"category":"Informática","subcategory":"Notebooks",'
        '"brand":"Dell","condition":"new","price_level":"medio"}'
    )
    return llm


class TestEnrichment:
    async def test_enrich_ml(self, mock_llm: MagicMock) -> None:
        svc = EnrichmentService(llm_client=mock_llm)
        products = [{"title": "Notebook Dell", "price": 3800.0}]
        result = await svc.enrich_ml(products)
        assert result[0]["ai_category"] == "Informática"
        assert result[0]["ai_subcategory"] == "Notebooks"
        assert result[0]["ai_brand"] == "Dell"
        assert result[0]["ai_price_level"] == "medio"

    async def test_enrich_maps(self, mock_llm: MagicMock) -> None:
        mock_llm.generate = AsyncMock(
            return_value='{"sector":"Saúde","size":"medio",'
            '"lead_potential":"alto","lead_reason":"Alta demanda"}'
        )
        svc = EnrichmentService(llm_client=mock_llm)
        businesses = [{"name": "Clinica X", "category": "Dentista"}]
        result = await svc.enrich_maps(businesses)
        assert result[0]["ai_sector"] == "Saúde"
        assert result[0]["ai_lead_potential"] == "alto"

    async def test_enrich_olx(self, mock_llm: MagicMock) -> None:
        mock_llm.generate = AsyncMock(
            return_value='{"category":"Informática","subcategory":"Notebooks",'
            '"condition":"usado","urgency":"normal","price_level":"medio"}'
        )
        svc = EnrichmentService(llm_client=mock_llm)
        ads = [{"title": "Notebook usado", "price": 1500.0}]
        result = await svc.enrich_olx(ads)
        assert result[0]["ai_category"] == "Informática"
        assert result[0]["ai_condition"] == "usado"

    async def test_enrich_llm_failure(self, mock_llm: MagicMock) -> None:
        mock_llm.generate = AsyncMock(side_effect=RuntimeError("API down"))
        svc = EnrichmentService(llm_client=mock_llm)
        products = [{"title": "Produto", "price": 100.0}]
        result = await svc.enrich_ml(products)
        assert result[0]["ai_category"] is None  # graceful fallback

    async def test_enrich_routing(self, mock_llm: MagicMock) -> None:
        svc = EnrichmentService(llm_client=mock_llm)
        data = [{"title": "Test", "price": 100.0}]
        result = await svc.enrich("mercado_livre", data)
        assert result[0].get("ai_category") == "Informática"

    async def test_no_llm_returns_original(self) -> None:
        """Without LLM, enrichment returns data unchanged."""
        svc = EnrichmentService(llm_client=None)
        # Simulate no LLM available
        svc._llm = None
        data = [{"title": "Test"}]
        result = await svc.enrich("mercado_livre", data)
        assert result == data
        assert "ai_category" not in result[0]
