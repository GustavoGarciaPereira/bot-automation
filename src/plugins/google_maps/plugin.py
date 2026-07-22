"""Google Maps platform plugin.

Searches for places on Google Maps and extracts business information.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.interfaces.portal_plugin import PortalPlugin
from src.models import Advogado, IntimacaoRecord, PortalType
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleMapsPlugin(PortalPlugin):
    """Plugin for Google Maps place search and extraction."""

    @property
    def portal_type(self) -> PortalType:
        return PortalType.GOOGLE_MAPS

    @property
    def portal_name(self) -> str:
        return "Google Maps"

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self.headless = headless
        self.remote_url = remote_url

    async def authenticate(
        self, advogado: Advogado, config: dict[str, Any]
    ) -> bool:
        """No authentication required for public Google Maps search."""
        logger.info("Google Maps: no authentication required")
        return True

    async def fetch_intimations(
        self, advogado: Advogado, data_referencia: str
    ) -> list[dict[str, Any]]:
        """Placeholder — will search Google Maps for configured query."""
        logger.info("Google Maps: fetch placeholder")
        return []

    async def process_intimation(
        self, raw_data: dict[str, Any], advogado: Advogado
    ) -> IntimacaoRecord:
        return IntimacaoRecord(
            data_consulta=datetime.now().strftime("%Y-%m-%d"),
            portal=self.portal_name,
            advogado=advogado.nome,
            objeto_comunicacao=raw_data.get("name", ""),
            raw_data=raw_data,
        )

    async def take_action(
        self, record: IntimacaoRecord, advogado: Advogado
    ) -> None:
        logger.info(
            "Google Maps: recorded place — %s", record.objeto_comunicacao
        )

    async def cleanup(self) -> None:
        logger.debug("Google Maps: cleanup")
