"""Google Maps scraper — uses Selenium to scrape business search results.

# ============================================================
# REAL SELECTORS (from gmaps_items_20260722_214916/, Chrome 150)
# ============================================================
# Container:        div[role='article'].Nv2PK
# Name (aria):      a.hfpxzc[aria-label]
# Name (text):      div.qBF1Pd.fontHeadlineSmall
# Name (span):      span.xxVWCe
# Rating:           span.MW4etd (text like "4,9")
# Category:         div.W4Efsd > div.W4Efsd > span > span (first text)
# Address:          div.W4Efsd > div.W4Efsd > span > span (third text, after ·)
# Phone:            span.UsdlK (text like "(19) 3325-0025")
# Hours:            span[style*='color: rgba(43,127,63']
# Website button:   a.lcr4fd.S9kvJb[data-value="Website"] href
# Website label:    a[aria-label*='Acessar o site']
# ============================================================
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.parse
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
        """Search Google Maps and extract business listings."""
        sanitized = query.strip().replace(" ", "+")
        search_url = f"{self._cfg['base_url']}/{sanitized}"
        min_rating = kwargs.get("min_rating", 0.0)
        save_debug = kwargs.get("save_debug", False)

        logger.info("GMaps scraping: opening %s", search_url)

        driver = None
        try:
            async with selenium_driver(
                headless=self._headless,
                remote_url=self._remote_url,
            ) as driver:
                driver.get(search_url)

                # Wait for results
                if not self._wait_for_results(driver):
                    self._save_debug(driver, query)
                    return []

                # Scroll the feed
                self._scroll_feed(driver)
                self._random_delay()

                # ---- Save debug artifacts (same session) ----
                if save_debug:
                    self._save_debug(driver, query, also_items=True)

                # Extract items
                items = self._find_items(driver)
                logger.info("GMaps scraping: found %d raw items", len(items))

                businesses: list[Business] = []
                limit = min(max_results, len(items))
                seen: set[tuple[str, float | None]] = set()
                no_name_count = 0
                no_addr_count = 0
                no_phone_count = 0
                discarded_dup = 0

                for item in items[:limit]:
                    try:
                        biz = self._parse_item(item)
                        if biz is None:
                            no_name_count += 1
                            if no_name_count <= 5:
                                try:
                                    preview = (item.text or "")[:80]
                                except Exception:
                                    preview = "(no text)"
                                logger.debug("Discarded item (no name): %s", preview)
                            continue

                        if biz.address is None:
                            no_addr_count += 1
                        if biz.phone is None:
                            no_phone_count += 1

                        if min_rating > 0 and biz.rating is not None and biz.rating < min_rating:
                            continue

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
                    "GMaps scraping: %d businesses parsed | "
                    "No name: %d | No address: %d | No phone: %d | Dup: %d | Raw: %d",
                    len(businesses), no_name_count, no_addr_count,
                    no_phone_count, discarded_dup, len(items),
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
                return Business(name=name or "Unknown", place_url=place_url).model_dump()
        except Exception as exc:
            logger.error("GMaps extraction failed for %s: %s", place_url, exc)
            if driver:
                self._save_debug(driver, place_url)
            return {}

    # ------------------------------------------------------------------
    # Internal — navigation helpers
    # ------------------------------------------------------------------

    def _wait_for_results(self, driver: Any) -> bool:
        timeout = self._cfg.get("timeout_seconds", 30)
        for selector in [
            "div.Nv2PK",
            "div[role='article']",
            "div[role='feed']",
        ]:
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
        for selector in ["div.Nv2PK", "div[role='article']"]:
            items = driver.find_elements(By.CSS_SELECTOR, selector)
            if items:
                return items
        return []

    def _find_feed(self, driver: Any) -> Any | None:
        for selector in [
            "div[role='feed']",
            "div[aria-label*='Resultados']",
            "div[aria-label*='Results']",
            "div.m6QErb.DxyBCb",
        ]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                if el:
                    return el
            except Exception:
                continue
        return None

    def _scroll_feed(self, driver: Any) -> None:
        feed = self._find_feed(driver)
        if feed is None:
            logger.debug("No feed container — trying body scroll")
            feed = driver
        max_scrolls = self._cfg.get("max_scrolls", 10)
        pause_min = self._cfg.get("scroll_pause_min", 1.5)
        pause_max = self._cfg.get("scroll_pause_max", 3.0)
        last_count = 0
        stale_count = 0
        for i in range(max_scrolls):
            try:
                driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight", feed
                )
            except Exception:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(pause_min, pause_max))
            current_items = self._find_items(driver)
            current_count = len(current_items)
            if current_count == last_count:
                stale_count += 1
                if stale_count >= 2:
                    logger.debug("Scroll stopped after %d scrolls", i + 1)
                    break
            else:
                stale_count = 0
            last_count = current_count

    # ------------------------------------------------------------------
    # Internal — item parsing (REAL selectors from saved HTML)
    # ------------------------------------------------------------------

    def _parse_item(self, item: Any) -> Business | None:
        """Parse a single Google Maps result card into a Business."""
        name = self._place_name(item)
        if not name:
            return None

        rating = self._rating(item)
        category = self._category(item)
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
            reviews_count=None,  # Reviews count not available in list view
            opening_hours=hours,
            place_url=place_url,
        )

    def _place_name(self, item: Any) -> str | None:
        """REAL selector: a.hfpxzc[aria-label] or div.qBF1Pd or span.xxVWCe."""
        # Strategy 1: a.hfpxzc[aria-label]
        try:
            el = item.find_element(By.CSS_SELECTOR, "a.hfpxzc")
            aria = el.get_attribute("aria-label")
            if aria and len(aria.strip()) > 2:
                return aria.strip()
        except Exception:
            pass
        # Strategy 2: div.qBF1Pd
        try:
            el = item.find_element(By.CSS_SELECTOR, "div.qBF1Pd")
            text = el.text.strip()
            if text and len(text) > 2:
                return text
        except Exception:
            pass
        # Strategy 3: span.xxVWCe
        try:
            el = item.find_element(By.CSS_SELECTOR, "span.xxVWCe")
            text = el.text.strip()
            if text and len(text) > 2:
                return text
        except Exception:
            pass
        # Strategy 4: any a with aria-label
        try:
            for link in item.find_elements(By.CSS_SELECTOR, "a[aria-label]"):
                aria = link.get_attribute("aria-label")
                if aria and len(aria) > 2:
                    return aria.strip()
        except Exception:
            pass
        # Strategy 5: first long text line
        try:
            for line in (item.text or "").split("\n"):
                line = line.strip()
                if line and len(line) > 5 and not line.startswith(("⭐", "4", "5")):
                    return line
        except Exception:
            pass
        return None

    def _rating(self, item: Any) -> float | None:
        """REAL selector: span.MW4etd (text like '4,9')."""
        try:
            el = item.find_element(By.CSS_SELECTOR, "span.MW4etd")
            text = el.text.strip().replace(",", ".")
            return float(text)
        except Exception:
            return None

    def _category(self, item: Any) -> str | None:
        """Category is the first text in the address block before address."""
        try:
            spans = item.find_elements(
                By.CSS_SELECTOR,
                "div.W4Efsd > div.W4Efsd > span > span",
            )
            for s in spans:
                t = s.text.strip()
                if t and t not in ("·",) and not t.startswith(("R.", "Av.", "Rua")):
                    return t
        except Exception:
            pass
        return None

    def _address(self, item: Any) -> str | None:
        """REAL selector: find address-like text in the W4Efsd block."""
        import re

        def _clean(text: str) -> str:
            """Remove leading · and whitespace."""
            return re.sub(r'^·\s*', '', text).strip()

        # Strategy 1: look for span containing street pattern
        try:
            spans = item.find_elements(
                By.CSS_SELECTOR,
                "div.W4Efsd > div.W4Efsd span",
            )
            for s in spans:
                t = _clean(s.text.strip())
                if re.match(r'^[A-Za-z]\.\s', t) or any(p in t for p in ["Rua", "Av.", "Alameda", "Praça", "Avenida"]):
                    if not re.match(r'^\d+[.,]\d+$', t) and len(t) >= 5:
                        return t
        except Exception:
            pass
        # Strategy 2: try the third span in address block
        try:
            spans = item.find_elements(
                By.CSS_SELECTOR,
                "div.W4Efsd > div.W4Efsd > span > span",
            )
            texts = [_clean(s.text.strip()) for s in spans if s.text.strip() and s.text.strip() != "·"]
            for t in texts:
                if len(t) > 5 and not re.match(r'^\d+[.,]\d+$', t):
                    return t
        except Exception:
            pass
        # Strategy 3: button[data-item-id="address"]
        try:
            for btn in item.find_elements(By.CSS_SELECTOR, "button[data-item-id]"):
                did = btn.get_attribute("data-item-id") or ""
                if "address" in did:
                    t = _clean(btn.text or "")
                    if t and not re.match(r'^\d+[.,]\d+$', t) and len(t) >= 5:
                        return t
        except Exception:
            pass
        return None

    def _phone(self, item: Any) -> str | None:
        """REAL selector: span.UsdlK (text like '(19) 3325-0025')."""
        try:
            el = item.find_element(By.CSS_SELECTOR, "span.UsdlK")
            return el.text.strip() or None
        except Exception:
            pass
        # Fallback: scan data-item-id for phone:
        try:
            for btn in item.find_elements(By.CSS_SELECTOR, "button[data-item-id]"):
                did = btn.get_attribute("data-item-id") or ""
                if "phone" in did:
                    return did.split(":")[-1]
        except Exception:
            pass
        return None

    def _website(self, item: Any) -> str | None:
        """Extract website URL from the card."""
        # Try specific website selectors only
        for sel in [
            "a[data-item-id='authority']",
            "a[data-item-id='authority'][href]",
            "a[aria-label*='Acessar o site']",
            "a[aria-label*='site']",
            "a.lcr4fd.S9kvJb[data-value='Website']",
            "a.lcr4fd[data-value='Website']",
        ]:
            try:
                el = item.find_element(By.CSS_SELECTOR, sel)
                href = el.get_attribute("href") or ""
                if href and self._is_valid_website(href):
                    return href
            except Exception:
                continue
        return None

    def _is_valid_website(self, url: str) -> bool:
        """Check if a URL is a real external website (not Google internal)."""
        if not url.startswith("http"):
            return False
        url_lower = url.lower()
        # Block all Google domains
        google_patterns = [
            "google.com", "google.com.br", "googleadservices",
            "gstatic.com", "googleapis.com", "googleoptimize.com",
            "googlesyndication.com", "doubleclick.net",
        ]
        return not any(p in url_lower for p in google_patterns)

    def _hours(self, item: Any) -> str | None:
        """REAL selector: span[style*='color: rgba(43,127,63']"""
        try:
            el = item.find_element(By.CSS_SELECTOR, "span[style*='color: rgba(43,127,63']")
            return el.text.strip() or None
        except Exception:
            pass
        return None

    def _place_url(self, item: Any) -> str:
        try:
            el = item.find_element(By.CSS_SELECTOR, "a.hfpxzc")
            return el.get_attribute("href") or ""
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    def _single_text(self, element: Any, selector: str) -> str:
        try:
            found = element.find_element(By.CSS_SELECTOR, selector)
            return found.text.strip()
        except Exception:
            return ""

    def _random_delay(self) -> None:
        time.sleep(random.uniform(
            self._cfg.get("random_delay_min", 2),
            self._cfg.get("random_delay_max", 5),
        ))

    def _save_debug(self, driver: Any, label: str, also_items: bool = False) -> None:
        """Save screenshot + HTML + individual items for debugging."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = Path("data/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            shot = log_dir / f"gmaps_debug_{ts}.png"
            driver.save_screenshot(str(shot))
            logger.info("Debug screenshot → %s", shot)
        except Exception as exc:
            logger.warning("Debug screenshot failed: %s", exc)
        try:
            html_path = log_dir / f"gmaps_debug_{ts}.html"
            html_path.write_text(driver.page_source, encoding="utf-8")
            logger.info("Debug HTML → %s", html_path)
        except Exception as exc:
            logger.warning("Debug HTML save failed: %s", exc)
        if also_items:
            try:
                items_dir = log_dir / f"gmaps_items_{ts}"
                items_dir.mkdir(exist_ok=True)
                items = driver.find_elements(By.CSS_SELECTOR, "div.Nv2PK, div[role='article']")
                for i, item in enumerate(items[:10]):
                    try:
                        outer = item.get_attribute("outerHTML") or item.text
                        (items_dir / f"item_{i+1}.html").write_text(outer, encoding="utf-8")
                    except Exception:
                        pass
                logger.info("Sample items saved → %s/", items_dir)
            except Exception as exc:
                logger.warning("Sample items save failed: %s", exc)
