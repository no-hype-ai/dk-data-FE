"""
External API Clients for Ground Truth Service.

Provides async clients for free/public pharmaceutical data sources:
- UMLS: Medical terminology and concept mappings
- RxNorm: Drug name normalization
- OpenFDA: Drug labels, adverse events, Orange Book
- ClinicalTrials.gov: Clinical trial data
- ORCID: Researcher profiles for KOL identification
- NIH Reporter: NIH grant and project information
- NORD: Rare disease and patient advocacy organizations
- CMS Medicare: Drug utilization and spending data
- CDC WONDER: Mortality and morbidity statistics
- AHRQ HCUP: Healthcare utilization data
"""

from .base_client import (
    APIClientConfig,
    BaseAPIClient,
    CriticalAPIError,
    NonCriticalAPIError,
    is_critical_source,
    CRITICAL_SOURCES,
    NON_CRITICAL_SOURCES,
)

from .cache_manager import (
    CacheManager,
    CacheConfig,
    DataSource,
    SOURCE_TTL_MAP,
    get_cache_manager,
    close_cache_manager,
)

from .umls_client import (
    UMLSClient,
    UMLSConcept,
    UMLSAtom,
    CrosswalkMapping,
    get_umls_client,
)

from .rxnorm_client import (
    RxNormClient,
    RxNormConcept,
    DrugClass,
    DrugInteraction,
    get_rxnorm_client,
)

from .openfda_client import (
    OpenFDAClient,
    DrugLabel,
    AdverseEvent,
    OrangeBookEntry,
    DrugApplication,
    get_openfda_client,
)

from .clinicaltrials_client import (
    ClinicalTrialsClient,
    ClinicalTrial,
    TrialPhase,
    TrialStatus,
    StudyType,
    Sponsor,
    Intervention,
    TrialSearchResult,
    get_clinicaltrials_client,
)

from .orcid_client import (
    ORCIDClient,
    ResearcherProfile,
    ResearcherSearchResult,
    Affiliation,
    Work,
    get_orcid_client,
)

from .nih_reporter_client import (
    NIHReporterClient,
    NIHProject,
    NIHPublication,
    PrincipalInvestigator,
    get_nih_reporter_client,
)

from .nord_client import (
    NORDClient,
    PatientAdvocacyOrg,
    RareDisease,
    get_nord_client,
)

from .cms_medicare_client import (
    CMSMedicareClient,
    DrugUtilization,
    PrescriberData,
    PartDSpending,
    get_cms_medicare_client,
)

from .cdc_wonder_client import (
    CDCWonderClient,
    MortalityData,
    NatalityData,
    CauseOfDeathStats,
    get_cdc_wonder_client,
)

from .ahrq_hcup_client import (
    AHRQHCUPClient,
    HCUPStats,
    HospitalStayData,
    EmergencyVisitData,
    get_ahrq_hcup_client,
)

try:
    from .sec_edgar_client import (
        SECEdgarClient,
    )
except ImportError:
    SECEdgarClient = None  # models.market_intelligence not yet implemented

from .sec_rate_limiter import (
    SECRateLimiter,
)

from .who_icd_client import (
    WHOICDClient,
    ICDCode,
    ICDSearchResult,
    get_who_icd_client,
)

from .ema_client import (
    EMAClient,
    EMAProduct,
    EMASafetyAlert,
    get_ema_client,
)

from .openalex_client import (
    OpenAlexClient,
    Author,
    Publication,
)

from .patent_client import (
    PatentsViewClient,
    Patent,
)

from .pubmed_client import (
    PubMedClient,
)

from .health_canada_client import (
    HealthCanadaClient,
    HealthCanadaProduct,
)

from .chembl_client import (
    ChEMBLClient,
    ChEMBLMolecule,
    ChEMBLActivity,
    ChEMBLTarget,
    get_chembl_client,
)

from .uniprot_client import (
    UniProtClient,
    UniProtProtein,
    ProteinFeature,
    get_uniprot_client,
)

from .rss_client import (
    RSSFeedClient,
    FeedItem,
)

from .websearch_client import (
    WebSearchClient,
    SearchResult,
)

__all__ = [
    # Base
    "APIClientConfig",
    "BaseAPIClient",
    "CriticalAPIError",
    "NonCriticalAPIError",
    "is_critical_source",
    "CRITICAL_SOURCES",
    "NON_CRITICAL_SOURCES",
    # Cache
    "CacheManager",
    "CacheConfig",
    "DataSource",
    "SOURCE_TTL_MAP",
    "get_cache_manager",
    "close_cache_manager",
    # UMLS
    "UMLSClient",
    "UMLSConcept",
    "UMLSAtom",
    "CrosswalkMapping",
    "get_umls_client",
    # RxNorm
    "RxNormClient",
    "RxNormConcept",
    "DrugClass",
    "DrugInteraction",
    "get_rxnorm_client",
    # OpenFDA
    "OpenFDAClient",
    "DrugLabel",
    "AdverseEvent",
    "OrangeBookEntry",
    "DrugApplication",
    "get_openfda_client",
    # ClinicalTrials.gov
    "ClinicalTrialsClient",
    "ClinicalTrial",
    "TrialPhase",
    "TrialStatus",
    "StudyType",
    "Sponsor",
    "Intervention",
    "TrialSearchResult",
    "get_clinicaltrials_client",
    # ORCID
    "ORCIDClient",
    "ResearcherProfile",
    "ResearcherSearchResult",
    "Affiliation",
    "Work",
    "get_orcid_client",
    # NIH Reporter
    "NIHReporterClient",
    "NIHProject",
    "NIHPublication",
    "PrincipalInvestigator",
    "get_nih_reporter_client",
    # NORD
    "NORDClient",
    "PatientAdvocacyOrg",
    "RareDisease",
    "get_nord_client",
    # CMS Medicare
    "CMSMedicareClient",
    "DrugUtilization",
    "PrescriberData",
    "PartDSpending",
    "get_cms_medicare_client",
    # CDC WONDER
    "CDCWonderClient",
    "MortalityData",
    "NatalityData",
    "CauseOfDeathStats",
    "get_cdc_wonder_client",
    # AHRQ HCUP
    "AHRQHCUPClient",
    "HCUPStats",
    "HospitalStayData",
    "EmergencyVisitData",
    "get_ahrq_hcup_client",
    # SEC EDGAR
    "SECEdgarClient",
    "SECRateLimiter",
    # WHO ICD
    "WHOICDClient",
    "ICDCode",
    "ICDSearchResult",
    "get_who_icd_client",
    # EMA
    "EMAClient",
    "EMAProduct",
    "EMASafetyAlert",
    "get_ema_client",
    # OpenAlex
    "OpenAlexClient",
    "Author",
    "Publication",
    # Patents
    "PatentsViewClient",
    "Patent",
    # PubMed
    "PubMedClient",
    # Health Canada
    "HealthCanadaClient",
    "HealthCanadaProduct",
    # ChEMBL
    "ChEMBLClient",
    "ChEMBLMolecule",
    "ChEMBLActivity",
    "ChEMBLTarget",
    "get_chembl_client",
    # UniProt
    "UniProtClient",
    "UniProtProtein",
    "ProteinFeature",
    "get_uniprot_client",
    # RSS
    "RSSFeedClient",
    "FeedItem",
    # WebSearch
    "WebSearchClient",
    "SearchResult",
]
