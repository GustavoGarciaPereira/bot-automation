"""Consumidor.gov.br platform plugin.

Provides:
- ``ConsumidorGovScraper`` — Selenium-based complaint scraper
- ``ConsumidorGovPlugin`` — PortalPlugin adapter
- ``Complaint``, ``CompanyStats`` — Pydantic models
"""

from __future__ import annotations

from src.plugins.consumidor_gov.models import Complaint, CompanyStats
from src.plugins.consumidor_gov.plugin import ConsumidorGovPlugin
from src.plugins.consumidor_gov.scraper import ConsumidorGovScraper

__all__ = [
    "ConsumidorGovPlugin",
    "ConsumidorGovScraper",
    "Complaint",
    "CompanyStats",
]
