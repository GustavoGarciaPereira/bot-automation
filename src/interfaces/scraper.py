"""Abstract contract for platform scrapers.

New platforms are added by subclassing `BaseScraper` and implementing
the ``search`` and ``extract`` methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseScraper(ABC):
    """Generic scraper interface for any web platform.

    Concrete implementations handle one platform (Mercado Livre, Google Maps,
    Reclame Aqui, etc.) and provide search + extract operations.
    """

    @abstractmethod
    async def search(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Search the platform for items matching *query*.

        Returns a list of raw dicts — one per result found.
        """
        ...

    @abstractmethod
    async def extract(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """Extract detailed information from a specific *url*.

        Returns a single dict with the extracted data.
        """
        ...
