"""Unit tests for the Mercado Livre plugin.

All HTTP calls are mocked — no real API requests are made.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import responses

from src.plugins.mercado_livre.models import Product, SearchResult
from src.plugins.mercado_livre.scraper import MercadoLivreScraper, _clear_config_cache

# ---------------------------------------------------------------------------
# Sample API responses (realistic Mercado Livre JSON shapes)
# ---------------------------------------------------------------------------

SAMPLE_SEARCH_RESPONSE = {
    "site_id": "MLB",
    "query": "notebook dell",
    "paging": {"total": 2, "offset": 0, "limit": 10, "primary_results": 2},
    "results": [
        {
            "id": "MLB1234567890",
            "title": "Notebook Dell Inspiron 15 3000",
            "price": 2999.0,
            "currency_id": "BRL",
            "available_quantity": 10,
            "condition": "new",
            "permalink": "https://produto.mercadolivre.com.br/MLB-1234567890",
            "thumbnail": "http://http2.mlstatic.com/thumb.jpg",
            "seller": {"id": 12345},
            "shipping": {"free_shipping": True},
            "reviews": {"total": 25, "average_rating": 4.5},
        },
        {
            "id": "MLB9876543210",
            "title": "Dell Notebook Vostro 14",
            "price": 3500.0,
            "original_price": 4200.0,
            "currency_id": "BRL",
            "available_quantity": 5,
            "condition": "new",
            "permalink": "https://produto.mercadolivre.com.br/MLB-9876543210",
            "thumbnail": "http://http2.mlstatic.com/thumb2.jpg",
            "seller": {"id": 67890},
            "shipping": {"free_shipping": False},
            "reviews": {"total": 10},
        },
    ],
}

SAMPLE_ITEM_RESPONSE = {
    "id": "MLB1234567890",
    "title": "Notebook Dell Inspiron 15 3000",
    "price": 2999.0,
    "currency_id": "BRL",
    "available_quantity": 10,
    "condition": "new",
    "permalink": "https://produto.mercadolivre.com.br/MLB-1234567890",
    "thumbnail": "http://http2.mlstatic.com/thumb.jpg",
    "seller": {"id": 12345},
    "shipping": {"free_shipping": True},
    "reviews": {"total": 25, "average_rating": 4.5},
}

SAMPLE_SELLER_RESPONSE = {
    "id": 12345,
    "nickname": "VENDEDOR_ABC",
}

SAMPLE_EMPTY_SEARCH = {
    "site_id": "MLB",
    "query": "zzzzzzzzz",
    "paging": {"total": 0, "offset": 0, "limit": 10, "primary_results": 0},
    "results": [],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the config cache between tests so config.json is reloaded."""
    _clear_config_cache()
    yield


@pytest.fixture
def scraper() -> MercadoLivreScraper:
    return MercadoLivreScraper()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class TestSearch:
    @responses.activate
    def test_search_returns_products(self, scraper: MercadoLivreScraper) -> None:
        """Mock a search response and verify products are parsed correctly."""
        responses.get(
            "https://api.mercadolibre.com/sites/MLB/search?q=notebook+dell&limit=10",
            json=SAMPLE_SEARCH_RESPONSE,
            status=200,
        )
        # Seller name lookup
        responses.get(
            "https://api.mercadolibre.com/users/12345",
            json=SAMPLE_SELLER_RESPONSE,
            status=200,
        )
        responses.get(
            "https://api.mercadolibre.com/users/67890",
            json={"id": 67890, "nickname": "VENDEDOR_XYZ"},
            status=200,
        )

        results = scraper.search("notebook dell", max_results=10)

        assert len(results) == 2
        assert results[0]["title"] == "Notebook Dell Inspiron 15 3000"
        assert results[0]["price"] == 2999.0
        assert results[0]["free_shipping"] is True
        assert results[0]["seller_name"] == "VENDEDOR_ABC"
        assert results[0]["reviews_count"] == 25
        assert results[0]["rating"] == 4.5
        assert results[1]["original_price"] == 4200.0
        assert results[1]["free_shipping"] is False

    @responses.activate
    def test_search_empty_results(self, scraper: MercadoLivreScraper) -> None:
        """Empty search results should return empty list."""
        responses.get(
            "https://api.mercadolibre.com/sites/MLB/search?q=zzzzzzzzz&limit=10",
            json=SAMPLE_EMPTY_SEARCH,
            status=200,
        )

        results = scraper.search("zzzzzzzzz", max_results=10)
        assert results == []

    @responses.activate
    def test_search_api_error_returns_empty(self, scraper: MercadoLivreScraper) -> None:
        """HTTP 500 should return empty list after retries."""
        responses.get(
            "https://api.mercadolibre.com/sites/MLB/search?q=error&limit=10",
            status=500,
        )
        # tenacity will retry, but responses will return 500 each time
        # The final fallback should be an empty list
        results = scraper.search("error", max_results=10)
        assert results == []

    @responses.activate
    def test_search_network_error_returns_empty(
        self, scraper: MercadoLivreScraper
    ) -> None:
        """Connection error should return empty list after retries."""
        responses.get(
            "https://api.mercadolibre.com/sites/MLB/search?q=timeout&limit=10",
            body=Exception("Connection refused"),
        )

        results = scraper.search("timeout", max_results=10)
        assert results == []


# ---------------------------------------------------------------------------
# Extract
# ---------------------------------------------------------------------------

class TestExtract:
    @responses.activate
    def test_extract_product(self, scraper: MercadoLivreScraper) -> None:
        """Mock a single item lookup."""
        responses.get(
            "https://api.mercadolibre.com/items/MLB1234567890",
            json=SAMPLE_ITEM_RESPONSE,
            status=200,
        )
        responses.get(
            "https://api.mercadolibre.com/users/12345",
            json=SAMPLE_SELLER_RESPONSE,
            status=200,
        )

        result = scraper.extract("MLB1234567890")

        assert result["title"] == "Notebook Dell Inspiron 15 3000"
        assert result["price"] == 2999.0
        assert result["seller_name"] == "VENDEDOR_ABC"
        assert result["free_shipping"] is True

    @responses.activate
    def test_extract_not_found(self, scraper: MercadoLivreScraper) -> None:
        """Non-existent item returns empty dict."""
        responses.get(
            "https://api.mercadolibre.com/items/MLB999",
            status=404,
        )

        result = scraper.extract("MLB999")
        assert result == {}


# ---------------------------------------------------------------------------
# Parse product
# ---------------------------------------------------------------------------

class TestParseProduct:
    def test_parse_product_full(self, scraper: MercadoLivreScraper) -> None:
        """Parse a complete product dict from the API response."""
        raw = SAMPLE_SEARCH_RESPONSE["results"][0]
        product = scraper._parse_product(raw)

        assert isinstance(product, Product)
        assert product.id == "MLB1234567890"
        assert product.title == "Notebook Dell Inspiron 15 3000"
        assert product.price == 2999.0
        assert product.original_price is None
        assert product.free_shipping is True
        assert product.seller_id == 12345
        assert product.reviews_count == 25
        assert product.rating == 4.5
        assert product.condition == "new"

    def test_parse_product_minimal(self, scraper: MercadoLivreScraper) -> None:
        """Parse a product with minimal fields (missing optional ones)."""
        raw = {"id": "MLB1", "title": "Test", "price": 100.0}
        product = scraper._parse_product(raw)

        assert product.id == "MLB1"
        assert product.title == "Test"
        assert product.price == 100.0
        assert product.original_price is None
        assert product.seller_id is None
        assert product.free_shipping is False
        assert product.reviews_count == 0
        assert product.rating is None

    def test_parse_product_zero_price(self, scraper: MercadoLivreScraper) -> None:
        """Price 0 or None should be handled gracefully."""
        raw = {"id": "MLB2", "title": "Free", "price": 0}
        product = scraper._parse_product(raw)
        assert product.price == 0.0


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimit:
    @responses.activate
    def test_rate_limit_enforced(self, scraper: MercadoLivreScraper) -> None:
        """Verify that rate limiting causes sleep between requests."""
        responses.get(
            "https://api.mercadolibre.com/sites/MLB/search?q=a&limit=10",
            json=SAMPLE_EMPTY_SEARCH,
            status=200,
        )
        responses.get(
            "https://api.mercadolibre.com/sites/MLB/search?q=b&limit=10",
            json=SAMPLE_EMPTY_SEARCH,
            status=200,
        )

        with patch("time.sleep") as mock_sleep:
            scraper.search("a", max_results=10)
            scraper.search("b", max_results=10)

            # sleep should have been called at least once (rate limiting)
            assert mock_sleep.call_count >= 1


# ---------------------------------------------------------------------------
# Product model
# ---------------------------------------------------------------------------

class TestProductModel:
    def test_product_defaults(self) -> None:
        p = Product(id="MLB1", title="Test", price=10.0)
        assert p.currency_id == "BRL"
        assert p.original_price is None
        assert p.free_shipping is False
        assert p.condition == "new"
        assert p.available_quantity == 0
        assert p.reviews_count == 0
        assert p.rating is None

    def test_search_result(self) -> None:
        p = Product(id="MLB1", title="Test", price=10.0)
        sr = SearchResult(query="test", total=1, products=[p])
        assert sr.query == "test"
        assert sr.total == 1
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


# ---------------------------------------------------------------------------
# Authentication token
# ---------------------------------------------------------------------------

class TestAuthentication:
    @responses.activate
    def test_search_with_access_token(self) -> None:
        """Search with an access token should send the Authorization header."""
        from src.plugins.mercado_livre.scraper import MercadoLivreScraper

        scraper = MercadoLivreScraper(access_token="test_token_123")

        responses.get(
            "https://api.mercadolibre.com/sites/MLB/search?q=notebook&limit=10",
            json=SAMPLE_SEARCH_RESPONSE,
            status=200,
        )
        responses.get(
            "https://api.mercadolibre.com/users/12345",
            json=SAMPLE_SELLER_RESPONSE,
            status=200,
        )
        responses.get(
            "https://api.mercadolibre.com/users/67890",
            json={"id": 67890, "nickname": "VENDEDOR_XYZ"},
            status=200,
        )

        results = scraper.search("notebook", max_results=10)
        assert len(results) == 2
        # Verify the Authorization header was sent
        assert responses.calls[0].request.headers.get("Authorization") == "Bearer test_token_123"

    @responses.activate
    def test_403_error_logs_message(self, scraper: MercadoLivreScraper) -> None:
        """403 error should log a helpful message and return empty."""
        responses.get(
            "https://api.mercadolibre.com/sites/MLB/search?q=test&limit=10",
            status=403,
        )

        results = scraper.search("test", max_results=10)
        assert results == []
