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
]
