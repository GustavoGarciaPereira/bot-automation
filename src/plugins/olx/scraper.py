"""OLX Brasil scraper — Selenium + regex hybrid parsing.

# ============================================================
# REAL OLX STRUCTURE (confirmed via debug HTML)
# ============================================================
# Container:  div[class*='AdCard'] → 50 found
# Title:      h2 or h3 inside card
# Price:      "R$ 3.800" text extracted via regex
# Location:   "São Paulo - SP" → regex Cidade - UF
# Date:       "Hoje, 00:45" → regex (Hoje|Ontem|\d{2}/\d{2})
# Image:      img[src*='img.olx.com.br']
# Link:       a[href*='olx.com.br'] or a[href*='/anuncio/']
# ============================================================
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
    "section.olx-adcard",
    "div.olx-adcard__content",
    "div[class*='AdCard']",
    "div[data-testid='ad-card']",
]

_TITLE_SELECTORS = [
    "a[data-testid='adcard-link']",
    "a.olx-adcard__link",
    "h2.olx-adcard__title",
    "[class*='adcard__title']",
    "h2",
    "a[title]",
]


class OLXScraper(BaseScraper):
    """Scraper for OLX Brasil — Selenium + regex hybrid parsing."""

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self._cfg = _load_config()
        self._headless = headless
        self._remote_url = remote_url

    async def search(
        self, query: str, max_results: int = 15, **kwargs: Any
    ) -> list[dict[str, Any]]:
        save_debug = kwargs.get("save_debug", False)
        sanitized = query.strip().lower().replace(" ", "-")
        url = f"{self._cfg['base_url']}/brasil?q={sanitized}"
        logger.info("OLX: %s (max %d)", url, max_results)

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

                # Save debug artifacts in the SAME session
                if save_debug:
                    self._save_debug(driver, query, save_items=True)

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

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _wait_for_results(self, driver: Any) -> bool:
        timeout = self._cfg.get("timeout_seconds", 30)
        for sel in _CONTAINER_SELECTORS + ["main", "section", "div[data-testid]"]:
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

    # ------------------------------------------------------------------
    # Parsing — hybrid (CSS selectors + regex fallback)
    # ------------------------------------------------------------------

    def _parse_card(self, card: Any) -> OLXAd | None:
        text = (card.text or "").strip()
        if not text:
            return None

        # 1. Title: CSS selectors, then img alt / link title, then text fallback
        title = self._try_selectors(card, _TITLE_SELECTORS)
        if not title:
            title = self._try_attr(card, ["img[alt]", "a[title]"], "alt", "title")
        if not title:
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            # Skip common UI text and short lines
            skip_words = [
                "adicionar", "compartilhar", "favoritar", "favorito",
                "curtir", "salvar", "comprar", "ver mais",
                "telefone", "whatsapp", "mensagem",
            ]
            for line in lines:
                if len(line) < 10:
                    continue
                if any(w in line.lower() for w in skip_words):
                    continue
                if re.match(r"^R?\$", line):
                    continue
                # Looks like a title
                title = line
                break

        if not title:
            logger.debug("OLX: no title found. Text preview: %s", text[:100])
            # Still parse price — item may be valid with just price
            price = self._extract_price(text)
            if price is None:
                return None
            title = "Sem título"
        else:
            # 2. Price
            price = self._extract_price(text)

        # 3. Location
        location = self._extract_location(text)

        # 4. Date
        date = self._extract_date(text)

        # 5. Link
        link = self._try_attr(card, [
            "a[href*='olx.com.br']",
            "a[href*='/anuncio/']",
            "a",
        ], "href")

        # 6. Image
        img = self._try_attr(card, [
            "img[src*='img.olx.com.br']",
            "img[src*='thumbs']",
            "img",
        ], "src")

        return OLXAd(
            title=title,
            price=price,
            location=location or None,
            date=date or None,
            ad_url=link or "",
            image_url=img or "",
        )

    def _extract_price(self, text: str) -> float | None:
        """Extract price via regex. If multiple prices, last is current."""
        prices = re.findall(r"R\$\s*([\d.,]+)", text)
        if not prices:
            return None
        raw = prices[-1]  # last = discounted price
        raw = raw.replace(".", "").replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            return None

    def _extract_location(self, text: str) -> str | None:
        # Find all "City - UF" patterns, take the LAST one
        # Use a space (not \s) to avoid matching across newlines
        matches = list(re.finditer(
            r"([A-ZÀ-Ú][a-zà-ú]+(?: [A-ZÀ-Ú][a-zà-ú]+)*)\s*-\s*([A-Z]{2})",
            text,
        ))
        if not matches:
            return None
        m = matches[-1]
        return f"{m.group(1)} - {m.group(2)}"

    def _extract_date(self, text: str) -> str | None:
        m = re.search(r"(Hoje|Ontem|\d{2}/\d{2}(?:/\d{4})?),?\s*(\d{2}:\d{2})?", text)
        return m.group(0).strip() if m else None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _try_selectors(self, element: Any, selectors: list[str]) -> str:
        for sel in selectors:
            try:
                el = element.find_element(By.CSS_SELECTOR, sel)
                t = el.text.strip()
                if t and len(t) > 3:
                    return t
            except Exception:
                continue
        return ""

    def _try_attr(self, element: Any, selectors: list[str], attr: str) -> str:
        for sel in selectors:
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

    def _save_debug(self, driver: Any, label: str, save_items: bool = False) -> None:
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
        if save_items:
            try:
                items_dir = log_dir / f"olx_items_{ts}"
                items_dir.mkdir(exist_ok=True)
                for sel in _CONTAINER_SELECTORS:
                    items = driver.find_elements(By.CSS_SELECTOR, sel)
                    if items:
                        for i, item in enumerate(items[:5]):
                            try:
                                outer = item.get_attribute("outerHTML") or item.text
                                (items_dir / f"item_{i}.html").write_text(outer or "", encoding="utf-8")
                            except Exception:
                                pass
                        break
                logger.info("Debug items saved → %s/", items_dir)
            except Exception as exc:
                logger.warning("Debug items save failed: %s", exc)
