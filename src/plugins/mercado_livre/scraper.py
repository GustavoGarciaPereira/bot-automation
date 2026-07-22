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

from selenium.common.exceptions import TimeoutException
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
    "timeout_seconds": 30,
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
# Multiple CSS selectors for ML result containers (tried in order)
# ---------------------------------------------------------------------------

_RESULT_CONTAINER_SELECTORS = [
    "ol.ui-search-layout",
    "section.ui-search-results",
    "div.ui-search-result__wrapper",
    "li.ui-search-layout__item",
    "div.poly-card",
    "ol.poly-card-list",
    "div.ui-search-result",
    "div[class*='poly-card']",
]

_ITEM_SELECTORS = [
    "li.ui-search-layout__item",
    "div.poly-card",
    "div.ui-search-result__wrapper",
    "li[class*='poly-card']",
    "div.ui-search-result",
    "div.ui-search-item",
]

_TITLE_SELECTORS = [
    "a.poly-component__title",
    "h2.poly-box__title",
    "h2[class*='poly']",
    "a[class*='poly-component__title']",
    "h2 a",
    "a.ui-search-item__group__title",
    "a.ui-search-link",
]

_PRICE_FRACTION_SELECTORS = [
    "span.andes-money-amount__fraction",
    "span[class*='andes-money-amount__fraction']",
    "span.poly-price__current span.andes-money-amount__fraction",
    "span.price-tag-fraction",
]

_PRICE_CENTS_SELECTORS = [
    "span.andes-money-amount__cents",
    "span[class*='andes-money-amount__cents']",
    "span.price-tag-cents",
]

_ORIGINAL_PRICE_SELECTORS = [
    "span.poly-price__previous span.andes-money-amount__fraction",
    "s.andes-money-amount span.andes-money-amount__fraction",
    "span.poly-price__previous [class*='andes-money-amount__fraction']",
]

_URL_SELECTORS = [
    "a.poly-component__title",
    "a.ui-search-link",
    "a[class*='poly-component__title']",
    "a",
]

_IMAGE_SELECTORS = [
    ("img.poly-component__picture", "src"),
    ("img[class*='poly-component__picture']", "src"),
    ("img", "data-src"),
    ("img", "src"),
]

_FREE_SHIPPING_SELECTORS = [
    "span.poly-component__shipping",
    "div.poly-component__shipping",
    "p.poly-component__shipping",
    "[class*='shipping']",
]

_RATING_SELECTORS = [
    "span.poly-reviews__rating",
    "[class*='reviews__rating']",
    "span.reviews-rating",
]

_REVIEWS_COUNT_SELECTORS = [
    "span.poly-reviews__total",
    "[class*='reviews__total']",
    "span.reviews-count",
]

_CONDITION_SELECTORS = [
    "span.poly-component__condition",
    "[class*='condition']",
    "span.ui-search-item__group__element",
]


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class MercadoLivreScraper(BaseScraper):
    """Scraper for Mercado Livre product search using Selenium."""

    def __init__(
        self,
        headless: bool = True,
        remote_url: str | None = None,
    ) -> None:
        self._cfg = _load_config()
        # Respect passed headless; fall back to config.json default
        self._headless = headless
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

                # ---- Wait for any known result container ----
                timeout = self._cfg.get("timeout_seconds", 30)
                if not self._wait_for_container(driver, timeout):
                    self._save_debug_artifacts(driver, query)
                    return []

                # ---- Scroll to trigger lazy loading ----
                self._scroll_page(driver)

                # ---- Random human-like delay ----
                self._random_delay()

                # ---- Extract items ----
                items = self._find_items(driver)
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
            self._save_debug_artifacts(driver, query) if driver else None
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

                title = (
                    self._safe_text(driver, "h1.ui-pdp-title")
                    or self._safe_text(driver, "h1")
                )
                price = self._safe_price_element(driver)
                condition = self._safe_text(driver, "span.ui-pdp-subtitle")
                seller = self._safe_text(
                    driver,
                    "a.ui-pdp-seller__link span, "
                    "span.ui-pdp-seller__link-text, "
                    "a.andes-dropdown__trigger",
                )

                return Product(
                    title=title,
                    price=price,
                    condition=condition or None,
                    seller=seller or None,
                    url=url,
                ).model_dump()

        except Exception as exc:
            logger.error("ML extraction failed for %s: %s", url, exc)
            if driver:
                self._save_debug_artifacts(driver, url)
            return {}

    # ------------------------------------------------------------------
    # Internal — container wait
    # ------------------------------------------------------------------

    def _wait_for_container(self, driver: Any, timeout: int) -> bool:
        """Try multiple selectors for the result container.

        Returns True if any selector matched within *timeout* seconds.
        """
        for selector in _RESULT_CONTAINER_SELECTORS:
            try:
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                logger.debug("ML container found with: %s", selector)
                return True
            except TimeoutException:
                continue
        return False

    def _find_items(self, driver: Any) -> list[Any]:
        """Try multiple selectors to locate result items."""
        for selector in _ITEM_SELECTORS:
            items = driver.find_elements(By.CSS_SELECTOR, selector)
            if items:
                logger.debug("ML items found with selector: %s (%d)", selector, len(items))
                return items
        return []

    def _scroll_page(self, driver: Any) -> None:
        """Scroll down to trigger lazy-loaded content."""
        try:
            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight / 2);"
            )
            time.sleep(2)
            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(2)
        except Exception as exc:
            logger.debug("Scroll failed: %s", exc)

    def _save_debug_artifacts(self, driver: Any, label: str) -> None:
        """Save screenshot + page HTML for debugging."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = Path("data/logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        # Screenshot
        try:
            shot = log_dir / f"ml_debug_{ts}.png"
            driver.save_screenshot(str(shot))
            logger.info("Debug screenshot saved → %s", shot)
        except Exception as exc:
            logger.warning("Debug screenshot failed: %s", exc)

        # HTML source
        try:
            html_path = log_dir / f"ml_debug_{ts}.html"
            html_path.write_text(driver.page_source, encoding="utf-8")
            logger.info("Debug HTML saved → %s", html_path)
        except Exception as exc:
            logger.warning("Debug HTML save failed: %s", exc)

    # ------------------------------------------------------------------
    # Internal — item parsing
    # ------------------------------------------------------------------

    def _parse_item(self, item: Any) -> Product | None:
        """Parse a single search-result HTML element into a Product."""
        title = self._first_text(item, _TITLE_SELECTORS)
        if not title:
            return None

        price = self._price_from_item(item)
        original_price_str = self._first_text(item, _ORIGINAL_PRICE_SELECTORS)
        original_price = self._parse_price_str(original_price_str) if original_price_str else None

        url = self._first_attr(item, _URL_SELECTORS, "href")
        image_url = self._first_attr_from_pairs(item, _IMAGE_SELECTORS)

        free_shipping = bool(self._first_text(item, _FREE_SHIPPING_SELECTORS))

        rating_str = self._first_text(item, _RATING_SELECTORS)
        rating = self._parse_float(rating_str)

        reviews_str = self._first_text(item, _REVIEWS_COUNT_SELECTORS)
        reviews_count = self._parse_int(reviews_str)

        condition = self._first_text(item, _CONDITION_SELECTORS)

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
        fraction = self._first_text(item, _PRICE_FRACTION_SELECTORS)
        cents = self._first_text(item, _PRICE_CENTS_SELECTORS)
        return self._build_price(fraction, cents)

    # ------------------------------------------------------------------
    # Internal — helpers with multiple selector fallback
    # ------------------------------------------------------------------

    def _first_text(self, element: Any, selectors: list[str]) -> str:
        """Try each selector until one returns non-empty text."""
        for sel in selectors:
            try:
                found = element.find_element(By.CSS_SELECTOR, sel)
                text = found.text.strip()
                if text:
                    return text
            except Exception:
                continue
        return ""

    def _first_attr(self, element: Any, selectors: list[str], attr: str) -> str:
        """Try each selector until one returns a non-empty attribute."""
        for sel in selectors:
            try:
                found = element.find_element(By.CSS_SELECTOR, sel)
                val = found.get_attribute(attr)
                if val:
                    return val
            except Exception:
                continue
        return ""

    def _first_attr_from_pairs(
        self, element: Any, pairs: list[tuple[str, str]]
    ) -> str:
        """Try each (selector, attr) pair until one returns a value."""
        for sel, attr in pairs:
            try:
                found = element.find_element(By.CSS_SELECTOR, sel)
                val = found.get_attribute(attr)
                if val:
                    return val
            except Exception:
                continue
        return ""

    def _safe_text(self, element: Any, selector: str) -> str:
        """Single-selector text extraction with error handling."""
        try:
            found = element.find_element(By.CSS_SELECTOR, selector)
            return found.text.strip()
        except Exception:
            return ""

    def _safe_price_element(self, driver: Any) -> float:
        """Extract price from a product detail page."""
        fraction = self._first_text(driver, _PRICE_FRACTION_SELECTORS)
        cents = self._first_text(driver, _PRICE_CENTS_SELECTORS)
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
        if not raw:
            return None
        cleaned = raw.strip().replace(",", ".")
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    def _parse_int(self, raw: str) -> int | None:
        """Parse a string like '(25)' or '25' into int, or return None."""
        if not raw:
            return None
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
