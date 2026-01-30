"""
Silver Adverse Events Models

Pydantic models for the Silver adverse_events table (aggregated FAERS data).

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class AdverseEventBase(BaseModel):
    """Base adverse event fields."""
    meddra_pt: str = Field(..., description="MedDRA Preferred Term")
    meddra_pt_code: Optional[str] = None
    meddra_soc: Optional[str] = Field(None, description="System Organ Class")
    meddra_soc_code: Optional[str] = None
    report_count: int = Field(default=0, ge=0)
    serious_count: int = Field(default=0, ge=0)
    death_count: int = Field(default=0, ge=0)
    hospitalization_count: int = Field(default=0, ge=0)


class AdverseEventCreate(AdverseEventBase):
    """Model for creating an adverse event record."""
    molecule_id: UUID
    reporting_rate: Optional[float] = None
    prr: Optional[float] = Field(None, description="Proportional Reporting Ratio")
    ror: Optional[float] = Field(None, description="Reporting Odds Ratio")
    first_report_date: Optional[date] = None
    last_report_date: Optional[date] = None


class AdverseEvent(AdverseEventBase):
    """Full adverse event model from database."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    molecule_id: UUID
    reporting_rate: Optional[float] = None
    prr: Optional[float] = None
    ror: Optional[float] = None
    first_report_date: Optional[date] = None
    last_report_date: Optional[date] = None
    source: str = "openfda_faers"
    created_at: datetime
    updated_at: datetime


class AdverseEventSummary(BaseModel):
    """Summary of adverse events for a molecule."""
    molecule_id: UUID
    molecule_name: str
    total_reports: int
    serious_reports: int
    death_reports: int
    unique_events: int
    first_report_date: Optional[date]
    last_report_date: Optional[date]


class TopAdverseEvent(BaseModel):
    """Top adverse event with counts."""
    term: str
    count: int
    serious_count: int
    reporting_rate: Optional[float]
    prr: Optional[float] = None
    ror: Optional[float] = None


class SafetySignal(BaseModel):
    """Safety signal detection result."""
    molecule_id: UUID
    molecule_name: str
    meddra_pt: str
    report_count: int
    prr: float
    ror: float
    signal_strength: str = Field(..., description="Low, Medium, High")
    first_detected: date
    last_updated: date
