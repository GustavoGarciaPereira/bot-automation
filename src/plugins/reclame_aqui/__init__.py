"""Reclame Aqui platform plugin.

Provides:
- ``ReclameAquiScraper`` — Selenium-based complaint scraper
- ``ReclameAquiPlugin`` — PortalPlugin adapter for the orchestrator
- ``Complaint``, ``CompanyReport`` — Pydantic data models
"""

from __future__ import annotations

from src.plugins.reclame_aqui.models import Complaint, CompanyReport
from src.plugins.reclame_aqui.plugin import ReclameAquiPlugin
from src.plugins.reclame_aqui.scraper import ReclameAquiScraper, slugify

__all__ = [
    "ReclameAquiPlugin",
    "ReclameAquiScraper",
    "Complaint",
    "CompanyReport",
    "slugify",
]
