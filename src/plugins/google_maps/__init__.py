"""Google Maps platform plugin.

Provides:
- ``GoogleMapsScraper`` — Selenium-based HTML scraper
- ``GoogleMapsPlugin`` — PortalPlugin adapter for the orchestrator
- ``Business``, ``LeadSearch`` — Pydantic data models
"""

from __future__ import annotations

from src.plugins.google_maps.models import Business, LeadSearch
from src.plugins.google_maps.plugin import GoogleMapsPlugin
from src.plugins.google_maps.scraper import GoogleMapsScraper

__all__ = [
    "GoogleMapsPlugin",
    "GoogleMapsScraper",
    "Business",
    "LeadSearch",
]
