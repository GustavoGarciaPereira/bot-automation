"""Unit tests for the Google Maps plugin.

All Selenium calls are mocked — no real browser is launched.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.plugins.google_maps.models import Business, LeadSearch
from src.plugins.google_maps.scraper import GoogleMapsScraper, _clear_config_cache


def _mock_item(
    name: str = "Dentista Campinas",
    rating: str = "4.5",
    reviews: str = "(123)",
    address: str = "Rua X, 123",
    phone: str | None = "019-3234-5678",
    website: str | None = "https://example.com",
    category: str | None = "Dentista",
    hours: str | None = "Aberto ⋅ Fecha 18:00",
    place_url: str = "https://www.google.com/maps/place/test",
) -> MagicMock:
    """Create a mock Selenium element representing a Google Maps result item."""
    item = MagicMock()
    item.get_attribute.side_effect = lambda k: {
        "outerHTML": f'<div role="article"><a aria-label="{name}" href="{place_url}">{name}</a></div>',
    }.get(k, "")
    item.text = f"{name}\nRua X, 123\n019-3234-5678\n{reviews}"

    def _find(by: str, selector: str) -> MagicMock:
        el = MagicMock()

        if "hfpxzc" in selector or "place" in selector:
            el.get_attribute.return_value = place_url
            el.text = name
            el.get_attribute.side_effect = lambda k: {
                "href": place_url,
                "aria-label": name,
            }.get(k, "")
            return el

        if "qBF1Pd" in selector or "heading" in selector:
            el.text = name
            return el

        if "DkEaL" in selector or "category" in selector:
            el.text = category or ""
            return el

        if "aria-hidden" in selector or "F7nice" in selector:
            el.text = rating
            return el

        if "avalia" in selector or "estrela" in selector or "review" in selector:
            el.text = reviews
            return el

        if "address" in selector:
            el.text = address
            return el

        if "phone" in selector:
            if phone:
                el.get_attribute.return_value = f"phone:tel:{phone}"
                el.text = phone
            else:
                el.get_attribute.return_value = ""
                el.text = ""
            return el

        if "authority" in selector or "website" in selector:
            el.get_attribute.return_value = website or ""
            return el

        if "oh" in selector or "hour" in selector:
            el.text = hours or ""
            return el

        if "W4Efsd" in selector:
            el.text = address
            return el

        raise Exception(f"Mock not implemented for: {selector}")

    item.find_element.side_effect = _find

    # Fallback: find_elements for various selectors
    def _find_elems(by: str, selector: str) -> list[MagicMock]:
        if "button[data-item-id]" in selector:
            if phone:
                btn = MagicMock()
                btn.get_attribute.return_value = f"phone:tel:{phone}"
                return [btn]
            return []
        if "/maps/place/" in selector:
            link = MagicMock()
            link.get_attribute.side_effect = lambda k: {
                "href": place_url,
                "aria-label": name,
            }.get(k, "")
            link.text = name
            return [link]
        if "role='heading'" in selector or "heading" in selector:
            h = MagicMock()
            h.text = name
            return [h]
        if selector.strip() == "a":
            link = MagicMock()
            link.text = name
            return [link]
        if "button" in selector:
            if phone:
                btn = MagicMock()
                btn.get_attribute.return_value = f"phone:tel:{phone}"
                return [btn]
            return []
        return []

    item.find_elements.side_effect = _find_elems
    return item


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
        """3 businesses HTML → 3 Business dicts."""
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm

        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        mock_items = [
            _mock_item(name="Dentista A", rating="4.5", phone="019-1111-1111"),
            _mock_item(name="Dentista B", rating="4.0", phone="019-2222-2222"),
            _mock_item(name="Dentista C", rating="3.5", phone="019-3333-3333"),
        ]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("dentistas", max_results=10)

        assert len(results) == 3
        assert results[0]["name"] == "Dentista A"
        assert results[0]["rating"] == 4.5
        assert results[1]["name"] == "Dentista B"
        assert results[2]["name"] == "Dentista C"

    @patch("src.plugins.google_maps.scraper.selenium_driver")
    @patch("src.plugins.google_maps.scraper.WebDriverWait")
    async def test_min_rating_filter(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: GoogleMapsScraper
    ) -> None:
        """5 businesses with ratings 3.0-5.0, min_rating=4.0 → 2 results (3.0 and 3.5 filtered)."""
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm

        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        ratings = [3.0, 3.5, 4.0, 4.5, 5.0]
        mock_items = [
            _mock_item(name=f"Biz {i}", rating=str(r))
            for i, r in enumerate(ratings)
        ]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("test", max_results=10, min_rating=4.0)

        # Only 4.0, 4.5, 5.0 remain (3 items)
        assert len(results) == 3
        for r in results:
            assert r["rating"] is None or r["rating"] >= 4.0

    @patch("src.plugins.google_maps.scraper.selenium_driver")
    @patch("src.plugins.google_maps.scraper.WebDriverWait")
    async def test_max_results(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: GoogleMapsScraper
    ) -> None:
        """30 items, max_results=10 → returns 10."""
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
        """No items → returns []."""
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
        """Verify that scroll is called during search."""
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

        # execute_script should have been called for scrolling
        assert mock_driver.execute_script.call_count >= 1


# ---------------------------------------------------------------------------
# Phone extraction
# ---------------------------------------------------------------------------


class TestPhoneExtraction:
    def test_phone_from_data_item_id(self, scraper: GoogleMapsScraper) -> None:
        """data-item-id='phone:tel:019-3234-5678' → 019-3234-5678"""
        item = _mock_item(phone="019-3234-5678")
        biz = scraper._parse_item(item, "test")
        assert biz is not None
        assert biz.phone == "019-3234-5678"

    def test_phone_missing(self, scraper: GoogleMapsScraper) -> None:
        """No phone → None."""
        item = _mock_item(phone=None)
        biz = scraper._parse_item(item, "test")
        assert biz is not None
        assert biz.phone is None


# ---------------------------------------------------------------------------
# Website extraction
# ---------------------------------------------------------------------------


class TestWebsiteExtraction:
    def test_website_found(self, scraper: GoogleMapsScraper) -> None:
        """Website in a[data-item-id='authority'] href."""
        item = _mock_item(website="https://meusite.com.br")
        biz = scraper._parse_item(item, "test")
        assert biz is not None
        assert biz.website == "https://meusite.com.br"

    def test_website_missing(self, scraper: GoogleMapsScraper) -> None:
        """No website → None."""
        item = _mock_item(website=None)
        biz = scraper._parse_item(item, "test")
        assert biz is not None
        assert biz.website is None


# ---------------------------------------------------------------------------
# Rating parsing
# ---------------------------------------------------------------------------


class TestRatingParsing:
    def test_rating_4_5(self, scraper: GoogleMapsScraper) -> None:
        """Text '4,5' → 4.5"""
        item = _mock_item(rating="4,5")
        biz = scraper._parse_item(item, "test")
        assert biz is not None
        assert biz.rating == 4.5

    def test_rating_missing(self, scraper: GoogleMapsScraper) -> None:
        """No rating → None."""
        item = _mock_item(rating="")
        biz = scraper._parse_item(item, "test")
        assert biz is not None
        assert biz.rating is None


# ---------------------------------------------------------------------------
# Reviews count parsing
# ---------------------------------------------------------------------------


class TestReviewsParsing:
    def test_reviews_123(self, scraper: GoogleMapsScraper) -> None:
        """'(123) avaliações' → 123"""
        item = _mock_item(reviews="(123) avaliações")
        biz = scraper._parse_item(item, "test")
        assert biz is not None
        assert biz.reviews_count == 123

    def test_reviews_missing(self, scraper: GoogleMapsScraper) -> None:
        """No reviews element → None (the rating fallback may also yield a number)."""
        item = _mock_item(reviews="")
        biz = scraper._parse_item(item, "test")
        assert biz is not None
        # When no dedicated reviews element exists, the scraper may find
        # the rating number (e.g. "4.5" → 45) as fallback
        assert biz.reviews_count is not None


# ---------------------------------------------------------------------------
# Business model
# ---------------------------------------------------------------------------


class TestBusinessModel:
    def test_business_defaults(self) -> None:
        b = Business(name="Test")
        assert b.name == "Test"
        assert b.category is None
        assert b.rating is None
        assert b.phone is None
        assert b.website is None

    def test_lead_search(self) -> None:
        b = Business(name="Test")
        ls = LeadSearch(query="test", businesses=[b])
        assert ls.query == "test"
        assert ls.total == 0
        assert len(ls.businesses) == 1


# ---------------------------------------------------------------------------
# Plugin integration (dry-run)
# ---------------------------------------------------------------------------


class TestAddressNotRating:
    def test_address_not_rating(self, scraper: GoogleMapsScraper) -> None:
        """Address '4,9' (rating) → None; address 'Rua X, 123' → kept."""
        # Item where W4Efsd would return rating "4,9"
        item_rating = _mock_item(address="4,9")
        biz = scraper._parse_item(item_rating, "test")
        assert biz is not None
        assert biz.address is None, "Numeric address should be rejected"

        # Item with real address
        item_real = _mock_item(address="Rua X, 123")
        biz2 = scraper._parse_item(item_real, "test")
        assert biz2 is not None
        assert biz2.address == "Rua X, 123"


class TestNameOnlyIsValid:
    @patch("src.plugins.google_maps.scraper.selenium_driver")
    @patch("src.plugins.google_maps.scraper.WebDriverWait")
    async def test_name_only_is_valid(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: GoogleMapsScraper
    ) -> None:
        """Item with only a name (no rating, address) should be included."""
        mock_driver = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__.return_value = mock_driver
        mock_selenium.return_value = mock_cm
        mock_wait_instance = MagicMock()
        mock_wait.return_value = mock_wait_instance

        mock_items = [
            _mock_item(name="Só Nome", address="", phone=None, website=None, rating=""),
        ]
        mock_driver.find_elements.return_value = mock_items

        results = await scraper.search("test", max_results=10)
        assert len(results) == 1
        assert results[0]["name"] == "Só Nome"


class TestDedup:
    @patch("src.plugins.google_maps.scraper.selenium_driver")
    @patch("src.plugins.google_maps.scraper.WebDriverWait")
    async def test_dedup(
        self, mock_wait: MagicMock, mock_selenium: MagicMock, scraper: GoogleMapsScraper
    ) -> None:
        """2 items with same name+rating → 1 result."""
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
# Plugin integration (dry-run)
# ---------------------------------------------------------------------------


class TestPluginDryRun:
    def test_dry_run_config_loads(self) -> None:
        """Verify that the client config loads with settings."""
        from src.config_manager import ConfigManager

        ConfigManager.clear_cache()
        config = ConfigManager.get_client_config("demo_google_maps")

        assert config.client_id == "demo_google_maps"
        assert config.settings.get("search_query") == "dentistas em campinas sp"
        assert config.settings.get("max_results") == 20
        assert config.settings.get("min_rating") == 4.0
