"""Enrichment service: adds AI classification to scraped data using DeepSeek."""

from __future__ import annotations

import json
import logging

from src.services.llm_client import LLMClient
from src.services.prompts import (
    ML_CLASSIFY_PROMPT,
    MAPS_CLASSIFY_PROMPT,
    OLX_CLASSIFY_PROMPT,
)

logger = logging.getLogger(__name__)


class EnrichmentService:
    """Classifies scraped data using LLM (DeepSeek)."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        try:
            self._llm = llm_client or LLMClient.from_env()
        except ValueError:
            logger.warning("No LLM API key configured — AI enrichment disabled")
            self._llm = None

    async def enrich_ml(self, products: list[dict]) -> list[dict]:
        """Classify ML products."""
        if not self._llm:
            return products
        for product in products:
            try:
                prompt = ML_CLASSIFY_PROMPT.format(
                    title=product.get("title", ""),
                    price=product.get("price", 0),
                )
                response = await self._llm.generate(prompt)
                classification = json.loads(response)
                product["ai_category"] = classification.get("category")
                product["ai_subcategory"] = classification.get("subcategory")
                product["ai_brand"] = classification.get("brand")
                product["ai_condition"] = classification.get("condition")
                product["ai_price_level"] = classification.get("price_level")
            except Exception as e:
                logger.warning("ML enrichment failed for '%s': %s", str(product.get("title", ""))[:30], e)
                product["ai_category"] = None
        return products

    async def enrich_maps(self, businesses: list[dict]) -> list[dict]:
        """Classify Maps businesses."""
        if not self._llm:
            return businesses
        for biz in businesses:
            try:
                prompt = MAPS_CLASSIFY_PROMPT.format(
                    name=biz.get("name", ""),
                    category=biz.get("category", ""),
                    address=biz.get("address", ""),
                    rating=biz.get("rating", ""),
                )
                response = await self._llm.generate(prompt)
                classification = json.loads(response)
                biz["ai_sector"] = classification.get("sector")
                biz["ai_size"] = classification.get("size")
                biz["ai_lead_potential"] = classification.get("lead_potential")
                biz["ai_lead_reason"] = classification.get("lead_reason")
            except Exception as e:
                logger.warning("Maps enrichment failed for '%s': %s", str(biz.get("name", ""))[:30], e)
                biz["ai_sector"] = None
        return businesses

    async def enrich_olx(self, ads: list[dict]) -> list[dict]:
        """Classify OLX ads."""
        if not self._llm:
            return ads
        for ad in ads:
            try:
                prompt = OLX_CLASSIFY_PROMPT.format(
                    title=ad.get("title", ""),
                    price=ad.get("price", 0),
                    location=ad.get("location", ""),
                )
                response = await self._llm.generate(prompt)
                classification = json.loads(response)
                ad["ai_category"] = classification.get("category")
                ad["ai_subcategory"] = classification.get("subcategory")
                ad["ai_condition"] = classification.get("condition")
                ad["ai_urgency"] = classification.get("urgency")
                ad["ai_price_level"] = classification.get("price_level")
            except Exception as e:
                logger.warning("OLX enrichment failed for '%s': %s", str(ad.get("title", ""))[:30], e)
                ad["ai_category"] = None
        return ads

    async def enrich(self, plugin_name: str, data: list[dict]) -> list[dict]:
        """Route to correct enrichment method based on plugin name."""
        if plugin_name == "mercado_livre":
            return await self.enrich_ml(data)
        elif plugin_name == "google_maps":
            return await self.enrich_maps(data)
        elif plugin_name == "olx":
            return await self.enrich_olx(data)
        else:
            logger.warning("No enrichment for plugin: %s", plugin_name)
            return data
