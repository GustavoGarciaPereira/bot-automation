"""Reclame Aqui scraper — uses Selenium to scrape complaint listings.

Navigates to ``reclameaqui.com.br/empresa/{slug}/`` and extracts
complaint data with pagination, company stats, and modal handling.
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
    """Convert company name to URL slug.

    ``'Magazine Luiza'`` → ``'magazine-luiza'``
    ``'João & Maria Ltda'`` → ``'joao-maria-ltda'``
    """
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

_PAGE_CONTAINER_SELECTORS = [
    "div.complaints-list",
    "div[class*='complaint']",
    "div[data-testid*='complaint']",
    "div.listing-complaints",
    "div[class*='reclamacoes']",
    "section[class*='complaint']",
]

_CARD_SELECTORS = [
    "div.complaint-card",
    "div[class*='complaint-card']",
    "div[data-testid='complaint-card']",
    "article[class*='complaint']",
    "div[class*='card-reclamacoes']",
    "div[class*='reclamacao']",
]

_TITLE_SELECTORS = [
    "h2.complaint-card__title",
    "a.complaint-card__title",
    "h2[class*='title']",
    "a[href*='/reclamacao/']",
    "h2 a",
    "a[class*='title']",
]

_DATE_SELECTORS = [
    "span.complaint-card__date",
    "time[datetime]",
    "span[class*='date']",
    "span[class*='data']",
    "small",
]

_STATUS_SELECTORS = [
    "span.complaint-card__status",
    "span[class*='status']",
    "span[class*='badge']",
    "div[class*='status']",
    "span[class*='tag']",
]

_URL_SELECTORS = [
    "a.complaint-card__title",
    "a[href*='/reclamacao/']",
    "a[class*='title']",
]

_TEXT_SELECTORS = [
    "p.complaint-card__text",
    "div[class*='description']",
    "p[class*='text']",
    "div[class*='body']",
    "p",
]

_NEXT_PAGE_SELECTORS = [
    "a[class*='next']",
    "button[class*='load-more']",
    "a[aria-label='Próxima p\u00e1gina']",
    "li.next a",
    "button[class*='pagination']",
    "a[class*='pagination-next']",
    "a[class*='next']",
    "button:has-text('Carregar mais')",
    "a:has-text('Pr\u00f3ximo')",
]

_MODAL_CLOSE_SELECTORS = [
    "button[class*='cookie']",
    "#onetrust-accept-btn-handler",
    "button:has-text('Aceitar')",
    "button:has-text('Entendi')",
    "button[aria-label='Fechar']",
    "div[class*='modal'] button[class*='close']",
    ".cookie-notice button",
    "[class*='cookie-bar'] button",
]

_STATS_SELECTORS: dict[str, list[str]] = {
    "total_complaints": [
        "span[class*='total']",
        "div[class*='count']",
        "span[class*='reclamacoes']",
    ],
    "response_rate": [
        "span[class*='response-rate']",
        "div[class*='resposta']",
        "span[class*='respondidas']",
    ],
    "avg_rating": [
        "span[class*='average-rating']",
        "div[class*='nota-media']",
        "span[class*='nota']",
        "div[class*='score']",
    ],
}


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class ReclameAquiScraper(BaseScraper):
    """Scraper for Reclame Aqui complaint listings using Selenium."""

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
        """Search complaints for a company by slug.

        Returns flat list of complaint dicts.
        """
        # Slugify if needed
        if " " in company_slug or not re.match(r"^[a-z0-9-]+$", company_slug):
            company_slug = slugify(company_slug)

        company_page = f"{self._cfg['base_url']}/empresa/{company_slug}/"
        max_pages = max_pages or self._cfg.get("max_pages_default", 3)

        logger.info("RA scraping: %s (max %d pages)", company_page, max_pages)

        all_complaints: list[Complaint] = []
        driver = None
        no_title_count = 0
        dup_count = 0
        pages_scraped = 0

        try:
            async with selenium_driver(
                headless=self._headless,
                remote_url=self._remote_url,
            ) as driver:
                driver.get(company_page)
                self._random_delay()

                # Close modals
                self._close_modals(driver)

                # Wait for content
                if not self._wait_for_content(driver):
                    self._save_debug(driver, company_slug)
                    logger.warning("RA: no content found for %s", company_slug)
                    return []

                # Extract company stats
                stats = self._get_company_stats(driver)

                # Pagination loop
                while pages_scraped < max_pages:
                    pages_scraped += 1

                    cards = self._find_cards(driver)
                    logger.info("RA page %d: %d cards", pages_scraped, len(cards))

                    for card in cards:
                        complaint = self._parse_card(card, company_slug)
                        if complaint is None:
                            no_title_count += 1
                            continue
                        # Dedup by title
                        key = complaint.title.lower().strip()
                        if any(c.title.lower().strip() == key for c in all_complaints):
                            dup_count += 1
                            continue
                        all_complaints.append(complaint)

                    if not self._go_next_page(driver, pages_scraped):
                        break

                logger.info(
                    "RA: %d complaints | No title: %d | Dup: %d | Pages: %d | %s",
                    len(all_complaints), no_title_count, dup_count,
                    pages_scraped, company_slug,
                )
                return [c.model_dump() for c in all_complaints]

        except Exception as exc:
            logger.error("RA scraping failed for %s: %s", company_slug, exc)
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
                    self._single_text(driver, "h1[class*='title'], h1.complaint-title")
                    or self._single_text(driver, "h1")
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
                date = self._date_from_element(driver)
                status = self._multi_text(driver, [
                    "span[class*='status']",
                    "div[class*='status']",
                ])

                return Complaint(
                    title=title or "Unknown",
                    text=text,
                    date=date,
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
    # Internal — navigation helpers
    # ------------------------------------------------------------------

    def _close_modals(self, driver: Any) -> None:
        """Close cookie/modals popups (critical for RA)."""
        for selector in _MODAL_CLOSE_SELECTORS:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, selector)
                btn.click()
                logger.debug("RA modal closed: %s", selector)
                time.sleep(1)
            except Exception:
                continue

    def _wait_for_content(self, driver: Any) -> bool:
        timeout = self._cfg.get("timeout_seconds", 30)
        for selector in _PAGE_CONTAINER_SELECTORS + _CARD_SELECTORS:
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

    def _go_next_page(self, driver: Any, current_page: int) -> bool:
        """Navigate to next page. Returns False when no more pages."""
        for selector in _NEXT_PAGE_SELECTORS:
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
        """Parse a single complaint card element."""
        title = self._multi_text(card, _TITLE_SELECTORS)
        if not title:
            return None

        text = self._multi_text(card, _TEXT_SELECTORS)
        date = self._date_from_element(card)
        status = self._multi_text(card, _STATUS_SELECTORS)
        url = self._card_url(card)
        rating = self._parse_rating(card)

        return Complaint(
            title=title,
            text=text,
            date=date or None,
            status=status or None,
            rating=rating,
            complaint_url=url,
        )

    def _card_url(self, card: Any) -> str:
        for selector in _URL_SELECTORS:
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

    def _get_company_stats(self, driver: Any) -> dict[str, Any]:
        """Extract company-level statistics from the page."""
        stats: dict[str, Any] = {}
        for key, selectors in _STATS_SELECTORS.items():
            for sel in selectors:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                    text = el.text.strip()
                    nums = re.findall(r"[\d.,]+", text)
                    if nums:
                        raw = nums[0].replace(".", "").replace(",", ".")
                        stats[key] = float(raw)
                    break
                except Exception:
                    continue
        return stats

    def _parse_rating(self, element: Any) -> float | None:
        """Extract rating from the element."""
        for sel in [
            "span[class*='rating']",
            "div[class*='score']",
            "span[class*='nota']",
            "span[class*='grade']",
            "div[class*='nota']",
            "span[class*='star']",
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

    def _date_from_element(self, element: Any) -> str | None:
        """Extract date from element, preferring datetime attribute."""
        # Try <time datetime="...">
        try:
            el = element.find_element(By.CSS_SELECTOR, "time[datetime]")
            dt = el.get_attribute("datetime")
            if dt:
                return dt[:10]  # YYYY-MM-DD
        except Exception:
            pass
        # Fallback: text selectors
        text = self._multi_text(element, _DATE_SELECTORS)
        return text or None

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    def _multi_text(self, element: Any, selectors: list[str]) -> str:
        """Try each selector, return first non-empty text."""
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
            shot = log_dir / f"ra_debug_{ts}.png"
            driver.save_screenshot(str(shot))
            logger.info("Debug screenshot → %s", shot)
        except Exception:
            pass
        try:
            html_path = log_dir / f"ra_debug_{ts}.html"
            html_path.write_text(driver.page_source, encoding="utf-8")
            logger.info("Debug HTML → %s", html_path)
        except Exception:
            pass
