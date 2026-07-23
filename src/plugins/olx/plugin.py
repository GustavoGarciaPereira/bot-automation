"""OLX Brasil platform plugin — classified ads via Selenium."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType
from src.plugins.olx.scraper import OLXScraper
from src.utils.logger import get_logger

logger = get_logger(__name__)


class OLXPlugin(PortalPlugin):
    @property
    def portal_type(self) -> PortalType:
        return PortalType.OLX

    @property
    def portal_name(self) -> str:
        return "OLX"

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self.headless = headless
        self.remote_url = remote_url
        self._scraper: OLXScraper | None = None
        self._settings: dict[str, Any] = {}

    async def authenticate(self, advogado: Advogado, config: dict[str, Any]) -> bool:
        self._settings = config.get("settings", {})
        return True

    async def fetch_intimations(self, advogado: Advogado, data_referencia: str) -> list[dict[str, Any]]:
        terms: list[str] = self._settings.get("search_terms", [])
        max_r = int(self._settings.get("max_results", 15))
        if not terms:
            return []
        self._scraper = OLXScraper(headless=self.headless, remote_url=self.remote_url)
        all_r = []
        for term in terms:
            try:
                r = await self._scraper.search(term, max_results=max_r)
                for item in r:
                    item["_search_term"] = term
                all_r.extend(r)
            except Exception as exc:
                logger.error("OLX failed for %s: %s", term, exc)
        return all_r

    async def process_intimation(self, raw: dict[str, Any], advogado: Advogado) -> IntimacaoRecord:
        return IntimacaoRecord(
            data_consulta=datetime.now().strftime("%Y-%m-%d"),
            portal=self.portal_name, advogado=advogado.nome,
            tipo_comunicacao="Anúncio",
            objeto_comunicacao=raw.get("title", ""),
            parte_1=raw.get("location", ""),
            instancia=raw.get("category", ""),
            comarca=f"R$ {raw['price']:.2f}" if raw.get("price") else None,
            despacho="Profissional" if raw.get("is_professional") else "Particular",
            raw_data=raw,
        )

    async def take_action(self, record: IntimacaoRecord, advogado: Advogado) -> None:
        pass

    async def cleanup(self) -> None:
        self._scraper = None
