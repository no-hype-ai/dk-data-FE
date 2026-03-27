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

from .sources import cms_inpatient, cms_hospital_info, cms_cost_reports, acc_tvc, hrsa
# 019-cms-puf-platform-reconciliation: 28 CMS PUF loaders + 2 API loaders
from .sources.cms_part_d_spending import load_cms_part_d_spending
from .sources.cms_part_b_spending import load_cms_part_b_spending
from .sources.cms_open_payments import load_cms_open_payments
from .sources.cms_nppes import load_cms_nppes
from .sources.cms_inpatient_puf import load_cms_inpatient_puf
from .sources.cms_physician_puf import load_cms_physician_puf
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
from .sources.cms_geographic_variation import load_cms_geographic_variation
from .sources.cms_chronic_conditions import load_cms_chronic_conditions
from .sources.cms_dual_eligible import load_cms_dual_eligible
from .sources.cms_enrollment_puf import load_cms_enrollment_puf
from .sources.cms_claim_type_puf import load_cms_claim_type_puf
from .sources.cms_utilization_puf import load_cms_utilization_puf
from .sources.cms_cost_reports_puf import load_cms_cost_reports_puf
from .sources.cms_physician_puf_services import load_cms_physician_puf_services
from .sources.cms_cost_reports_puf_lines import load_cms_cost_reports_puf_lines
from .sources.europepmc import load_europepmc_data
from .sources.nih_reporter import load_nih_reporter_data
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

from .fetchers.europepmc import EuropePMCFetcher
from .fetchers.nih_reporter import NIHReporterFetcher
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

    # =========================================================================
    # 019-cms-puf-platform-reconciliation: 28 CMS PUF file-based sources
    # source_name keys MUST match meta.data_sources.source_name exactly
    # (no meta_name override needed — keys match DB rows in migration 085)
    # =========================================================================

    # 7 core CMS PUF sources
    'cms_part_d_spending': {
        'name': 'CMS Part D Drug Spending',
        'description': 'CMS Medicare Part D Drug Spending by Drug',
        'loader': load_cms_part_d_spending,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_part_b_spending': {
        'name': 'CMS Part B Drug Spending',
        'description': 'CMS Medicare Part B Drug Spending by Manufacturer',
        'loader': load_cms_part_b_spending,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_open_payments': {
        'name': 'CMS Open Payments',
        'description': 'CMS Open Payments (Sunshine Act) physician payments',
        'loader': load_cms_open_payments,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_nppes': {
        'name': 'CMS NPPES NPI Registry',
        'description': 'CMS NPPES National Provider Identifier registry',
        'loader': load_cms_nppes,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_inpatient_puf': {
        'name': 'CMS Inpatient PUF',
        'description': 'CMS Inpatient Public Use File (all DRGs)',
        'loader': load_cms_inpatient_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_physician_puf': {
        'name': 'CMS Physician PUF',
        'description': 'CMS Medicare Physician and Other Practitioners PUF',
        'loader': load_cms_physician_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_hospital_general_info': {
        'name': 'CMS Hospital General Information',
        'description': 'CMS Hospital General Information',
        'loader': load_cms_hospital_general_info,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },

    # 21 additional CMS PUF sources
    'cms_medicare_advantage': {
        'name': 'CMS Medicare Advantage',
        'description': 'CMS Medicare Advantage enrollment data',
        'loader': load_cms_medicare_advantage,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_medicaid_drug_spending': {
        'name': 'CMS Medicaid Drug Spending',
        'description': 'CMS Medicaid drug spending by drug and state',
        'loader': load_cms_medicaid_drug_spending,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_dme_puf': {
        'name': 'CMS DME PUF',
        'description': 'CMS Durable Medical Equipment PUF',
        'loader': load_cms_dme_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_home_health': {
        'name': 'CMS Home Health',
        'description': 'CMS Home Health Agency compare data',
        'loader': load_cms_home_health,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_hospice_puf': {
        'name': 'CMS Hospice PUF',
        'description': 'CMS Hospice provider utilization PUF',
        'loader': load_cms_hospice_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_snf_puf': {
        'name': 'CMS SNF PUF',
        'description': 'CMS Skilled Nursing Facility PUF',
        'loader': load_cms_snf_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_outpatient_puf': {
        'name': 'CMS Outpatient PUF',
        'description': 'CMS Hospital Outpatient PUF',
        'loader': load_cms_outpatient_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_referring_providers': {
        'name': 'CMS Referring Providers',
        'description': 'CMS Medicare referring provider patterns',
        'loader': load_cms_referring_providers,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_ordering_providers': {
        'name': 'CMS Ordering Providers',
        'description': 'CMS Medicare ordering/referring/prescribing PUF',
        'loader': load_cms_ordering_providers,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_lab_services': {
        'name': 'CMS Lab Services',
        'description': 'CMS Medicare lab services utilization PUF',
        'loader': load_cms_lab_services,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_imaging_puf': {
        'name': 'CMS Imaging PUF',
        'description': 'CMS Medicare imaging services PUF',
        'loader': load_cms_imaging_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_mental_health_puf': {
        'name': 'CMS Mental Health PUF',
        'description': 'CMS Medicare mental health services PUF',
        'loader': load_cms_mental_health_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_opioid_puf': {
        'name': 'CMS Opioid PUF',
        'description': 'CMS Medicare opioid prescribing rates by geography',
        'loader': load_cms_opioid_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_telehealth_puf': {
        'name': 'CMS Telehealth PUF',
        'description': 'CMS Medicare telehealth utilization PUF',
        'loader': load_cms_telehealth_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_geographic_variation': {
        'name': 'CMS Geographic Variation',
        'description': 'CMS Medicare geographic variation public use file',
        'loader': load_cms_geographic_variation,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_chronic_conditions': {
        'name': 'CMS Chronic Conditions',
        'description': 'CMS Medicare chronic conditions prevalence data',
        'loader': load_cms_chronic_conditions,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_dual_eligible': {
        'name': 'CMS Dual Eligible',
        'description': 'CMS Medicare-Medicaid dual eligible beneficiaries',
        'loader': load_cms_dual_eligible,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_enrollment_puf': {
        'name': 'CMS Enrollment PUF',
        'description': 'CMS Medicare enrollment by geography and demographics',
        'loader': load_cms_enrollment_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_claim_type_puf': {
        'name': 'CMS Claim Type PUF',
        'description': 'CMS Medicare claims by type and service category',
        'loader': load_cms_claim_type_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_utilization_puf': {
        'name': 'CMS Utilization PUF',
        'description': 'CMS Medicare utilization by service category',
        'loader': load_cms_utilization_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_cost_reports_puf': {
        'name': 'CMS Cost Reports PUF',
        'description': 'CMS Hospital Cost Reports PUF (all providers)',
        'loader': load_cms_cost_reports_puf,
        'requires_file': True,
        'accepts_file': True,
        'default_days_back': None,
    },
    'cms_physician_puf_services': {
        'loader': load_cms_physician_puf_services,
        'requires_file': True,
        'requires_fiscal_year': False,
        'default_days_back': None,
        'meta_name': 'cms_physician_puf_services',
        'description': 'CMS Physician PUF by Provider and Service (HCPCS grain)',
    },
    'cms_cost_reports_puf_lines': {
        'loader': load_cms_cost_reports_puf_lines,
        'requires_file': True,
        'requires_fiscal_year': False,
        'default_days_back': None,
        'meta_name': 'cms_cost_reports_puf_lines',
        'description': 'CMS Cost Reports PUF worksheet-level staffing lines',
    },

    # =========================================================================
    # 019-cms-puf-platform-reconciliation: 2 new API sources
    # =========================================================================

    'europepmc': {
        'name': 'EuropePMC',
        'description': 'EuropePMC publication search API (incremental by update date)',
        'fetcher': EuropePMCFetcher,
        'loader': load_europepmc_data,
        'requires_file': False,
        'default_days_back': 30,
    },
    'nih_reporter': {
        'name': 'NIH Reporter',
        'description': 'NIH RePORTER research grants API (incremental by start date)',
        'fetcher': NIHReporterFetcher,
        'loader': load_nih_reporter_data,
        'requires_file': False,
        'default_days_back': 90,
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
                    source_id, refresh_started_at, refresh_completed_at,
                    status, records_fetched, records_inserted, records_updated,
                    error_message
                ) VALUES (
                    %s, %s, NOW(), %s, %s, %s, %s, %s
                )
            """, (
                source_id,
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

    # API source: fetch then load
    if 'fetcher' in source_info:
        data_dir = kwargs.get('data_dir', '/tmp/data/raw')
        Path(data_dir).mkdir(parents=True, exist_ok=True)

        # Per-source retry overrides (optional keys in SOURCES entry)
        fetcher_kwargs: dict = {'data_dir': data_dir}
        if 'max_retries' in source_info:
            fetcher_kwargs['max_retries'] = source_info['max_retries']
        if 'retry_base_delay_seconds' in source_info:
            fetcher_kwargs['retry_base_delay_seconds'] = source_info['retry_base_delay_seconds']

        fetcher = source_info['fetcher'](**fetcher_kwargs)

        # Compute incremental days_back from last successful refresh
        fetch_kwargs = {}
        days_back = _compute_days_back(source, source_info)
        if days_back is not None:
            fetch_kwargs['days_back'] = days_back

        fetch_result = fetcher.fetch(**fetch_kwargs)

        if fetch_result.get('status') == 'failed' or not fetch_result.get('records'):
            logger.warning(f"Fetch returned no records for {source}")
            log_to_meta(meta_source, fetch_result)
            return fetch_result

        loader = source_info['loader']
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
            if kwargs.get('skip_if_no_file'):
                logger.info("Skipping file-required source '%s' — no file provided (scheduled run)", source)
                return {"status": "skipped", "records_inserted": 0, "source": source}
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
    parser.add_argument(
        '--skip-if-no-file', action='store_true', dest='skip_if_no_file',
        help='For file-required sources: exit 0 with status=skipped when no --file is given '
             '(used by scheduled CronJobs that run before the file has been deposited)',
    )

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
                    skip_if_no_file=args.skip_if_no_file,
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
                skip_if_no_file=args.skip_if_no_file,
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
