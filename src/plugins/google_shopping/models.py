"""Pydantic models for Google Shopping product data."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ShoppingProduct(BaseModel):
    """Represents a product from Google Shopping search results."""

    title: str
    price: float | None = None
    original_price: float | None = None
    store_name: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    image_url: str = ""
    product_url: str = ""
    free_shipping: bool = False
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class ShoppingSearch(BaseModel):
    """Represents a Google Shopping search result."""

    query: str
    total_results: int = 0
    products: list[ShoppingProduct] = Field(default_factory=list)
