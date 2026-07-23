"""Reclame Aqui platform plugin.

Uses Selenium to scrape ``reclameaqui.com.br/empresa/{slug}/``
for complaints and reviews.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType
from src.plugins.reclame_aqui.scraper import ReclameAquiScraper, slugify
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ReclameAquiPlugin(PortalPlugin):
    """Plugin for Reclame Aqui complaint extraction."""

    @property
    def portal_type(self) -> PortalType:
        return PortalType.RECLAME_AQUI

    @property
    def portal_name(self) -> str:
        return "Reclame Aqui"

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self.headless = headless
        self.remote_url = remote_url
        self._scraper: ReclameAquiScraper | None = None
        self._settings: dict[str, Any] = {}

    async def authenticate(
        self, advogado: Advogado, config: dict[str, Any]
    ) -> bool:
        """No authentication required — public pages."""
        self._settings = config.get("settings", {})
        logger.info("Reclame Aqui: no authentication required")
        return True

    async def fetch_intimations(
        self, advogado: Advogado, data_referencia: str
    ) -> list[dict[str, Any]]:
        """Fetch complaints for the configured company."""
        company_slug: str = self._settings.get("company_slug", "")
        max_pages: int = int(self._settings.get("max_pages", 5))

        if not company_slug:
            logger.warning("No company_slug configured in settings")
            return []

        # Convert friendly name to slug if needed
        slug = slugify(company_slug)

        self._scraper = ReclameAquiScraper(
            headless=self.headless,
            remote_url=self.remote_url,
        )

        logger.info("Reclame Aqui: fetching complaints for company=%s", slug)
        try:
            results = await self._scraper.search(slug, max_pages=max_pages)
            for r in results:
                r["_company_slug"] = slug
            logger.info("Reclame Aqui: fetched %d complaints", len(results))
            return results
        except Exception as exc:
            logger.error("Reclame Aqui search failed: %s", exc)
            return []

    async def process_intimation(
        self, raw_data: dict[str, Any], advogado: Advogado
    ) -> IntimacaoRecord:
        """Map a complaint dict into the canonical record."""
        return IntimacaoRecord(
            data_consulta=datetime.now().strftime("%Y-%m-%d"),
            portal=self.portal_name,
            advogado=advogado.nome,
            tipo_comunicacao=raw_data.get("status", "Reclamação"),
            numero_processo=raw_data.get("id", ""),
            objeto_comunicacao=raw_data.get("title", ""),
            data_comunicacao=raw_data.get("date", ""),
            parte_1=raw_data.get("category", ""),
            instancia=raw_data.get("sentiment", ""),
            comarca=f"Nota: {raw_data['rating']}" if raw_data.get("rating") else None,
            despacho=raw_data.get("text", "")[:200] if raw_data.get("text") else None,
            raw_data=raw_data,
        )

    async def take_action(
        self, record: IntimacaoRecord, advogado: Advogado
    ) -> None:
        logger.debug("Reclame Aqui: recorded complaint — %s", record.objeto_comunicacao)

    async def cleanup(self) -> None:
        self._scraper = None
        logger.debug("Reclame Aqui: cleanup done")
