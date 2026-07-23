"""Pydantic models for OLX Brasil ad data."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OLXAd(BaseModel):
    """Represents a classified ad from OLX Brasil."""

    title: str
    price: float | None = None
    location: str | None = None
    date: str | None = None
    category: str | None = None
    description: str | None = None
    seller_name: str | None = None
    ad_url: str = ""
    image_url: str = ""
    is_professional: bool = False
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class OLXSearch(BaseModel):
    """Represents an OLX search result."""

    query: str
    total_results: int = 0
    ads: list[OLXAd] = Field(default_factory=list)
