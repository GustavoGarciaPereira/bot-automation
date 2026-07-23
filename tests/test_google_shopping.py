"""Tests for Google Shopping plugin."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from src.plugins.google_shopping.models import ShoppingProduct, ShoppingSearch
from src.plugins.google_shopping.scraper import GoogleShoppingScraper, _clear_config_cache


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


@pytest.fixture(autouse=True)
def _clear():
    _clear_config_cache()
    yield


@pytest.fixture
def scraper() -> GoogleShoppingScraper:
    return GoogleShoppingScraper(headless=True)


class TestSearch:
    @patch("src.plugins.google_shopping.scraper.selenium_driver")
    @patch("src.plugins.google_shopping.scraper.WebDriverWait")
    @patch("src.plugins.google_shopping.scraper.time.sleep")
    async def test_parses_products(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock,
        scraper: GoogleShoppingScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        mock_items = [
            _make_item('<div class="sh-dgr__content"><h3>Notebook Dell</h3><span class="price">R$ 3.499</span></div>'),
            _make_item('<div class="sh-dgr__content"><h3>iPhone 15</h3><span class="price">R$ 7.999</span></div>'),
            _make_item('<div class="sh-dgr__content"><h3>Monitor</h3><span class="price">R$ 1.299</span></div>'),
        ]
        mock_driver.find_elements.return_value = mock_items

        with patch.object(scraper, "_wait_for_results", return_value=True):
            results = await scraper.search("notebook", max_results=10)

        assert len(results) == 3
        assert results[0]["title"] == "Notebook Dell"
        assert results[1]["title"] == "iPhone 15"

    @patch("src.plugins.google_shopping.scraper.selenium_driver")
    @patch("src.plugins.google_shopping.scraper.WebDriverWait")
    @patch("src.plugins.google_shopping.scraper.time.sleep")
    async def test_empty(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock,
        scraper: GoogleShoppingScraper,
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

    @patch("src.plugins.google_shopping.scraper.selenium_driver")
    @patch("src.plugins.google_shopping.scraper.WebDriverWait")
    @patch("src.plugins.google_shopping.scraper.time.sleep")
    async def test_max_results(
        self, mock_sleep: MagicMock, mock_wait: MagicMock, mock_selenium: MagicMock,
        scraper: GoogleShoppingScraper,
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_items = [_make_item(f'<div class="sh-dgr__content"><h3>P{i}</h3></div>') for i in range(20)]
        mock_driver.find_elements.return_value = mock_items

        with patch.object(scraper, "_wait_for_results", return_value=True):
            results = await scraper.search("test", max_results=10)
        assert len(results) == 10


class TestPriceParsing:
    def test_brl_format(self, scraper: GoogleShoppingScraper) -> None:
        """R$ 3.499,90 → 3499.90 via _parse_price on a mock card."""
        item = _make_item('<div><span class="price">R$ 3.499,90</span></div>')
        assert scraper._parse_price(item) == 3499.90

    def test_simple(self, scraper: GoogleShoppingScraper) -> None:
        """R$ 1.299 → 1299.0"""
        item = _make_item('<div><span class="price">R$ 1.299</span></div>')
        assert scraper._parse_price(item) == 1299.0


class TestModels:
    def test_defaults(self) -> None:
        p = ShoppingProduct(title="Test")
        assert p.title == "Test"
        assert p.price is None

    def test_search(self) -> None:
        s = ShoppingSearch(query="test", products=[ShoppingProduct(title="T")])
        assert s.total_results == 0


class TestDryRun:
    def test_config_loads(self) -> None:
        from src.config_manager import ConfigManager
        ConfigManager.clear_cache()
        config = ConfigManager.get_client_config("demo_google_shopping")
        assert config.client_id == "demo_google_shopping"
        assert "notebook dell" in config.settings.get("search_terms", [])
