"""Mercado Livre platform plugin.

Scrapes Mercado Livre search results and extracts product data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType
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

    async def authenticate(
        self, advogado: Advogado, config: dict[str, Any]
    ) -> bool:
        """No authentication required for public Mercado Livre search."""
        logger.info("Mercado Livre: no authentication required")
        return True

    async def fetch_intimations(
        self, advogado: Advogado, data_referencia: str
    ) -> list[dict[str, Any]]:
        """Placeholder — will search Mercado Livre for configured terms."""
        logger.info("Mercado Livre: fetch placeholder")
        return []

    async def process_intimation(
        self, raw_data: dict[str, Any], advogado: Advogado
    ) -> IntimacaoRecord:
        return IntimacaoRecord(
            data_consulta=datetime.now().strftime("%Y-%m-%d"),
            portal=self.portal_name,
            advogado=advogado.nome,
            objeto_comunicacao=raw_data.get("title", ""),
            raw_data=raw_data,
        )

    async def take_action(
        self, record: IntimacaoRecord, advogado: Advogado
    ) -> None:
        logger.info("Mercado Livre: recorded product — %s", record.objeto_comunicacao)

    async def cleanup(self) -> None:
        logger.debug("Mercado Livre: cleanup")
