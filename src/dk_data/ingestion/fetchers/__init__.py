"""Data fetchers for external data sources."""

from .base import BaseFetcher
from .cms_inpatient import CMSInpatientFetcher
from .cms_hospital_info import CMSHospitalInfoFetcher
from .cms_cost_reports import CMSCostReportsFetcher
from .acc_tvc import ACCTVCFetcher
from .hrsa import HRSAFetcher
from .pubmed import PubMedFetcher
from .ema_regulatory import EMARegulatoryCIFetcher
from .openalex_ci import OpenAlexCIFetcher
from .drugbank import DrugBankFetcher
from .uspto_patents import USPTOPatentsFetcher
from .journal_rss import JournalRSSFetcher
from .uspto_ci import USPTOCIFetcher
from .hta_bodies import HTABodiesFetcher
from .epo_ops import EPOOPSFetcher
from .cochrane import CochraneFetcher
from .medical_news import MedicalNewsFetcher
from .sec_edgar import SECEdgarFetcher
from .uniprot import UniProtFetcher
from .pdb import PDBFetcher
from .orcid import ORCIDFetcher
from .uspto_trademarks import USPTOTrademarksFetcher
from .euipo_trademarks import EUIPOTrademarksFetcher
from .euipo_designs import EUIPODesignsFetcher
# CMS PUF fetchers (016-cms-puf-datasource-integration)
from .cms_nppes import CMSNPPESFetcher
from .cms_part_d_prescriber import CMSPartDPrescriberFetcher
from .cms_physician_puf import CMSPhysicianPUFFetcher
from .cms_open_payments import CMSOpenPaymentsFetcher
from .cms_care_compare import CMSCareCompareFetcher
# CMS PUF Phase 3: Facility fetchers
from .cms_pos import CMSPOSFetcher
from .cms_pecos import CMSPECOSFetcher
from .cms_chow import CMSCHOWFetcher
from .cms_hospital_affiliation import CMSHospitalAffiliationFetcher
from .cms_inpatient_puf import CMSInpatientPUFFetcher
from .cms_outpatient_puf import CMSOutpatientPUFFetcher
from .cms_hospital_quality import CMSHospitalQualityFetcher
from .cms_hospital_general_info import CMSHospitalGeneralInfoFetcher
from .cms_hcris import CMSHCRISFetcher
from .cms_magnet import CMSMagnetFetcher
# CMS PUF Phase 4: Drug/Market fetchers
from .cms_ndc import CMSNDCFetcher
from .cms_part_d_spending import CMSPartDSpendingFetcher
from .cms_part_b_spending import CMSPartBSpendingFetcher
from .cms_formulary import CMSFormularyFetcher
from .cms_rbcs import CMSRBCSFetcher
from .cms_usp import CMSUSPFetcher
from .cms_nucc import CMSNUCCFetcher
from .cms_geographic_variation import CMSGeographicVariationFetcher
from .cms_chronic_conditions import CMSChronicConditionsFetcher
from .cms_post_acute import CMSPostAcuteFetcher
from .cms_dmepos import CMSDMEPOSFetcher
from .cms_ddinter import CMSDDInterFetcher
from .cms_stabilis import CMSStabilisFetcher

__all__ = [
    'BaseFetcher',
    'CMSInpatientFetcher',
    'CMSHospitalInfoFetcher',
    'CMSCostReportsFetcher',
    'ACCTVCFetcher',
    'HRSAFetcher',
    'PubMedFetcher',
    'EMARegulatoryCIFetcher',
    'OpenAlexCIFetcher',
    'DrugBankFetcher',
    'USPTOPatentsFetcher',
    'JournalRSSFetcher',
    'USPTOCIFetcher',
    'HTABodiesFetcher',
    'EPOOPSFetcher',
    'CochraneFetcher',
    'MedicalNewsFetcher',
    'SECEdgarFetcher',
    'UniProtFetcher',
    'PDBFetcher',
    'ORCIDFetcher',
    'USPTOTrademarksFetcher',
    'EUIPOTrademarksFetcher',
    'EUIPODesignsFetcher',
    # CMS PUF (016)
    'CMSNPPESFetcher',
    'CMSPartDPrescriberFetcher',
    'CMSPhysicianPUFFetcher',
    'CMSOpenPaymentsFetcher',
    'CMSCareCompareFetcher',
    # Phase 3: Facility
    'CMSPOSFetcher',
    'CMSPECOSFetcher',
    'CMSCHOWFetcher',
    'CMSHospitalAffiliationFetcher',
    'CMSInpatientPUFFetcher',
    'CMSOutpatientPUFFetcher',
    'CMSHospitalQualityFetcher',
    'CMSHospitalGeneralInfoFetcher',
    'CMSHCRISFetcher',
    'CMSMagnetFetcher',
    # Phase 4: Drug/Market
    'CMSNDCFetcher',
    'CMSPartDSpendingFetcher',
    'CMSPartBSpendingFetcher',
    'CMSFormularyFetcher',
    'CMSRBCSFetcher',
    'CMSUSPFetcher',
    'CMSNUCCFetcher',
    'CMSGeographicVariationFetcher',
    'CMSChronicConditionsFetcher',
    'CMSPostAcuteFetcher',
    'CMSDMEPOSFetcher',
    'CMSDDInterFetcher',
    'CMSStabilisFetcher',
]
