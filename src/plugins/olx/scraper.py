"""OLX Brasil scraper — Selenium-based for product/classified ads."""

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
from src.plugins.olx.models import OLXAd, OLXSearch
from src.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_CONFIG = {
    "plugin_name": "olx",
    "base_url": "https://www.olx.com.br",
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


_CONTAINER_SELECTORS = [
    "div[data-testid='ad-card']",
    "div.ad-card",
    "div[class*='AdCard']",
    "li.ad-item",
    "div[class*='ad-item']",
    "div[class*='card']",
]

_TITLE_SELECTORS = [
    "h2 a",
    "h2[class*='title']",
    "h3[class*='title']",
    "span[class*='title']",
    "a[class*='title']",
    "a[data-testid='ad-card-link']",
]

_PRICE_SELECTORS = [
    "span[class*='price']",
    "div[class*='price']",
    "span[class*='Price']",
    "div[class*='Price']",
]

_LOCATION_SELECTORS = [
    "span[class*='location']",
    "div[class*='location']",
    "span[class*='municipality']",
]

_DATE_SELECTORS = [
    "span[class*='date']",
    "div[class*='date']",
    "span[class*='Date']",
]

_LINK_SELECTORS = [
    ("a[href*='/anuncio/']", "href"),
    ("a[data-testid='ad-card-link']", "href"),
    ("a", "href"),
]

_IMAGE_SELECTORS = [
    ("img[src]", "src"),
    ("img[data-src]", "data-src"),
    ("img", "src"),
]

_PROFESSIONAL_SELECTORS = [
    "span[class*='professional']",
    "span[class*='badge']",
    "span[class*='store']",
]


class OLXScraper(BaseScraper):
    """Scraper for OLX Brasil classified ads."""

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self._cfg = _load_config()
        self._headless = headless
        self._remote_url = remote_url

    async def search(
        self, query: str, max_results: int = 15, **kwargs: Any
    ) -> list[dict[str, Any]]:
        sanitized = query.strip().lower().replace(" ", "-")
        url = f"{self._cfg['base_url']}/brasil?q={sanitized}"
        logger.info("OLX: searching %s (max %d)", url, max_results)

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
                logger.info("OLX: %d raw items", len(cards))

                ads: list[OLXAd] = []
                seen: set[str] = set()

                for card in cards[:max_results]:
                    ad = self._parse_card(card)
                    if ad is None:
                        continue
                    key = ad.title.lower().strip()
                    if key in seen:
                        continue
                    seen.add(key)
                    ads.append(ad)

                logger.info("OLX: %d ads for %s", len(ads), query)
                return [a.model_dump() for a in ads]

        except Exception as exc:
            logger.error("OLX failed: %s", exc)
            if driver:
                self._save_debug(driver, query)
            return []

    async def extract(self, ad_url: str, **kwargs: Any) -> dict[str, Any]:
        return {}

    def _wait_for_results(self, driver: Any) -> bool:
        timeout = self._cfg.get("timeout_seconds", 30)
        for sel in _CONTAINER_SELECTORS + ["div[data-testid]", "main", "section"]:
            try:
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                return True
            except TimeoutException:
                continue
        return False

    def _find_cards(self, driver: Any) -> list[Any]:
        for sel in _CONTAINER_SELECTORS:
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

    def _parse_card(self, card: Any) -> OLXAd | None:
        title = self._first_text(card, _TITLE_SELECTORS)
        if not title:
            # Fallback: try text-based extraction
            try:
                raw = card.text.strip()
                if not raw:
                    logger.debug("OLX item vazio")
                    return None
                lines = [l.strip() for l in raw.split("\n") if l.strip()]
                if not lines:
                    return None
                # Title: first long line that isn't a price
                for line in lines:
                    if len(line) > 10 and not re.match(r"^R?\$?\s*[\d.,]+", line):
                        title = line
                        break
                if not title:
                    title = lines[0]
            except Exception:
                pass
            if not title:
                logger.debug("OLX: item sem título. Text: %s", raw[:100] if 'raw' in dir() else "?")
                return None

        price = self._parse_price(card)
        if price is None:
            # Fallback: find price in raw text
            try:
                raw = card.text.strip()
                m = re.search(r"R\$\s*([\d.,]+)", raw)
                if m:
                    price = self._parse_price_str(m.group(1))
            except Exception:
                pass

        location = self._first_text(card, _LOCATION_SELECTORS)
        if not location:
            # Fallback: look for "City - ST" pattern
            try:
                raw = card.text.strip()
                m = re.search(r"([A-Za-zÀ-ÿ\s]+)\s*-\s*[A-Z]{2}", raw)
                if m:
                    location = m.group(0)
            except Exception:
                pass

        date = self._first_text(card, _DATE_SELECTORS)
        if not date:
            # Fallback: look for date-like text
            try:
                raw = card.text.strip()
                for line in raw.split("\n"):
                    if re.search(r"(Hoje|Ontem|\d{2}/\d{2})", line):
                        date = line.strip()
                        break
            except Exception:
                pass

        link = self._first_attr(card, _LINK_SELECTORS)
        img = self._first_attr(card, _IMAGE_SELECTORS)
        prof = bool(self._first_text(card, _PROFESSIONAL_SELECTORS))

        return OLXAd(
            title=title, price=price, location=location or None,
            date=date or None, ad_url=link, image_url=img,
            is_professional=prof,
        )

    def _parse_price(self, card: Any) -> float | None:
        text = self._first_text(card, _PRICE_SELECTORS)
        if not text:
            return None
        return self._parse_price_str(text)

    def _parse_price_str(self, raw: str) -> float | None:
        """Parse a price string like 'R$ 1.200' or 'R$ 3.499,90' into float."""
        if not raw:
            return None
        if "grátis" in raw.lower() or "gratis" in raw.lower():
            return 0.0
        text = raw.replace("R$", "").replace(" ", "").strip()
        if re.search(r",\d{2}$", text):
            text = text.replace(".", "").replace(",", ".")
        elif "." in text and "," not in text:
            text = text.replace(".", "")
        else:
            text = text.replace(",", ".")
        try:
            return float(text)
        except ValueError:
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
            driver.save_screenshot(str(log_dir / f"olx_debug_{ts}.png"))
        except Exception:
            pass
        try:
            (log_dir / f"olx_debug_{ts}.html").write_text(driver.page_source, encoding="utf-8")
        except Exception:
            pass
