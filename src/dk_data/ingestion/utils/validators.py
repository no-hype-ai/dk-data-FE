"""Pydantic validation models for raw data entities."""

import math
from datetime import date
from decimal import Decimal
from typing import Any, ClassVar, List, Optional, Set
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class CMSPUFBaseRecord(BaseModel):
    """Base class for CMS PUF record validators.

    Converts all float NaN values (from pandas dtype=str CSV reads) to None
    before field validation runs.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    @model_validator(mode='before')
    @classmethod
    def coerce_nan_to_none(cls, values: Any) -> Any:
        if isinstance(values, dict):
            coerced = {}
            for k, v in values.items():
                if isinstance(v, float) and math.isnan(v):
                    coerced[k] = None
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    # Coerce numeric API values to str so Pydantic lax mode
                    # can parse them for both Optional[str] and Optional[Decimal] fields
                    coerced[k] = str(int(v)) if isinstance(v, float) and v == int(v) else str(v)
                else:
                    coerced[k] = v
            return coerced
        return values


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


class CMSGeographicVariationRecord(BaseModel):
    """Validation model for CMS Medicare Geographic Variation PUF data.

    Maps 1:1 to raw.cms_geographic_variation columns (excluding underscore-prefixed
    metadata columns set at INSERT time).

    CMS suppresses values below a threshold with '*'; these arrive as None
    after the CSV reader applies na_values=['*'].
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    year: int = Field(..., ge=2000, le=2100)

    # Geographic identifiers
    bene_geo_lvl: str = Field(..., min_length=1)    # National / State / County
    bene_geo_desc: str = Field(..., min_length=1)   # Description text
    bene_geo_cd: Optional[str] = None               # FIPS code as TEXT

    # Beneficiary demographic slice
    bene_age_lvl: Optional[str] = None
    bene_demo_lvl: Optional[str] = None
    bene_demo_desc: Optional[str] = None
    bene_mcc_lvl: Optional[str] = None

    # Counts
    tot_benes: Optional[int] = Field(None, ge=0)

    # Utilization rates
    ip_cvrd_stays_per_1000_benes: Optional[Decimal] = None
    er_visits_per_1000_benes: Optional[Decimal] = None
    hosp_readmsn_rate: Optional[Decimal] = None
    acute_hosp_readmsn_rate: Optional[Decimal] = None

    # Spending per capita
    tot_mdcr_stdzd_pymt_pc: Optional[Decimal] = None
    tot_mdcr_stdzd_pymt_pct_chg: Optional[Decimal] = None
    tot_mdcr_pymt_pc: Optional[Decimal] = None
    tot_mdcr_alowd_amt_pc: Optional[Decimal] = None

    # Medicare Advantage
    ma_prtcptn_rate: Optional[Decimal] = None

    @field_validator('bene_geo_cd')
    @classmethod
    def preserve_fips_text(cls, v: Optional[str]) -> Optional[str]:
        """Keep FIPS codes as TEXT (leading zeros must not be stripped)."""
        if v is None:
            return None
        return v.strip() or None


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


# =============================================================================
# CI Source Validators (Tier 4)
# =============================================================================


class PubMedRecord(BaseModel):
    """Validation model for PubMed/MEDLINE articles."""

    model_config = ConfigDict(str_strip_whitespace=True)

    pmid: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    abstract: Optional[str] = None
    authors: Optional[Any] = None  # JSONB
    journal: Optional[str] = None
    publication_date: Optional[date] = None
    mesh_terms: Optional[list[str]] = None
    doi: Optional[str] = None
    publication_types: Optional[list[str]] = None
    keywords: Optional[list[str]] = None

    @field_validator('pmid')
    @classmethod
    def validate_pmid(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError('PMID must be numeric')
        return v

    @field_validator('doi')
    @classmethod
    def validate_doi(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if v and not v.startswith('10.'):
            raise ValueError('DOI must start with 10.')
        return v


class OpenAlexCIRecord(BaseModel):
    """Validation model for OpenAlex CI publications."""

    model_config = ConfigDict(str_strip_whitespace=True)

    work_id: str = Field(..., min_length=1)
    doi: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    publication_date: Optional[date] = None
    cited_by_count: Optional[int] = Field(None, ge=0)
    concepts: Optional[Any] = None  # JSONB
    authorships: Optional[Any] = None  # JSONB
    primary_location: Optional[Any] = None  # JSONB
    open_access: Optional[Any] = None  # JSONB

    @field_validator('work_id')
    @classmethod
    def validate_work_id(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith('W'):
            raise ValueError('OpenAlex work_id must start with W')
        return v


class EMARegulatoryCIRecord(BaseModel):
    """Validation model for EMA regulatory decisions.

    Maps 1:1 to raw.ema_regulatory columns (excluding underscore-prefixed
    metadata columns that are set at INSERT time).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    VALID_DOCUMENT_TYPES: ClassVar[Set[str]] = {
        'chmp_opinion', 'epar', 'referral', 'safety_signal',
    }
    VALID_DECISION_TYPES: ClassVar[Set[str]] = {
        'authorisation', 'variation', 'withdrawal', 'suspension',
        'renewal', 'referral', 'orphan_designation', 'paediatric',
        'advanced_therapy', 'biosimilar', 'conditional_approval',
        'exceptional_circumstances', 'sunset_clause',
    }

    document_id: str = Field(..., min_length=1, max_length=100)
    document_type: Optional[str] = Field(None, max_length=50)
    product_name: Optional[str] = Field(None, max_length=500)
    active_substance: Optional[str] = Field(None, max_length=500)
    therapeutic_area: Optional[str] = Field(None, max_length=500)
    decision_date: Optional[date] = None
    decision_type: Optional[str] = Field(None, max_length=100)
    document_url: Optional[str] = None
    summary: Optional[str] = None

    @field_validator('document_type')
    @classmethod
    def validate_document_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        # Allow document types not in the canonical set (API may return new types)
        return v

    @field_validator('decision_type')
    @classmethod
    def validate_decision_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower().replace(' ', '_').replace('-', '_')
        if v not in cls.VALID_DECISION_TYPES:
            raise ValueError(
                f"Invalid decision_type '{v}'. "
                f"Must be one of: {sorted(cls.VALID_DECISION_TYPES)}"
            )
        return v

    @field_validator('decision_date', mode='before')
    @classmethod
    def parse_decision_date(cls, v: Any) -> Optional[date]:
        """Accept ISO-format date strings and date objects."""
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
            from datetime import datetime as _dt
            try:
                return _dt.strptime(v[:10], '%Y-%m-%d').date()
            except ValueError:
                raise ValueError(f'Cannot parse date: {v}')
        return v


class JournalRSSRecord(BaseModel):
    """Validation model for Journal RSS feed articles."""

    model_config = ConfigDict(str_strip_whitespace=True)

    article_id: str = Field(..., min_length=1)
    feed_source: str = Field(..., min_length=1)
    title: Optional[str] = None
    authors: Optional[str] = None
    abstract: Optional[str] = None
    publication_date: Optional[date] = None
    link: Optional[str] = None
    doi: Optional[str] = None
    categories: Optional[list[str]] = None


class USPTOCIRecord(BaseModel):
    """Validation model for USPTO CI patents."""

    model_config = ConfigDict(str_strip_whitespace=True)

    patent_id: str = Field(..., min_length=1)
    title: Optional[str] = None
    abstract: Optional[str] = None
    inventors: Optional[Any] = None  # JSONB
    assignees: Optional[Any] = None  # JSONB
    filing_date: Optional[date] = None
    grant_date: Optional[date] = None
    cpc_codes: Optional[list[str]] = None
    claims_count: Optional[int] = Field(None, ge=0)


class USPTOPatentsRecord(BaseModel):
    """Validation model for USPTO PatentsView direct patent data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    patent_number: str = Field(..., min_length=1)
    title: Optional[str] = None
    abstract: Optional[str] = None
    inventors: Optional[Any] = None  # JSONB
    assignees: Optional[Any] = None  # JSONB
    filing_date: Optional[date] = None
    grant_date: Optional[date] = None
    cpc_codes: Optional[list[str]] = None
    claims_count: Optional[int] = Field(None, ge=0)


class DrugBankRecord(BaseModel):
    """Validation model for DrugBank drug entries."""

    model_config = ConfigDict(str_strip_whitespace=True)

    drugbank_id: str = Field(..., min_length=1)  # DB00001 format
    name: Optional[str] = None
    description: Optional[str] = None
    cas_number: Optional[str] = None
    categories: Optional[list[str]] = None
    targets: Optional[Any] = None  # JSONB
    enzymes: Optional[Any] = None  # JSONB
    indication: Optional[str] = None
    pharmacodynamics: Optional[str] = None

    @field_validator('drugbank_id')
    @classmethod
    def validate_drugbank_id(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith('DB'):
            raise ValueError('DrugBank ID must start with DB')
        return v


class HTADecisionRecord(BaseModel):
    """Validation model for HTA body decisions."""

    model_config = ConfigDict(str_strip_whitespace=True)

    VALID_AGENCIES: ClassVar[Set[str]] = {'nice', 'gba', 'has', 'pbac'}

    decision_id: str = Field(..., min_length=1)
    agency: str = Field(..., min_length=1)
    drug_name: Optional[str] = None
    indication: Optional[str] = None
    decision_type: Optional[str] = None
    decision_date: Optional[date] = None
    document_url: Optional[str] = None
    summary: Optional[str] = None

    @field_validator('agency')
    @classmethod
    def validate_agency(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in cls.VALID_AGENCIES:
            raise ValueError(f'agency must be one of {cls.VALID_AGENCIES}')
        return v


class EPOPatentRecord(BaseModel):
    """Validation model for EPO OPS patents."""

    model_config = ConfigDict(str_strip_whitespace=True)

    publication_id: str = Field(..., min_length=1)
    title: Optional[str] = None
    abstract: Optional[str] = None
    applicants: Optional[Any] = None  # JSONB
    inventors: Optional[Any] = None  # JSONB
    filing_date: Optional[date] = None
    publication_date: Optional[date] = None
    ipc_codes: Optional[list[str]] = None
    family_id: Optional[str] = None


class CochraneReviewRecord(BaseModel):
    """Validation model for Cochrane reviews."""

    model_config = ConfigDict(str_strip_whitespace=True)

    review_id: str = Field(..., min_length=1)
    title: Optional[str] = None
    authors: Optional[str] = None
    abstract: Optional[str] = None
    publication_date: Optional[date] = None
    review_type: Optional[str] = None
    interventions: Optional[list[str]] = None
    conditions: Optional[list[str]] = None
    conclusions: Optional[str] = None
    doi: Optional[str] = None


class MedicalNewsRecord(BaseModel):
    """Validation model for medical news articles."""

    model_config = ConfigDict(str_strip_whitespace=True)

    article_id: str = Field(..., min_length=1)
    source_name: str = Field(..., min_length=1)
    title: Optional[str] = None
    summary: Optional[str] = None
    publication_date: Optional[date] = None
    url: Optional[str] = None
    drug_mentions: Optional[list[str]] = None
    therapeutic_areas: Optional[list[str]] = None


class SECEdgarRecord(BaseModel):
    """Validation model for SEC EDGAR filings."""

    model_config = ConfigDict(str_strip_whitespace=True)

    VALID_FILING_TYPES: ClassVar[Set[str]] = {'10-K', '10-Q', '8-K'}

    accession_number: str = Field(..., min_length=1)
    company_name: Optional[str] = None
    cik: Optional[str] = None
    filing_type: str = Field(..., min_length=1)
    filing_date: Optional[date] = None
    document_url: Optional[str] = None
    description: Optional[str] = None

    @field_validator('filing_type')
    @classmethod
    def validate_filing_type(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in cls.VALID_FILING_TYPES:
            raise ValueError(f'filing_type must be one of {cls.VALID_FILING_TYPES}')
        return v

    @field_validator('cik')
    @classmethod
    def validate_cik(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if v and not v.isdigit():
            raise ValueError('CIK must be numeric')
        return v


# =============================================================================
# Molecule Data Source Validators (012-platform-hardening)
# =============================================================================


class UniProtRecord(BaseModel):
    """Validation model for UniProt protein entries."""

    model_config = ConfigDict(str_strip_whitespace=True)

    accession: str = Field(..., min_length=1, max_length=20)
    entry_name: Optional[str] = Field(None, max_length=50)
    protein_name: Optional[str] = None
    gene_name: Optional[str] = Field(None, max_length=50)
    organism: Optional[str] = Field(None, max_length=200)
    sequence_length: Optional[int] = Field(None, ge=0)
    function_description: Optional[str] = None

    @field_validator('accession')
    @classmethod
    def validate_accession(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('UniProt accession cannot be empty')
        return v


class PDBRecord(BaseModel):
    """Validation model for RCSB PDB structure entries."""

    model_config = ConfigDict(str_strip_whitespace=True)

    pdb_id: str = Field(..., min_length=4, max_length=4)
    title: Optional[str] = None
    method: Optional[str] = Field(None, max_length=100)
    resolution: Optional[float] = Field(None, ge=0)
    deposit_date: Optional[str] = None

    @field_validator('pdb_id')
    @classmethod
    def validate_pdb_id(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 4:
            raise ValueError('PDB ID must be exactly 4 characters')
        return v


class ORCIDRecord(BaseModel):
    """Validation model for ORCID researcher profiles."""

    model_config = ConfigDict(str_strip_whitespace=True)

    orcid_id: str = Field(..., min_length=19, max_length=19)
    given_names: Optional[str] = Field(None, max_length=255)
    family_name: Optional[str] = Field(None, max_length=255)
    credit_name: Optional[str] = Field(None, max_length=500)

    @field_validator('orcid_id')
    @classmethod
    def validate_orcid_id(cls, v: str) -> str:
        v = v.strip()
        parts = v.split('-')
        if len(parts) != 4 or not all(len(p) == 4 for p in parts):
            raise ValueError('ORCID iD must be in format 0000-0000-0000-000X')
        return v


# =============================================================================
# IP / Trademark Data Source Validators (014-uspto-euipo-model-datasource)
# =============================================================================


class USPTOTrademarkRecord(BaseModel):
    """Validation model for USPTO TSDR trademark records."""

    model_config = ConfigDict(str_strip_whitespace=True)

    serial_number: str = Field(..., min_length=1)
    mark_element: Optional[str] = None
    mark_type: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, max_length=100)
    status_code: Optional[int] = None
    status_date: Optional[date] = None
    filing_date: Optional[date] = None
    registration_number: Optional[str] = Field(None, max_length=20)
    registration_date: Optional[date] = None
    nice_classes: Optional[List[int]] = None
    us_classes: Optional[List[str]] = None
    owner_name: Optional[str] = None
    owner_entity_type: Optional[str] = Field(None, max_length=50)
    goods_and_services: Optional[str] = None
    description_of_mark: Optional[str] = None

    @field_validator('serial_number')
    @classmethod
    def validate_serial_number(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('serial_number cannot be empty')
        return v


class EUIPOTrademarkRecord(BaseModel):
    """Validation model for EUIPO trademark records (TMview/IBM Gateway)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    application_number: str = Field(..., min_length=1)
    mark_name: Optional[str] = None
    mark_kind: Optional[str] = Field(None, max_length=50)
    mark_feature: Optional[str] = Field(None, max_length=50)
    mark_basis: Optional[str] = Field(None, max_length=50)
    applicant_name: Optional[str] = None
    applicant_country: Optional[str] = Field(None, max_length=10)
    representative_name: Optional[str] = None
    status: Optional[str] = Field(None, max_length=100)
    filing_date: Optional[date] = None
    registration_date: Optional[date] = None
    expiry_date: Optional[date] = None
    nice_classes: Optional[List[int]] = None
    goods_and_services: Optional[str] = None
    image_url: Optional[str] = None

    @field_validator('application_number')
    @classmethod
    def validate_application_number(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('application_number cannot be empty')
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


# =============================================================================
# CMS PUF Platform Validators (019-cms-puf-platform-reconciliation)
# =============================================================================


class CMSChronicConditionsRecord(CMSPUFBaseRecord):
    """Validation model for CMS Chronic Conditions PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    bene_geo_lvl: Optional[str] = None
    bene_geo_desc: Optional[str] = None
    bene_geo_cd: Optional[str] = None
    bene_age_lvl: Optional[str] = None
    bene_demo_lvl: Optional[str] = None
    bene_demo_desc: Optional[str] = None
    bene_cond: Optional[str] = None
    prvlnc: Optional[Decimal] = None
    tot_mdcr_stdzd_pymt_pc: Optional[Decimal] = None
    tot_mdcr_pymt_pc: Optional[Decimal] = None
    hosp_readmsn_rate: Optional[Decimal] = None
    ed_visits_per_1000_benes: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSClaimTypeRecord(CMSPUFBaseRecord):
    """Validation model for CMS Claim Type Utilization PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    bene_geo_lvl: Optional[str] = None
    bene_geo_desc: Optional[str] = None
    clm_type: Optional[str] = None
    clm_type_desc: Optional[str] = None
    tot_clms: Optional[int] = None
    tot_benes: Optional[int] = None
    tot_mdcr_pymt_amt: Optional[Decimal] = None
    avg_mdcr_pymt_amt: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSCostReportsPUFRecord(CMSPUFBaseRecord):
    """Validation model for CMS Cost Reports PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: str = Field(..., min_length=1)
    hospital_name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    fiscal_year_begin: Optional[date] = None
    fiscal_year_end: Optional[date] = None
    total_beds: Optional[int] = Field(None, ge=0)
    total_discharges: Optional[int] = Field(None, ge=0)
    net_patient_revenue: Optional[Decimal] = None
    total_operating_expenses: Optional[Decimal] = None
    operating_margin: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSDMERecord(CMSPUFBaseRecord):
    """Validation model for CMS Durable Medical Equipment (DME) PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    provider_last_org_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    provider_state_fips: Optional[str] = None
    provider_zip5: Optional[str] = None
    provider_ruca: Optional[str] = None
    provider_type: Optional[str] = None
    hcpcs_cd: Optional[str] = None
    hcpcs_desc: Optional[str] = None
    suplr_rentl_ind: Optional[str] = None
    tot_suplrs: Optional[int] = None
    tot_suplr_benes: Optional[int] = None
    tot_suplr_clms: Optional[int] = None
    tot_suplr_srvcs: Optional[int] = None
    avg_suplr_sbmtd_chrg: Optional[Decimal] = None
    avg_suplr_mdcr_alowd_amt: Optional[Decimal] = None
    avg_suplr_mdcr_pymt_amt: Optional[Decimal] = None
    avg_suplr_mdcr_stdzd_amt: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSDualEligibleRecord(CMSPUFBaseRecord):
    """Validation model for CMS Dual Eligible Beneficiary data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    state_cd: Optional[str] = None
    state_name: Optional[str] = None
    dual_elgbl_lvl: Optional[str] = None
    dual_elgbl_desc: Optional[str] = None
    tot_benes: Optional[int] = None
    ffs_benes: Optional[int] = None
    ma_benes: Optional[int] = None
    dual_elgbl_full_benes: Optional[int] = None
    dual_elgbl_prtl_benes: Optional[int] = None
    non_dual_benes: Optional[int] = None
    lis_benes: Optional[int] = None
    _source_year: Optional[int] = None


class CMSEnrollmentRecord(CMSPUFBaseRecord):
    """Validation model for CMS Medicare Enrollment PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    state_cd: Optional[str] = None
    county_cd: Optional[str] = None
    county_desc: Optional[str] = None
    bene_demo_lvl: Optional[str] = None
    bene_demo_desc: Optional[str] = None
    bene_age_lvl: Optional[str] = None
    tot_benes: Optional[int] = None
    orgnl_mdcr_benes: Optional[int] = None
    ma_benes: Optional[int] = None
    esrd_benes: Optional[int] = None
    dsbl_benes: Optional[int] = None
    _source_year: Optional[int] = None


class CMSHomeHealthRecord(CMSPUFBaseRecord):
    """Validation model for CMS Home Health Agency PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    provider_zip5: Optional[str] = None
    hh_srvc_cd: Optional[str] = None
    hh_srvc_desc: Optional[str] = None
    tot_epsd_stay: Optional[int] = None
    tot_benes: Optional[int] = None
    avg_hh_mdcr_pymt_amt: Optional[Decimal] = None
    avg_hh_outlier_pymt: Optional[Decimal] = None
    avg_age: Optional[Decimal] = None
    female_pct: Optional[Decimal] = None
    dual_pct: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSHospiceRecord(CMSPUFBaseRecord):
    """Validation model for CMS Hospice Provider PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    provider_zip5: Optional[str] = None
    hspce_cd: Optional[str] = None
    hspce_desc: Optional[str] = None
    tot_benes: Optional[int] = None
    tot_mdcr_alowd_amt: Optional[Decimal] = None
    tot_mdcr_pymt_amt: Optional[Decimal] = None
    avg_mdcr_pymt_amt: Optional[Decimal] = None
    avg_age: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSHospitalGeneralInfoRecord(CMSPUFBaseRecord):
    """Validation model for CMS Hospital General Information PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    facility_id: Optional[str] = None
    facility_name: Optional[str] = None
    address: Optional[str] = None
    city_town: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    county_parish: Optional[str] = None
    telephone_number: Optional[str] = None
    hospital_type: Optional[str] = None
    hospital_ownership: Optional[str] = None
    emergency_services: Optional[str] = None
    meets_criteria_for_birthing_friendly_designation: Optional[str] = None
    hospital_overall_rating: Optional[int] = None
    hospital_overall_rating_footnote: Optional[str] = None
    _source_year: Optional[int] = None

    @field_validator('hospital_overall_rating', mode='before')
    @classmethod
    def coerce_overall_rating(cls, v: Any) -> Optional[int]:
        if v is None or v == '' or str(v).strip().lower() in ('not available', 'n/a', 'na'):
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None


class CMSImagingRecord(CMSPUFBaseRecord):
    """Validation model for CMS Imaging Services PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    provider_last_org_name: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    provider_zip5: Optional[str] = None
    provider_type: Optional[str] = None
    hcpcs_cd: Optional[str] = None
    hcpcs_desc: Optional[str] = None
    tot_benes: Optional[int] = None
    tot_srvcs: Optional[int] = None
    tot_mdcr_alowd_amt: Optional[Decimal] = None
    avg_mdcr_alowd_amt: Optional[Decimal] = None
    avg_mdcr_pymt_amt: Optional[Decimal] = None
    avg_mdcr_stdzd_amt: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSInpatientPUFRecord(CMSPUFBaseRecord):
    """Validation model for CMS Inpatient PUF provider-level charge data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    drg_cd: Optional[str] = None
    drg_definition: Optional[str] = None
    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    provider_street_address: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    provider_state_fips: Optional[str] = None
    provider_zip_code: Optional[str] = None
    provider_ruca: Optional[str] = None
    hospital_referral_region_desc: Optional[str] = None
    total_discharges: Optional[int] = None
    average_covered_charges: Optional[Decimal] = None
    average_total_payments: Optional[Decimal] = None
    average_medicare_payments: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSLabServicesRecord(CMSPUFBaseRecord):
    """Validation model for CMS Lab Services PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    provider_last_org_name: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    provider_zip5: Optional[str] = None
    provider_type: Optional[str] = None
    hcpcs_cd: Optional[str] = None
    hcpcs_desc: Optional[str] = None
    tot_benes: Optional[int] = None
    tot_srvcs: Optional[int] = None
    tot_mdcr_alowd_amt: Optional[Decimal] = None
    avg_mdcr_alowd_amt: Optional[Decimal] = None
    avg_mdcr_pymt_amt: Optional[Decimal] = None
    avg_mdcr_stdzd_amt: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSMedicaidDrugSpendingRecord(CMSPUFBaseRecord):
    """Validation model for CMS Medicaid Drug Spending data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    brnd_name: Optional[str] = None
    gnrc_name: Optional[str] = None
    tot_mftr: Optional[str] = None
    util_type: Optional[str] = None
    tot_spndng: Optional[Decimal] = None
    medicaid_spndng_per_dosage_unit: Optional[Decimal] = None
    medicaid_spndng_per_prescription: Optional[Decimal] = None
    unit_type: Optional[str] = None
    tot_dosage_units: Optional[Decimal] = None
    tot_prescriptions: Optional[Decimal] = None
    tot_benes: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSMedicareAdvantageRecord(CMSPUFBaseRecord):
    """Validation model for CMS Medicare Advantage enrollment data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    contract_id: Optional[str] = None
    organization_name: Optional[str] = None
    organization_type: Optional[str] = None
    plan_id: Optional[str] = None
    plan_name: Optional[str] = None
    segment_id: Optional[str] = None
    enrollment_data_period: Optional[str] = None
    fips_cd: Optional[str] = None
    state_fips: Optional[str] = None
    county_fips: Optional[str] = None
    enrollment: Optional[int] = None
    avg_age: Optional[str] = None
    pct_female: Optional[str] = None
    avg_risk_score: Optional[str] = None
    ma_participation_rate: Optional[str] = None
    star_rating: Optional[str] = None
    _source_year: Optional[int] = None


class CMSMentalHealthRecord(CMSPUFBaseRecord):
    """Validation model for CMS Mental Health PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    provider_last_org_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    provider_zip5: Optional[str] = None
    provider_type: Optional[str] = None
    hcpcs_cd: Optional[str] = None
    hcpcs_desc: Optional[str] = None
    mh_srvc_ind: Optional[str] = None
    tot_benes: Optional[int] = None
    tot_srvcs: Optional[str] = None
    tot_mdcr_alowd_amt: Optional[Decimal] = None
    avg_mdcr_alowd_amt: Optional[Decimal] = None
    avg_mdcr_pymt_amt: Optional[Decimal] = None
    avg_mdcr_stdzd_amt: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSNPPESRecord(CMSPUFBaseRecord):
    """Validation model for CMS NPPES National Provider Identifier data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    entity_type_code: Optional[str] = None
    provider_last_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_organization_name: Optional[str] = None
    provider_credential_text: Optional[str] = None
    provider_first_line_business_mailing_address: Optional[str] = None
    provider_second_line_business_mailing_address: Optional[str] = None
    provider_business_mailing_address_city_name: Optional[str] = None
    provider_business_mailing_address_state_name: Optional[str] = None
    provider_business_mailing_address_postal_code: Optional[str] = None
    provider_business_mailing_address_telephone_number: Optional[str] = None
    provider_first_line_business_practice_location_address: Optional[str] = None
    provider_second_line_business_practice_location_address: Optional[str] = None
    provider_business_practice_location_address_city_name: Optional[str] = None
    provider_business_practice_location_address_state_name: Optional[str] = None
    provider_business_practice_location_address_postal_code: Optional[str] = None
    provider_business_practice_location_address_country_code: Optional[str] = None
    provider_business_practice_location_address_telephone_number: Optional[str] = None
    provider_business_practice_location_address_fax_number: Optional[str] = None
    healthcare_provider_taxonomy_code_1: Optional[str] = None
    healthcare_provider_taxonomy_code_2: Optional[str] = None
    npi_deactivation_date: Optional[date] = None
    npi_reactivation_date: Optional[date] = None
    _source_year: Optional[int] = None


class CMSOpenPaymentsRecord(CMSPUFBaseRecord):
    """Validation model for CMS Open Payments (Sunshine Act) data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    covered_recipient_type: Optional[str] = None
    physician_profile_id: Optional[str] = None
    physician_first_name: Optional[str] = None
    physician_last_name: Optional[str] = None
    physician_specialty: Optional[str] = None
    applicable_manufacturer_or_gpo_name: Optional[str] = None
    total_amount_of_payment_usdollars: Optional[Decimal] = None
    date_of_payment: Optional[str] = None
    number_of_payments_included_in_total_amount: Optional[int] = None
    form_of_payment_or_transfer_of_value: Optional[str] = None
    nature_of_payment_or_transfer_of_value: Optional[str] = None
    recipient_city: Optional[str] = None
    recipient_state: Optional[str] = None
    recipient_zip_code: Optional[str] = None
    payment_publication_date: Optional[str] = None
    record_id: Optional[str] = None
    program_year: Optional[str] = None
    name_of_drug_or_biological_or_device_or_medical_supply_1: Optional[str] = None
    name_of_drug_or_biological_or_device_or_medical_supply_2: Optional[str] = None
    name_of_drug_or_biological_or_device_or_medical_supply_3: Optional[str] = None
    name_of_drug_or_biological_or_device_or_medical_supply_4: Optional[str] = None
    name_of_drug_or_biological_or_device_or_medical_supply_5: Optional[str] = None
    associated_drug_or_biological_ndc_1: Optional[str] = None
    associated_drug_or_biological_ndc_2: Optional[str] = None
    associated_drug_or_biological_ndc_3: Optional[str] = None
    associated_drug_or_biological_ndc_4: Optional[str] = None
    associated_drug_or_biological_ndc_5: Optional[str] = None
    _source_year: Optional[int] = None


class CMSOpioidRecord(CMSPUFBaseRecord):
    """Validation model for CMS Opioid Prescribing Geographic Variation PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    prscrbr_npi: Optional[str] = None
    prscrbr_last_org_name: Optional[str] = None
    prscrbr_first_name: Optional[str] = None
    prscrbr_city: Optional[str] = None
    prscrbr_state_abrvtn: Optional[str] = None
    prscrbr_state_fips: Optional[str] = None
    prscrbr_type: Optional[str] = None
    prscrbr_type_src: Optional[str] = None
    brnd_name: Optional[str] = None
    gnrc_name: Optional[str] = None
    opioid_drug_flag: Optional[str] = None
    la_opioid_drug_flag: Optional[str] = None
    tot_clms: Optional[int] = None
    tot_30day_fills: Optional[Decimal] = None
    tot_day_suply: Optional[int] = None
    tot_drug_cst: Optional[Decimal] = None
    tot_benes: Optional[int] = None
    opioid_clms: Optional[int] = None
    opioid_benes: Optional[int] = None
    la_opioid_clms: Optional[int] = None
    la_opioid_benes: Optional[int] = None
    _source_year: Optional[int] = None


class CMSOrderingProviderRecord(CMSPUFBaseRecord):
    """Validation model for CMS Ordering Providers PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    rndrng_npi: Optional[str] = None
    rndrng_prvdr_last_org_name: Optional[str] = None
    rndrng_prvdr_first_name: Optional[str] = None
    rndrng_prvdr_city: Optional[str] = None
    rndrng_prvdr_state_abrvtn: Optional[str] = None
    rndrng_prvdr_zip5: Optional[str] = None
    rndrng_prvdr_type: Optional[str] = None
    rfrd_npi: Optional[str] = None
    rfrd_prvdr_last_org_name: Optional[str] = None
    rfrd_prvdr_type: Optional[str] = None
    tot_srvcs: Optional[str] = None
    tot_benes: Optional[int] = None
    tot_mdcr_alowd_amt: Optional[Decimal] = None
    tot_mdcr_pymt_amt: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSOutpatientRecord(CMSPUFBaseRecord):
    """Validation model for CMS Outpatient PUF hospital APC-level charge data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    provider_street_address: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    provider_state_fips: Optional[str] = None
    provider_zip_code: Optional[str] = None
    provider_ruca: Optional[str] = None
    apc: Optional[str] = None
    apc_desc: Optional[str] = None
    total_services: Optional[int] = None
    bene_cnt: Optional[int] = None
    comp_asgn_pymt_cnt: Optional[int] = None
    average_estimated_submitted_charges: Optional[Decimal] = None
    average_medicare_allowed_amt: Optional[Decimal] = None
    average_total_payments: Optional[Decimal] = None
    average_medicare_payments: Optional[Decimal] = None
    average_medicare_stnd_amt: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSPartBSpendingRecord(CMSPUFBaseRecord):
    """Validation model for CMS Part B Drug Spending data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    hcpcs_cd: Optional[str] = None
    hcpcs_desc: Optional[str] = None
    tot_mftr: Optional[str] = None
    mftr_name: Optional[str] = None
    tot_spndng: Optional[Decimal] = None
    tot_dsg_unts: Optional[Decimal] = None
    tot_benes: Optional[Decimal] = None
    tot_clms: Optional[Decimal] = None
    avg_spnd_per_dsg_unt: Optional[Decimal] = None
    avg_spnd_per_clm: Optional[Decimal] = None
    avg_spnd_per_bene: Optional[Decimal] = None
    outlier_flag: Optional[str] = None
    _source_year: Optional[int] = None


class CMSPartDPrescriberRecord(CMSPUFBaseRecord):
    """Validation model for CMS Part D Prescribers by Provider and Drug data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    prscrbr_npi: str = Field(..., min_length=1)
    prscrbr_last_org_name: Optional[str] = None
    prscrbr_first_name: Optional[str] = None
    prscrbr_city: Optional[str] = None
    prscrbr_state_abrvtn: Optional[str] = None
    prscrbr_state_fips: Optional[str] = None
    prscrbr_type: Optional[str] = None
    prscrbr_type_src: Optional[str] = None
    brnd_name: Optional[str] = None
    gnrc_name: str = Field(..., min_length=1)
    tot_clms: Optional[int] = None
    tot_30day_fills: Optional[str] = None
    tot_day_suply: Optional[int] = None
    tot_drug_cst: Optional[str] = None
    tot_benes: Optional[int] = None
    ge65_sprsn_flag: Optional[str] = None
    ge65_tot_clms: Optional[int] = None
    ge65_tot_30day_fills: Optional[str] = None
    ge65_tot_drug_cst: Optional[str] = None
    ge65_tot_day_suply: Optional[int] = None
    ge65_bene_sprsn_flag: Optional[str] = None
    ge65_tot_benes: Optional[int] = None
    _source_year: Optional[int] = None


class CMSPartDSpendingRecord(CMSPUFBaseRecord):
    """Validation model for CMS Part D Drug Spending data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    brnd_name: Optional[str] = None
    gnrc_name: Optional[str] = None
    tot_mftr: Optional[str] = None
    tot_spndng: Optional[Decimal] = None
    tot_dsg_unts: Optional[Decimal] = None
    tot_clms: Optional[Decimal] = None
    tot_benes: Optional[Decimal] = None
    avg_spnd_per_dsg_unt_wghtd: Optional[Decimal] = None
    avg_spnd_per_clm: Optional[Decimal] = None
    avg_spnd_per_bene: Optional[Decimal] = None
    outlier_flag: Optional[str] = None
    _source_year: Optional[int] = None


class CMSPhysicianPUFRecord(CMSPUFBaseRecord):
    """Validation model for CMS Physician and Other Practitioners PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    nppes_provider_last_org_name: Optional[str] = None
    nppes_provider_first_name: Optional[str] = None
    nppes_provider_mi: Optional[str] = None
    nppes_credentials: Optional[str] = None
    nppes_provider_gender: Optional[str] = None
    nppes_entity_code: Optional[str] = None
    nppes_provider_street1: Optional[str] = None
    nppes_provider_street2: Optional[str] = None
    nppes_provider_city: Optional[str] = None
    nppes_provider_state: Optional[str] = None
    nppes_provider_state_fips: Optional[str] = None
    nppes_provider_zip: Optional[str] = None
    nppes_provider_ruca: Optional[str] = None
    nppes_provider_country: Optional[str] = None
    provider_type: Optional[str] = None
    medicare_participation_indicator: Optional[str] = None
    number_of_hcpcs: Optional[int] = None
    total_services: Optional[str] = None
    total_unique_benes: Optional[int] = None
    total_submitted_chrg_amt: Optional[Decimal] = None
    total_medicare_allowed_amt: Optional[Decimal] = None
    total_medicare_payment_amt: Optional[Decimal] = None
    total_medicare_stnd_amt: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSReferringProviderRecord(CMSPUFBaseRecord):
    """Validation model for CMS Referring Providers PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    rndrng_npi: Optional[str] = None
    rndrng_prvdr_last_org_name: Optional[str] = None
    rndrng_prvdr_first_name: Optional[str] = None
    rndrng_prvdr_city: Optional[str] = None
    rndrng_prvdr_state_abrvtn: Optional[str] = None
    rndrng_prvdr_zip5: Optional[str] = None
    rndrng_prvdr_type: Optional[str] = None
    rfrd_npi: Optional[str] = None
    rfrd_prvdr_last_org_name: Optional[str] = None
    rfrd_prvdr_type: Optional[str] = None
    tot_srvcs: Optional[str] = None
    tot_benes: Optional[int] = None
    tot_mdcr_alowd_amt: Optional[Decimal] = None
    tot_mdcr_pymt_amt: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSSNFRecord(CMSPUFBaseRecord):
    """Validation model for CMS Skilled Nursing Facility (SNF) PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    provider_zip5: Optional[str] = None
    rug_cd: Optional[str] = None
    rug_desc: Optional[str] = None
    tot_benes: Optional[int] = None
    tot_cvrd_days: Optional[int] = None
    avg_cvrd_days: Optional[Decimal] = None
    tot_mdcr_alowd_amt: Optional[Decimal] = None
    avg_mdcr_alowd_amt: Optional[Decimal] = None
    tot_mdcr_pymt_amt: Optional[Decimal] = None
    avg_mdcr_pymt_amt: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSTelehealthRecord(CMSPUFBaseRecord):
    """Validation model for CMS Telehealth Utilization PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    provider_last_org_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    provider_zip5: Optional[str] = None
    provider_type: Optional[str] = None
    hcpcs_cd: Optional[str] = None
    hcpcs_desc: Optional[str] = None
    th_srvc_ind: Optional[str] = None
    tot_benes: Optional[int] = None
    tot_srvcs: Optional[str] = None
    tot_mdcr_alowd_amt: Optional[Decimal] = None
    avg_mdcr_alowd_amt: Optional[Decimal] = None
    avg_mdcr_pymt_amt: Optional[Decimal] = None
    avg_mdcr_stdzd_amt: Optional[Decimal] = None
    _source_year: Optional[int] = None


class CMSUtilizationRecord(CMSPUFBaseRecord):
    """Validation model for CMS Medicare Utilization PUF data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    bene_geo_lvl: Optional[str] = None
    bene_geo_desc: Optional[str] = None
    bene_geo_cd: Optional[str] = None
    bene_age_lvl: Optional[str] = None
    bene_demo_lvl: Optional[str] = None
    bene_demo_desc: Optional[str] = None
    srvcs_per_bene: Optional[Decimal] = None
    ip_cvrd_stays_per_1000_benes: Optional[Decimal] = None
    avg_ip_los: Optional[Decimal] = None
    er_visits_per_1000_benes: Optional[Decimal] = None
    phy_visits_per_bene: Optional[Decimal] = None
    tot_mdcr_pymt_pc: Optional[Decimal] = None
    _source_year: Optional[int] = None


class EUIPODesignRecord(CMSPUFBaseRecord):
    """Validation model for EUIPO registered community design records."""

    model_config = ConfigDict(str_strip_whitespace=True)

    application_number: str = Field(..., min_length=1)
    design_title: Optional[str] = None
    applicant_name: Optional[str] = None
    applicant_country: Optional[str] = Field(None, max_length=10)
    representative_name: Optional[str] = None
    designer_name: Optional[str] = None
    status: Optional[str] = Field(None, max_length=100)
    filing_date: Optional[date] = None
    registration_date: Optional[date] = None
    expiry_date: Optional[date] = None
    publication_date: Optional[date] = None
    locarno_classes: Optional[List[str]] = None
    product_indication: Optional[str] = None
    image_url: Optional[str] = None
    number_of_designs: Optional[int] = None


# ---------------------------------------------------------------------------
# Legacy source validators (019-cms-puf-platform-reconciliation)
# ---------------------------------------------------------------------------

class RxNormRecord(CMSPUFBaseRecord):
    """Validation model for NLM RxNorm concept records."""

    model_config = ConfigDict(str_strip_whitespace=True)

    rxcui: str = Field(..., min_length=1, description="RxNorm Concept Unique Identifier")
    name: Optional[str] = None
    tty: Optional[str] = Field(None, max_length=10, description="Term type (IN, BN, SCDC, etc.)")
    synonym: Optional[str] = None
    suppress: Optional[str] = None

    @field_validator('rxcui')
    @classmethod
    def validate_rxcui(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError(f"RxCUI must be numeric, got: {v!r}")
        return v


class WHOINNRecord(CMSPUFBaseRecord):
    """Validation model for WHO International Nonproprietary Name records."""

    model_config = ConfigDict(str_strip_whitespace=True)

    inn_name: str = Field(..., min_length=1, description="WHO International Nonproprietary Name")
    inn_latin: Optional[str] = None
    inn_list_number: Optional[int] = Field(None, ge=1)
    inn_year: Optional[int] = Field(None, ge=1950, le=2100)
    cas_number: Optional[str] = None
    molecular_formula: Optional[str] = None
    smiles: Optional[str] = None
    inchi_key: Optional[str] = Field(None, min_length=27, max_length=27)
    inn_stem: Optional[str] = None
    stem_definition: Optional[str] = None
    status: Optional[str] = Field(None, max_length=50)

    @field_validator('inn_name')
    @classmethod
    def validate_inn_name(cls, v: str) -> str:
        if not v or v.strip() == '':
            raise ValueError("INN name cannot be empty")
        return v.lower()


class PharmGKBRecord(CMSPUFBaseRecord):
    """Validation model for PharmGKB pharmacogenomics chemical/drug records."""

    model_config = ConfigDict(str_strip_whitespace=True)

    pharmgkb_id: str = Field(..., min_length=1, description="PharmGKB accession ID (PA...)")
    name: Optional[str] = None
    entity_type: Optional[str] = None
    drugbank_id: Optional[str] = None
    chembl_id: Optional[str] = None
    rxnorm_id: Optional[str] = None
    pubchem_cid: Optional[int] = Field(None, ge=1)
    cas_number: Optional[str] = None
    drug_type: Optional[str] = None
    smiles: Optional[str] = None
    inchi_key: Optional[str] = Field(None, min_length=27, max_length=27)


class KEGGDrugRecord(CMSPUFBaseRecord):
    """Validation model for KEGG Drug compound records."""

    model_config = ConfigDict(str_strip_whitespace=True)

    kegg_id: str = Field(..., min_length=1, description="KEGG Drug ID (D#####)")
    name: Optional[str] = None
    formula: Optional[str] = None
    exact_mass: Optional[float] = Field(None, ge=0)
    smiles: Optional[str] = None
    inchi: Optional[str] = None
    inchi_key: Optional[str] = Field(None, min_length=27, max_length=27)
    drugbank_id: Optional[str] = None
    pubchem_sid: Optional[int] = Field(None, ge=1)
    chembl_id: Optional[str] = None
    cas_number: Optional[str] = None

    @field_validator('kegg_id')
    @classmethod
    def validate_kegg_id(cls, v: str) -> str:
        if not (v.startswith('D') and v[1:].isdigit()):
            raise ValueError(f"KEGG Drug ID must be D#####, got: {v!r}")
        return v


class TDCAdmetRecord(CMSPUFBaseRecord):
    """Validation model for TDC ADMET prediction records."""

    model_config = ConfigDict(str_strip_whitespace=True)

    compound_id: str = Field(..., min_length=1, description="Compound identifier (Drug_ID field)")
    smiles: Optional[str] = None
    inchi_key: Optional[str] = None
    dataset_name: str = Field(..., min_length=1, description="TDC ADMET dataset name")
    property_name: str = Field(..., min_length=1)
    property_value: Optional[float] = None
    dataset_type: Optional[str] = Field(
        None,
        description="ADMET category: absorption|distribution|metabolism|excretion|toxicity|other"
    )
    property_category: Optional[str] = None

