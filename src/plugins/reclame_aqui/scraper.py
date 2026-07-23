"""Reclame Aqui scraper — uses cloudscraper to bypass CloudFlare protection.

Reclame Aqui uses CloudFlare challenge pages, making Selenium-based
scraping unreliable (browser crashes).  This scraper uses ``cloudscraper``
to bypass CF and parses the server-rendered HTML with BeautifulSoup.
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

from bs4 import BeautifulSoup

from src.interfaces.scraper import BaseScraper
from src.plugins.reclame_aqui.models import Complaint, CompanyReport
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default config
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "plugin_name": "reclame_aqui",
    "base_url": "https://www.reclameaqui.com.br",
    "timeout_seconds": 30,
    "max_pages_default": 3,
    "request_delay_min": 2,
    "request_delay_max": 4,
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
    """Convert company name to URL slug."""
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"[\s]+", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


# ---------------------------------------------------------------------------
# CSS selectors for page parsing
# ---------------------------------------------------------------------------

_CARD_SELECTORS = [
    "div.complaint-card",
    "div[class*='complaint-card']",
    "div[class*='card-reclamacoes']",
    "div[class*='reclamacao']",
]

_TITLE_SELECTORS = [
    "h2.complaint-card__title a",
    "h2[class*='title'] a",
    "a[href*='/reclamacao/']",
    "h2.complaint-card__title",
    "h2 a",
    "a[class*='title']",
]

_DATE_SELECTORS = [
    "span.complaint-card__date",
    "time[datetime]",
    "span[class*='date']",
    "span[class*='data']",
]

_STATUS_SELECTORS = [
    "span.complaint-card__status",
    "span[class*='status']",
    "span[class*='badge']",
    "div[class*='status']",
]

_TEXT_SELECTORS = [
    "p.complaint-card__text",
    "div[class*='description']",
    "p[class*='text']",
]

_PAGINATION_SELECTORS = [
    "a[class*='next']",
    "a[aria-label*='próxima']",
    "a[aria-label*='next']",
    "a[rel='next']",
    "a[class*='pagination-next']",
]


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class ReclameAquiScraper(BaseScraper):
    """Scraper for Reclame Aqui complaint listings using cloudscraper."""

    def __init__(
        self,
        headless: bool = True,  # kept for interface compatibility, unused
        remote_url: str | None = None,
    ) -> None:
        self._cfg = _load_config()
        self._session = self._build_session()
        self._last_request: float = 0

    def _build_session(self) -> Any:
        """Create a cloudscraper session that bypasses CloudFlare."""
        import cloudscraper
        sess = cloudscraper.create_scraper(
            browser={
                "browser": "chrome",
                "platform": "windows",
                "desktop": True,
                "mobile": False,
            },
        )
        sess.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        return sess

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self, company_slug: str, max_pages: int | None = None, **kwargs: Any
    ) -> list[dict[str, Any]]:
        """Search complaints for a company by slug."""
        import asyncio

        if " " in company_slug or not re.match(r"^[a-z0-9-]+$", company_slug):
            company_slug = slugify(company_slug)

        max_pages = max_pages or self._cfg.get("max_pages_default", 3)

        all_complaints: list[Complaint] = []
        no_title_count = 0
        dup_count = 0

        for page in range(1, max_pages + 1):
            logger.info("RA: fetching page %d for %s", page, company_slug)
            if page == 1:
                url = f"{self._cfg['base_url']}/empresa/{company_slug}/reclamacoes"
            else:
                url = f"{self._cfg['base_url']}/empresa/{company_slug}/reclamacoes?pagina={page}"

            html = await asyncio.get_running_loop().run_in_executor(
                None, self._fetch_page, url
            )
            if not html:
                logger.warning("RA: page %d returned empty — stopping", page)
                break

            soup = BeautifulSoup(html, "html.parser")
            cards = self._find_cards(soup)
            logger.info("RA page %d: %d cards found", page, len(cards))

            if not cards:
                logger.warning(
                    "RA: no complaint cards found on page %d. "
                    "Reclame Aqui is a JavaScript-rendered SPA. "
                    "Data may not be available via HTTP scraping.",
                    page,
                )

            for card in cards:
                c = self._parse_card(card, company_slug)
                if c is None:
                    no_title_count += 1
                    continue
                key = c.title.lower().strip()
                if any(x.title.lower().strip() == key for x in all_complaints):
                    dup_count += 1
                    continue
                all_complaints.append(c)

            # Check if next page exists
            if not self._has_next_page(soup):
                logger.info("RA: no next page after %d", page)
                break

            # Rate limiting
            await asyncio.get_running_loop().run_in_executor(None, self._rate_limit)

        logger.info(
            "RA: %d complaints | No title: %d | Dup: %d | %s",
            len(all_complaints), no_title_count, dup_count, company_slug,
        )
        return [c.model_dump() for c in all_complaints]

    async def extract(self, complaint_url: str, **kwargs: Any) -> dict[str, Any]:
        """Extract full complaint details from a single page."""
        import asyncio

        logger.info("RA extract: %s", complaint_url)

        html = await asyncio.get_running_loop().run_in_executor(
            None, self._fetch_page, complaint_url
        )
        if not html:
            return {}

        soup = BeautifulSoup(html, "html.parser")

        title = (
            self._text(soup, "h1[class*='title'], h1.complaint-title")
            or self._text(soup, "h1")
        )
        text = self._multi_text(soup, [
            "div.complaint-text",
            "div[class*='complaint-body']",
            "div[class*='description']",
            "div[class*='content']",
            "div[class*='text']",
        ])
        response = self._multi_text(soup, [
            "div.company-response",
            "div[class*='response']",
            "div[class*='resposta']",
            "div[class*='answer']",
        ])
        rating = self._parse_rating(soup)
        category = self._multi_text(soup, [
            "span[class*='category']",
            "a[class*='category']",
        ])
        date = self._date_from_soup(soup)
        status = self._multi_text(soup, [
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

    # ------------------------------------------------------------------
    # Internal — HTTP
    # ------------------------------------------------------------------

    def _fetch_page(self, url: str) -> str | None:
        """Fetch page HTML via cloudscraper."""
        try:
            resp = self._session.get(
                url,
                timeout=self._cfg.get("timeout_seconds", 30),
            )
            if resp.status_code != 200:
                logger.warning(
                    "RA HTTP %d for %s. "
                    "Reclame Aqui is a JS-rendered SPA behind CloudFlare. "
                    "Try accessing the URL in a browser to verify it exists.",
                    resp.status_code, url,
                )
                return None
            return resp.text
        except Exception as exc:
            logger.error("RA fetch failed for %s: %s", url, exc)
            return None

    def _rate_limit(self) -> None:
        """Ensure delay between requests."""
        elapsed = time.time() - self._last_request
        min_interval = random.uniform(
            self._cfg.get("request_delay_min", 2),
            self._cfg.get("request_delay_max", 4),
        )
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request = time.time()

    # ------------------------------------------------------------------
    # Internal — parsing
    # ------------------------------------------------------------------

    def _find_cards(self, soup: BeautifulSoup) -> list[Any]:
        for selector in _CARD_SELECTORS:
            cards = soup.select(selector)
            if cards:
                return cards
        return []

    def _parse_card(self, card: Any, company_slug: str) -> Complaint | None:
        title = self._multi_text(card, _TITLE_SELECTORS)
        if not title:
            return None

        text = self._multi_text(card, _TEXT_SELECTORS)
        date = self._date_from_soup(card)
        status = self._multi_text(card, _STATUS_SELECTORS)
        url = self._card_url(card)
        rating = self._parse_rating(card)

        return Complaint(
            title=title,
            text=text or None,
            date=date or None,
            status=status or None,
            rating=rating,
            complaint_url=url,
        )

    def _card_url(self, card: Any) -> str:
        for selector in [
            "a[href*='/reclamacao/']",
            "h2 a",
            "a[class*='title']",
            "a",
        ]:
            tag = card.select_one(selector)
            if tag and tag.get("href"):
                href = tag["href"]
                if href.startswith("/"):
                    href = f"{self._cfg['base_url']}{href}"
                return href
        return ""

    def _has_next_page(self, soup: BeautifulSoup) -> bool:
        for selector in _PAGINATION_SELECTORS:
            if soup.select_one(selector):
                return True
        return False

    def _parse_rating(self, element: Any) -> float | None:
        for sel in [
            "span[class*='rating']",
            "div[class*='score']",
            "span[class*='nota']",
            "span[class*='grade']",
            "div[class*='nota']",
        ]:
            tag = element.select_one(sel)
            if tag:
                text = tag.text.strip().replace(",", ".")
                nums = re.findall(r"[\d.]+", text)
                for n in nums:
                    try:
                        val = float(n)
                        if 0 <= val <= 10:
                            return val
                    except ValueError:
                        continue
        return None

    def _date_from_soup(self, element: Any) -> str | None:
        time_tag = element.select_one("time[datetime]")
        if time_tag and time_tag.get("datetime"):
            return str(time_tag["datetime"])[:10]
        text = self._multi_text(element, _DATE_SELECTORS)
        return text or None

    # ------------------------------------------------------------------
    # Internal — helpers
    # ------------------------------------------------------------------

    def _multi_text(self, element: Any, selectors: list[str]) -> str:
        for sel in selectors:
            tag = element.select_one(sel)
            if tag:
                text = tag.text.strip()
                if text:
                    return text
        return ""

    def _text(self, element: Any, selector: str) -> str:
        tag = element.select_one(selector)
        if tag:
            return tag.text.strip()
        return ""
