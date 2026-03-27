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
from .who_icd import WHOICDFetcher
from .bindingdb import BindingDBFetcher
from .sider import SIDERFetcher
from .europepmc import EuropePMCFetcher
from .nih_reporter import NIHReporterFetcher
from .cms_geographic_variation import CMSGeographicVariationFetcher
from .cms_part_d_prescriber import CMSPartDPrescriberFetcher
from .cms_care_compare import CMSCareCompareFetcher
from .cms_chow import CMSCHOWFetcher
from .cms_ddinter import CMSDDInterFetcher
from .cms_dmepos import CMSDMEPOSFetcher
from .cms_formulary import CMSFormularyFetcher
from .cms_hcris import CMSHCRISFetcher
from .cms_hospital_affiliation import CMSHospitalAffiliationFetcher
from .cms_hospital_quality import CMSHospitalQualityFetcher
from .cms_magnet import CMSMagnetFetcher
from .cms_ndc import CMSNDCFetcher
from .cms_nucc import CMSNUCCFetcher
from .cms_pecos import CMSPECOSFetcher
from .cms_pos import CMSPOSFetcher
from .cms_post_acute import CMSPostAcuteFetcher
from .cms_rbcs import CMSRBCSFetcher
from .cms_stabilis import CMSStabilisFetcher
from .cms_usp import CMSUSPFetcher
from .euipo_designs import EUIPODesignsFetcher
from .rxnorm import RxNormFetcher
from .who_inn import WHOINNFetcher
from .pharmgkb import PharmGKBFetcher
from .kegg_drug import KEGGDrugFetcher
from .tdc_admet import TDCAdmetFetcher

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
    'WHOICDFetcher',
    'BindingDBFetcher',
    'SIDERFetcher',
    'EuropePMCFetcher',
    'NIHReporterFetcher',
    'CMSGeographicVariationFetcher',
    'CMSPartDPrescriberFetcher',
    'CMSCareCompareFetcher',
    'CMSCHOWFetcher',
    'CMSDDInterFetcher',
    'CMSDMEPOSFetcher',
    'CMSFormularyFetcher',
    'CMSHCRISFetcher',
    'CMSHospitalAffiliationFetcher',
    'CMSHospitalQualityFetcher',
    'CMSMagnetFetcher',
    'CMSNDCFetcher',
    'CMSNUCCFetcher',
    'CMSPECOSFetcher',
    'CMSPOSFetcher',
    'CMSPostAcuteFetcher',
    'CMSRBCSFetcher',
    'CMSStabilisFetcher',
    'CMSUSPFetcher',
    'EUIPODesignsFetcher',
    'RxNormFetcher',
    'WHOINNFetcher',
    'PharmGKBFetcher',
    'KEGGDrugFetcher',
    'TDCAdmetFetcher',
]
