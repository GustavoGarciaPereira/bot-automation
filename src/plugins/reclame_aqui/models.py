"""Pydantic models for Reclame Aqui complaint data."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Complaint(BaseModel):
    """Represents a single complaint/review from Reclame Aqui."""

    title: str
    text: str | None = None
    date: str | None = None
    status: str | None = None  # "Respondida", "Não respondida", etc.
    company_response: str | None = None
    rating: float | None = None  # Nota do consumidor (0-10)
    category: str | None = None
    complaint_url: str = ""
    sentiment: str | None = None  # Preenchido depois pela IA
    theme: str | None = None      # Preenchido depois pela IA
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class CompanyReport(BaseModel):
    """Aggregated report for a company on Reclame Aqui."""

    company_name: str
    company_slug: str = ""
    total_complaints: int = 0
    complaints: list[Complaint] = Field(default_factory=list)
    avg_rating: float | None = None
    response_rate: float | None = None  # % de reclamações respondidas (0-100)
    period: str | None = None
