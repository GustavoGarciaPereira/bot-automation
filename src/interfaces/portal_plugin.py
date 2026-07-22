"""Abstract contract that every platform plugin must fulfil.

New platforms are added by subclassing `PortalPlugin` and registering the
class in `PLUGIN_REGISTRY` (see `orchestrator.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.models import Advogado, IntimacaoRecord, PortalType


class PortalPlugin(ABC):
    """Each concrete plugin handles one specific web platform (Mercado Livre,
    Google Maps, Reclame Aqui, etc.).  The orchestrator calls the methods in
    the order defined below.
    """

    # -- Identity -----------------------------------------------------------

    @property
    @abstractmethod
    def portal_type(self) -> PortalType:
        """The `PortalType` enum member this plugin is responsible for."""
        ...

    @property
    @abstractmethod
    def portal_name(self) -> str:
        """Human-readable platform name (used in logs and Excel output)."""
        ...

    # -- Lifecycle -----------------------------------------------------------

    @abstractmethod
    async def authenticate(self, advogado: Advogado, config: dict[str, Any]) -> bool:
        """Perform login / authentication.

        Returns `True` on success.  MUST raise a descriptive exception on
        failure so the orchestrator can log and skip to the next platform.
        """
        ...

    @abstractmethod
    async def fetch_intimations(
        self, advogado: Advogado, data_referencia: str
    ) -> list[dict[str, Any]]:
        """Navigate the platform and return a list of raw dicts — one per
        record found for the given user / reference date.
        """
        ...

    @abstractmethod
    async def process_intimation(
        self, raw_data: dict[str, Any], advogado: Advogado
    ) -> IntimacaoRecord:
        """Map one raw dict into the canonical `IntimacaoRecord` model."""
        ...

    @abstractmethod
    async def take_action(
        self, record: IntimacaoRecord, advogado: Advogado
    ) -> None:
        """Execute a platform-specific action — download, acknowledge, etc."""
        ...

    @abstractmethod
    async def cleanup(self) -> None:
        """Release resources (close browser, delete temp files)."""
        ...
