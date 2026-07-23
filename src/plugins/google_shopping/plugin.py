"""Google Shopping plugin — product search via Selenium."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType
from src.plugins.google_shopping.scraper import GoogleShoppingScraper
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleShoppingPlugin(PortalPlugin):
    @property
    def portal_type(self) -> PortalType:
        return PortalType.GOOGLE_SHOPPING

    @property
    def portal_name(self) -> str:
        return "Google Shopping"

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self.headless = headless
        self.remote_url = remote_url
        self._scraper: GoogleShoppingScraper | None = None
        self._settings: dict[str, Any] = {}

    async def authenticate(self, advogado: Advogado, config: dict[str, Any]) -> bool:
        self._settings = config.get("settings", {})
        logger.info("Google Shopping: no auth required")
        return True

    async def fetch_intimations(
        self, advogado: Advogado, data_referencia: str
    ) -> list[dict[str, Any]]:
        terms: list[str] = self._settings.get("search_terms", [])
        max_results: int = int(self._settings.get("max_results", 15))
        if not terms:
            return []
        self._scraper = GoogleShoppingScraper(headless=self.headless, remote_url=self.remote_url)
        all_results = []
        for term in terms:
            logger.info("Google Shopping: searching %s", term)
            try:
                r = await self._scraper.search(term, max_results=max_results)
                for item in r:
                    item["_search_term"] = term
                all_results.extend(r)
            except Exception as exc:
                logger.error("GS search failed for %s: %s", term, exc)
        return all_results

    async def process_intimation(self, raw: dict[str, Any], advogado: Advogado) -> IntimacaoRecord:
        return IntimacaoRecord(
            data_consulta=datetime.now().strftime("%Y-%m-%d"),
            portal=self.portal_name, advogado=advogado.nome,
            tipo_comunicacao="Produto",
            objeto_comunicacao=raw.get("title", ""),
            parte_1=raw.get("store_name", ""),
            instancia=f"R$ {raw['price']:.2f}" if raw.get("price") else None,
            despacho=f"⭐ {raw['rating']}" if raw.get("rating") else None,
            raw_data=raw,
        )

    async def take_action(self, record: IntimacaoRecord, advogado: Advogado) -> None:
        pass

    async def cleanup(self) -> None:
        self._scraper = None
