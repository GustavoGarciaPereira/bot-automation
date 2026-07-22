"""Mercado Livre API scraper — uses the public Mercado Livre REST API.

API docs: https://developers.mercadolivre.com.br/
No authentication is required for search and item lookup endpoints.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    RetryError,
)

from src.interfaces.scraper import BaseScraper
from src.plugins.mercado_livre.models import Product, SearchResult
from src.utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default config (overridable via config.json)
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "base_url": "https://api.mercadolibre.com",
    "site_id": "MLB",
    "rate_limit_seconds": 1.0,
    "max_retries": 3,
    "timeout_seconds": 15,
    "user_agent": "Mozilla/5.0 (compatible; AutoBotRPA/1.0)",
}

_CONFIG_CACHE: dict[str, Any] | None = None


def _load_config() -> dict[str, Any]:
    """Load plugin config from config.json, merged with defaults."""
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
# Retry decorator for transient HTTP failures
# ---------------------------------------------------------------------------

_retry_decorator = retry(
    stop=stop_after_attempt(_DEFAULT_CONFIG["max_retries"]),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type(
        (requests.ConnectionError, requests.Timeout, requests.HTTPError)
    ),
    before_sleep=lambda retry_state: logger.info(
        "Retrying ML API (attempt %d)...", retry_state.attempt_number
    ),
)


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------


class MercadoLivreScraper(BaseScraper):
    """Scraper for the Mercado Livre public API.

    Performs search and product detail extraction using REST API calls.
    Respects rate limiting and includes retry logic.
    """

    def __init__(self, access_token: str | None = None) -> None:
        self._cfg = _load_config()
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self._cfg["user_agent"]})
        if access_token:
            self._session.headers.update(
                {"Authorization": f"Bearer {access_token}"}
            )
        self._seller_cache: dict[int, str] = {}
        self._last_request_time: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, max_results: int = 10, **kwargs: Any) -> list[dict[str, Any]]:
        """Search Mercado Livre for *query*.

        Returns a list of product dicts (flat, API-shaped).
        """
        url = f"{self._cfg['base_url']}/sites/{self._cfg['site_id']}/search"
        params: dict[str, Any] = {"q": query, "limit": min(max_results, 50)}

        try:
            data = self._request("GET", url, params=params)
        except RetryError:
            logger.error("ML search failed after retries for query=%r", query)
            return []

        if data is None:
            logger.warning("ML search returned no data for query=%r", query)
            return []

        results = data.get("results", [])
        logger.info(
            "ML search: query=%r total=%d returned=%d",
            query,
            data.get("paging", {}).get("total", 0),
            len(results),
        )

        products: list[dict[str, Any]] = []
        for raw in results:
            product = self._parse_product(raw)
            products.append(product.model_dump())

        return products

    def extract(self, item_id: str, **kwargs: Any) -> dict[str, Any]:
        """Fetch detailed information for a single item.

        Returns a flat dict of product data.
        """
        url = f"{self._cfg['base_url']}/items/{item_id}"
        try:
            data = self._request("GET", url)
        except RetryError:
            logger.error("ML extract failed after retries for item_id=%r", item_id)
            return {}

        if data is None:
            logger.warning("ML extract returned no data for item_id=%r", item_id)
            return {}

        product = self._parse_product(data)
        return product.model_dump()

    # ------------------------------------------------------------------
    # Internal — HTTP
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        """Ensure we don't exceed the rate limit."""
        elapsed = time.time() - self._last_request_time
        min_interval = self._cfg.get("rate_limit_seconds", 1.0)
        if elapsed < min_interval:
            sleep_for = min_interval - elapsed
            time.sleep(sleep_for)
        self._last_request_time = time.time()

    @_retry_decorator
    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any] | None:
        """Make an HTTP request with rate limiting and retry."""
        self._rate_limit()

        try:
            resp = self._session.request(
                method,
                url,
                timeout=self._cfg.get("timeout_seconds", 15),
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status == 403:
                logger.error(
                    "ML API 403 Forbidden. The Mercado Livre public API now requires "
                    "an access token. Register an app at https://developers.mercadolivre.com "
                    "and add 'access_token' to clients/demo_mercado_livre.json settings."
                )
                return None
            if status >= 500:
                logger.warning("ML API %d error for %s: %s", status, url, exc)
                raise  # Will trigger tenacity retry
            logger.error("ML API %d error for %s: %s", status, url, exc)
            return None
        except (requests.ConnectionError, requests.Timeout) as exc:
            logger.warning("ML API request failed for %s: %s", url, exc)
            raise  # Will trigger tenacity retry
        except Exception as exc:
            logger.error("ML API unexpected error for %s: %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # Internal — data parsing
    # ------------------------------------------------------------------

    def _parse_product(self, raw: dict[str, Any]) -> Product:
        """Convert a raw Mercado Livre API response dict into a Product."""
        # Extract seller id
        seller_id: int | None = None
        seller_raw = raw.get("seller")
        if isinstance(seller_raw, dict):
            seller_id = seller_raw.get("id")

        # Extract reviews
        reviews_count = 0
        rating: float | None = None
        reviews_raw = raw.get("reviews")
        if isinstance(reviews_raw, dict):
            reviews_count = reviews_raw.get("total", 0)
            rating = reviews_raw.get("average_rating")

        # Shipping
        shipping_raw = raw.get("shipping", {})
        free_shipping = bool(shipping_raw.get("free_shipping", False))

        return Product(
            id=raw.get("id", ""),
            title=raw.get("title", ""),
            price=float(raw.get("price", 0) or 0),
            original_price=(
                float(raw["original_price"]) if raw.get("original_price") else None
            ),
            currency_id=raw.get("currency_id", "BRL"),
            seller_id=seller_id,
            seller_name=self._resolve_seller_name(seller_id),
            reviews_count=reviews_count,
            rating=rating,
            free_shipping=free_shipping,
            condition=raw.get("condition", "new"),
            permalink=raw.get("permalink", ""),
            thumbnail=raw.get("thumbnail", ""),
            available_quantity=int(raw.get("available_quantity", 0) or 0),
        )

    def _resolve_seller_name(self, seller_id: int | None) -> str | None:
        """Fetch seller nickname from the ML users API with caching."""
        if seller_id is None:
            return None

        if seller_id in self._seller_cache:
            return self._seller_cache[seller_id]

        try:
            url = f"{self._cfg['base_url']}/users/{seller_id}"
            data = self._request("GET", url)
            if data and "nickname" in data:
                name = str(data["nickname"])
                self._seller_cache[seller_id] = name
                return name
        except Exception as exc:
            logger.debug("Failed to fetch seller %d: %s", seller_id, exc)

        return None
