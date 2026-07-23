"""Google Shopping scraper — Selenium-based.

Uses the same google.com infrastructure as Google Maps (no CloudFlare).
"""

from __future__ import annotations

import json
import random
import re
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
from src.plugins.google_shopping.models import ShoppingProduct, ShoppingSearch
from src.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_CONFIG = {
    "plugin_name": "google_shopping",
    "base_url": "https://www.google.com/search",
    "headless": True,
    "timeout_seconds": 30,
    "max_scrolls": 3,
    "random_delay_min": 2,
    "random_delay_max": 4,
}

_CONFIG_CACHE: dict[str, Any] | None = None


def _load_config() -> dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    cfg_path = Path(__file__).resolve().parent / "config.json"
    overrides = {}
    if cfg_path.exists():
        try:
            overrides = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load config: %s", exc)
    merged = {**_DEFAULT_CONFIG, **overrides}
    _CONFIG_CACHE = merged
    return merged


def _clear_config_cache() -> None:
    global _CONFIG_CACHE
    _CONFIG_CACHE = None


_SHOPPING_RESULTS = [
    "div.sh-dgr__content",
    "div[class*='sh-dgr']",
    "div[data-testid='shopping-results']",
    "div.sh-sr__shop-result-group",
    "div[data-testid='shopping-result']",
]

_TITLE_SELECTORS = [
    "h3[class*='t']",
    "h3",
    "div[class*='title']",
    "span[role='heading']",
    "a[class*='title']",
]

_PRICE_SELECTORS = [
    "span[class*='price']",
    "span.HRLxBb",
    "div[class*='price']",
    "span[class*='a-offscreen']",
]

_STORE_SELECTORS = [
    "div[class*='merchant']",
    "span[class*='merchant']",
    "div.aULzUe",
    "span[class*='store']",
]

_RATING_SELECTORS = [
    "span[class*='rating']",
    "div[class*='star']",
    "span[class*='star']",
]

_IMAGE_SELECTORS = [
    ("img[src]", "src"),
    ("img[data-src]", "data-src"),
    ("img", "src"),
]

_LINK_SELECTORS = [
    ("a[href*='/shopping/']", "href"),
    ("a[href*='/url?']", "href"),
    ("a[href]", "href"),
]


class GoogleShoppingScraper(BaseScraper):
    """Scraper for Google Shopping product search."""

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self._cfg = _load_config()
        self._headless = headless
        self._remote_url = remote_url

    async def search(
        self, query: str, max_results: int = 15, **kwargs: Any
    ) -> list[dict[str, Any]]:
        sanitized = query.strip().replace(" ", "+")
        url = f"{self._cfg['base_url']}?q={sanitized}&tbm=shop"
        logger.info("GS: searching %s (max %d)", url, max_results)

        driver = None
        try:
            async with selenium_driver(
                headless=self._headless, remote_url=self._remote_url,
            ) as driver:
                driver.get(url)
                self._random_delay()

                if not self._wait_for_results(driver):
                    self._save_debug(driver, query)
                    return []

                self._scroll(driver)
                cards = self._find_cards(driver)
                logger.info("GS: %d raw items", len(cards))

                products: list[ShoppingProduct] = []
                seen: set[str] = set()

                for card in cards[:max_results]:
                    p = self._parse_card(card)
                    if p is None:
                        continue
                    key = p.title.lower().strip()
                    if key in seen:
                        continue
                    seen.add(key)
                    products.append(p)

                logger.info("GS: %d products for %s", len(products), query)
                return [p.model_dump() for p in products]

        except Exception as exc:
            logger.error("GS failed: %s", exc)
            if driver:
                self._save_debug(driver, query)
            return []

    async def extract(self, product_url: str, **kwargs: Any) -> dict[str, Any]:
        return {}

    def _wait_for_results(self, driver: Any) -> bool:
        timeout = self._cfg.get("timeout_seconds", 30)
        for sel in _SHOPPING_RESULTS:
            try:
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                return True
            except TimeoutException:
                continue
        return False

    def _find_cards(self, driver: Any) -> list[Any]:
        for sel in _SHOPPING_RESULTS:
            items = driver.find_elements(By.CSS_SELECTOR, sel)
            if items:
                return items
        return []

    def _scroll(self, driver: Any) -> None:
        n = self._cfg.get("max_scrolls", 3)
        for _ in range(n):
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(1.5, 3))
            except Exception:
                break

    def _parse_card(self, card: Any) -> ShoppingProduct | None:
        title = self._first_text(card, _TITLE_SELECTORS)
        if not title:
            return None

        price = self._parse_price(card)
        store = self._first_text(card, _STORE_SELECTORS)
        rating = self._parse_rating(card)
        img = self._first_attr(card, _IMAGE_SELECTORS)
        link = self._first_attr(card, _LINK_SELECTORS)

        return ShoppingProduct(
            title=title, price=price, store_name=store or None,
            rating=rating, image_url=img, product_url=link,
        )

    def _parse_price(self, card: Any) -> float | None:
        text = self._first_text(card, _PRICE_SELECTORS)
        if not text:
            return None
        # "R$ 3.499,90" or "R$ 1.299" → float
        text = text.replace("R$", "").replace("$", "").strip()
        # Detect Brazilian format: 1.234,56
        if re.search(r",\d{2}$", text):
            # Has cents after comma: remove thousand dots, replace comma with dot
            text = text.replace(".", "").replace(",", ".")
        elif "." in text and "," not in text:
            # Has dots but no commas: likely thousand separators
            text = text.replace(".", "")
        else:
            text = text.replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None

    def _parse_rating(self, card: Any) -> float | None:
        text = self._first_text(card, _RATING_SELECTORS)
        if not text:
            return None
        text = text.strip().replace(",", ".")
        nums = re.findall(r"[\d.]+", text)
        if nums:
            try:
                return float(nums[0])
            except ValueError:
                pass
        return None

    def _first_text(self, element: Any, selectors: list[str]) -> str:
        for sel in selectors:
            try:
                el = element.find_element(By.CSS_SELECTOR, sel)
                t = el.text.strip()
                if t:
                    return t
            except Exception:
                continue
        return ""

    def _first_attr(self, element: Any, pairs: list[tuple[str, str]]) -> str:
        for sel, attr in pairs:
            try:
                el = element.find_element(By.CSS_SELECTOR, sel)
                v = el.get_attribute(attr)
                if v:
                    return v
            except Exception:
                continue
        return ""

    def _random_delay(self) -> None:
        time.sleep(random.uniform(
            self._cfg.get("random_delay_min", 2),
            self._cfg.get("random_delay_max", 4),
        ))

    def _save_debug(self, driver: Any, label: str) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = Path("data/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            driver.save_screenshot(str(log_dir / f"gs_debug_{ts}.png"))
        except Exception:
            pass
        try:
            (log_dir / f"gs_debug_{ts}.html").write_text(driver.page_source, encoding="utf-8")
        except Exception:
            pass
