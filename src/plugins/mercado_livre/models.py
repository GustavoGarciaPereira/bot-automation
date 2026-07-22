"""Pydantic models for Mercado Livre product data scraped from HTML."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Product(BaseModel):
    """Represents a product scraped from Mercado Livre HTML."""

    title: str
    price: float
    original_price: float | None = None
    currency: str = "R$"
    rating: float | None = None
    reviews_count: int | None = None
    free_shipping: bool = False
    condition: str | None = None
    seller: str | None = None
    url: str = ""
    image_url: str = ""
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class SearchResult(BaseModel):
    """Represents a search result from Mercado Livre."""

    query: str
    total_results: int | None = None
    products: list[Product]
