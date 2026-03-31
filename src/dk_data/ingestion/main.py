#!/usr/bin/env python3
"""TAVR Data Infrastructure - Ingestion CLI.

Main entry point for data ingestion operations.
Handles both file-based TAVR sources and API-based sources (fetch + load + log).
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .sources import cms_inpatient, cms_hospital_info, cms_cost_reports, acc_tvc
from .sources.hrsa import load_hrsa_shortage_areas_from_records
from .sources.pubmed import load_pubmed_data
from .sources.ema_regulatory import load_ema_regulatory_data
from .sources.openalex_ci import load_openalex_ci_data
from .sources.drugbank import load_drugbank_data
from .sources.uspto_patents import load_uspto_patents_data
from .sources.journal_rss import load_journal_rss_data
from .sources.uspto_ci import load_uspto_ci_data
from .sources.hta_bodies import load_hta_decisions_data
from .sources.epo_ops import load_epo_ops_data
from .sources.cochrane import load_cochrane_data
from .sources.medical_news import load_medical_news_data
from .sources.sec_edgar import load_sec_edgar_data
from .sources.uniprot import load_uniprot_data
from .sources.pdb import load_pdb_data
from .sources.orcid import load_orcid_data
from .sources.uspto_trademarks import load_uspto_trademarks_data
from .sources.euipo_trademarks import load_euipo_trademarks_data
from .sources.who_icd import load_who_icd_data
from .sources.bindingdb import load_bindingdb_data
from .sources.sider import load_sider_data
from .sources.europepmc import load_europepmc_data
from .sources.nih_reporter import load_nih_reporter_data
from .sources.cms_geographic_variation import (
    load_cms_geographic_variation_from_records,
)
from .sources.cms_part_d_prescriber import load_cms_part_d_prescriber
from .sources.cms_care_compare import load_cms_care_compare_data
from .sources.cms_chow import load_cms_chow_data
from .sources.cms_ddinter import load_cms_ddinter_data
from .sources.cms_dmepos import load_cms_dmepos_data
from .sources.cms_formulary import load_cms_formulary_data
from .sources.cms_hcris import load_cms_hcris_data
from .sources.cms_hospital_affiliation import load_cms_hospital_affiliation_data
from .sources.cms_hospital_quality import load_cms_hospital_quality_data
from .sources.cms_magnet import load_cms_magnet_data
from .sources.cms_ndc import load_cms_ndc_data
from .sources.cms_nucc import load_cms_nucc_data
from .sources.cms_pecos import load_cms_pecos_data
from .sources.cms_pos import load_cms_pos_data
from .sources.cms_post_acute import load_cms_post_acute_data
from .sources.cms_rbcs import load_cms_rbcs_data
from .sources.cms_stabilis import load_cms_stabilis_data
from .sources.cms_usp import load_cms_usp_data
from .sources.euipo_designs import load_euipo_designs_data
from .sources.rxnorm import load_rxnorm_data
from .sources.who_inn import load_who_inn_data
from .sources.pharmgkb import load_pharmgkb_data
from .sources.kegg_drug import load_kegg_drug_data
from .sources.tdc_admet import load_tdc_admet_data
from .sources.cms_nppes import load_cms_nppes
from .sources.cms_physician_puf import load_cms_physician_puf
from .sources.cms_physician_puf_services import load_cms_physician_puf_services
from .sources.cms_part_d_spending import load_cms_part_d_spending
from .sources.cms_part_b_spending import load_cms_part_b_spending
from .sources.cms_open_payments import load_cms_open_payments
from .sources.cms_inpatient_puf import load_cms_inpatient_puf
from .sources.cms_hospital_general_info import load_cms_hospital_general_info
from .sources.cms_medicare_advantage import load_cms_medicare_advantage
from .sources.cms_medicaid_drug_spending import load_cms_medicaid_drug_spending
from .sources.cms_dme_puf import load_cms_dme_puf
from .sources.cms_home_health import load_cms_home_health
from .sources.cms_hospice_puf import load_cms_hospice_puf
from .sources.cms_snf_puf import load_cms_snf_puf
from .sources.cms_outpatient_puf import load_cms_outpatient_puf
from .sources.cms_referring_providers import load_cms_referring_providers
from .sources.cms_ordering_providers import load_cms_ordering_providers
from .sources.cms_lab_services import load_cms_lab_services
from .sources.cms_imaging_puf import load_cms_imaging_puf
from .sources.cms_mental_health_puf import load_cms_mental_health_puf
from .sources.cms_opioid_puf import load_cms_opioid_puf
from .sources.cms_telehealth_puf import load_cms_telehealth_puf
from .sources.cms_chronic_conditions import load_cms_chronic_conditions
from .sources.cms_dual_eligible import load_cms_dual_eligible
from .sources.cms_enrollment_puf import load_cms_enrollment_puf
from .sources.cms_claim_type_puf import load_cms_claim_type_puf
from .sources.cms_utilization_puf import load_cms_utilization_puf
from .sources.cms_cost_reports_puf import load_cms_cost_reports_puf
from .sources.cms_cost_reports_puf_lines import load_cms_cost_reports_puf_lines
from .sources.ema_mol import load_ema_mol_data
from .sources.orange_book import load_orange_book_data
from .sources.dailymed import load_dailymed_data
from .sources.fda_drugs import load_fda_drugs_data
from .sources.ttd import load_ttd_data
from .sources.imgt import load_imgt_data
from .sources.cdc_vaccines import load_cdc_vaccines_data
from .sources.clinicaltrials import load_clinicaltrials_data
from .sources.openfda_labels import load_openfda_labels_data
from .sources.chembl_activities import load_chembl_activities_data
from .sources.fda_rems import load_fda_rems_data
from .sources.fda_ndc import load_fda_ndc_data

from .fetchers import (
    PubMedFetcher,
    EMARegulatoryCIFetcher,
    OpenAlexCIFetcher,
    DrugBankFetcher,
    USPTOPatentsFetcher,
    JournalRSSFetcher,
    USPTOCIFetcher,
    HTABodiesFetcher,
    EPOOPSFetcher,
    CochraneFetcher,
    MedicalNewsFetcher,
    SECEdgarFetcher,
    UniProtFetcher,
    PDBFetcher,
    ORCIDFetcher,
    USPTOTrademarksFetcher,
    EUIPOTrademarksFetcher,
    WHOICDFetcher,
    BindingDBFetcher,
    SIDERFetcher,
    EuropePMCFetcher,
    NIHReporterFetcher,
    CMSGeographicVariationFetcher,
    CMSPartDPrescriberFetcher,
    CMSCareCompareFetcher,
    CMSCHOWFetcher,
    CMSDDInterFetcher,
    CMSDMEPOSFetcher,
    CMSFormularyFetcher,
    CMSHCRISFetcher,
    CMSHospitalAffiliationFetcher,
    CMSHospitalQualityFetcher,
    CMSMagnetFetcher,
    CMSNDCFetcher,
    CMSNUCCFetcher,
    CMSPECOSFetcher,
    CMSPOSFetcher,
    CMSPostAcuteFetcher,
    CMSRBCSFetcher,
    CMSStabilisFetcher,
    CMSUSPFetcher,
    EUIPODesignsFetcher,
    RxNormFetcher,
    WHOINNFetcher,
    PharmGKBFetcher,
    KEGGDrugFetcher,
    TDCAdmetFetcher,
    CMSNPPESFetcher,
    CMSPhysicianPUFFetcher,
    CMSPhysicianPUFServicesFetcher,
    CMSPartDSpendingFetcher,
    CMSPartBSpendingFetcher,
    CMSOpenPaymentsFetcher,
    CMSInpatientPUFFetcher,
    CMSHospitalGeneralInfoFetcher,
    CMSMedicareAdvantageFetcher,
    CMSMedicaidDrugSpendingFetcher,
    CMSDMEPUFFetcher,
    CMSHomeHealthFetcher,
    CMSHospicePUFFetcher,
    CMSSNFPUFFetcher,
    CMSOutpatientPUFFetcher,
    CMSReferringProvidersFetcher,
    CMSOrderingProvidersFetcher,
    CMSLabServicesFetcher,
    CMSImagingPUFFetcher,
    CMSMentalHealthPUFFetcher,
    CMSOpioidPUFFetcher,
    CMSTelehealthPUFFetcher,
    CMSChronicConditionsFetcher,
    CMSDualEligibleFetcher,
    CMSEnrollmentPUFFetcher,
    CMSClaimTypePUFFetcher,
    CMSUtilizationPUFFetcher,
    CMSCostReportsPUFFetcher,
    HRSAFetcher,
    EMAMolFetcher,
    OrangeBookFetcher,
    DailyMedFetcher,
    FDADrugsFetcher,
    TTDFetcher,
    IMGTFetcher,
    CDCVaccinesFetcher,
    ClinicalTrialsFetcher,
    OpenFDALabelsFetcher,
    ChEMBLActivitiesFetcher,
    FDARemsFetcher,
    FDANDCFetcher,
)

from .utils.database import init_connection_pool, close_connection_pool, get_cursor

# Observability (013-dk-data-observability T023+T027)
try:
    from dk_data.observability import setup_telemetry, get_tracer
    from dk_data.observability.logging import setup_logging, get_logger
    from dk_data.observability.reporting import report_completion
    _OBS_AVAILABLE = True
except ImportError:
    _OBS_AVAILABLE = False

import logging
logger = logging.getLogger(__name__)

# Available data sources
SOURCES = {
    'cms_inpatient': {
        'name': 'CMS Medicare Inpatient',
        'description': 'TAVR procedure volumes by DRG',
        'loader': cms_inpatient.load_cms_inpatient_file,
        'requires_file': True,
        'requires_fiscal_year': True,
        'meta_name': 'cms_medicare_inpatient',
    },
    'cms_hospital_info': {
        'name': 'CMS Hospital General Information',
        'description': 'Hospital demographics and ratings',
        'loader': cms_hospital_info.load_cms_hospital_info,
        'requires_file': True,
    },
    'cms_cost_reports': {
        'name': 'CMS Cost Reports',
        'description': 'Hospital financial metrics',
        'loader': cms_cost_reports.load_cms_cost_reports,
        'requires_file': True,
    },
    'acc_tvc': {
        'name': 'ACC TVC Certifications',
        'description': 'Transcatheter Valve Certifications',
        'loader': acc_tvc.load_acc_tvc_certifications,
        'requires_file': True,
    },
    'hrsa': {
        'name': 'HRSA Shortage Areas',
        'description': 'Health Professional Shortage Areas',
        'fetcher': HRSAFetcher,
        'loader': load_hrsa_shortage_areas_from_records,
        'requires_file': False,
        'default_days_back': None,
        'meta_name': 'hrsa_shortage_areas',
    },
    # --- API-based sources (fetch + load) ---
    # default_days_back: backfill window for first run (no prior refresh in meta)
    # None means fetcher doesn't support days_back (full-fetch / ID-based)
    'pubmed': {
        'name': 'PubMed Literature',
        'description': 'PubMed via NCBI E-utilities',
        'fetcher': PubMedFetcher,
        'loader': load_pubmed_data,
        'requires_file': False,
        'default_days_back': 30,
    },
    'ema_regulatory': {
        'name': 'EMA Regulatory Decisions',
        'description': 'EMA CHMP opinions, EPARs, safety signals',
        'fetcher': EMARegulatoryCIFetcher,
        'loader': load_ema_regulatory_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    'openalex_ci': {
        'name': 'OpenAlex CI',
        'description': 'OpenAlex CI pharmaceutical research works',
        'fetcher': OpenAlexCIFetcher,
        'loader': load_openalex_ci_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    'drugbank': {
        'name': 'DrugBank',
        'description': 'DrugBank drug data (credential-gated)',
        'fetcher': DrugBankFetcher,
        'loader': load_drugbank_data,
        'requires_file': False,
        'default_days_back': None,  # full dump every run
    },
    'uspto_patents': {
        'name': 'USPTO Patents',
        'description': 'USPTO PatentsView pharma patents',
        'fetcher': USPTOPatentsFetcher,
        'loader': load_uspto_patents_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    'journal_rss': {
        'name': 'Journal RSS Feeds',
        'description': 'Journal RSS feeds (NEJM, Lancet, JAMA, etc.)',
        'fetcher': JournalRSSFetcher,
        'loader': load_journal_rss_data,
        'requires_file': False,
        'default_days_back': None,  # RSS feeds are inherently recent
    },
    'uspto_ci': {
        'name': 'USPTO CI',
        'description': 'USPTO PatentsView CI pharma patents',
        'fetcher': USPTOCIFetcher,
        'loader': load_uspto_ci_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    'hta_bodies': {
        'name': 'HTA Body Decisions',
        'description': 'HTA body decisions (NICE, G-BA, HAS, PBAC)',
        'fetcher': HTABodiesFetcher,
        'loader': load_hta_decisions_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    'epo_ops': {
        'name': 'EPO OPS',
        'description': 'EPO Open Patent Services (credential-gated)',
        'fetcher': EPOOPSFetcher,
        'loader': load_epo_ops_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    'cochrane': {
        'name': 'Cochrane Library',
        'description': 'Cochrane Library systematic reviews',
        'fetcher': CochraneFetcher,
        'loader': load_cochrane_data,
        'requires_file': False,
        'default_days_back': 180,
    },
    'medical_news': {
        'name': 'Medical News',
        'description': 'Medical news RSS (Medscape, Healio, FiercePharma)',
        'fetcher': MedicalNewsFetcher,
        'loader': load_medical_news_data,
        'requires_file': False,
        'default_days_back': 30,
    },
    'sec_edgar': {
        'name': 'SEC EDGAR',
        'description': 'SEC EDGAR pharma filings (10-K, 10-Q, 8-K)',
        'fetcher': SECEdgarFetcher,
        'loader': load_sec_edgar_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    'uniprot': {
        'name': 'UniProt',
        'description': 'UniProt protein targets (drug target data)',
        'fetcher': UniProtFetcher,
        'loader': load_uniprot_data,
        'requires_file': False,
        'default_days_back': None,  # static query, no date filter
    },
    'pdb': {
        'name': 'RCSB PDB',
        'description': 'RCSB PDB protein structures',
        'fetcher': PDBFetcher,
        'loader': load_pdb_data,
        'requires_file': False,
        'default_days_back': None,  # static query, no date filter
    },
    'orcid': {
        'name': 'ORCID',
        'description': 'ORCID researcher profiles (KOL identification)',
        'fetcher': ORCIDFetcher,
        'loader': load_orcid_data,
        'requires_file': False,
        'default_days_back': None,  # static query, no date filter
    },
    'uspto_trademarks': {
        'name': 'USPTO Trademarks',
        'description': 'USPTO TSDR trademark case status data',
        'fetcher': USPTOTrademarksFetcher,
        'loader': load_uspto_trademarks_data,
        'requires_file': False,
        'default_days_back': None,  # ID-based lookup, no date filter
    },
    'euipo_trademarks': {
        'name': 'EUIPO Trademarks',
        'description': 'EUIPO trademark data via TMview/IBM Gateway',
        'fetcher': EUIPOTrademarksFetcher,
        'loader': load_euipo_trademarks_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    'who_icd': {
        'name': 'WHO ICD',
        'description': 'WHO ICD-11 (with ICD-10 fallback) disease classification codes',
        'fetcher': WHOICDFetcher,
        'loader': load_who_icd_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'bindingdb': {
        'name': 'BindingDB',
        'description': 'BindingDB protein-ligand binding affinities',
        'fetcher': BindingDBFetcher,
        'loader': load_bindingdb_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'sider': {
        'name': 'SIDER',
        'description': 'SIDER drug side effects (STITCH/MedDRA)',
        'fetcher': SIDERFetcher,
        'loader': load_sider_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'europepmc': {
        'name': 'Europe PMC',
        'description': 'Europe PMC biomedical literature',
        'fetcher': EuropePMCFetcher,
        'loader': load_europepmc_data,
        'requires_file': False,
        'default_days_back': 30,
    },
    'nih_reporter': {
        'name': 'NIH Reporter',
        'description': 'NIH Reporter grant and project data',
        'fetcher': NIHReporterFetcher,
        'loader': load_nih_reporter_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    'cms_geographic_variation': {
        'name': 'CMS Geographic Variation',
        'description': 'CMS Medicare Geographic Variation PUF',
        'fetcher': CMSGeographicVariationFetcher,
        'loader': load_cms_geographic_variation_from_records,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_part_d_prescriber': {
        'name': 'CMS Part D by Prescriber',
        'description': 'CMS Medicare Part D Prescriber PUF',
        'fetcher': CMSPartDPrescriberFetcher,
        'loader': load_cms_part_d_prescriber,
        'requires_file': False,
        'default_days_back': None,
    },
    # --- CMS facility/provider/reference sources (ported from 016) ---
    'cms_care_compare': {
        'name': 'CMS Care Compare',
        'description': 'Hospital Compare star ratings and quality data',
        'fetcher': CMSCareCompareFetcher,
        'loader': load_cms_care_compare_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_chow': {
        'name': 'CMS Change of Ownership',
        'description': 'CMS CHOW facility ownership change records',
        'fetcher': CMSCHOWFetcher,
        'loader': load_cms_chow_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_ddinter': {
        'name': 'CMS DDInter',
        'description': 'CMS drug-drug interaction data',
        'fetcher': CMSDDInterFetcher,
        'loader': load_cms_ddinter_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_dmepos': {
        'name': 'CMS DMEPOS',
        'description': 'CMS Durable Medical Equipment supplier utilization',
        'fetcher': CMSDMEPOSFetcher,
        'loader': load_cms_dmepos_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_formulary': {
        'name': 'CMS Medicare Formulary',
        'description': 'CMS Medicare Part D plan formulary data',
        'fetcher': CMSFormularyFetcher,
        'loader': load_cms_formulary_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_hcris': {
        'name': 'CMS HCRIS',
        'description': 'CMS Hospital Cost Report Information System',
        'fetcher': CMSHCRISFetcher,
        'loader': load_cms_hcris_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_hospital_affiliation': {
        'name': 'CMS Hospital Affiliation',
        'description': 'CMS hospital system affiliation data',
        'fetcher': CMSHospitalAffiliationFetcher,
        'loader': load_cms_hospital_affiliation_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_hospital_quality': {
        'name': 'CMS Hospital Quality',
        'description': 'CMS HCAHPS and hospital quality measures',
        'fetcher': CMSHospitalQualityFetcher,
        'loader': load_cms_hospital_quality_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_magnet': {
        'name': 'CMS Magnet',
        'description': 'CMS Magnet hospital designation data',
        'fetcher': CMSMagnetFetcher,
        'loader': load_cms_magnet_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_ndc': {
        'name': 'CMS NDC Directory',
        'description': 'CMS National Drug Code directory',
        'fetcher': CMSNDCFetcher,
        'loader': load_cms_ndc_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_nucc': {
        'name': 'CMS NUCC Taxonomy',
        'description': 'NUCC National Uniform Claim Committee provider taxonomy codes',
        'fetcher': CMSNUCCFetcher,
        'loader': load_cms_nucc_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_pecos': {
        'name': 'CMS PECOS',
        'description': 'CMS Provider Enrollment, Chain, and Ownership System',
        'fetcher': CMSPECOSFetcher,
        'loader': load_cms_pecos_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_pos': {
        'name': 'CMS Place of Service',
        'description': 'CMS Place of Service codes',
        'fetcher': CMSPOSFetcher,
        'loader': load_cms_pos_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_post_acute': {
        'name': 'CMS Post-Acute Care',
        'description': 'CMS SNF/IRF/LTACH post-acute care data',
        'fetcher': CMSPostAcuteFetcher,
        'loader': load_cms_post_acute_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_rbcs': {
        'name': 'CMS RBCS',
        'description': 'CMS Restructured BETOS Classification System',
        'fetcher': CMSRBCSFetcher,
        'loader': load_cms_rbcs_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_stabilis': {
        'name': 'CMS Stabilis',
        'description': 'IV drug compatibility and stability data',
        'fetcher': CMSStabilisFetcher,
        'loader': load_cms_stabilis_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_usp': {
        'name': 'CMS USP Classifications',
        'description': 'USP drug classification system',
        'fetcher': CMSUSPFetcher,
        'loader': load_cms_usp_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'euipo_designs': {
        'name': 'EUIPO Designs',
        'description': 'EUIPO registered design data',
        'fetcher': EUIPODesignsFetcher,
        'loader': load_euipo_designs_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    # --- CMS PUF file-based sources (019-cms-puf-platform-reconciliation) ---
    'cms_nppes': {
        'name': 'CMS NPPES',
        'description': 'National Plan and Provider Enumeration System — NPI registry (weekly incremental)',
        'fetcher': CMSNPPESFetcher,
        'loader': load_cms_nppes,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_physician_puf': {
        'name': 'CMS Physician PUF',
        'description': 'CMS Medicare Physician & Other Suppliers PUF (provider-level)',
        'fetcher': CMSPhysicianPUFFetcher,
        'loader': load_cms_physician_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_physician_puf_services': {
        'name': 'CMS Physician PUF Services',
        'description': 'CMS Medicare Physician PUF at NPI × HCPCS service-line grain',
        'fetcher': CMSPhysicianPUFServicesFetcher,
        'loader': load_cms_physician_puf_services,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_part_d_spending': {
        'name': 'CMS Part D Drug Spending',
        'description': 'Medicare Part D drug spending by drug (annual PUF)',
        'fetcher': CMSPartDSpendingFetcher,
        'loader': load_cms_part_d_spending,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_part_b_spending': {
        'name': 'CMS Part B Drug Spending',
        'description': 'Medicare Part B drug and biological spending (annual PUF)',
        'fetcher': CMSPartBSpendingFetcher,
        'loader': load_cms_part_b_spending,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_open_payments': {
        'name': 'CMS Open Payments',
        'description': 'Physician-industry payment data (Sunshine Act)',
        'fetcher': CMSOpenPaymentsFetcher,
        'loader': load_cms_open_payments,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_inpatient_puf': {
        'name': 'CMS Inpatient PUF',
        'description': 'Medicare inpatient prospective payment system PUF (DRG level)',
        'fetcher': CMSInpatientPUFFetcher,
        'loader': load_cms_inpatient_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_hospital_general_info': {
        'name': 'CMS Hospital General Info',
        'description': 'Hospital Compare general information and overall ratings',
        'fetcher': CMSHospitalGeneralInfoFetcher,
        'loader': load_cms_hospital_general_info,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_medicare_advantage': {
        'name': 'CMS Medicare Advantage',
        'description': 'Medicare Advantage enrollment and plan data (monthly PUF)',
        'fetcher': CMSMedicareAdvantageFetcher,
        'loader': load_cms_medicare_advantage,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_medicaid_drug_spending': {
        'name': 'CMS Medicaid Drug Spending',
        'description': 'Medicaid drug spending by drug (annual PUF)',
        'fetcher': CMSMedicaidDrugSpendingFetcher,
        'loader': load_cms_medicaid_drug_spending,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_dme_puf': {
        'name': 'CMS DME PUF',
        'description': 'Medicare DME supplier utilization and payment (annual PUF)',
        'fetcher': CMSDMEPUFFetcher,
        'loader': load_cms_dme_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_home_health': {
        'name': 'CMS Home Health PUF',
        'description': 'Medicare home health agency utilization and payment (annual PUF)',
        'fetcher': CMSHomeHealthFetcher,
        'loader': load_cms_home_health,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_hospice_puf': {
        'name': 'CMS Hospice PUF',
        'description': 'Medicare hospice provider utilization and payment (annual PUF)',
        'fetcher': CMSHospicePUFFetcher,
        'loader': load_cms_hospice_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_snf_puf': {
        'name': 'CMS SNF PUF',
        'description': 'Medicare skilled nursing facility utilization and payment (annual PUF)',
        'fetcher': CMSSNFPUFFetcher,
        'loader': load_cms_snf_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_outpatient_puf': {
        'name': 'CMS Outpatient PUF',
        'description': 'Medicare outpatient prospective payment system PUF (APC level)',
        'fetcher': CMSOutpatientPUFFetcher,
        'loader': load_cms_outpatient_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_referring_providers': {
        'name': 'CMS Referring Providers',
        'description': 'Medicare physician referral patterns PUF',
        'fetcher': CMSReferringProvidersFetcher,
        'loader': load_cms_referring_providers,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_ordering_providers': {
        'name': 'CMS Ordering Providers',
        'description': 'Medicare ordering and referring provider utilization PUF',
        'fetcher': CMSOrderingProvidersFetcher,
        'loader': load_cms_ordering_providers,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_lab_services': {
        'name': 'CMS Lab Services PUF',
        'description': 'Medicare clinical lab fee schedule utilization (annual PUF)',
        'fetcher': CMSLabServicesFetcher,
        'loader': load_cms_lab_services,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_imaging_puf': {
        'name': 'CMS Imaging PUF',
        'description': 'Medicare imaging services utilization and payment (annual PUF)',
        'fetcher': CMSImagingPUFFetcher,
        'loader': load_cms_imaging_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_mental_health_puf': {
        'name': 'CMS Mental Health PUF',
        'description': 'Medicare mental health services utilization and payment (from Physician PUF, filtered by MH provider types)',
        'fetcher': CMSMentalHealthPUFFetcher,
        'loader': load_cms_mental_health_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_opioid_puf': {
        'name': 'CMS Opioid PUF',
        'description': 'Medicare opioid prescribing patterns at provider-drug grain',
        'fetcher': CMSOpioidPUFFetcher,
        'loader': load_cms_opioid_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_telehealth_puf': {
        'name': 'CMS Telehealth PUF',
        'description': 'Medicare telehealth services utilization and payment (annual PUF)',
        'fetcher': CMSTelehealthPUFFetcher,
        'loader': load_cms_telehealth_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_chronic_conditions': {
        'name': 'CMS Chronic Conditions PUF',
        'description': 'Medicare chronic condition prevalence — retired from public download; requires CMS CCW research access (https://www2.ccwdata.org)',
        'fetcher': CMSChronicConditionsFetcher,
        'loader': load_cms_chronic_conditions,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_dual_eligible': {
        'name': 'CMS Dual Eligible PUF',
        'description': 'Medicare-Medicaid dual eligible beneficiary statistics — Excel workbook format requires custom parser',
        'fetcher': CMSDualEligibleFetcher,
        'loader': load_cms_dual_eligible,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_enrollment_puf': {
        'name': 'CMS Enrollment PUF',
        'description': 'Medicare beneficiary enrollment statistics by geography/demographics',
        'fetcher': CMSEnrollmentPUFFetcher,
        'loader': load_cms_enrollment_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_claim_type_puf': {
        'name': 'CMS Claim Type PUF',
        'description': 'Medicare claims by claim type and geography',
        'fetcher': CMSClaimTypePUFFetcher,
        'loader': load_cms_claim_type_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_utilization_puf': {
        'name': 'CMS Utilization PUF',
        'description': 'Medicare service utilization rates by beneficiary demographics/geography',
        'fetcher': CMSUtilizationPUFFetcher,
        'loader': load_cms_utilization_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_cost_reports_puf': {
        'name': 'CMS Cost Reports PUF',
        'description': 'Hospital cost report data (HCRIS PUF)',
        'fetcher': CMSCostReportsPUFFetcher,
        'loader': load_cms_cost_reports_puf,
        'requires_file': True,
        'default_days_back': None,
    },
    'cms_cost_reports_puf_lines': {
        'name': 'CMS Cost Reports PUF Lines',
        'description': 'Hospital cost report worksheet line items (HCRIS PUF)',
        'fetcher': CMSCostReportsPUFFetcher,
        'loader': load_cms_cost_reports_puf_lines,
        'requires_file': True,
        'default_days_back': None,
    },
    # --- Legacy molecule sources (promoted from raw.* to mol_raw.* in migration 095) ---
    'rxnorm': {
        'name': 'NLM RxNorm',
        'description': 'NLM RxNorm drug identifier vocabulary (ingredients and brand names)',
        'fetcher': RxNormFetcher,
        'loader': load_rxnorm_data,
        'requires_file': False,
        'default_days_back': None,  # full-refresh vocabulary, no date filter
    },
    'who_inn': {
        'name': 'WHO INN',
        'description': 'WHO International Nonproprietary Names (via PubChem synonyms)',
        'fetcher': WHOINNFetcher,
        'loader': load_who_inn_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'pharmgkb': {
        'name': 'PharmGKB',
        'description': 'PharmGKB pharmacogenomics knowledge base',
        'fetcher': PharmGKBFetcher,
        'loader': load_pharmgkb_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'kegg_drug': {
        'name': 'KEGG Drug',
        'description': 'KEGG Drug compound and pathway database',
        'fetcher': KEGGDrugFetcher,
        'loader': load_kegg_drug_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'tdc_admet': {
        'name': 'TDC ADMET',
        'description': 'Therapeutics Data Commons ADMET prediction benchmarks',
        'fetcher': TDCAdmetFetcher,
        'loader': load_tdc_admet_data,
        'requires_file': False,
        'default_days_back': None,  # static benchmark datasets, monthly refresh
    },
    # --- New molecule vocabulary sources (019-cms-puf-platform-reconciliation) ---
    'ema': {
        'name': 'EMA EPAR',
        'description': 'EMA European Public Assessment Reports (authorised medicines)',
        'fetcher': EMAMolFetcher,
        'loader': load_ema_mol_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'orange_book': {
        'name': 'FDA Orange Book',
        'description': 'FDA Approved Drug Products with Therapeutic Equivalence Evaluations',
        'fetcher': OrangeBookFetcher,
        'loader': load_orange_book_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'dailymed': {
        'name': 'DailyMed',
        'description': 'NLM DailyMed structured product labels (SPL)',
        'fetcher': DailyMedFetcher,
        'loader': load_dailymed_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'fda_drugs': {
        'name': 'FDA Drugs@FDA',
        'description': 'FDA drug application approvals (NDA/ANDA/BLA)',
        'fetcher': FDADrugsFetcher,
        'loader': load_fda_drugs_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'ttd': {
        'name': 'TTD',
        'description': 'Therapeutic Target Database — targets, drugs, and drug-target interactions',
        'fetcher': TTDFetcher,
        'loader': load_ttd_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'imgt': {
        'name': 'IMGT',
        'description': 'IMGT immunogenetics gene database (IG/TR FASTA sequences)',
        'fetcher': IMGTFetcher,
        'loader': load_imgt_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cdc_vaccines': {
        'name': 'CDC Vaccines',
        'description': 'CDC CVX/MVX vaccine code sets',
        'fetcher': CDCVaccinesFetcher,
        'loader': load_cdc_vaccines_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'clinicaltrials': {
        'name': 'ClinicalTrials.gov',
        'description': 'ClinicalTrials.gov v2 study data',
        'fetcher': ClinicalTrialsFetcher,
        'loader': load_clinicaltrials_data,
        'requires_file': False,
        'default_days_back': 30,
    },
    'openfda_labels': {
        'name': 'OpenFDA Drug Labels',
        'description': 'FDA drug label (SPL) data via openFDA API',
        'fetcher': OpenFDALabelsFetcher,
        'loader': load_openfda_labels_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    'chembl_activities': {
        'name': 'ChEMBL Bioactivity',
        'description': 'ChEMBL IC50/Ki/EC50 bioactivity measurements',
        'fetcher': ChEMBLActivitiesFetcher,
        'loader': load_chembl_activities_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'fda_rems': {
        'name': 'FDA REMS Programs',
        'description': 'FDA Risk Evaluation and Mitigation Strategy programs',
        'fetcher': FDARemsFetcher,
        'loader': load_fda_rems_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'fda_ndc': {
        'name': 'FDA NDC Directory',
        'description': 'FDA National Drug Code product directory',
        'fetcher': FDANDCFetcher,
        'loader': load_fda_ndc_data,
        'requires_file': False,
        'default_days_back': None,
    },
}


def _meta_name(source: str) -> str:
    """Resolve the meta.data_sources source_name for a given SOURCES key."""
    return SOURCES.get(source, {}).get('meta_name', source)


def get_last_successful_refresh(source_name: str) -> datetime | None:
    """Query meta.data_sources for the last successful refresh timestamp."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT last_successful_refresh
                FROM meta.data_sources
                WHERE source_name = %s
            """, (source_name,))
            row = cur.fetchone()
            if row and row[0]:
                dt = row[0]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
    except Exception as e:
        logger.warning(f"Could not read last_successful_refresh for {source_name}: {e}")
    return None


def _compute_days_back(source: str, source_info: dict) -> int | None:
    """Compute days_back from the last successful refresh, with safety margin.

    Returns None if the source doesn't support days_back.
    """
    default = source_info.get('default_days_back')
    if default is None:
        return None  # source doesn't support incremental fetching

    meta_source = _meta_name(source)
    last_refresh = get_last_successful_refresh(meta_source)
    if last_refresh is None:
        logger.info(
            "No prior refresh for %s — using backfill window of %d days",
            source, default,
        )
        return default

    elapsed = (datetime.now(timezone.utc) - last_refresh).total_seconds() / 86400
    # +1 day safety overlap to avoid gaps from timezone/clock skew
    days_back = max(int(elapsed) + 1, 1)
    logger.info(
        "Last successful refresh for %s was %.1f days ago — fetching %d days",
        source, elapsed, days_back,
    )
    return days_back


def log_to_meta(source_name: str, result: dict) -> None:
    """Log ingestion result to meta.refresh_log."""
    try:
        with get_cursor() as cur:
            # Get source_id
            cur.execute("""
                SELECT source_id FROM meta.data_sources WHERE source_name = %s
            """, (source_name,))
            row = cur.fetchone()

            if row is None:
                logger.warning(f"Source '{source_name}' not found in meta.data_sources")
                return

            source_id = row[0]

            # Insert log entry
            status = result.get('status', 'unknown')
            cur.execute("""
                INSERT INTO meta.refresh_log (
                    source_id, source_name, started_at, completed_at,
                    status, records_fetched, records_inserted, records_updated,
                    error_message
                ) VALUES (
                    %s, %s, %s, NOW(), %s, %s, %s, %s, %s
                )
            """, (
                source_id,
                source_name,
                datetime.now(),
                status,
                result.get('records_fetched', result.get('records_inserted', 0)),
                result.get('records_inserted', 0),
                result.get('records_updated', 0),
                json.dumps(result['errors'][:5]) if result.get('errors') else None
            ))

            # Update data_sources
            cur.execute("""
                UPDATE meta.data_sources
                SET last_refresh_attempt = NOW(),
                    last_refresh_status = %s,
                    last_successful_refresh = CASE
                        WHEN %s IN ('success', 'partial') THEN NOW()
                        ELSE last_successful_refresh
                    END,
                    record_count = COALESCE(%s, record_count)
                WHERE source_id = %s
            """, (
                status,
                status,
                result.get('records_inserted'),
                source_id
            ))

    except Exception as e:
        logger.error(f"Failed to log to meta: {e}")


def run_ingestion(source: str, **kwargs) -> dict:
    """Run ingestion for a specific source."""
    if source not in SOURCES:
        raise ValueError(f"Unknown source: {source}. Available: {list(SOURCES.keys())}")

    source_info = SOURCES[source]
    meta_source = _meta_name(source)

    logger.info(f"Starting ingestion for {source_info['name']}")

    # File-based source with explicit --file: skip fetcher, go straight to loader.
    # Many CMS PUF fetchers are stubs (the file is pre-downloaded by the CronJob or
    # seed_samples.py). When a filepath is provided and the source requires a file,
    # bypass the fetcher entirely so the loader actually runs.
    if kwargs.get('filepath') and source_info.get('requires_file'):
        pass  # fall through to the file-loader path below

    # API source: fetch then load
    elif 'fetcher' in source_info:
        data_dir = kwargs.get('data_dir', '/tmp/data/raw')
        Path(data_dir).mkdir(parents=True, exist_ok=True)

        fetcher = source_info['fetcher'](data_dir=data_dir)

        # Compute incremental days_back from last successful refresh.
        # --days-back CLI override bypasses the computed window (for manual backfills).
        fetch_kwargs = {}
        if kwargs.get('days_back') is not None:
            # Explicit override: use the caller-specified window regardless of state.
            days_back = kwargs['days_back']
            logger.info("Using explicit days_back=%d override for %s", days_back, source)
        else:
            days_back = _compute_days_back(source, source_info)
        if days_back is not None:
            fetch_kwargs['days_back'] = days_back
        if kwargs.get('max_records') is not None:
            fetch_kwargs['max_records'] = kwargs['max_records']

        fetch_result = fetcher.fetch(**fetch_kwargs)

        if fetch_result.get('status') in ('failed', 'source_unavailable'):
            logger.warning(f"Fetch failed for {source}: {fetch_result.get('error')}")
            log_to_meta(meta_source, fetch_result)
            return fetch_result

        loader = source_info['loader']

        # File-path fetchers (e.g. GV PUF) return extracted_files + int records count.
        # Call the loader once per extracted file using filepath + year kwargs.
        if fetch_result.get('extracted_files'):
            import inspect as _inspect
            import csv as _csv
            agg = {'status': 'success', 'records_inserted': 0, 'records_failed': 0, 'errors': []}
            loader_params = set(_inspect.signature(loader).parameters.keys())
            for fpath in fetch_result['extracted_files']:
                loader_kw: dict = {'filepath': fpath}
                # Pass source_year to loaders that accept it.  Precedence:
                #   1. explicit --fiscal-year / fiscal_year kwarg
                #   2. year returned by fetcher (fetch_result['year'])
                #   3. YEAR column in the first row of the fetched CSV (most CMS datasets)
                #   4. loader default (2023 — only used when none of the above apply)
                if 'source_year' in loader_params:
                    sy = kwargs.get('fiscal_year') or fetch_result.get('year')
                    if sy is None:
                        # Auto-detect year from the first data row of the CSV.
                        try:
                            with open(fpath, newline='', encoding='utf-8') as _f:
                                _row = next(_csv.DictReader(_f), None)
                            if _row:
                                for _col in ('YEAR', 'Year', 'year'):
                                    _yval = _row.get(_col, '')
                                    if _yval and str(_yval).strip().isdigit():
                                        sy = int(str(_yval).strip())
                                        break
                        except Exception:
                            pass
                    if sy is not None:
                        loader_kw['source_year'] = int(sy)
                # Legacy 'year' parameter name used by some older loaders
                elif fetch_result.get('year') is not None and 'year' in loader_params:
                    loader_kw['year'] = fetch_result['year']
                if 'batch_size' in kwargs and 'batch_size' in loader_params:
                    loader_kw['batch_size'] = kwargs['batch_size']
                if kwargs.get('max_records') and 'max_records' in loader_params:
                    loader_kw['max_records'] = kwargs['max_records']
                r = loader(**loader_kw)
                agg['records_inserted'] += r.get('records_inserted', 0)
                agg['records_failed'] += r.get('records_failed', 0)
                agg['errors'].extend(r.get('errors', []))
            agg['records_fetched'] = fetch_result.get('records', 0)
            log_to_meta(meta_source, agg)
            return agg

        # Standard API fetchers return records as a list of dicts.
        if not fetch_result.get('records'):
            logger.warning(f"Fetch returned no records for {source}")
            log_to_meta(meta_source, fetch_result)
            return fetch_result

        result = loader(fetch_result['records'], source_hash=fetch_result.get('hash'))
        result['records_fetched'] = fetch_result.get(
            'record_count', len(fetch_result.get('records', []))
        )
        log_to_meta(meta_source, result)
        return result

    # File source: existing pattern
    loader = source_info['loader']

    # Build kwargs for loader
    loader_kwargs = {}

    if source_info.get('requires_file'):
        if 'filepath' not in kwargs or not kwargs['filepath']:
            raise ValueError(f"Source '{source}' requires a file path")
        loader_kwargs['filepath'] = kwargs['filepath']
    elif source_info.get('accepts_file') and kwargs.get('filepath'):
        # Optional file parameter
        loader_kwargs['filepath'] = kwargs['filepath']

    if source_info.get('requires_fiscal_year'):
        if 'fiscal_year' not in kwargs or not kwargs['fiscal_year']:
            raise ValueError(f"Source '{source}' requires fiscal_year")
        loader_kwargs['fiscal_year'] = kwargs['fiscal_year']

    # Pass source_year to any loader that accepts it (all CMS PUF loaders do).
    import inspect as _inspect
    _loader_params = set(_inspect.signature(loader).parameters.keys())
    if 'source_year' in _loader_params and kwargs.get('fiscal_year'):
        loader_kwargs['source_year'] = int(kwargs['fiscal_year'])

    if 'batch_size' in kwargs and source_info.get('accepts_batch_size'):
        loader_kwargs['batch_size'] = kwargs['batch_size']

    # Pass max_records to file loaders that support it (limits rows read from CSV)
    if kwargs.get('max_records') and source_info.get('requires_file'):
        loader_kwargs['max_records'] = kwargs['max_records']

    # Run loader
    result = loader(**loader_kwargs)

    # Log to meta
    log_to_meta(meta_source, result)

    return result


def list_sources():
    """Print available data sources."""
    print("\nAvailable Data Sources:")
    print("-" * 60)
    for key, info in SOURCES.items():
        file_req = "[file required]" if info.get('requires_file') else "[API]"
        print(f"  {key:20} - {info['description']} {file_req}")
    print()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='TAVR Data Infrastructure - Data Ingestion CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load CMS Medicare Inpatient data
  python -m dk_data.ingestion.main cms_inpatient --file data/cms_inpatient_2023.csv --fiscal-year 2023

  # Load CMS Hospital Info
  python -m dk_data.ingestion.main cms_hospital_info --file data/hospital_info.csv

  # Load HRSA data from API
  python -m dk_data.ingestion.main hrsa

  # Fetch and load PubMed data (API source)
  python -m dk_data.ingestion.main pubmed

  # API source with --source flag
  python -m dk_data.ingestion.main --source pubmed

  # List available sources
  python -m dk_data.ingestion.main --list
        """
    )

    parser.add_argument('source', nargs='?', help='Data source to ingest')
    parser.add_argument('--source', '-s', dest='source_flag', help='Data source (alternative to positional)')
    parser.add_argument('--file', '-f', dest='filepath', help='Path to data file')
    parser.add_argument('--fiscal-year', '-y', type=int, help='Fiscal year of data')
    parser.add_argument('--batch-size', '-b', type=int, default=1000, help='Batch size for commits')
    parser.add_argument('--max-records', '-m', type=int, default=None, help='Cap on records fetched (for seeding/testing)')
    parser.add_argument('--data-dir', '-d', default='/tmp/data/raw', help='Directory for fetcher temp storage')
    parser.add_argument('--days-back', type=int, default=None,
                        help='Override incremental days_back window (bypasses meta.data_sources state). '
                             'Use for initial backfill: --days-back 730 fetches 2 years regardless of last_successful_refresh.')
    parser.add_argument('--list', '-l', action='store_true', help='List available sources')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    args = parser.parse_args()

    # Resolve source from positional arg or --source flag
    source = args.source or args.source_flag

    # Configure observability (013-dk-data-observability)
    global logger
    job_name = f"fetch-{source}" if source else "ingestion-cli"
    if _OBS_AVAILABLE:
        setup_telemetry(job_name)
        setup_logging(job_name)
        logger = get_logger(__name__)
    else:
        log_level = logging.DEBUG if args.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    if args.list:
        list_sources()
        return 0

    if not source:
        parser.print_help()
        return 1

    # Initialize connection pool
    init_connection_pool()

    start_time = time.monotonic()
    status = "failure"
    records = 0

    try:
        tracer = get_tracer(__name__) if _OBS_AVAILABLE else None

        if tracer:
            with tracer.start_as_current_span(f"{job_name}-execution") as span:
                span.set_attribute("source", source)
                span.set_attribute("batch_size", args.batch_size)
                result = run_ingestion(
                    source=source,
                    filepath=args.filepath,
                    fiscal_year=args.fiscal_year,
                    batch_size=args.batch_size,
                    max_records=args.max_records,
                    data_dir=args.data_dir,
                    days_back=args.days_back,
                )
                records = result.get('records_inserted', result.get('records_fetched', 0))
                span.set_attribute("records_fetched", records)
        else:
            result = run_ingestion(
                source=source,
                filepath=args.filepath,
                fiscal_year=args.fiscal_year,
                batch_size=args.batch_size,
                max_records=args.max_records,
                data_dir=args.data_dir,
                days_back=args.days_back,
            )
            records = result.get('records_inserted', result.get('records_fetched', 0))

        print("\nIngestion Result:")
        print("-" * 40)
        for key, value in result.items():
            if key != 'errors':
                print(f"  {key}: {value}")

        if result.get('errors'):
            print("\nFirst few errors:")
            for err in result['errors'][:5]:
                print(f"  - {err}")

        result_status = result.get('status')
        # Loaders that succeed often return {records_inserted, records_skipped} with no 'status' key.
        loader_succeeded = result_status is None and 'records_inserted' in result
        if result_status in ('success', 'skipped', 'partial', 'source_unavailable') or loader_succeeded:
            status = "success"
            return 0
        else:
            return 1

    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        return 1

    finally:
        close_connection_pool()
        duration = time.monotonic() - start_time
        if _OBS_AVAILABLE:
            try:
                asyncio.run(report_completion(
                    job_name=job_name,
                    status=status,
                    duration_seconds=duration,
                    records_processed=records,
                    source_name=source,
                ))
            except Exception as e:
                logger.warning(f"Failed to report completion: {e}")


if __name__ == '__main__':
    sys.exit(main())
