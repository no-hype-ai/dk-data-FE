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
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from .sources import cms_inpatient, cms_hospital_info, cms_cost_reports, acc_tvc, hrsa
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
from .sources.uspto_trademarks import load_uspto_trademarks_data
from .sources.euipo_trademarks import load_euipo_trademarks_data
from .sources.euipo_designs import load_euipo_designs_data
# CMS PUF source loaders (016-cms-puf-datasource-integration)
from .sources.cms_nppes import load_cms_nppes_data
from .sources.cms_part_d_prescriber import load_cms_part_d_prescriber_data
from .sources.cms_physician_puf import load_cms_physician_puf_data
from .sources.cms_open_payments import load_cms_open_payments_data
from .sources.cms_care_compare import load_cms_care_compare_data
# CMS PUF Phase 3: Facility loaders
from .sources.cms_pos import load_cms_pos_data
from .sources.cms_pecos import load_cms_pecos_data
from .sources.cms_chow import load_cms_chow_data
from .sources.cms_hospital_affiliation import load_cms_hospital_affiliation_data
from .sources.cms_inpatient_puf import load_cms_inpatient_puf_data
from .sources.cms_outpatient_puf import load_cms_outpatient_puf_data
from .sources.cms_hospital_quality import load_cms_hospital_quality_data
from .sources.cms_hospital_general_info import load_cms_hospital_general_info_data
from .sources.cms_hcris import load_cms_hcris_data
from .sources.cms_magnet import load_cms_magnet_data
# CMS PUF Phase 4: Drug/Market loaders
from .sources.cms_ndc import load_cms_ndc_data
from .sources.cms_part_d_spending import load_cms_part_d_spending_data
from .sources.cms_part_b_spending import load_cms_part_b_spending_data
from .sources.cms_formulary import load_cms_formulary_data
from .sources.cms_rbcs import load_cms_rbcs_data
from .sources.cms_usp import load_cms_usp_data
from .sources.cms_nucc import load_cms_nucc_data
from .sources.cms_geographic_variation import load_cms_geographic_variation_data
from .sources.cms_chronic_conditions import load_cms_chronic_conditions_data
from .sources.cms_post_acute import load_cms_post_acute_data
from .sources.cms_dmepos import load_cms_dmepos_data
from .sources.cms_ddinter import load_cms_ddinter_data
from .sources.cms_stabilis import load_cms_stabilis_data

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
    USPTOTrademarksFetcher,
    EUIPOTrademarksFetcher,
    EUIPODesignsFetcher,
    # CMS PUF (016)
    CMSNPPESFetcher,
    CMSPartDPrescriberFetcher,
    CMSPhysicianPUFFetcher,
    CMSOpenPaymentsFetcher,
    CMSCareCompareFetcher,
    # Phase 3: Facility
    CMSPOSFetcher,
    CMSPECOSFetcher,
    CMSCHOWFetcher,
    CMSHospitalAffiliationFetcher,
    CMSInpatientPUFFetcher,
    CMSOutpatientPUFFetcher,
    CMSHospitalQualityFetcher,
    CMSHospitalGeneralInfoFetcher,
    CMSHCRISFetcher,
    CMSMagnetFetcher,
    # Phase 4: Drug/Market
    CMSNDCFetcher,
    CMSPartDSpendingFetcher,
    CMSPartBSpendingFetcher,
    CMSFormularyFetcher,
    CMSRBCSFetcher,
    CMSUSPFetcher,
    CMSNUCCFetcher,
    CMSGeographicVariationFetcher,
    CMSChronicConditionsFetcher,
    CMSPostAcuteFetcher,
    CMSDMEPOSFetcher,
    CMSDDInterFetcher,
    CMSStabilisFetcher,
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
        'loader': hrsa.load_hrsa_shortage_areas,
        'requires_file': False,  # Can use API or file
        'accepts_file': True,  # File is optional
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
        'hash_skip_enabled': False,  # ephemeral feed, always reload
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
        'hash_skip_enabled': False,  # ephemeral feed, always reload
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
    'euipo_designs': {
        'name': 'EUIPO Designs',
        'description': 'EUIPO registered community design data (pharma packaging, medical devices)',
        'fetcher': EUIPODesignsFetcher,
        'loader': load_euipo_designs_data,
        'requires_file': False,
        'default_days_back': 90,
    },
    # ── CMS PUF sources (016-cms-puf-datasource-integration) ──────────────
    'cms_nppes': {
        'name': 'CMS NPPES',
        'description': 'National Plan & Provider Enumeration System (bulk NPI registry)',
        'fetcher': CMSNPPESFetcher,
        'loader': load_cms_nppes_data,
        'requires_file': False,
        'default_days_back': None,  # full dump each run (weekly)
    },
    'cms_part_d_prescriber': {
        'name': 'CMS Part D Prescriber',
        'description': 'Medicare Part D prescriber-level drug utilization',
        'fetcher': CMSPartDPrescriberFetcher,
        'loader': load_cms_part_d_prescriber_data,
        'requires_file': False,
        'default_days_back': None,  # annual release
    },
    'cms_physician_puf': {
        'name': 'CMS Physician PUF',
        'description': 'Medicare Physician & Other Practitioners procedure utilization',
        'fetcher': CMSPhysicianPUFFetcher,
        'loader': load_cms_physician_puf_data,
        'requires_file': False,
        'default_days_back': None,  # annual release
    },
    'cms_open_payments': {
        'name': 'CMS Open Payments',
        'description': 'Industry payments to physicians (General, Research, Ownership)',
        'fetcher': CMSOpenPaymentsFetcher,
        'loader': load_cms_open_payments_data,
        'requires_file': False,
        'default_days_back': None,  # annual release
    },
    'cms_care_compare': {
        'name': 'CMS Care Compare',
        'description': 'Hospital quality ratings and general information',
        'fetcher': CMSCareCompareFetcher,
        'loader': load_cms_care_compare_data,
        'requires_file': False,
        'default_days_back': None,  # quarterly release
    },
    # ── CMS PUF Phase 3: Facility sources ─────────────────────────────────
    'cms_pos': {
        'name': 'CMS Provider of Services',
        'description': 'Provider of Services file (facility demographics)',
        'fetcher': CMSPOSFetcher,
        'loader': load_cms_pos_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_pecos': {
        'name': 'CMS PECOS',
        'description': 'Medicare Provider Supplier Enrollment',
        'fetcher': CMSPECOSFetcher,
        'loader': load_cms_pecos_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_chow': {
        'name': 'CMS CHOW',
        'description': 'Change of Ownership records',
        'fetcher': CMSCHOWFetcher,
        'loader': load_cms_chow_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_hospital_affiliation': {
        'name': 'CMS Hospital Affiliation',
        'description': 'Hospital affiliation relationships',
        'fetcher': CMSHospitalAffiliationFetcher,
        'loader': load_cms_hospital_affiliation_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_inpatient_puf': {
        'name': 'CMS Inpatient PUF',
        'description': 'Medicare inpatient DRG volumes',
        'fetcher': CMSInpatientPUFFetcher,
        'loader': load_cms_inpatient_puf_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_outpatient_puf': {
        'name': 'CMS Outpatient PUF',
        'description': 'Medicare outpatient procedure volumes',
        'fetcher': CMSOutpatientPUFFetcher,
        'loader': load_cms_outpatient_puf_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_hospital_quality': {
        'name': 'CMS Hospital Quality',
        'description': 'Hospital star ratings',
        'fetcher': CMSHospitalQualityFetcher,
        'loader': load_cms_hospital_quality_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_hospital_general_info': {
        'name': 'CMS Hospital General Info',
        'description': 'Hospital general information',
        'fetcher': CMSHospitalGeneralInfoFetcher,
        'loader': load_cms_hospital_general_info_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_hcris': {
        'name': 'CMS HCRIS',
        'description': 'Healthcare Cost Report Information System',
        'fetcher': CMSHCRISFetcher,
        'loader': load_cms_hcris_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_magnet': {
        'name': 'CMS Magnet',
        'description': 'ANCC Magnet Recognition (web scrape)',
        'fetcher': CMSMagnetFetcher,
        'loader': load_cms_magnet_data,
        'requires_file': False,
        'default_days_back': None,
    },
    # ── CMS PUF Phase 4: Drug/Market sources ──────────────────────────────
    'cms_ndc': {
        'name': 'CMS NDC',
        'description': 'National Drug Code Directory',
        'fetcher': CMSNDCFetcher,
        'loader': load_cms_ndc_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_part_d_spending': {
        'name': 'CMS Part D Spending',
        'description': 'Medicare Part D drug spending by drug',
        'fetcher': CMSPartDSpendingFetcher,
        'loader': load_cms_part_d_spending_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_part_b_spending': {
        'name': 'CMS Part B Spending',
        'description': 'Medicare Part B drug spending',
        'fetcher': CMSPartBSpendingFetcher,
        'loader': load_cms_part_b_spending_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_formulary': {
        'name': 'CMS Formulary',
        'description': 'Medicare plan formulary data',
        'fetcher': CMSFormularyFetcher,
        'loader': load_cms_formulary_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_rbcs': {
        'name': 'CMS RBCS',
        'description': 'Restructured BETOS Classification',
        'fetcher': CMSRBCSFetcher,
        'loader': load_cms_rbcs_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_usp': {
        'name': 'CMS USP',
        'description': 'USP Drug Classification',
        'fetcher': CMSUSPFetcher,
        'loader': load_cms_usp_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_nucc': {
        'name': 'CMS NUCC',
        'description': 'NUCC Provider Taxonomy',
        'fetcher': CMSNUCCFetcher,
        'loader': load_cms_nucc_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_geographic_variation': {
        'name': 'CMS Geographic Variation',
        'description': 'Medicare geographic comparisons',
        'fetcher': CMSGeographicVariationFetcher,
        'loader': load_cms_geographic_variation_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_chronic_conditions': {
        'name': 'CMS Chronic Conditions',
        'description': 'Chronic conditions prevalence by state',
        'fetcher': CMSChronicConditionsFetcher,
        'loader': load_cms_chronic_conditions_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_post_acute': {
        'name': 'CMS Post-Acute',
        'description': 'Post-acute care utilization',
        'fetcher': CMSPostAcuteFetcher,
        'loader': load_cms_post_acute_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_dmepos': {
        'name': 'CMS DMEPOS',
        'description': 'Durable medical equipment utilization',
        'fetcher': CMSDMEPOSFetcher,
        'loader': load_cms_dmepos_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_ddinter': {
        'name': 'CMS DDInter',
        'description': 'Drug-drug interactions (DDInter API)',
        'fetcher': CMSDDInterFetcher,
        'loader': load_cms_ddinter_data,
        'requires_file': False,
        'default_days_back': None,
    },
    'cms_stabilis': {
        'name': 'CMS Stabilis',
        'description': 'IV drug compatibility (Stabilis)',
        'fetcher': CMSStabilisFetcher,
        'loader': load_cms_stabilis_data,
        'requires_file': False,
        'default_days_back': None,
    },
}


def _meta_name(source: str) -> str:
    """Resolve the meta.ops_data_sources source_name for a given SOURCES key."""
    return SOURCES.get(source, {}).get('meta_name', source)


def get_last_successful_refresh(source_name: str) -> datetime | None:
    """Query meta.ops_data_sources for the last successful refresh timestamp."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT last_successful_refresh
                FROM meta.ops_data_sources
                WHERE source_name = %s
            """, (source_name,))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
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

    elapsed = (datetime.now() - last_refresh).total_seconds() / 86400
    # +1 day safety overlap to avoid gaps from timezone/clock skew
    days_back = max(int(elapsed) + 1, 1)
    logger.info(
        "Last successful refresh for %s was %.1f days ago — fetching %d days",
        source, elapsed, days_back,
    )
    return days_back


def get_last_content_hash(source_name: str) -> Optional[str]:
    """Query meta.ops_data_sources.last_content_hash for a source."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT last_content_hash
                FROM meta.ops_data_sources
                WHERE source_name = %s
            """, (source_name,))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
    except Exception as e:
        logger.warning(f"Could not read last_content_hash for {source_name}: {e}")
    return None


def get_conditional_headers(source_name: str) -> Dict[str, Optional[str]]:
    """Query meta.ops_data_sources for last_etag + last_modified_header."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT last_etag, last_modified_header
                FROM meta.ops_data_sources
                WHERE source_name = %s
            """, (source_name,))
            row = cur.fetchone()
            if row:
                return {"etag": row[0], "last_modified": row[1]}
    except Exception as e:
        logger.warning(f"Could not read conditional headers for {source_name}: {e}")
    return {"etag": None, "last_modified": None}


def get_checkpoint_offset(source_name: str) -> int:
    """Get pagination_offset from last failed/partial run in meta.ops_refresh_log."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT rl.pagination_offset
                FROM meta.ops_refresh_log rl
                JOIN meta.ops_data_sources ds ON ds.source_id = rl.source_id
                WHERE ds.source_name = %s
                  AND rl.status IN ('failed', 'partial')
                  AND rl.pagination_offset IS NOT NULL
                  AND rl.pagination_offset > 0
                ORDER BY rl.refresh_started_at DESC
                LIMIT 1
            """, (source_name,))
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
    except Exception as e:
        logger.warning(f"Could not read checkpoint offset for {source_name}: {e}")
    return 0


def log_to_meta(source_name: str, result: dict) -> None:
    """Log ingestion result to meta.ops_refresh_log."""
    try:
        with get_cursor() as cur:
            # Get source_id
            cur.execute("""
                SELECT source_id FROM meta.ops_data_sources WHERE source_name = %s
            """, (source_name,))
            row = cur.fetchone()

            if row is None:
                logger.warning(f"Source '{source_name}' not found in meta.ops_data_sources")
                return

            source_id = row[0]

            # Insert log entry
            status = result.get('status', 'unknown')
            cur.execute("""
                INSERT INTO meta.ops_refresh_log (
                    source_id, refresh_started_at, refresh_completed_at,
                    status, records_fetched, records_inserted, records_updated,
                    error_message, content_hash, pagination_offset, skipped_by_hash
                ) VALUES (
                    %s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                source_id,
                datetime.now(),
                status,
                result.get('records_fetched', result.get('records_inserted', 0)),
                result.get('records_inserted', 0),
                result.get('records_updated', 0),
                json.dumps(result['errors'][:5]) if result.get('errors') else None,
                result.get('content_hash'),
                result.get('last_offset'),
                result.get('skipped_by_hash', False),
            ))

            # Update data_sources
            cur.execute("""
                UPDATE meta.ops_data_sources
                SET last_refresh_attempt = NOW(),
                    last_refresh_status = %s,
                    last_successful_refresh = CASE
                        WHEN %s IN ('success', 'partial') THEN NOW()
                        ELSE last_successful_refresh
                    END,
                    record_count = COALESCE(%s, record_count),
                    last_content_hash = COALESCE(%s, last_content_hash),
                    last_etag = COALESCE(%s, last_etag),
                    last_modified_header = COALESCE(%s, last_modified_header)
                WHERE source_id = %s
            """, (
                status,
                status,
                result.get('records_inserted'),
                result.get('content_hash'),
                result.get('etag'),
                result.get('last_modified'),
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

    # API source: fetch then load
    if 'fetcher' in source_info:
        data_dir = kwargs.get('data_dir', '/tmp/data/raw')
        Path(data_dir).mkdir(parents=True, exist_ok=True)

        fetcher = source_info['fetcher'](data_dir=data_dir)

        # Compute incremental days_back from last successful refresh
        fetch_kwargs: Dict[str, Any] = {}
        days_back = _compute_days_back(source, source_info)
        if days_back is not None:
            fetch_kwargs['days_back'] = days_back

        # Conditional HTTP: pass cached etag/last_modified to fetcher
        cond_headers = get_conditional_headers(meta_source)
        if cond_headers.get('etag') or cond_headers.get('last_modified'):
            fetch_kwargs['etag'] = cond_headers['etag']
            fetch_kwargs['last_modified'] = cond_headers['last_modified']

        # Checkpoint resume: pass last failed offset to fetcher
        resume_offset = get_checkpoint_offset(meta_source)
        if resume_offset > 0:
            fetch_kwargs['resume_offset'] = resume_offset
            logger.info(
                "Resuming %s from checkpoint offset %d", source, resume_offset
            )

        fetch_result = fetcher.fetch(**fetch_kwargs)

        # Propagate conditional HTTP headers from fetch result
        fetch_result.setdefault('etag', cond_headers.get('etag'))
        fetch_result.setdefault('last_modified', cond_headers.get('last_modified'))

        if fetch_result.get('status') == 'not_modified':
            logger.info("Source %s returned 304 Not Modified, skipping load", source)
            fetch_result['skipped_by_hash'] = True
            fetch_result['content_hash'] = get_last_content_hash(meta_source)
            fetch_result['status'] = 'skipped'
            log_to_meta(meta_source, fetch_result)
            return fetch_result

        if fetch_result.get('status') == 'failed' or not fetch_result.get('records'):
            logger.warning(f"Fetch returned no records for {source}")
            log_to_meta(meta_source, fetch_result)
            return fetch_result

        # Hash-skip: compare content hash to last run.
        # Uses a PostgreSQL advisory lock keyed on the source name hash to prevent
        # TOCTOU races where two concurrent runs both read the same previous hash.
        hash_skip_enabled = source_info.get('hash_skip_enabled', True)
        current_hash = fetch_result.get('hash')
        if hash_skip_enabled and current_hash:
            skip = False
            try:
                with get_cursor() as cur:
                    # Advisory lock: hashtext(source_name) → bigint, held until cursor closes
                    cur.execute("SELECT pg_advisory_lock(hashtext(%s))", (meta_source,))
                    cur.execute("""
                        SELECT last_content_hash FROM meta.ops_data_sources
                        WHERE source_name = %s
                    """, (meta_source,))
                    row = cur.fetchone()
                    previous_hash = row[0] if row and row[0] else None
                    if previous_hash and current_hash == previous_hash:
                        skip = True
                    # Lock released on cursor/connection close (get_cursor commits)
            except Exception as e:
                logger.warning(f"Hash-skip lock failed for {source}, proceeding with load: {e}")
                previous_hash = get_last_content_hash(meta_source)
                if previous_hash and current_hash == previous_hash:
                    skip = True

            if skip:
                logger.info(
                    "Hash unchanged for %s (%s), skipping load", source, current_hash[:12]
                )
                result = {
                    'status': 'skipped',
                    'records_fetched': len(fetch_result.get('records', [])),
                    'records_inserted': 0,
                    'records_updated': 0,
                    'skipped_by_hash': True,
                    'content_hash': current_hash,
                    'etag': fetch_result.get('etag'),
                    'last_modified': fetch_result.get('last_modified'),
                }
                log_to_meta(meta_source, result)
                return result

        loader = source_info['loader']
        result = loader(fetch_result['records'], source_hash=fetch_result.get('hash'))
        result['records_fetched'] = fetch_result.get(
            'record_count', len(fetch_result.get('records', []))
        )
        result['content_hash'] = current_hash
        result['etag'] = fetch_result.get('etag')
        result['last_modified'] = fetch_result.get('last_modified')
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

    if 'batch_size' in kwargs:
        loader_kwargs['batch_size'] = kwargs['batch_size']

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
    parser.add_argument('--data-dir', '-d', default='/tmp/data/raw', help='Directory for fetcher temp storage')
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
                    data_dir=args.data_dir,
                )
                records = result.get('records_inserted', result.get('records_fetched', 0))
                span.set_attribute("records_fetched", records)
        else:
            result = run_ingestion(
                source=source,
                filepath=args.filepath,
                fiscal_year=args.fiscal_year,
                batch_size=args.batch_size,
                data_dir=args.data_dir,
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

        if result.get('status') in ('success', 'skipped', 'partial'):
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

        # Emit CMS-specific Prometheus metrics for CMS sources
        if source.startswith("cms_"):
            try:
                from ..observability.metrics import record_cms_fetch
                record_cms_fetch(source, duration, records)
            except Exception:
                pass

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
