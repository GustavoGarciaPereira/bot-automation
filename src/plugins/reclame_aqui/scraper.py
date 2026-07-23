"""Reclame Aqui scraper — uses Selenium (JS-rendered SPA).

Reclame Aqui is a JavaScript-rendered SPA behind CloudFlare.
HTTP/requests cannot extract complaint data — only Selenium
can execute the JS and render the actual content.
"""

from __future__ import annotations

import json
import random
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.interfaces.scraper import BaseScraper
from src.plugins.base_selenium_plugin import selenium_driver
from src.plugins.reclame_aqui.models import Complaint, CompanyReport
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "plugin_name": "reclame_aqui",
    "base_url": "https://www.reclameaqui.com.br",
    "headless": True,
    "timeout_seconds": 30,
    "max_pages_default": 3,
    "random_delay_min": 3,
    "random_delay_max": 7,
    "max_scrolls": 5,
    "scroll_pause": 2,
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
# Slugify
# ---------------------------------------------------------------------------


def slugify(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"[\s]+", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


# ---------------------------------------------------------------------------
# CSS selectors with fallbacks
# ---------------------------------------------------------------------------

_MODAL_SELECTORS = [
    "button:has-text('Aceitar')",
    "button:has-text('Entendi')",
    "button[class*='cookie']",
    "button[class*='accept']",
    "button[aria-label='Fechar']",
    "div[class*='modal'] button",
    "#onetrust-accept-btn-handler",
]

_CONTAINER_SELECTORS = [
    "div[class*='complaint']",
    "div[class*='reclamacao']",
    "a[href*='/reclamacao/']",
    "div[class*='card']",
    "div[class*='list']",
]

_CARD_SELECTORS = [
    "div[class*='complaint-card']",
    "div[data-testid*='complaint']",
    "article[class*='complaint']",
    "div[class*='card-reclamacao']",
    "div[class*='reclamacao']",
    "div[class*='card']",
]

_TITLE_SELECTORS = [
    "a[href*='/reclamacao/']",
    "h2[class*='title'] a",
    "a[class*='title']",
    "h2 a",
    "h2",
]

_DATE_SELECTORS = [
    "time[datetime]",
    "span[class*='date']",
    "span[class*='data']",
]

_STATUS_SELECTORS = [
    "span[class*='status']",
    "span[class*='badge']",
    "div[class*='status']",
]

_TEXT_SELECTORS = [
    "p[class*='text']",
    "div[class*='description']",
    "p",
]

_NEXT_PAGE = [
    "a[class*='next']",
    "button[class*='next']",
    "a[aria-label*='Pr\u00f3xima']",
    "button:has-text('Carregar mais')",
    "a[class*='pagination']",
]


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class ReclameAquiScraper(BaseScraper):
    """Scraper for Reclame Aqui using Selenium (JS-rendered SPA)."""

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
        self, company_slug: str, max_pages: int | None = None, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Search complaints for a company via Selenium."""

        if " " in company_slug or not re.match(r"^[a-z0-9-]+$", company_slug):
            company_slug = slugify(company_slug)
            logger.warning(
                "RA: slug auto-generated to '%s'. "
                "Each RA company has a specific slug. "
                "If this fails, verify the correct slug at reclameaqui.com.br",
                company_slug,
            )

        max_pages = max_pages or self._cfg.get("max_pages_default", 3)
        company_url = f"{self._cfg['base_url']}/empresa/{company_slug}/reclamacoes"

        logger.info("RA Selenium: opening %s (max %d pages)", company_url, max_pages)

        all_complaints: list[Complaint] = []
        driver = None
        no_title = 0
        dup = 0

        # URLs to try (some companies use different slug patterns)
        urls_to_try = [
            company_url,
            f"{self._cfg['base_url']}/empresa/{company_slug}/",
            f"{self._cfg['base_url']}/{company_slug}/",
        ]

        try:
            async with selenium_driver(
                headless=self._headless,
                remote_url=self._remote_url,
            ) as driver:
                page_loaded = False
                for try_url in urls_to_try:
                    logger.info("RA: trying URL %s", try_url)
                    driver.get(try_url)
                    self._random_delay()
                    self._close_modals(driver)
                    if self._wait_for_content(driver):
                        page_loaded = True
                        break
                    logger.warning("RA: no content at %s — trying next URL", try_url)

                if not page_loaded:
                    self._save_debug(driver, company_slug)
                    logger.warning("RA: no content found at any URL for %s", company_slug)
                    return []

                # Scroll to trigger lazy loading
                self._scroll_page(driver)

                for page in range(1, max_pages + 1):
                    logger.info("RA: scraping page %d", page)

                    cards = self._find_cards(driver)
                    logger.info("RA page %d: %d cards", page, len(cards))

                    for card in cards:
                        c = self._parse_card(card, company_slug)
                        if c is None:
                            no_title += 1
                            continue
                        key = c.title.lower().strip()
                        if any(x.title.lower().strip() == key for x in all_complaints):
                            dup += 1
                            continue
                        all_complaints.append(c)

                    if page < max_pages:
                        if not self._go_next_page(driver):
                            logger.info("RA: no next page after %d", page)
                            break
                        self._random_delay()

                logger.info(
                    "RA: %d complaints | No title: %d | Dup: %d | %s",
                    len(all_complaints), no_title, dup, company_slug,
                )
                return [c.model_dump() for c in all_complaints]

        except Exception as exc:
            logger.error("RA scraping failed: %s", exc)
            if driver:
                self._save_debug(driver, company_slug)
            return []

    async def extract(self, complaint_url: str, **kwargs: Any) -> dict[str, Any]:
        """Extract full complaint details from a single page."""
        logger.info("RA extract: %s", complaint_url)

        driver = None
        try:
            async with selenium_driver(
                headless=self._headless,
                remote_url=self._remote_url,
            ) as driver:
                driver.get(complaint_url)
                self._random_delay()
                self._close_modals(driver)

                title = (
                    self._text(driver, "h1[class*='title'], h1.complaint-title")
                    or self._text(driver, "h1")
                )
                text = self._multi_text(driver, [
                    "div.complaint-text",
                    "div[class*='complaint-body']",
                    "div[class*='description']",
                    "div[class*='content']",
                    "div[class*='text']",
                ])
                response = self._multi_text(driver, [
                    "div.company-response",
                    "div[class*='response']",
                    "div[class*='resposta']",
                    "div[class*='answer']",
                ])
                rating = self._parse_rating(driver)
                category = self._multi_text(driver, [
                    "span[class*='category']",
                    "a[class*='category']",
                ])
                date = self._date_from_driver(driver)
                status = self._multi_text(driver, _STATUS_SELECTORS)

                return Complaint(
                    title=title or "Unknown",
                    text=text or None,
                    date=date or None,
                    status=status or None,
                    company_response=response or None,
                    rating=rating,
                    category=category or None,
                    complaint_url=complaint_url,
                ).model_dump()

        except Exception as exc:
            logger.error("RA extract failed: %s", exc)
            if driver:
                self._save_debug(driver, complaint_url)
            return {}

    # ------------------------------------------------------------------
    # Internal — navigation
    # ------------------------------------------------------------------

    def _close_modals(self, driver: Any) -> None:
        """Close cookie/modals popups."""
        for sel in [
            "button[class*='cookie']",
            "#onetrust-accept-btn-handler",
            "button[class*='accept']",
            "button[aria-label='Fechar']",
            "div[class*='modal'] button",
        ]:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                btn.click()
                logger.debug("RA modal closed: %s", sel)
                time.sleep(1)
            except Exception:
                continue

    def _wait_for_content(self, driver: Any) -> bool:
        timeout = self._cfg.get("timeout_seconds", 30)
        for selector in _CONTAINER_SELECTORS:
            try:
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                logger.debug("RA content found: %s", selector)
                return True
            except TimeoutException:
                continue
        return False

    def _find_cards(self, driver: Any) -> list[Any]:
        for selector in _CARD_SELECTORS:
            items = driver.find_elements(By.CSS_SELECTOR, selector)
            if items:
                return items
        return []

    def _scroll_page(self, driver: Any) -> None:
        """Scroll down to trigger lazy loading."""
        max_scrolls = self._cfg.get("max_scrolls", 5)
        pause = self._cfg.get("scroll_pause", 2)
        for i in range(max_scrolls):
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(pause)
            except Exception:
                break

    def _go_next_page(self, driver: Any) -> bool:
        for selector in _NEXT_PAGE:
            try:
                el = driver.find_element(By.CSS_SELECTOR, selector)
                href = el.get_attribute("href")
                if href:
                    driver.get(href)
                    self._random_delay()
                    self._close_modals(driver)
                    return True
                el.click()
                self._random_delay()
                self._close_modals(driver)
                return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------
    # Internal — parsing
    # ------------------------------------------------------------------

    def _parse_card(self, card: Any, company_slug: str) -> Complaint | None:
        title = self._multi_text(card, _TITLE_SELECTORS)
        if not title:
            return None
        text = self._multi_text(card, _TEXT_SELECTORS)
        date = self._date_from_driver(card)
        status = self._multi_text(card, _STATUS_SELECTORS)
        url = self._card_url(card)
        rating = self._parse_rating(card)
        return Complaint(
            title=title, text=text or None, date=date or None,
            status=status or None, rating=rating, complaint_url=url,
        )

    def _card_url(self, card: Any) -> str:
        for selector in ["a[href*='/reclamacao/']", "a[class*='title']", "a"]:
            try:
                el = card.find_element(By.CSS_SELECTOR, selector)
                href = el.get_attribute("href") or ""
                if href:
                    if href.startswith("/"):
                        href = f"{self._cfg['base_url']}{href}"
                    return href
            except Exception:
                continue
        return ""

    def _parse_rating(self, element: Any) -> float | None:
        for sel in [
            "span[class*='rating']", "div[class*='score']",
            "span[class*='nota']", "span[class*='grade']",
        ]:
            try:
                el = element.find_element(By.CSS_SELECTOR, sel)
                text = el.text.strip().replace(",", ".")
                nums = re.findall(r"[\d.]+", text)
                for n in nums:
                    val = float(n)
                    if 0 <= val <= 10:
                        return val
            except Exception:
                continue
        return None

    def _date_from_driver(self, element: Any) -> str | None:
        try:
            el = element.find_element(By.CSS_SELECTOR, "time[datetime]")
            dt = el.get_attribute("datetime")
            if dt:
                return dt[:10]
        except Exception:
            pass
        return self._multi_text(element, _DATE_SELECTORS) or None

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    def _multi_text(self, element: Any, selectors: list[str]) -> str:
        for sel in selectors:
            try:
                found = element.find_element(By.CSS_SELECTOR, sel)
                text = found.text.strip()
                if text:
                    return text
            except Exception:
                continue
        return ""

    def _text(self, element: Any, selector: str) -> str:
        try:
            found = element.find_element(By.CSS_SELECTOR, selector)
            return found.text.strip()
        except Exception:
            return ""

    def _random_delay(self) -> None:
        time.sleep(random.uniform(
            self._cfg.get("random_delay_min", 3),
            self._cfg.get("random_delay_max", 7),
        ))

    def _save_debug(self, driver: Any, label: str) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = Path("data/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            driver.save_screenshot(str(log_dir / f"ra_debug_{ts}.png"))
        except Exception:
            pass
        try:
            (log_dir / f"ra_debug_{ts}.html").write_text(
                driver.page_source, encoding="utf-8"
            )
        except Exception:
            pass
