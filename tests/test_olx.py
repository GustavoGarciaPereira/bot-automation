"""Tests for OLX Brasil plugin."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from src.plugins.olx.models import OLXAd, OLXSearch
from src.plugins.olx.scraper import OLXScraper, _clear_config_cache


def _make_item(html: str) -> MagicMock:
    item = MagicMock()
    soup = BeautifulSoup(html, "html.parser")

    def _find(by: str, selector: str) -> MagicMock:
        tag = soup.select_one(selector)
        if tag is None:
            raise Exception(f"Not found: {selector}")
        m = MagicMock()
        m.text = tag.text.strip()
        attrs = {}
        for a in ("href", "src"):
            v = tag.get(a)
            if v:
                attrs[a] = v
        if attrs:
            m.get_attribute.side_effect = lambda k: attrs.get(k, "")
        else:
            m.get_attribute.return_value = ""
        return m

    item.find_element.side_effect = _find
    item.find_elements.return_value = []
    item.text = soup.get_text("\n", strip=True)
    return item


HTML_CARD = '<div data-testid="ad-card"><h2><a href="/anuncio/123">Notebook Dell</a></h2><span class="price">R$ 1.200</span><span class="location">Campinas, SP</span><span class="date">Hoje</span></div>'


@pytest.fixture(autouse=True)
def _clear():
    _clear_config_cache()
    yield


@pytest.fixture
def scraper() -> OLXScraper:
    return OLXScraper(headless=True)


class TestSearch:
    @patch("src.plugins.olx.scraper.selenium_driver")
    @patch("src.plugins.olx.scraper.WebDriverWait")
    @patch("src.plugins.olx.scraper.time.sleep")
    async def test_parses_ads(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: OLXScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        items = [_make_item(HTML_CARD.replace("Notebook Dell", f"Ad {i}")) for i in range(3)]
        mock_driver.find_elements.return_value = items

        with patch.object(scraper, "_wait_for_results", return_value=True):
            results = await scraper.search("notebook", max_results=10)

        assert len(results) == 3

    @patch("src.plugins.olx.scraper.selenium_driver")
    @patch("src.plugins.olx.scraper.WebDriverWait")
    @patch("src.plugins.olx.scraper.time.sleep")
    async def test_empty(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: OLXScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_driver.find_elements.return_value = []
        with patch.object(scraper, "_wait_for_results", return_value=True):
            results = await scraper.search("x", max_results=10)
        assert results == []

    @patch("src.plugins.olx.scraper.selenium_driver")
    @patch("src.plugins.olx.scraper.WebDriverWait")
    @patch("src.plugins.olx.scraper.time.sleep")
    async def test_max_results(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: OLXScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        items = [_make_item(HTML_CARD.replace("Notebook Dell", f"Notebook Model {i}")) for i in range(20)]
        mock_driver.find_elements.return_value = items
        with patch.object(scraper, "_wait_for_results", return_value=True):
            results = await scraper.search("t", max_results=10)
        assert len(results) == 10


class TestPrice:
    def test_brl(self, scraper: OLXScraper) -> None:
        """R$ 1.200 → 1200.0 via _extract_price"""
        assert scraper._extract_price("R$ 1.200") == 1200.0

    def test_gratis(self, scraper: OLXScraper) -> None:
        """Grátis → None (not matched by R$ regex)"""
        assert scraper._extract_price("Grátis") is None

    def test_two_prices(self, scraper: OLXScraper) -> None:
        """Multiple prices: last one wins"""
        assert scraper._extract_price("R$ 4.100\nR$ 3.800") == 3800.0

    def test_price_thousands(self, scraper: OLXScraper) -> None:
        """R$ 3.800 → 3800.0 (dot is thousand separator)"""
        assert scraper._extract_price("R$ 3.800") == 3800.0

    def test_price_with_cents(self, scraper: OLXScraper) -> None:
        """R$ 1.390,50 → 1390.5"""
        assert scraper._extract_price("R$ 1.390,50") == 1390.5


class TestLocation:
    def test_online_prefix(self, scraper: OLXScraper) -> None:
        """Text 'Online\nSão Paulo - SP' → 'São Paulo - SP'"""
        assert scraper._extract_location("Online\nSão Paulo - SP") == "São Paulo - SP"

    def test_simple(self, scraper: OLXScraper) -> None:
        assert scraper._extract_location("Campinas, SP") is None  # comma separator, not hyphen

    def test_hyphen(self, scraper: OLXScraper) -> None:
        assert scraper._extract_location("São Paulo - SP") == "São Paulo - SP"


class TestModels:
    def test_defaults(self) -> None:
        a = OLXAd(title="Test")
        assert a.title == "Test"
        assert a.price is None

    def test_search(self) -> None:
        s = OLXSearch(query="test", ads=[OLXAd(title="T")])
        assert s.query == "test"


class TestDryRun:
    def test_config_loads(self) -> None:
        from src.config_manager import ConfigManager
        ConfigManager.clear_cache()
        config = ConfigManager.get_client_config("demo_olx")
        assert config.client_id == "demo_olx"
        assert "notebook dell" in config.settings.get("search_terms", [])
