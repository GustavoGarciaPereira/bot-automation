"""Google Maps scraper — uses Selenium to scrape business search results.

Navigates to ``google.com/maps/search/{query}`` and parses the sidebar
result list with lazy-load scroll support.
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
from src.plugins.google_maps.models import Business, LeadSearch
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "plugin_name": "google_maps",
    "base_url": "https://www.google.com/maps/search",
    "headless": True,
    "timeout_seconds": 30,
    "max_scrolls": 10,
    "scroll_pause_min": 1.5,
    "scroll_pause_max": 3.0,
    "random_delay_min": 2,
    "random_delay_max": 5,
    "language": "pt-BR",
}

_CONFIG_CACHE: dict[str, Any] | None = None


def _load_config() -> dict[str, Any]:
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
# CSS selector lists with fallbacks
# ---------------------------------------------------------------------------

_RESULT_ITEM_SELECTORS = [
    "div[role='article']",
    "div.Nv2PK",
    "div[class*='result']",
]

_FEED_CONTAINER_SELECTORS = [
    "div[role='feed']",
    "div[aria-label*='Resultados']",
    "div[aria-label*='Results']",
    "div.m6QErb.DxyBCb",
    "div[class*='section-result']",
]

_NAME_SELECTORS = [
    "a.hfpxzc",
    "div.qBF1Pd",
    "div[role='heading']",
    "div.Cw1rxb",
    "h3",
]

_CATEGORY_SELECTORS = [
    "button.DkEaL",
    "button[class*='category']",
    "div[class*='category']",
]

_RATING_SELECTORS = [
    "span[aria-hidden='true']",
    "div.F7nice span",
    "span.z5jxId",
]

_REVIEWS_SELECTORS = [
    "span[aria-label*='avalia']",
    "span[aria-label*='review']",
    "span[aria-label*='estrela']",
    "div.F7nice span:last-child",
]

_ADDRESS_SELECTORS = [
    "button[data-item-id='address'] div.W4Efsd",
    "button[data-item-id='address'] span",
    "div[role='article'] button[data-item-id*='address']",
    "div[data-item-id='address']",
]

_PHONE_SELECTORS = [
    "button[data-item-id^='phone:'] div.W4Efsd",
    "button[data-item-id*='phone'] span",
    "div[role='article'] button[data-item-id^='phone:']",
    "button[data-item-id*='phone:']",
    "button[data-item-id*='phone']",
]

_WEBSITE_SELECTORS = [
    "a[data-item-id='authority']",
    "a[aria-label*='site']",
    "a[href*='http']:not([href*='google.com']):not([href*='maps']) a",
    "a[class*='website']",
]

_HOURS_SELECTORS = [
    "button[data-item-id*='oh'] div.W4Efsd",
    "button[data-item-id*='hour']",
    "div.o7FIHe",
]

_PLACE_LINK_SELECTORS = [
    "a.hfpxzc",
    "a[class*='place']",
]


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class GoogleMapsScraper(BaseScraper):
    """Scraper for Google Maps business search using Selenium."""

    def __init__(
        self,
        headless: bool = True,
        remote_url: str | None = None,
    ) -> None:
        self._cfg = _load_config()
        self._headless = headless
        self._remote_url = remote_url

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self, query: str, max_results: int = 20, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Search Google Maps for *query* and extract business listings.

        Automatically scrolls the result sidebar to load more results.
        """
        sanitized = query.strip().replace(" ", "+")
        search_url = f"{self._cfg['base_url']}/{sanitized}"

        min_rating = kwargs.get("min_rating", 0.0)
        logger.info("GMaps scraping: opening %s", search_url)

        driver = None
        try:
            async with selenium_driver(
                headless=self._headless,
                remote_url=self._remote_url,
            ) as driver:
                driver.get(search_url)

                # Wait for the first result to appear
                if not self._wait_for_results(driver):
                    self._save_debug(driver, query)
                    return []

                # Scroll the feed to load more items
                self._scroll_feed(driver)

                # Random delay after scrolling
                self._random_delay()

                # Extract items
                items = self._find_items(driver)
                logger.info("GMaps scraping: found %d raw items", len(items))

                businesses: list[Business] = []
                limit = min(max_results, len(items))
                seen: set[tuple[str, float | None]] = set()
                discarded_no_name = 0
                discarded_dup = 0

                for item in items[:limit]:
                    try:
                        biz = self._parse_item(item, query)
                        if biz is None:
                            discarded_no_name += 1
                            continue
                        if min_rating > 0 and biz.rating is not None and biz.rating < min_rating:
                            continue
                        # Dedup by (name, rating)
                        key = (biz.name.lower().strip(), biz.rating)
                        if key in seen:
                            discarded_dup += 1
                            continue
                        seen.add(key)
                        businesses.append(biz)
                    except Exception as exc:
                        logger.debug("Failed to parse GMaps item: %s", exc)
                        continue

                logger.info(
                    "GMaps scraping: %d businesses parsed for query=%r "
                    "(discarded: %d no name, %d dup)",
                    len(businesses), query, discarded_no_name, discarded_dup,
                )
                return [b.model_dump() for b in businesses]

        except Exception as exc:
            logger.error("GMaps scraping failed for query=%r: %s", query, exc)
            if driver:
                self._save_debug(driver, query)
            return []

    async def extract(self, place_url: str, **kwargs: Any) -> dict[str, Any]:
        """Extract detailed info from a single place page."""
        logger.info("GMaps scraping: extracting from %s", place_url)

        driver = None
        try:
            async with selenium_driver(
                headless=self._headless,
                remote_url=self._remote_url,
            ) as driver:
                driver.get(place_url)
                self._random_delay()

                name = (
                    self._single_text(driver, "h1")
                    or self._single_text(driver, "div[role='heading']")
                )
                rating = self._parse_float(
                    self._single_text(driver, "div.F7nice span[aria-hidden='true']")
                )

                return Business(
                    name=name or "Unknown",
                    rating=rating,
                    place_url=place_url,
                ).model_dump()

        except Exception as exc:
            logger.error("GMaps extraction failed for %s: %s", place_url, exc)
            if driver:
                self._save_debug(driver, place_url)
            return {}

    # ------------------------------------------------------------------
    # Internal — navigation helpers
    # ------------------------------------------------------------------

    def _wait_for_results(self, driver: Any) -> bool:
        """Wait for any known result element to appear."""
        timeout = self._cfg.get("timeout_seconds", 30)
        for selector in _RESULT_ITEM_SELECTORS + _FEED_CONTAINER_SELECTORS:
            try:
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                logger.debug("GMaps container found: %s", selector)
                return True
            except TimeoutException:
                continue
        return False

    def _find_items(self, driver: Any) -> list[Any]:
        """Return result items using the first matching selector."""
        for selector in _RESULT_ITEM_SELECTORS:
            items = driver.find_elements(By.CSS_SELECTOR, selector)
            if items:
                logger.debug("GMaps items via %s: %d", selector, len(items))
                return items
        return []

    def _find_feed(self, driver: Any) -> Any | None:
        """Return the scrollable feed container element."""
        for selector in _FEED_CONTAINER_SELECTORS:
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                if el:
                    return el
            except Exception:
                continue
        return None

    def _scroll_feed(self, driver: Any) -> None:
        """Scroll the result feed to load more results (Google Maps lazy loading)."""
        feed = self._find_feed(driver)
        if feed is None:
            logger.debug("No feed container found — trying body scroll")
            feed = driver

        max_scrolls = self._cfg.get("max_scrolls", 10)
        pause_min = self._cfg.get("scroll_pause_min", 1.5)
        pause_max = self._cfg.get("scroll_pause_max", 3.0)

        last_count = 0
        stale_count = 0

        for i in range(max_scrolls):
            try:
                driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight",
                    feed,
                )
            except Exception:
                driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )

            pause = random.uniform(pause_min, pause_max)
            time.sleep(pause)

            # Check if new items appeared
            current_items = self._find_items(driver)
            current_count = len(current_items)

            if current_count == last_count:
                stale_count += 1
                if stale_count >= 2:
                    logger.debug(
                        "Scroll stopped: no new items after %d scrolls", i + 1
                    )
                    break
            else:
                stale_count = 0

            last_count = current_count
            logger.debug("Scroll %d/%d — items: %d", i + 1, max_scrolls, current_count)

    # ------------------------------------------------------------------
    # Internal — item parsing
    # ------------------------------------------------------------------

    def _parse_item(self, item: Any, query: str) -> Business | None:
        """Parse a single result item into a Business."""
        name = self._place_name(item)
        if not name:
            return None

        category = self._category(item)
        rating = self._rating(item)
        reviews = self._reviews_count(item)
        address = self._address(item)
        phone = self._phone(item)
        website = self._website(item)
        hours = self._hours(item)
        place_url = self._place_url(item)

        return Business(
            name=name,
            category=category,
            address=address,
            phone=phone,
            website=website,
            rating=rating,
            reviews_count=reviews,
            opening_hours=hours,
            place_url=place_url,
        )

    def _place_name(self, item: Any) -> str | None:
        """Extract business name using multiple fallback selectors."""
        for sel in _NAME_SELECTORS:
            try:
                el = item.find_element(By.CSS_SELECTOR, sel)
                # Try aria-label first (it often has the clean name)
                label = el.get_attribute("aria-label")
                if label:
                    return label.strip()
                text = el.text.strip()
                if text:
                    return text
                # For a.hfpxzc, sometimes the href has the name
                href = el.get_attribute("href")
                if href and "/maps/place/" in href:
                    # Extract from URL: /maps/place/NAME/
                    import urllib.parse
                    parts = href.split("/maps/place/")
                    if len(parts) > 1:
                        name_part = parts[1].split("/")[0]
                        return urllib.parse.unquote(name_part).replace("+", " ")
            except Exception:
                continue
        return None

    def _category(self, item: Any) -> str | None:
        text = self._first_text(item, _CATEGORY_SELECTORS)
        return text or None

    def _rating(self, item: Any) -> float | None:
        text = self._first_text(item, _RATING_SELECTORS)
        if not text:
            return None
        cleaned = text.strip().replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _reviews_count(self, item: Any) -> int | None:
        text = self._first_text(item, _REVIEWS_SELECTORS)
        if not text:
            return None
        # Extract digits from strings like "(123) avaliações" or "123 reviews"
        import re
        nums = re.findall(r"\d+", text.replace(".", "").replace(",", ""))
        if nums:
            return int(nums[0])
        return None

    def _address(self, item: Any) -> str | None:
        text = self._first_text(item, _ADDRESS_SELECTORS)
        if not text:
            return None
        # Reject numeric-only values (those are ratings, not addresses)
        import re
        if re.match(r'^\d+[.,]\d+$', text.strip()):
            return None
        # Reject short text (less than 5 chars is unlikely an address)
        if len(text.strip()) < 5:
            return None
        return text.strip() or None

    def _phone(self, item: Any) -> str | None:
        # Try specific selectors first
        for sel in _PHONE_SELECTORS:
            try:
                el = item.find_element(By.CSS_SELECTOR, sel)
                data_id = el.get_attribute("data-item-id") or ""
                if ":" in data_id:
                    return data_id.split(":", 2)[-1]
                text = (el.text or "").strip()
                if text:
                    return text
            except Exception:
                continue

        # Fallback: iterate all buttons with data-item-id
        try:
            buttons = item.find_elements(
                By.CSS_SELECTOR, "button[data-item-id]"
            )
            for btn in buttons:
                data_id = btn.get_attribute("data-item-id") or ""
                if data_id.startswith("phone:"):
                    return data_id.replace("phone:tel:", "").replace("phone:", "")
        except Exception:
            pass

        return None

    def _website(self, item: Any) -> str | None:
        for sel in _WEBSITE_SELECTORS:
            try:
                el = item.find_element(By.CSS_SELECTOR, sel)
                href = el.get_attribute("href")
                if href:
                    return href
            except Exception:
                continue
        return None

    def _hours(self, item: Any) -> str | None:
        text = self._first_text(item, _HOURS_SELECTORS)
        return text or None

    def _place_url(self, item: Any) -> str:
        for sel in _PLACE_LINK_SELECTORS:
            try:
                el = item.find_element(By.CSS_SELECTOR, sel)
                href = el.get_attribute("href")
                if href:
                    return href
            except Exception:
                continue
        return ""

    # ------------------------------------------------------------------
    # Internal — helpers
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

    def _single_text(self, element: Any, selector: str) -> str:
        """Single-selector text extraction."""
        try:
            found = element.find_element(By.CSS_SELECTOR, selector)
            return found.text.strip()
        except Exception:
            return ""

    def _parse_float(self, raw: str) -> float | None:
        if not raw:
            return None
        cleaned = raw.strip().replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _random_delay(self) -> None:
        min_s = self._cfg.get("random_delay_min", 2)
        max_s = self._cfg.get("random_delay_max", 5)
        time.sleep(random.uniform(min_s, max_s))

    def _save_debug(self, driver: Any, label: str) -> None:
        """Save screenshot + HTML for debugging."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = Path("data/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            shot = log_dir / f"gmaps_debug_{ts}.png"
            driver.save_screenshot(str(shot))
            logger.info("Debug screenshot saved → %s", shot)
        except Exception as exc:
            logger.warning("Debug screenshot failed: %s", exc)
        try:
            html_path = log_dir / f"gmaps_debug_{ts}.html"
            html_path.write_text(driver.page_source, encoding="utf-8")
            logger.info("Debug HTML saved → %s", html_path)
        except Exception as exc:
            logger.warning("Debug HTML save failed: %s", exc)
