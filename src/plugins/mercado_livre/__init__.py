"""Mercado Livre platform plugin.

Provides:
- ``MercadoLivreScraper`` — API-based search and extraction
- ``MercadoLivrePlugin`` — PortalPlugin adapter for the orchestrator
- ``Product``, ``SearchResult`` — Pydantic data models
"""

from __future__ import annotations

from src.plugins.mercado_livre.models import Product, SearchResult
from src.plugins.mercado_livre.plugin import MercadoLivrePlugin
from src.plugins.mercado_livre.scraper import MercadoLivreScraper

__all__ = [
    "MercadoLivrePlugin",
    "MercadoLivreScraper",
    "Product",
    "SearchResult",
]
