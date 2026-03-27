"""Pydantic validation models for raw data entities."""

from datetime import date
from decimal import Decimal
from typing import Any, ClassVar, List, Optional, Set
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


# =============================================================================
# CMS PUF Data Source Validators
# =============================================================================


class CMSPartDSpendingRecord(BaseModel):
    """Validation model for CMS Part D Drug Spending PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    brnd_name: Optional[str] = None
    gnrc_name: str = Field(..., min_length=1)
    mftr_name: Optional[str] = None
    tot_mftr: Optional[str] = None
    tot_clms: Optional[Decimal] = Field(None, ge=0)
    tot_30day_fills: Optional[Decimal] = Field(None, ge=0)
    tot_drug_cst: Optional[Decimal] = Field(None, ge=0)
    tot_benes: Optional[Decimal] = Field(None, ge=0)
    avg_spnd_per_clm: Optional[Decimal] = Field(None, ge=0)
    avg_spnd_per_30day_fills: Optional[Decimal] = Field(None, ge=0)
    avg_spnd_per_bene: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)


class CMSPartBSpendingRecord(BaseModel):
    """Validation model for CMS Part B Drug Spending PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    hcpcs_cd: str = Field(..., min_length=1, max_length=10)
    hcpcs_desc: Optional[str] = None
    hcpcs_drug_indicator: Optional[str] = None
    tot_mftr: Optional[str] = None
    tot_clms: Optional[Decimal] = Field(None, ge=0)
    tot_allowed_amt: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    avg_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    avg_mdcr_allowed_amt: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)


class CMSOpenPaymentsRecord(BaseModel):
    """Validation model for CMS Open Payments (Sunshine Act) data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    physician_profile_id: Optional[str] = None
    applicable_manufacturer_or_gpo_name: Optional[str] = None
    total_amount_of_payment_usdollars: Optional[Decimal] = Field(None, ge=0)
    nature_of_payment_or_transfer_of_value: Optional[str] = None
    recipient_state: Optional[str] = Field(None, max_length=2)
    payment_publication_date: Optional[str] = None
    covered_recipient_type: Optional[str] = None
    record_id: Optional[str] = None
    program_year: Optional[str] = None
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('recipient_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSNPPESRecord(BaseModel):
    """Validation model for CMS NPPES National Provider Identifier registry."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: str = Field(..., min_length=10, max_length=10)
    entity_type_code: Optional[str] = None
    provider_last_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_organization_name: Optional[str] = None
    provider_credential_text: Optional[str] = None
    provider_business_practice_location_address_state_name: Optional[str] = Field(None, max_length=2)
    provider_taxonomy_code_1: Optional[str] = None
    healthcare_provider_taxonomy_code_1: Optional[str] = None
    # Mailing address fields (used by idn_hierarchy agent)
    provider_business_mailing_address_city_name: Optional[str] = None
    provider_business_mailing_address_state_name: Optional[str] = None
    provider_business_mailing_address_postal_code: Optional[str] = None
    # Practice location fields (used by contact_verification agent)
    provider_business_practice_location_address_telephone_number: Optional[str] = None
    provider_business_practice_location_address_fax_number: Optional[str] = None
    provider_first_line_business_practice_location_address: Optional[str] = None
    provider_second_line_business_practice_location_address: Optional[str] = None
    provider_business_practice_location_address_city_name: Optional[str] = None
    provider_business_practice_location_address_postal_code: Optional[str] = None
    provider_business_practice_location_address_country_code: Optional[str] = None
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('npi')
    @classmethod
    def validate_npi(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError('NPI must be numeric')
        if len(v) != 10:
            raise ValueError('NPI must be exactly 10 digits')
        return v


class CMSInpatientPUFRecord(BaseModel):
    """Validation model for CMS Inpatient PUF (provider-level charge data)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    drg_definition: str = Field(..., min_length=1)
    provider_id: str = Field(..., min_length=1, max_length=10)
    provider_name: Optional[str] = None
    provider_street_address: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = Field(None, max_length=2)
    provider_zip_code: Optional[str] = Field(None, max_length=10)
    hospital_referral_region_description: Optional[str] = None
    total_discharges: Optional[int] = Field(None, ge=0)
    average_covered_charges: Optional[Decimal] = Field(None, ge=0)
    average_total_payments: Optional[Decimal] = Field(None, ge=0)
    average_medicare_payments: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('provider_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSPhysicianPUFRecord(BaseModel):
    """Validation model for CMS Physician and Other Practitioners PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: str = Field(..., min_length=10, max_length=10)
    provider_last_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_credentials: Optional[str] = None
    provider_gender: Optional[str] = None
    provider_entity_type: Optional[str] = None
    provider_street_address_1: Optional[str] = None
    provider_city: Optional[str] = None
    provider_zip_code: Optional[str] = None
    provider_state: Optional[str] = Field(None, max_length=2)
    provider_country: Optional[str] = None
    provider_type: Optional[str] = None
    medicare_participation_indicator: Optional[str] = None
    total_hcpcs_cds: Optional[int] = Field(None, ge=0)
    total_services: Optional[Decimal] = Field(None, ge=0)
    total_unique_benes: Optional[int] = Field(None, ge=0)
    total_medicare_payment_amt: Optional[Decimal] = Field(None, ge=0)
    total_medicare_allowed_amt: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('npi')
    @classmethod
    def validate_npi(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError('NPI must be numeric')
        if len(v) != 10:
            raise ValueError('NPI must be exactly 10 digits')
        return v

    @field_validator('provider_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSMedicareAdvantageRecord(BaseModel):
    """Validation model for CMS Medicare Advantage enrollment/contract data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    contract_id: Optional[str] = None
    plan_id: Optional[str] = None
    segment_id: Optional[str] = None
    organization_name: Optional[str] = None
    organization_type: Optional[str] = None
    plan_name: Optional[str] = None
    plan_type: Optional[str] = None
    state: Optional[str] = Field(None, max_length=2)
    county_name: Optional[str] = None
    county_code: Optional[str] = None
    enrollment: Optional[int] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSMedicaidDrugSpendingRecord(BaseModel):
    """Validation model for CMS Medicaid Drug Spending data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    drug_name: Optional[str] = None
    state: Optional[str] = Field(None, max_length=2)
    labeler_code: Optional[str] = None
    product_code: Optional[str] = None
    package_size_code: Optional[str] = None
    ndc: Optional[str] = None
    units_reimbursed: Optional[Decimal] = Field(None, ge=0)
    number_of_prescriptions: Optional[int] = Field(None, ge=0)
    total_amount_reimbursed: Optional[Decimal] = Field(None, ge=0)
    medicaid_amount_reimbursed: Optional[Decimal] = Field(None, ge=0)
    non_medicaid_amount_reimbursed: Optional[Decimal] = Field(None, ge=0)
    quarter: Optional[str] = None
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSDMERecord(BaseModel):
    """Validation model for CMS Durable Medical Equipment (DME) PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: str = Field(..., min_length=10, max_length=10)
    provider_last_org_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_type: Optional[str] = None
    provider_state: Optional[str] = Field(None, max_length=2)
    hcpcs_cd: Optional[str] = Field(None, max_length=10)
    hcpcs_desc: Optional[str] = None
    bene_unique_cnt: Optional[int] = Field(None, ge=0)
    total_suplrs: Optional[int] = Field(None, ge=0)
    suplr_rental_ind: Optional[str] = None
    tot_suplr_sbmtd_chrg: Optional[Decimal] = Field(None, ge=0)
    tot_suplr_mdcr_alowd_amt: Optional[Decimal] = Field(None, ge=0)
    tot_suplr_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('npi')
    @classmethod
    def validate_npi(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError('NPI must be numeric')
        if len(v) != 10:
            raise ValueError('NPI must be exactly 10 digits')
        return v

    @field_validator('provider_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSHomeHealthRecord(BaseModel):
    """Validation model for CMS Home Health Agency PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: Optional[str] = None
    agency_name: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(None, max_length=2)
    zip_code: Optional[str] = Field(None, max_length=10)
    tot_epis: Optional[int] = Field(None, ge=0)
    tot_hha_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    avg_hha_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    tot_benes: Optional[int] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSHospiceRecord(BaseModel):
    """Validation model for CMS Hospice Provider PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: Optional[str] = None
    facility_name: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(None, max_length=2)
    zip_code: Optional[str] = Field(None, max_length=10)
    tot_benes: Optional[int] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    avg_mdcr_pymt_per_bene: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSSNFRecord(BaseModel):
    """Validation model for CMS Skilled Nursing Facility (SNF) PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: Optional[str] = None
    facility_name: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(None, max_length=2)
    zip_code: Optional[str] = Field(None, max_length=10)
    tot_snf_stays: Optional[int] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    avg_mdcr_pymt_per_stay: Optional[Decimal] = Field(None, ge=0)
    tot_benes: Optional[int] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSOutpatientRecord(BaseModel):
    """Validation model for CMS Outpatient PUF (hospital APC-level charges)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    provider_id: Optional[str] = None
    provider_name: Optional[str] = None
    provider_street_address: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = Field(None, max_length=2)
    provider_zip_code: Optional[str] = Field(None, max_length=10)
    apc: Optional[str] = None
    outpatient_services: Optional[int] = Field(None, ge=0)
    average_estimated_submitted_charges: Optional[Decimal] = Field(None, ge=0)
    average_total_payments: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('provider_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSReferringProviderRecord(BaseModel):
    """Validation model for CMS Referring Provider PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    rndrng_npi: Optional[str] = None
    rfr_npi: Optional[str] = None
    rfr_prvdr_last_org_name: Optional[str] = None
    rfr_prvdr_first_name: Optional[str] = None
    rfr_prvdr_type: Optional[str] = None
    rfr_prvdr_state_abrvtn: Optional[str] = Field(None, max_length=2)
    tot_rndrng_prvdrs: Optional[int] = Field(None, ge=0)
    tot_srvcs: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_alowd_amt: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('rfr_prvdr_state_abrvtn')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSOrderingProviderRecord(BaseModel):
    """Validation model for CMS Ordering/Referring Provider PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    ordr_rndrng_npi: Optional[str] = None
    rndrng_npi: Optional[str] = None
    rndrng_prvdr_last_org_name: Optional[str] = None
    rndrng_prvdr_first_name: Optional[str] = None
    rndrng_prvdr_type: Optional[str] = None
    rndrng_prvdr_state_abrvtn: Optional[str] = Field(None, max_length=2)
    tot_srvcs: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_alowd_amt: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('rndrng_prvdr_state_abrvtn')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSLabServicesRecord(BaseModel):
    """Validation model for CMS Lab Services PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    provider_last_org_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_type: Optional[str] = None
    provider_state: Optional[str] = Field(None, max_length=2)
    hcpcs_cd: Optional[str] = Field(None, max_length=10)
    hcpcs_desc: Optional[str] = None
    tot_benes: Optional[int] = Field(None, ge=0)
    tot_srvcs: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_alowd_amt: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('provider_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSImagingRecord(BaseModel):
    """Validation model for CMS Imaging Services PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    provider_last_org_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_type: Optional[str] = None
    provider_state: Optional[str] = Field(None, max_length=2)
    hcpcs_cd: Optional[str] = Field(None, max_length=10)
    hcpcs_desc: Optional[str] = None
    tot_benes: Optional[int] = Field(None, ge=0)
    tot_srvcs: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_alowd_amt: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('provider_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSMentalHealthRecord(BaseModel):
    """Validation model for CMS Mental Health PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    provider_last_org_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_type: Optional[str] = None
    provider_state: Optional[str] = Field(None, max_length=2)
    hcpcs_cd: Optional[str] = Field(None, max_length=10)
    hcpcs_desc: Optional[str] = None
    tot_benes: Optional[int] = Field(None, ge=0)
    tot_srvcs: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_alowd_amt: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('provider_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSOpioidRecord(BaseModel):
    """Validation model for CMS Opioid Prescribing Map PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    prscrbr_npi: Optional[str] = None
    prscrbr_last_org_name: Optional[str] = None
    prscrbr_first_name: Optional[str] = None
    prscrbr_type: Optional[str] = None
    prscrbr_state_abrvtn: Optional[str] = Field(None, max_length=2)
    opioid_drug_flag: Optional[str] = None
    extended_release_opioid_drug_flag: Optional[str] = None
    tot_clms: Optional[int] = Field(None, ge=0)
    tot_opioid_clms: Optional[int] = Field(None, ge=0)
    opioid_prscrbr_rate: Optional[Decimal] = Field(None, ge=0)
    tot_benes: Optional[int] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('prscrbr_state_abrvtn')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSTelehealthRecord(BaseModel):
    """Validation model for CMS Telehealth Trends PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    provider_last_org_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_type: Optional[str] = None
    provider_state: Optional[str] = Field(None, max_length=2)
    hcpcs_cd: Optional[str] = Field(None, max_length=10)
    hcpcs_desc: Optional[str] = None
    place_of_service: Optional[str] = None
    tot_benes: Optional[int] = Field(None, ge=0)
    tot_srvcs: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_alowd_amt: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('provider_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSGeographicVariationRecord(BaseModel):
    """Validation model for CMS Geographic Variation Public Use File."""

    model_config = ConfigDict(str_strip_whitespace=True)

    bene_geo_lvl: Optional[str] = None
    bene_state_abrvtn: Optional[str] = Field(None, max_length=2)
    bene_state_desc: Optional[str] = None
    bene_county_desc: Optional[str] = None
    bene_fips_cd: Optional[str] = None
    year: Optional[int] = Field(None, ge=2000, le=2100)
    tot_mdcr_enrlees: Optional[int] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    avg_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    acute_hosp_readmsn_rate: Optional[Decimal] = None
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('bene_state_abrvtn')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSChronicConditionsRecord(BaseModel):
    """Validation model for CMS Chronic Conditions PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    bene_geo_lvl: Optional[str] = None
    bene_state_abrvtn: Optional[str] = Field(None, max_length=2)
    bene_state_desc: Optional[str] = None
    bene_county_desc: Optional[str] = None
    bene_fips_cd: Optional[str] = None
    bene_age_lvl: Optional[str] = None
    bene_sex_cd: Optional[str] = None
    bene_race_cd: Optional[str] = None
    bene_dual_stus_cd: Optional[str] = None
    chronic_condition: Optional[str] = None
    prevalence: Optional[Decimal] = Field(None, ge=0, le=1)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('bene_state_abrvtn')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSDualEligibleRecord(BaseModel):
    """Validation model for CMS Dual Eligible Beneficiary data."""

    model_config = ConfigDict(str_strip_whitespace=True)

    state: Optional[str] = Field(None, max_length=2)
    state_name: Optional[str] = None
    bene_count: Optional[int] = Field(None, ge=0)
    full_dual_count: Optional[int] = Field(None, ge=0)
    partial_dual_count: Optional[int] = Field(None, ge=0)
    medicaid_managed_care_count: Optional[int] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSEnrollmentRecord(BaseModel):
    """Validation model for CMS Medicare Enrollment PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    state: Optional[str] = Field(None, max_length=2)
    state_name: Optional[str] = None
    county_name: Optional[str] = None
    fips_cd: Optional[str] = None
    tot_benes: Optional[int] = Field(None, ge=0)
    orgnl_mdcr_benes: Optional[int] = Field(None, ge=0)
    ma_and_oth_benes: Optional[int] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSClaimTypeRecord(BaseModel):
    """Validation model for CMS Claim Type utilization PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    provider_type: Optional[str] = None
    provider_state: Optional[str] = Field(None, max_length=2)
    claim_type: Optional[str] = None
    tot_benes: Optional[int] = Field(None, ge=0)
    tot_clms: Optional[int] = Field(None, ge=0)
    tot_srvcs: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_alowd_amt: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('provider_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSUtilizationRecord(BaseModel):
    """Validation model for CMS Medicare Utilization PUF."""

    model_config = ConfigDict(str_strip_whitespace=True)

    npi: Optional[str] = None
    provider_last_org_name: Optional[str] = None
    provider_first_name: Optional[str] = None
    provider_type: Optional[str] = None
    provider_state: Optional[str] = Field(None, max_length=2)
    hcpcs_cd: Optional[str] = Field(None, max_length=10)
    hcpcs_desc: Optional[str] = None
    hcpcs_drug_ind: Optional[str] = None
    place_of_service: Optional[str] = None
    tot_benes: Optional[int] = Field(None, ge=0)
    tot_srvcs: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_alowd_amt: Optional[Decimal] = Field(None, ge=0)
    tot_mdcr_pymt_amt: Optional[Decimal] = Field(None, ge=0)
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('provider_state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


class CMSCostReportsPUFRecord(BaseModel):
    """Validation model for CMS Cost Reports PUF (hcs_raw schema version)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    rpt_rec_num: Optional[str] = None
    prvdr_ctrl_type_cd: Optional[str] = None
    prvdr_num: Optional[str] = None
    rpt_stus_cd: Optional[str] = None
    initl_rpt_sw: Optional[str] = None
    last_rpt_sw: Optional[str] = None
    trnsmtl_num: Optional[str] = None
    fi_num: Optional[str] = None
    adr_vndr_cd: Optional[str] = None
    fi_creat_dt: Optional[str] = None
    util_cd: Optional[str] = None
    npr_dt: Optional[str] = None
    spec_ind: Optional[str] = None
    fi_rcpt_dt: Optional[str] = None
    total_beds: Optional[int] = Field(None, ge=0)
    total_discharges: Optional[int] = Field(None, ge=0)
    net_patient_revenue: Optional[Decimal] = None
    total_operating_expenses: Optional[Decimal] = None
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)


class CMSHospitalGeneralInfoRecord(BaseModel):
    """Validation model for CMS Hospital General Information PUF (hcs_raw schema)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    facility_id: Optional[str] = None
    facility_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = Field(None, max_length=2)
    zip_code: Optional[str] = Field(None, max_length=10)
    county_name: Optional[str] = None
    phone_number: Optional[str] = Field(None, max_length=20)
    hospital_type: Optional[str] = None
    hospital_ownership: Optional[str] = None
    emergency_services: Optional[str] = None
    hospital_overall_rating: Optional[str] = None
    hospital_overall_rating_footnote: Optional[str] = None
    source_year: int = Field(..., alias="_source_year", ge=2000, le=2100)

    @field_validator('state')
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if v and len(v) != 2:
            return None
        return v


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
