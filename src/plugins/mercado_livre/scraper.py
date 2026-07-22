"""Mercado Livre HTML scraper — uses Selenium to scrape search result pages.

The ML public API now requires authentication (PolicyAgent 403), so we fall
back to scraping the public search page at ``lista.mercadolivre.com.br``.
"""

from __future__ import annotations

import json
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.interfaces.scraper import BaseScraper
from src.plugins.base_selenium_plugin import selenium_driver
from src.plugins.mercado_livre.models import Product, SearchResult
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default config (overridable via config.json)
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "plugin_name": "mercado_livre",
    "base_url": "https://lista.mercadolivre.com.br",
    "headless": True,
    "timeout_seconds": 15,
    "random_delay_min": 2,
    "random_delay_max": 4,
    "max_results_default": 10,
}

_CONFIG_CACHE: dict[str, Any] | None = None


def _load_config() -> dict[str, Any]:
    """Load plugin config from config.json, merged with defaults."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    cfg_path = Path(__file__).resolve().parent / "config.json"
    overrides: dict[str, Any] = {}
    if cfg_path.exists():
        try:
            overrides = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load config.json: %s — using defaults", exc)

    merged = {**_DEFAULT_CONFIG, **overrides}
    _CONFIG_CACHE = merged
    return merged


def _clear_config_cache() -> None:
    global _CONFIG_CACHE
    _CONFIG_CACHE = None


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class MercadoLivreScraper(BaseScraper):
    """Scraper for Mercado Livre product search using Selenium.

    Navigates to ``lista.mercadolivre.com.br/{query}`` and parses the
    HTML result list.
    """

    def __init__(
        self,
        headless: bool = True,
        remote_url: str | None = None,
    ) -> None:
        self._cfg = _load_config()
        self._headless = headless if headless else self._cfg.get("headless", True)
        self._remote_url = remote_url

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(self, query: str, max_results: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        """Search Mercado Livre for *query* and parse product listings.

        Returns a list of product dicts.
        """
        sanitized = query.lower().replace(" ", "-").replace("--", "-")
        search_url = f"{self._cfg['base_url']}/{sanitized}"

        logger.info("ML scraping: opening %s", search_url)

        driver = None
        try:
            async with selenium_driver(
                headless=self._headless,
                remote_url=self._remote_url,
            ) as driver:
                driver.get(search_url)

                # Wait for the result container
                wait = WebDriverWait(driver, self._cfg["timeout_seconds"])
                wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "ol.ui-search-layout")
                    )
                )

                # Random human-like delay
                self._random_delay()

                # Extract items
                items = driver.find_elements(
                    By.CSS_SELECTOR, "li.ui-search-layout__item"
                )

                if not items:
                    logger.warning(
                        "No items found with primary selector — trying fallback"
                    )
                    items = driver.find_elements(
                        By.CSS_SELECTOR,
                        "div.ui-search-result, div.ui-search-item",
                    )

                logger.info("ML scraping: found %d raw items", len(items))

                products: list[Product] = []
                limit = min(max_results, self._cfg.get("max_results_default", 10))
                for item in items[:limit]:
                    try:
                        product = self._parse_item(item)
                        if product:
                            products.append(product)
                    except Exception as exc:
                        logger.debug("Failed to parse item: %s", exc)
                        continue

                logger.info(
                    "ML scraping: %d products parsed for query=%r",
                    len(products),
                    query,
                )
                return [p.model_dump() for p in products]

        except Exception as exc:
            logger.error("ML scraping failed for query=%r: %s", query, exc)
            if driver:
                try:
                    screenshot_path = (
                        Path("data/logs")
                        / f"ml_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    )
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    driver.save_screenshot(str(screenshot_path))
                    logger.info("Screenshot saved to %s", screenshot_path)
                except Exception:
                    pass
            return []

    async def extract(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """Extract detailed information from a product page."""
        logger.info("ML scraping: extracting from %s", url)

        driver = None
        try:
            async with selenium_driver(
                headless=self._headless,
                remote_url=self._remote_url,
            ) as driver:
                driver.get(url)
                self._random_delay()

                # Title
                title = self._safe_text(
                    driver, "h1.ui-pdp-title"
                ) or self._safe_text(driver, "h1")

                # Price
                price = self._safe_price_element(driver)

                # Condition
                condition = self._safe_text(
                    driver, "span.ui-pdp-subtitle"
                )

                # Seller
                seller = self._safe_text(
                    driver,
                    "a.ui-pdp-seller__link span, "
                    "span.ui-pdp-seller__link-text, "
                    "a.andes-dropdown__trigger",
                )

                result = Product(
                    title=title,
                    price=price,
                    condition=condition or None,
                    seller=seller or None,
                    url=url,
                )

                return result.model_dump()

        except Exception as exc:
            logger.error("ML extraction failed for %s: %s", url, exc)
            if driver:
                try:
                    screenshot_path = (
                        Path("data/logs")
                        / f"ml_extract_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    )
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    driver.save_screenshot(str(screenshot_path))
                except Exception:
                    pass
            return {}

    # ------------------------------------------------------------------
    # Internal — item parsing
    # ------------------------------------------------------------------

    def _parse_item(self, item: Any) -> Product | None:
        """Parse a single search-result HTML element into a Product."""
        # Title
        title = (
            self._safe_text(item, "a.poly-component__title")
            or self._safe_text(item, "h2.poly-box__title")
            or self._safe_text(item, "h2 a")
            or self._safe_text(item, "a.ui-search-item__group__title")
        )
        if not title:
            return None

        # Price
        price = self._price_from_item(item)

        # Original price
        original_price_str = self._safe_text(
            item,
            "span.poly-price__previous span.andes-money-amount__fraction, "
            "s.andes-money-amount span.andes-money-amount__fraction",
        )
        original_price = self._parse_price_str(original_price_str) if original_price_str else None

        # URL
        url = (
            self._safe_attr(item, "a.poly-component__title", "href")
            or self._safe_attr(item, "a.ui-search-link", "href")
            or self._safe_attr(item, "a", "href")
        )

        # Image
        image_url = (
            self._safe_attr(item, "img.poly-component__picture", "src")
            or self._safe_attr(item, "img", "data-src")
            or self._safe_attr(item, "img", "src")
        )

        # Free shipping
        free_shipping = bool(
            self._safe_text(item, "span.poly-component__shipping, div.poly-component__shipping")
        ) or bool(
            self._safe_text(item, "p.poly-component__shipping")
        )

        # Rating
        rating_str = self._safe_text(item, "span.poly-reviews__rating")
        rating = self._parse_float(rating_str)

        # Reviews count
        reviews_str = self._safe_text(item, "span.poly-reviews__total")
        reviews_count = self._parse_int(reviews_str)

        # Condition
        condition = self._safe_text(item, "span.poly-component__condition")

        return Product(
            title=title,
            price=price,
            original_price=original_price,
            rating=rating,
            reviews_count=reviews_count,
            free_shipping=free_shipping,
            condition=condition or None,
            url=url,
            image_url=image_url,
        )

    def _price_from_item(self, item: Any) -> float:
        """Extract price from a search result item."""
        fraction = self._safe_text(
            item,
            "span.andes-money-amount__fraction, "
            "span.price-tag-fraction",
        )
        cents = self._safe_text(
            item,
            "span.andes-money-amount__cents, "
            "span.price-tag-cents",
        )
        return self._build_price(fraction, cents)

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    def _safe_text(self, element: Any, selector: str) -> str:
        """Try to extract text from *element* using *selector*.

        Returns empty string on failure.
        """
        try:
            found = element.find_element(By.CSS_SELECTOR, selector)
            return found.text.strip()
        except Exception:
            return ""

    def _safe_attr(self, element: Any, selector: str, attr: str) -> str:
        """Try to extract an attribute from *element* using *selector*."""
        try:
            found = element.find_element(By.CSS_SELECTOR, selector)
            return found.get_attribute(attr) or ""
        except Exception:
            return ""

    def _safe_price_element(self, driver: Any) -> float:
        """Extract price from a product detail page."""
        fraction = self._safe_text(
            driver,
            "span.andes-money-amount__fraction, "
            "span.price-tag-fraction",
        )
        cents = self._safe_text(
            driver,
            "span.andes-money-amount__cents, "
            "span.price-tag-cents",
        )
        return self._build_price(fraction, cents)

    def _build_price(self, fraction: str, cents: str) -> float:
        """Combine fraction and cents strings into a float price."""
        fraction = fraction.replace(".", "").replace(",", "").strip()
        cents = cents.strip()
        try:
            if cents:
                return float(f"{fraction}.{cents}")
            return float(fraction) if fraction else 0.0
        except (ValueError, TypeError):
            return 0.0

    def _parse_price_str(self, raw: str) -> float | None:
        """Parse a price string like '3.499' or 'R$ 3.499' into float."""
        cleaned = raw.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    def _parse_float(self, raw: str) -> float | None:
        """Parse a string like '4.5' into float, or return None."""
        cleaned = raw.strip().replace(",", ".")
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    def _parse_int(self, raw: str) -> int | None:
        """Parse a string like '(25)' or '25' into int, or return None."""
        cleaned = raw.strip().strip("()").replace(".", "")
        try:
            return int(cleaned)
        except (ValueError, TypeError):
            return None

    def _random_delay(self) -> None:
        """Sleep a random time to mimic human behaviour."""
        min_sec = self._cfg.get("random_delay_min", 2)
        max_sec = self._cfg.get("random_delay_max", 4)
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
