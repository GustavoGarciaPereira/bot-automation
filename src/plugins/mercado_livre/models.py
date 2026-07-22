"""Pydantic models for Mercado Livre product data."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Product(BaseModel):
    """Represents a product from Mercado Livre."""

    id: str
    title: str
    price: float
    original_price: float | None = None
    currency_id: str = "BRL"
    seller_id: int | None = None
    seller_name: str | None = None
    reviews_count: int = 0
    rating: float | None = None
    free_shipping: bool = False
    condition: str = "new"
    permalink: str = ""
    thumbnail: str = ""
    available_quantity: int = 0
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class SearchResult(BaseModel):
    """Represents a search result from Mercado Livre."""

    query: str
    total: int
    products: list[Product]
