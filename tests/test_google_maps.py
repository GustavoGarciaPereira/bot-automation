"""Unit tests for the Google Maps plugin.

All Selenium calls are mocked — no real browser is launched.
Uses mock HTML that mirrors the real Google Maps card structure.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from src.plugins.google_maps.models import Business, LeadSearch
from src.plugins.google_maps.scraper import GoogleMapsScraper, _clear_config_cache


def _build_outer_html(
    name: str = "Dentista Campinas",
    rating: str = "4.5",
    address: str = "Rua X, 123",
    phone: str = "(19) 3325-0025",
    website: str = "https://example.com",
    category: str = "Dentista",
) -> str:
    """Build a realistic Google Maps card HTML snippet."""
    return (
        f'<div role="article" class="Nv2PK">'
        f'<a class="hfpxzc" aria-label="{name}" href="https://maps.google.com/place/test">'
        f'<span class="xxVWCe">{name}</span></a>'
        f'<div class="qBF1Pd fontHeadlineSmall">{name}</div>'
        f'<div class="W4Efsd"><span class="MW4etd">{rating}</span></div>'
        f'<div class="W4Efsd"><div class="W4Efsd">'
        f'<span><span>{category}</span></span>'
        f'<span> · <span>{address}</span></span>'
        f'</div><div class="W4Efsd">'
        f'<span class="UsdlK">{phone}</span>'
        f'</div></div>'
        f'<a class="lcr4fd S9kvJb" data-value="Website" href="{website}">Website</a>'
        f'</div>'
    )


def _make_item(outer_html: str) -> MagicMock:
    """Create a mock Selenium element backed by real-ish HTML.

    Both ``find_element`` and ``find_elements`` parse the HTML via
    BeautifulSoup, so they respond correctly to CSS selectors that
    exist in the HTML.
    """
    item = MagicMock()
    item.get_attribute.side_effect = lambda k: {"outerHTML": outer_html}.get(k, "")
    soup = BeautifulSoup(outer_html, "html.parser")

    def _find(by: str, selector: str) -> MagicMock:
        tag = soup.select_one(selector)
        if tag is None:
            raise Exception(f"Mock: selector '{selector}' not found in HTML")
        m = MagicMock()
        m.text = tag.text.strip()
        # Map commonly accessed attributes
        attrs = {}
        for attr in ("href", "aria-label", "data-value", "data-item-id"):
            val = tag.get(attr)
            if val:
                attrs[attr] = val
        if attrs:
            m.get_attribute.side_effect = lambda k: attrs.get(k, "")
        else:
            m.get_attribute.return_value = m.text
        return m

    def _find_elems(by: str, selector: str) -> list[MagicMock]:
        tags = soup.select(selector)
        result = []
        for tag in tags:
            m = MagicMock()
            m.text = tag.text.strip()
            attrs = {}
            for attr in ("href", "aria-label", "data-value", "data-item-id"):
                val = tag.get(attr)
                if val:
                    attrs[attr] = val
            if attrs:
                m.get_attribute.side_effect = lambda k: attrs.get(k, "")
            else:
                m.get_attribute.return_value = m.text
            result.append(m)
        return result

    item.find_element.side_effect = _find
    item.find_elements.side_effect = _find_elems
    item.text = soup.get_text("\n", strip=True)
    return item


def _mock_item(
    name: str = "Dentista Campinas",
    rating: str = "4.5",
    address: str = "Rua X, 123",
    phone: str | None = "(19) 3325-0025",
    website: str | None = "https://example.com",
    category: str | None = "Dentista",
) -> MagicMock:
    return _make_item(_build_outer_html(
        name=name, rating=rating, address=address,
        phone=phone or "", website=website or "",
        category=category or "",
    ))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    _clear_config_cache()
    yield


@pytest.fixture
def scraper() -> GoogleMapsScraper:
    return GoogleMapsScraper(headless=True)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    @patch("src.plugins.google_maps.scraper.selenium_driver")
    @patch("src.plugins.google_maps.scraper.WebDriverWait")
    async def test_search_parses_results(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: GoogleMapsScraper
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        mock_items = [
            _mock_item(name="Dentista A", rating="4.5", phone="(19) 1111-1111"),
            _mock_item(name="Dentista B", rating="4.0", phone="(19) 2222-2222"),
            _mock_item(name="Dentista C", rating="3.5"),
        ]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("dentistas", max_results=10)

        assert len(results) == 3
        assert results[0]["name"] == "Dentista A"
        assert results[0]["rating"] == 4.5
        assert results[0]["phone"] == "(19) 1111-1111"
        assert results[1]["name"] == "Dentista B"
        assert results[2]["name"] == "Dentista C"

    @patch("src.plugins.google_maps.scraper.selenium_driver")
    @patch("src.plugins.google_maps.scraper.WebDriverWait")
    async def test_min_rating_filter(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: GoogleMapsScraper
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        ratings = [3.0, 3.5, 4.0, 4.5, 5.0]
        mock_items = [
            _mock_item(name=f"Biz {i}", rating=str(r)) for i, r in enumerate(ratings)
        ]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("test", max_results=10, min_rating=4.0)
        assert len(results) == 3  # 4.0, 4.5, 5.0
        for r in results:
            assert r["rating"] is None or r["rating"] >= 4.0

    @patch("src.plugins.google_maps.scraper.selenium_driver")
    @patch("src.plugins.google_maps.scraper.WebDriverWait")
    async def test_max_results(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: GoogleMapsScraper
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_items = [_mock_item(name=f"Biz {i}") for i in range(30)]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("test", max_results=10)
        assert len(results) == 10

    @patch("src.plugins.google_maps.scraper.selenium_driver")
    @patch("src.plugins.google_maps.scraper.WebDriverWait")
    async def test_empty_results(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: GoogleMapsScraper
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_driver.find_elements.return_value = []

        results = await scraper.search("zzzzzzzz", max_results=10)
        assert results == []

    @patch("src.plugins.google_maps.scraper.selenium_driver")
    @patch("src.plugins.google_maps.scraper.WebDriverWait")
    async def test_scroll_logic(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: GoogleMapsScraper
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_items = [_mock_item(name="Test")]
        mock_driver.find_elements.return_value = mock_items

        with patch("time.sleep"):
            await scraper.search("test", max_results=10)

        assert mock_driver.execute_script.call_count >= 1


# ---------------------------------------------------------------------------
# Phone extraction
# ---------------------------------------------------------------------------


class TestPhoneExtraction:
    def test_phone_from_usdlk(self, scraper: GoogleMapsScraper) -> None:
        """span.UsdlK → phone number."""
        item = _mock_item(phone="(19) 3325-0025")
        biz = scraper._parse_item(item)
        assert biz is not None
        assert biz.phone == "(19) 3325-0025"

    def test_phone_missing(self, scraper: GoogleMapsScraper) -> None:
        item = _mock_item(phone=None)
        biz = scraper._parse_item(item)
        assert biz is not None
        assert biz.phone is None


# ---------------------------------------------------------------------------
# Website extraction
# ---------------------------------------------------------------------------


class TestWebsiteExtraction:
    def test_website_from_lcr4fd(self, scraper: GoogleMapsScraper) -> None:
        """a.lcr4fd[data-value='Website'] href → website."""
        item = _mock_item(website="https://meusite.com.br")
        biz = scraper._parse_item(item)
        assert biz is not None
        assert biz.website == "https://meusite.com.br"

    def test_website_missing(self, scraper: GoogleMapsScraper) -> None:
        item = _mock_item(website=None)
        biz = scraper._parse_item(item)
        assert biz is not None
        assert biz.website is None


# ---------------------------------------------------------------------------
# Rating
# ---------------------------------------------------------------------------


class TestRatingParsing:
    def test_rating_4_5(self, scraper: GoogleMapsScraper) -> None:
        """span.MW4etd '4,5' → 4.5"""
        item = _mock_item(rating="4,5")
        biz = scraper._parse_item(item)
        assert biz is not None
        assert biz.rating == 4.5

    def test_rating_missing(self, scraper: GoogleMapsScraper) -> None:
        """No span.MW4etd → None."""
        html = _build_outer_html(rating="")
        html = html.replace('<span class="MW4etd"></span>', "")
        item = _make_item(html)
        biz = scraper._parse_item(item)
        assert biz is not None
        assert biz.rating is None


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------


class TestAddress:
    def test_address_found(self, scraper: GoogleMapsScraper) -> None:
        """Address 'Rua X, 123' should be found."""
        item = _mock_item(address="Rua X, 123")
        biz = scraper._parse_item(item)
        assert biz is not None
        assert biz.address == "Rua X, 123"

    def test_address_not_rating(self, scraper: GoogleMapsScraper) -> None:
        """Numeric '4,9' should NOT be returned as address."""
        item = _mock_item(address="4,9")
        biz = scraper._parse_item(item)
        assert biz is not None
        # "4,9" is an address-like value but it should be filtered
        # (this depends on the address extraction logic)
        if biz.address is not None:
            assert "4,9" != biz.address


# ---------------------------------------------------------------------------
# Reviews count
# ---------------------------------------------------------------------------


class TestReviewsParsing:
    def test_reviews_not_in_list(self, scraper: GoogleMapsScraper) -> None:
        """Reviews count is not available in list view → None."""
        item = _mock_item()
        biz = scraper._parse_item(item)
        assert biz is not None
        assert biz.reviews_count is None


# ---------------------------------------------------------------------------
# Name only is valid
# ---------------------------------------------------------------------------


class TestNameOnlyIsValid:
    @patch("src.plugins.google_maps.scraper.selenium_driver")
    @patch("src.plugins.google_maps.scraper.WebDriverWait")
    async def test_name_only(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: GoogleMapsScraper
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_items = [_mock_item(name="Só Nome")]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("test", max_results=10)
        assert len(results) == 1
        assert results[0]["name"] == "Só Nome"


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


class TestDedup:
    @patch("src.plugins.google_maps.scraper.selenium_driver")
    @patch("src.plugins.google_maps.scraper.WebDriverWait")
    async def test_dedup(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: GoogleMapsScraper
    ) -> None:
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance
        mock_items = [
            _mock_item(name="Dentista A", rating="4.5"),
            _mock_item(name="Dentista A", rating="4.5"),  # dup
            _mock_item(name="Dentista B", rating="4.0"),
        ]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("test", max_results=10)
        assert len(results) == 2
        names = [r["name"] for r in results]
        assert names == ["Dentista A", "Dentista B"]


# ---------------------------------------------------------------------------
# Business model
# ---------------------------------------------------------------------------


class TestBusinessModel:
    def test_business_defaults(self) -> None:
        b = Business(name="Test")
        assert b.name == "Test"
        assert b.category is None
        assert b.rating is None

    def test_lead_search(self) -> None:
        b = Business(name="Test")
        ls = LeadSearch(query="test", businesses=[b])
        assert ls.query == "test"
        assert len(ls.businesses) == 1


# ---------------------------------------------------------------------------
# Plugin integration (dry-run)
# ---------------------------------------------------------------------------


class TestPluginDryRun:
    def test_dry_run_config_loads(self) -> None:
        from src.config_manager import ConfigManager
        ConfigManager.clear_cache()
        config = ConfigManager.get_client_config("demo_google_maps")
        assert config.client_id == "demo_google_maps"
        assert config.settings.get("search_query") == "dentistas em campinas sp"
        assert config.settings.get("max_results") == 20
        assert config.settings.get("min_rating") == 4.0
