"""OLX Brasil platform plugin."""

from __future__ import annotations

from src.plugins.olx.models import OLXAd, OLXSearch
from src.plugins.olx.plugin import OLXPlugin
from src.plugins.olx.scraper import OLXScraper

__all__ = ["OLXPlugin", "OLXScraper", "OLXAd", "OLXSearch"]
