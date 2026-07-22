"""Unit tests for the Mercado Livre HTML scraper.

All Selenium calls are mocked — no real browser is launched.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.plugins.mercado_livre.models import Product, SearchResult
from src.plugins.mercado_livre.scraper import MercadoLivreScraper, _clear_config_cache

# ---------------------------------------------------------------------------
# Sample HTML snippets simulating Mercado Livre search result items
# ---------------------------------------------------------------------------

SAMPLE_ITEM_1 = """
<li class="ui-search-layout__item">
  <a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-1">
    Notebook Dell Inspiron 15 3000
  </a>
  <span class="andes-money-amount__fraction">3.499</span>
  <span class="andes-money-amount__cents">90</span>
  <span class="poly-price__previous">
    <span class="andes-money-amount__fraction">4.200</span>
  </span>
  <img class="poly-component__picture" src="http://mlstatic.com/img1.jpg" />
  <span class="poly-component__shipping">Frete grátis</span>
  <span class="poly-reviews__rating">4.5</span>
  <span class="poly-reviews__total">(25)</span>
  <span class="poly-component__condition">Novo</span>
</li>
"""

SAMPLE_ITEM_2 = """
<li class="ui-search-layout__item">
  <a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-2">
    iPhone 15 Pro Max 256GB
  </a>
  <span class="andes-money-amount__fraction">7.999</span>
  <span class="andes-money-amount__cents">00</span>
  <img class="poly-component__picture" src="http://mlstatic.com/img2.jpg" />
  <span class="poly-reviews__rating">4.8</span>
  <span class="poly-reviews__total">(152)</span>
  <span class="poly-component__condition">Novo</span>
</li>
"""

SAMPLE_ITEM_3 = """
<li class="ui-search-layout__item">
  <a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-3">
    Notebook usado em bom estado
  </a>
  <span class="andes-money-amount__fraction">1.200</span>
  <img class="poly-component__picture" src="http://mlstatic.com/img3.jpg" />
  <span class="poly-component__condition">Usado</span>
</li>
"""


def _make_mock_item(html: str) -> MagicMock:
    """Create a mock Selenium WebElement from an HTML string.

    The mock supports ``find_element(By.CSS_SELECTOR, selector)`` and
    returns a sub-element whose ``.text`` or ``.get_attribute()`` returns
    the expected values.
    """
    from selenium.webdriver.common.by import By

    def _fake_find_child(by: str, selector: str) -> MagicMock:
        """Simulate find_element on an item — returns the matching field."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # Try to find the element matching the selector
        if "poly-component__title" in selector:
            tag = soup.select_one("a.poly-component__title")
            if tag:
                m = MagicMock()
                m.text = tag.text.strip()
                m.get_attribute.return_value = tag.get("href", "")
                return m

        if "andes-money-amount__fraction" in selector:
            tag = soup.select_one("span.andes-money-amount__fraction")
            if tag:
                m = MagicMock()
                m.text = tag.text.strip()
                return m

        if "andes-money-amount__cents" in selector:
            tag = soup.select_one("span.andes-money-amount__cents")
            if tag:
                m = MagicMock()
                m.text = tag.text.strip()
                return m

        if "poly-price__previous" in selector:
            tag = soup.select_one("span.poly-price__previous")
            if tag:
                m = MagicMock()
                m.text = tag.text.strip()
                m.find_element.return_value = _fake_find_child(
                    by, "span.andes-money-amount__fraction"
                )
                return m

        if "poly-component__picture" in selector and "src" in selector:
            tag = soup.select_one("img.poly-component__picture")
            if tag:
                m = MagicMock()
                m.get_attribute.return_value = tag.get("src", "")
                return m
        if "poly-component__picture" in selector:
            tag = soup.select_one("img.poly-component__picture")
            if tag:
                m = MagicMock()
                m.get_attribute.return_value = tag.get("src", "")
                return m

        if "poly-component__shipping" in selector:
            tag = soup.select_one("span.poly-component__shipping")
            if tag:
                m = MagicMock()
                m.text = tag.text.strip()
                return m

        if "poly-reviews__rating" in selector:
            tag = soup.select_one("span.poly-reviews__rating")
            if tag:
                m = MagicMock()
                m.text = tag.text.strip()
                return m

        if "poly-reviews__total" in selector:
            tag = soup.select_one("span.poly-reviews__total")
            if tag:
                m = MagicMock()
                m.text = tag.text.strip()
                return m

        if "poly-component__condition" in selector:
            tag = soup.select_one("span.poly-component__condition")
            if tag:
                m = MagicMock()
                m.text = tag.text.strip()
                return m

        if "ui-search-link" in selector:
            tag = soup.select_one("a")
            if tag and tag.get("href"):
                m = MagicMock()
                m.get_attribute.return_value = tag.get("href", "")
                return m

        # Fallback for any img (src or data-src)
        if "img" in selector:
            tag = soup.select_one("img")
            if tag:
                src = tag.get("data-src") or tag.get("src", "")
                m = MagicMock()
                m.get_attribute.return_value = src
                return m

        # Fallback for h2
        if "h2" in selector:
            tag = soup.select_one("h2")
            if tag:
                m = MagicMock()
                m.text = tag.text.strip()
                return m

        raise Exception(f"Mock not found for selector: {selector}")

    mock_item = MagicMock()
    mock_item.find_element.side_effect = lambda by, sel: _fake_find_child(by, sel)
    return mock_item


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    _clear_config_cache()
    yield


@pytest.fixture
def scraper() -> MercadoLivreScraper:
    return MercadoLivreScraper(headless=True)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    @patch("src.plugins.mercado_livre.scraper.selenium_driver")
    @patch("src.plugins.mercado_livre.scraper.WebDriverWait")
    async def test_search_parses_html(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: MercadoLivreScraper
    ) -> None:
        """Mock Selenium with HTML containing 3 items and verify parsing."""
        # Mock the driver returned by selenium_driver context manager
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm

        # Mock wait.until to do nothing
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        # Mock the list items
        mock_items = [
            _make_mock_item(SAMPLE_ITEM_1),
            _make_mock_item(SAMPLE_ITEM_2),
            _make_mock_item(SAMPLE_ITEM_3),
        ]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("notebook dell", max_results=10)

        assert len(results) == 3
        assert results[0]["title"] == "Notebook Dell Inspiron 15 3000"
        assert results[0]["price"] == 3499.90
        assert results[0]["free_shipping"] is True
        assert results[0]["rating"] == 4.5
        assert results[0]["reviews_count"] == 25
        assert results[0]["condition"] == "Novo"

        assert results[1]["title"] == "iPhone 15 Pro Max 256GB"
        assert results[1]["price"] == 7999.00
        assert results[1]["free_shipping"] is False

        assert results[2]["title"] == "Notebook usado em bom estado"
        assert results[2]["price"] == 1200.00
        assert results[2]["condition"] == "Usado"

    @patch("src.plugins.mercado_livre.scraper.selenium_driver")
    @patch("src.plugins.mercado_livre.scraper.WebDriverWait")
    async def test_max_results_limit(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: MercadoLivreScraper
    ) -> None:
        """20 items in HTML, max_results=5 → returns 5."""
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm

        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        # Create 20 item mocks
        mock_items = [_make_mock_item(SAMPLE_ITEM_1) for _ in range(20)]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("notebook dell", max_results=5)

        assert len(results) == 5

    @patch("src.plugins.mercado_livre.scraper.selenium_driver")
    @patch("src.plugins.mercado_livre.scraper.WebDriverWait")
    async def test_empty_results(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: MercadoLivreScraper
    ) -> None:
        """No items in HTML → returns []."""
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm

        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        mock_driver.find_elements.return_value = []

        results = await scraper.search("zzzzzzzz", max_results=10)

        assert results == []


# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------


class TestPriceParsing:
    def test_price_3499_90(self, scraper: MercadoLivreScraper) -> None:
        """3.499 + 90 → 3499.90"""
        assert scraper._build_price("3.499", "90") == 3499.90

    def test_price_7999_00(self, scraper: MercadoLivreScraper) -> None:
        """7.999 + 00 → 7999.00"""
        assert scraper._build_price("7.999", "00") == 7999.00

    def test_price_no_cents(self, scraper: MercadoLivreScraper) -> None:
        """1.200 without cents → 1200.00"""
        assert scraper._build_price("1.200", "") == 1200.00

    def test_price_empty(self, scraper: MercadoLivreScraper) -> None:
        """Empty strings → 0.0"""
        assert scraper._build_price("", "") == 0.0

    def test_price_invalid(self, scraper: MercadoLivreScraper) -> None:
        """Invalid input → 0.0"""
        assert scraper._build_price("abc", "def") == 0.0


# ---------------------------------------------------------------------------
# Free shipping detection
# ---------------------------------------------------------------------------


class TestFreeShipping:
    def test_free_shipping_true(self, scraper: MercadoLivreScraper) -> None:
        """Item with 'Frete grátis' text → free_shipping=True."""
        mock_item = _make_mock_item(SAMPLE_ITEM_1)
        product = scraper._parse_item(mock_item)
        assert product is not None
        assert product.free_shipping is True

    def test_free_shipping_false(self, scraper: MercadoLivreScraper) -> None:
        """Item without shipping text → free_shipping=False."""
        mock_item = _make_mock_item(SAMPLE_ITEM_2)
        product = scraper._parse_item(mock_item)
        assert product is not None
        assert product.free_shipping is False


# ---------------------------------------------------------------------------
# Product model
# ---------------------------------------------------------------------------


class TestProductModel:
    def test_product_defaults(self) -> None:
        p = Product(title="Test", price=10.0)
        assert p.currency == "R$"
        assert p.original_price is None
        assert p.free_shipping is False
        assert p.condition is None
        assert p.rating is None
        assert p.reviews_count is None
        assert p.seller is None

    def test_search_result(self) -> None:
        p = Product(title="Test", price=10.0)
        sr = SearchResult(query="test", products=[p])
        assert sr.query == "test"
        assert sr.total_results is None
        assert len(sr.products) == 1


# ---------------------------------------------------------------------------
# Plugin integration (dry-run)
# ---------------------------------------------------------------------------


class TestPluginDryRun:
    def test_dry_run_config_loads(self) -> None:
        """Verify that the client config loads with settings."""
        from src.config_manager import ConfigManager

        ConfigManager.clear_cache()
        config = ConfigManager.get_client_config("demo_mercado_livre")

        assert config.client_id == "demo_mercado_livre"
        assert config.settings.get("search_terms") == ["notebook dell", "iphone 15"]
        assert config.settings.get("max_results") == 10
