"""Pydantic models for Google Maps business data scraped from HTML."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Business(BaseModel):
    """Represents a business/place scraped from Google Maps."""

    name: str
    category: str | None = None
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    opening_hours: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    place_url: str = ""
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class LeadSearch(BaseModel):
    """Represents a search result from Google Maps."""

    query: str
    location: str | None = None
    total: int = 0
    businesses: list[Business]
