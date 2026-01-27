"""
Gold Safety Signals Models

Pydantic models for the Gold safety_signals view.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class RiskLevel(str, Enum):
    """Safety risk level."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class SafetySignals(BaseModel):
    """Aggregated safety signals for a molecule."""
    model_config = ConfigDict(from_attributes=True)

    molecule_id: UUID
    inchi_key: Optional[str]
    canonical_name: str

    # FAERS Summary
    total_reports: int = 0
    serious_reports: int = 0
    death_reports: int = 0
    hospitalization_reports: int = 0

    # Percentages
    serious_pct: float = 0.0
    death_pct: float = 0.0

    # Date range
    first_report_date: Optional[date]
    last_report_date: Optional[date]

    # Top adverse events with signal metrics
    top_adverse_events: Optional[List[Dict[str, Any]]]

    # SOC breakdown
    soc_distribution: Optional[Dict[str, Dict[str, int]]]

    # Boxed warning
    boxed_warning: Optional[str]
    warning_effective_date: Optional[date]
    has_boxed_warning: bool = False

    # Risk assessment
    risk_level: RiskLevel = RiskLevel.LOW

    generated_at: datetime


class SafetySignalSummary(BaseModel):
    """Summary of safety signals."""
    molecule_id: UUID
    canonical_name: str
    total_reports: int
    serious_pct: float
    has_boxed_warning: bool
    risk_level: RiskLevel


class AdverseEventSignal(BaseModel):
    """Individual adverse event signal."""
    term: str
    soc: Optional[str]
    count: int
    serious_count: int
    death_count: int
    reporting_rate: Optional[float]
    prr: Optional[float]
    ror: Optional[float]
    signal_strength: str


class SafetyComparison(BaseModel):
    """Safety comparison between molecules."""
    molecules: List[SafetySignalSummary]
    comparison_date: datetime
    notes: Optional[str] = None
