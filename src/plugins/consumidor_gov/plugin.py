"""Consumidor.gov.br platform plugin.

Uses Selenium to scrape ``consumidor.gov.br`` for company complaints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType
from src.plugins.consumidor_gov.scraper import ConsumidorGovScraper
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ConsumidorGovPlugin(PortalPlugin):
    """Plugin for Consumidor.gov.br complaint extraction."""

    @property
    def portal_type(self) -> PortalType:
        return PortalType.CONSUMIDOR_GOV

    @property
    def portal_name(self) -> str:
        return "Consumidor.gov.br"

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self.headless = headless
        self.remote_url = remote_url
        self._scraper: ConsumidorGovScraper | None = None
        self._settings: dict[str, Any] = {}

    async def authenticate(
        self, advogado: Advogado, config: dict[str, Any]
    ) -> bool:
        self._settings = config.get("settings", {})
        logger.info("Consumidor.gov.br: no authentication required")
        return True

    async def fetch_intimations(
        self, advogado: Advogado, data_referencia: str
    ) -> list[dict[str, Any]]:
        company_name: str = self._settings.get("company_name", "")
        max_pages: int = int(self._settings.get("max_pages", 3))

        if not company_name:
            logger.warning("No company_name configured")
            return []

        self._scraper = ConsumidorGovScraper(
            headless=self.headless, remote_url=self.remote_url,
        )
        logger.info("Consumidor.gov.br: fetching for %s", company_name)
        try:
            results = await self._scraper.search(company_name, max_pages=max_pages)
            for r in results:
                r["_company_name"] = company_name
            return results
        except Exception as exc:
            logger.error("Consumidor.gov.br failed: %s", exc)
            return []

    async def process_intimation(
        self, raw_data: dict[str, Any], advogado: Advogado
    ) -> IntimacaoRecord:
        return IntimacaoRecord(
            data_consulta=datetime.now().strftime("%Y-%m-%d"),
            portal=self.portal_name,
            advogado=advogado.nome,
            tipo_comunicacao="Reclamação",
            numero_processo=raw_data.get("complaint_id", ""),
            objeto_comunicacao=raw_data.get("title", ""),
            data_comunicacao=raw_data.get("date", ""),
            parte_1=raw_data.get("category", ""),
            instancia=raw_data.get("status", ""),
            comarca=f"Resolução: {raw_data['resolution_status']}" if raw_data.get("resolution_status") else None,
            raw_data=raw_data,
        )

    async def take_action(
        self, record: IntimacaoRecord, advogado: Advogado
    ) -> None:
        logger.debug("CG: recorded — %s", record.objeto_comunicacao)

    async def cleanup(self) -> None:
        self._scraper = None
        logger.debug("CG: cleanup done")
