"""Pydantic models for Consumidor.gov.br complaint data."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Complaint(BaseModel):
    """Represents a single complaint from Consumidor.gov.br."""

    company_name: str
    complaint_id: str | None = None
    title: str | None = None
    description: str | None = None
    category: str | None = None
    subcategory: str | None = None
    date: str | None = None
    status: str | None = None
    response_time_days: int | None = None
    resolution_status: str | None = None
    complaint_url: str = ""
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class CompanyStats(BaseModel):
    """Aggregated company statistics from Consumidor.gov.br."""

    company_name: str
    total_complaints: int = 0
    response_rate: float | None = None
    avg_response_time_days: float | None = None
    resolution_rate: float | None = None
    complaints: list[Complaint] = Field(default_factory=list)
