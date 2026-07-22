"""Mercado Livre platform plugin.

Uses Selenium to scrape the public Mercado Livre search page
(``lista.mercadolivre.com.br``), since the REST API now requires
authentication.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType
from src.plugins.mercado_livre.scraper import MercadoLivreScraper
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MercadoLivrePlugin(PortalPlugin):
    """Plugin for Mercado Livre product search and extraction."""

    @property
    def portal_type(self) -> PortalType:
        return PortalType.MERCADO_LIVRE

    @property
    def portal_name(self) -> str:
        return "Mercado Livre"

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self.headless = headless
        self.remote_url = remote_url
        self._scraper: MercadoLivreScraper | None = None
        self._settings: dict[str, Any] = {}

    async def authenticate(
        self, advogado: Advogado, config: dict[str, Any]
    ) -> bool:
        """No authentication required — public HTML scraping."""
        self._settings = config.get("settings", {})
        logger.info("Mercado Livre: no authentication required (HTML scraping)")
        return True

    async def fetch_intimations(
        self, advogado: Advogado, data_referencia: str
    ) -> list[dict[str, Any]]:
        """Search Mercado Livre for the configured search terms.

        Reads ``settings`` from the client config JSON:
        - ``search_terms`` (list[str]): terms to search for
        - ``max_results`` (int): max products per term (default 10)
        """
        search_terms: list[str] = self._settings.get("search_terms", [])
        max_results: int = int(self._settings.get("max_results", 10))

        if not search_terms:
            logger.warning("No search_terms configured in client settings")
            return []

        self._scraper = MercadoLivreScraper(
            headless=self.headless,
            remote_url=self.remote_url,
        )
        all_results: list[dict[str, Any]] = []

        for term in search_terms:
            logger.info("Searching Mercado Livre for: %s", term)
            try:
                results = await self._scraper.search(term, max_results=max_results)
                for r in results:
                    r["_search_term"] = term
                all_results.extend(results)
            except Exception as exc:
                logger.error("Search failed for term %r: %s", term, exc)

        logger.info(
            "Mercado Livre: fetched %d products across %d terms",
            len(all_results),
            len(search_terms),
        )
        return all_results

    async def process_intimation(
        self, raw_data: dict[str, Any], advogado: Advogado
    ) -> IntimacaoRecord:
        """Map a Mercado Livre product dict into the canonical record."""
        return IntimacaoRecord(
            data_consulta=datetime.now().strftime("%Y-%m-%d"),
            portal=self.portal_name,
            advogado=advogado.nome,
            tipo_comunicacao="Produto",
            numero_processo=raw_data.get("url", ""),
            objeto_comunicacao=raw_data.get("title", ""),
            data_comunicacao=raw_data.get("collected_at", ""),
            parte_1=raw_data.get("seller", ""),
            instancia=raw_data.get("condition", ""),
            comarca=raw_data.get("currency", ""),
            despacho=(
                f"R$ {raw_data['price']:.2f}" if raw_data.get("price") else None
            ),
            raw_data=raw_data,
        )

    async def take_action(
        self, record: IntimacaoRecord, advogado: Advogado
    ) -> None:
        logger.debug(
            "Mercado Livre: recorded product %s", record.objeto_comunicacao
        )

    async def cleanup(self) -> None:
        self._scraper = None
        logger.debug("Mercado Livre: cleanup done")
