"""Google Shopping plugin."""

from __future__ import annotations

from src.plugins.google_shopping.models import ShoppingProduct, ShoppingSearch
from src.plugins.google_shopping.plugin import GoogleShoppingPlugin
from src.plugins.google_shopping.scraper import GoogleShoppingScraper

__all__ = ["GoogleShoppingPlugin", "GoogleShoppingScraper", "ShoppingProduct", "ShoppingSearch"]
