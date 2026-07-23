"""Google Maps platform plugin.

Uses Selenium to scrape ``google.com/maps/search`` for business leads.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType
from src.plugins.google_maps.scraper import GoogleMapsScraper
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleMapsPlugin(PortalPlugin):
    """Plugin for Google Maps business search and extraction."""

    @property
    def portal_type(self) -> PortalType:
        return PortalType.GOOGLE_MAPS

    @property
    def portal_name(self) -> str:
        return "Google Maps"

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self.headless = headless
        self.remote_url = remote_url
        self._scraper: GoogleMapsScraper | None = None
        self._settings: dict[str, Any] = {}

    async def authenticate(
        self, advogado: Advogado, config: dict[str, Any]
    ) -> bool:
        """No authentication required — public Google Maps search."""
        self._settings = config.get("settings", {})
        logger.info("Google Maps: no authentication required (HTML scraping)")
        return True

    async def fetch_intimations(
        self, advogado: Advogado, data_referencia: str
    ) -> list[dict[str, Any]]:
        """Search Google Maps for the configured query."""
        search_query: str = self._settings.get("search_query", "")
        max_results: int = int(self._settings.get("max_results", 20))
        min_rating: float = float(self._settings.get("min_rating", 0.0))

        if not search_query:
            logger.warning("No search_query configured in client settings")
            return []

        self._scraper = GoogleMapsScraper(
            headless=self.headless,
            remote_url=self.remote_url,
        )

        logger.info("Searching Google Maps for: %s", search_query)
        try:
            results = await self._scraper.search(
                search_query,
                max_results=max_results,
                min_rating=min_rating,
            )
            for r in results:
                r["_search_query"] = search_query
            logger.info("Google Maps: fetched %d businesses", len(results))
            return results
        except Exception as exc:
            logger.error("Google Maps search failed: %s", exc)
            return []

    async def process_intimation(
        self, raw_data: dict[str, Any], advogado: Advogado
    ) -> IntimacaoRecord:
        """Map a Google Maps business dict into the canonical record."""
        return IntimacaoRecord(
            data_consulta=datetime.now().strftime("%Y-%m-%d"),
            portal=self.portal_name,
            advogado=advogado.nome,
            tipo_comunicacao="Empresa",
            numero_processo=raw_data.get("place_url", ""),
            objeto_comunicacao=raw_data.get("name", ""),
            parte_1=raw_data.get("phone", ""),
            instancia=raw_data.get("category", ""),
            comarca=raw_data.get("address", ""),
            despacho=(
                f"⭐ {raw_data['rating']}" if raw_data.get("rating") else None
            ),
            raw_data=raw_data,
        )

    async def take_action(
        self, record: IntimacaoRecord, advogado: Advogado
    ) -> None:
        logger.debug("Google Maps: recorded — %s", record.objeto_comunicacao)

    async def cleanup(self) -> None:
        self._scraper = None
        logger.debug("Google Maps: cleanup done")
