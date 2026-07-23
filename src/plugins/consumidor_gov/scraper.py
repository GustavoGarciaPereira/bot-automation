"""Consumidor.gov.br scraper — Selenium-based.

Government site, server-rendered HTML, no CloudFlare blocking.
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
from src.plugins.consumidor_gov.models import Complaint, CompanyStats
from src.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_CONFIG = {
    "plugin_name": "consumidor_gov",
    "base_url": "https://www.consumidor.gov.br",
    "headless": True,
    "timeout_seconds": 30,
    "max_pages_default": 3,
    "random_delay_min": 2,
    "random_delay_max": 4,
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


_CONTAINER_SELECTORS = [
    "table tbody tr",
    "div[class*='reclamacao']",
    "div[class*='card']",
    "ul li[class*='complaint']",
    "tr[class*='complaint']",
]

_TITLE_SELECTORS = [
    "a[class*='titulo']",
    "td[class*='titulo']",
    "a",
    "td:first-child a",
    "h3 a",
    "h4 a",
]

_DATE_SELECTORS = [
    "time[datetime]",
    "td[class*='data']",
    "span[class*='data']",
    "td:nth-child(2)",
    "span.date",
]

_STATUS_SELECTORS = [
    "td[class*='status']",
    "span[class*='status']",
    "td:nth-child(3)",
    "span.badge",
]

_NEXT_PAGE_SELECTORS = [
    "a[class*='next']",
    "a[aria-label*='pr\u00f3xima']",
    "a[aria-label*='next']",
    "li.next a",
    "a[rel='next']",
]

_STATS_SELECTORS = {
    "total_complaints": ["span[class*='total']", "div[class*='count']", "h2[class*='total']"],
    "response_rate": ["span[class*='resposta']", "div[class*='percentual']"],
    "resolution_rate": ["span[class*='resolucao']", "div[class*='resolvidas']"],
    "avg_response_time": ["span[class*='tempo']", "div[class*='prazo']"],
}


class ConsumidorGovScraper(BaseScraper):
    """Scraper for Consumidor.gov.br complaint listings."""

    def __init__(self, headless: bool = True, remote_url: str | None = None) -> None:
        self._cfg = _load_config()
        self._headless = headless
        self._remote_url = remote_url

    async def search(
        self, company_name: str, max_pages: int | None = None, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Search for a company and scrape its complaints."""
        max_pages = max_pages or self._cfg.get("max_pages_default", 3)

        logger.info("CG: searching for company %s (max %d pages)", company_name, max_pages)
        all_complaints: list[Complaint] = []
        driver = None

        try:
            async with selenium_driver(
                headless=self._headless,
                remote_url=self._remote_url,
            ) as driver:
                # Go to search page
                search_url = f"{self._cfg['base_url']}/pages/empresas/buscar"
                driver.get(search_url)
                self._random_delay()

                # Type company name in search input
                try:
                    search_input = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, "input[type='text'], input[name='q'], input[placeholder*='busca']")
                        )
                    )
                    search_input.clear()
                    search_input.send_keys(company_name)
                    self._random_delay()

                    # Click search button
                    try:
                        btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit'], a[class*='buscar']")
                        btn.click()
                    except Exception:
                        search_input.submit()

                    self._random_delay()
                except Exception as exc:
                    logger.warning("CG: search input not found: %s", exc)

                # Wait for results
                if not self._wait_for_results(driver):
                    self._save_debug(driver, company_name)
                    logger.warning("CG: no results found for %s", company_name)
                    return []

                # Get stats
                stats = self._get_company_stats(driver)

                # Extract complaints across pages
                for page in range(1, max_pages + 1):
                    cards = driver.find_elements(By.CSS_SELECTOR, ", ".join(_CONTAINER_SELECTORS))
                    logger.info("CG page %d: %d items", page, len(cards))

                    for card in cards:
                        c = self._parse_card(card, company_name)
                        if c:
                            all_complaints.append(c)

                    if page < max_pages:
                        if not self._go_next_page(driver):
                            break
                        self._random_delay()

                logger.info("CG: %d complaints for %s", len(all_complaints), company_name)
                return [c.model_dump() for c in all_complaints]

        except Exception as exc:
            logger.error("CG scraping failed: %s", exc)
            if driver:
                self._save_debug(driver, company_name)
            return []

    async def extract(self, complaint_url: str, **kwargs: Any) -> dict[str, Any]:
        logger.info("CG extract: %s", complaint_url)
        driver = None
        try:
            async with selenium_driver(
                headless=self._headless,
                remote_url=self._remote_url,
            ) as driver:
                driver.get(complaint_url)
                self._random_delay()
                return Complaint(
                    company_name=kwargs.get("company", ""),
                    complaint_url=complaint_url,
                ).model_dump()
        except Exception as exc:
            logger.error("CG extract failed: %s", exc)
            return {}

    def _wait_for_results(self, driver: Any) -> bool:
        timeout = self._cfg.get("timeout_seconds", 30)
        for selector in _CONTAINER_SELECTORS + [
            "table", "div[class*='result']", "div[class*='listagem']"
        ]:
            try:
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                return True
            except TimeoutException:
                continue
        return False

    def _parse_card(self, card: Any, company_name: str) -> Complaint | None:
        title = self._text(card, _TITLE_SELECTORS)
        date = self._text(card, _DATE_SELECTORS)
        status = self._text(card, _STATUS_SELECTORS)
        url = self._card_url(card)
        return Complaint(
            company_name=company_name,
            title=title or None,
            date=date or None,
            status=status or None,
            complaint_url=url,
        )

    def _card_url(self, card: Any) -> str:
        for sel in ["a", "a[href]"]:
            try:
                el = card.find_element(By.CSS_SELECTOR, sel)
                href = el.get_attribute("href") or ""
                if href and not href.startswith("#"):
                    return href
            except Exception:
                continue
        return ""

    def _go_next_page(self, driver: Any) -> bool:
        for sel in _NEXT_PAGE_SELECTORS:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                href = el.get_attribute("href")
                if href:
                    driver.get(href)
                    return True
                el.click()
                return True
            except Exception:
                continue
        return False

    def _get_company_stats(self, driver: Any) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        for key, selectors in _STATS_SELECTORS.items():
            for sel in selectors:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    text = el.text.strip()
                    nums = re.findall(r"[\d.,]+", text)
                    if nums:
                        stats[key] = float(nums[0].replace(",", "."))
                    break
                except Exception:
                    continue
        return stats

    def _text(self, element: Any, selectors: list[str]) -> str:
        for sel in selectors:
            try:
                found = element.find_element(By.CSS_SELECTOR, sel)
                text = found.text.strip()
                if text:
                    return text
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
            driver.save_screenshot(str(log_dir / f"cg_debug_{ts}.png"))
        except Exception:
            pass
        try:
            (log_dir / f"cg_debug_{ts}.html").write_text(driver.page_source, encoding="utf-8")
        except Exception:
            pass
