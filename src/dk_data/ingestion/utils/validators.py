"""Pydantic validation models for raw data entities."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class CMSMedicareInpatientRecord(BaseModel):
    """Validation model for CMS Medicare Inpatient data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: str = Field(..., min_length=6, max_length=10)
    provider_name: Optional[str] = None
    provider_street_address: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = Field(None, max_length=2)
    provider_zip_code: Optional[str] = Field(None, max_length=10)
    drg_code: str = Field(..., max_length=10)
    drg_description: Optional[str] = None
    total_discharges: int = Field(..., ge=0)
    average_covered_charges: Optional[Decimal] = Field(None, ge=0)
    average_total_payments: Optional[Decimal] = Field(None, ge=0)
    average_medicare_payments: Optional[Decimal] = Field(None, ge=0)
    fiscal_year: int = Field(..., ge=2000, le=2100)

    @field_validator('provider_id')
    @classmethod
    def validate_provider_id(cls, v: str) -> str:
        """Validate CMS Provider ID format (6 characters)."""
        v = v.strip()
        if not v:
            raise ValueError("Provider ID cannot be empty")
        # Pad with leading zeros if needed
        return v.zfill(6)

    @field_validator('drg_code')
    @classmethod
    def validate_drg_code(cls, v: str) -> str:
        """Normalize DRG code."""
        return v.strip()

    @field_validator('provider_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        """Validate and uppercase state code."""
        if v is None:
            return None
        v = v.strip().upper()
        if len(v) != 2:
            raise ValueError("State must be 2 characters")
        return v


class ACCTVCCertificationRecord(BaseModel):
    """Validation model for ACC TVC certification data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    facility_name: str = Field(..., min_length=1)
    facility_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(None, max_length=2)
    zip_code: Optional[str] = Field(None, max_length=10)
    certification_type: str = Field(..., min_length=1)
    certification_date: Optional[date] = None
    expiration_date: Optional[date] = None

    @field_validator('state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v.strip().upper()


class HRSAShortageAreaRecord(BaseModel):
    """Validation model for HRSA shortage area data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    hpsa_id: str = Field(..., min_length=1)
    hpsa_name: Optional[str] = None
    hpsa_type: Optional[str] = None
    designation_type: Optional[str] = None
    state_abbr: str = Field(..., min_length=2, max_length=2)
    county_name: Optional[str] = None
    hpsa_score: Optional[int] = Field(None, ge=0, le=25)
    designation_date: Optional[date] = None
    rural_status: Optional[str] = None

    @field_validator('state_abbr')
    @classmethod
    def validate_state(cls, v: str) -> str:
        return v.strip().upper()


class CMSHospitalInfoRecord(BaseModel):
    """Validation model for CMS Hospital General Information."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: str = Field(..., min_length=6, max_length=10)
    hospital_name: str = Field(..., min_length=1)
    address: Optional[str] = None
    city: Optional[str] = None
    state: str = Field(..., min_length=2, max_length=2)
    zip_code: Optional[str] = Field(None, max_length=10)
    county_name: Optional[str] = None
    phone_number: Optional[str] = Field(None, max_length=20)
    hospital_type: Optional[str] = None
    hospital_ownership: Optional[str] = None
    emergency_services: Optional[bool] = None
    hospital_overall_rating: Optional[int] = Field(None, ge=1, le=5)

    @field_validator('provider_id')
    @classmethod
    def validate_provider_id(cls, v: str) -> str:
        v = v.strip()
        return v.zfill(6)

    @field_validator('state')
    @classmethod
    def validate_state(cls, v: str) -> str:
        return v.strip().upper()


class CMSCostReportRecord(BaseModel):
    """Validation model for CMS Cost Report data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: str = Field(..., min_length=6, max_length=10)
    fiscal_year_begin: Optional[date] = None
    fiscal_year_end: Optional[date] = None
    total_beds: Optional[int] = Field(None, ge=0)
    total_discharges: Optional[int] = Field(None, ge=0)
    net_patient_revenue: Optional[Decimal] = None
    total_operating_expenses: Optional[Decimal] = None
    operating_margin: Optional[Decimal] = Field(None, ge=-10, le=10)  # -1000% to 1000%

    @field_validator('provider_id')
    @classmethod
    def validate_provider_id(cls, v: str) -> str:
        v = v.strip()
        return v.zfill(6)


class StagingHospitalRecord(BaseModel):
    """Validation model for staging hospital records."""

    model_config = ConfigDict(str_strip_whitespace=True)

    hospital_id: str = Field(..., min_length=6, max_length=10)
    hospital_name: str = Field(..., min_length=1)
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: str = Field(..., min_length=2, max_length=2)
    zip_code: Optional[str] = Field(None, max_length=10)
    county: Optional[str] = None
    latitude: Optional[Decimal] = Field(None, ge=-90, le=90)
    longitude: Optional[Decimal] = Field(None, ge=-180, le=180)
    hospital_type: Optional[str] = None
    ownership_type: Optional[str] = None
    bed_count: Optional[int] = Field(None, ge=0)
    has_emergency_services: Optional[bool] = None
    cms_overall_rating: Optional[int] = Field(None, ge=1, le=5)


class TargetScoreRecord(BaseModel):
    """Validation model for target scores."""

    hospital_key: int = Field(..., ge=1)
    score_date: date
    clinical_readiness_score: Optional[int] = Field(None, ge=0, le=250)
    operational_readiness_score: Optional[int] = Field(None, ge=0, le=250)
    strategic_alignment_score: Optional[int] = Field(None, ge=0, le=200)
    financial_capacity_score: Optional[int] = Field(None, ge=0, le=150)
    champion_access_score: Optional[int] = Field(None, ge=0, le=150)
    bonus_points: int = Field(default=0, ge=0)
    penalty_points: int = Field(default=0, ge=0)
    total_trs: int = Field(..., ge=0, le=1000)
    tier_classification: str = Field(..., pattern='^[A-E]$')
    data_completeness: Optional[Decimal] = Field(None, ge=0, le=1)

    @field_validator('tier_classification')
    @classmethod
    def validate_tier(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ('A', 'B', 'C', 'D', 'E'):
            raise ValueError("Tier must be A, B, C, D, or E")
        return v


# TAVR-specific DRG codes
TAVR_DRG_CODES = {'266', '267'}


def is_tavr_drg(drg_code: str) -> bool:
    """Check if a DRG code is for TAVR procedures."""
    return drg_code.strip() in TAVR_DRG_CODES


def estimate_total_volume(medicare_volume: int, medicare_percentage: float = 0.65) -> int:
    """
    Estimate total TAVR volume from Medicare volume.

    Medicare represents approximately 65% of TAVR procedures.

    Args:
        medicare_volume: Number of Medicare TAVR discharges.
        medicare_percentage: Estimated Medicare market share (default: 0.65).

    Returns:
        Estimated total TAVR volume.
    """
    if medicare_volume <= 0:
        return 0
    return round(medicare_volume / medicare_percentage)


def calculate_tier(total_trs: int) -> str:
    """
    Calculate tier classification from total TRS score.

    Tier thresholds:
    - A: 800+
    - B: 600-799
    - C: 400-599
    - D: 200-399
    - E: <200
    """
    if total_trs >= 800:
        return 'A'
    elif total_trs >= 600:
        return 'B'
    elif total_trs >= 400:
        return 'C'
    elif total_trs >= 200:
        return 'D'
    else:
        return 'E'
