"""
Sync Runner - CLI entry point for pipeline execution.

This module is called by Kubernetes CronJobs to run scheduled data syncs.
It orchestrates the full Raw → Bronze → Silver → Gold pipeline.

Usage:
    python -m sync_runner --sources clinicaltrials,openfda_labels --tier daily

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import asyncio
import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import uuid4
import logging

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PipelineMetrics:
    """Tracks pipeline execution metrics."""

    def __init__(self):
        self.start_time = time.time()
        self.records_fetched = 0
        self.records_bronze = 0
        self.records_silver = 0
        self.records_gold = 0
        self.errors: List[str] = []

    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    def to_dict(self) -> Dict[str, Any]:
        return {
            'elapsed_seconds': self.elapsed_seconds(),
            'records_fetched': self.records_fetched,
            'records_bronze': self.records_bronze,
            'records_silver': self.records_silver,
            'records_gold': self.records_gold,
            'error_count': len(self.errors),
            'errors': self.errors[:10],  # Limit errors in response
        }


async def get_db_pool():
    """Create database connection pool."""
    import asyncpg

    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        db_host = os.getenv('POSTGRES_HOST', 'postgres')
        db_port = os.getenv('POSTGRES_PORT', '5432')
        db_name = os.getenv('POSTGRES_DB', 'dk_data')
        db_user = os.getenv('POSTGRES_USER', 'postgres')
        db_pass = os.getenv('POSTGRES_PASSWORD', 'postgres')
        db_url = f'postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}'

    return await asyncpg.create_pool(
        db_url,
        min_size=1,
        max_size=5,
        command_timeout=30,
    )


async def run_dynamic_source_ingestion(
    pool,
    source: str,
    metrics: PipelineMetrics,
    full_refresh: bool = False
) -> int:
    """
    Handle data ingestion for dynamically onboarded sources.

    Supports:
    - Authentication (API key, Bearer token, Basic auth)
    - Pagination (offset, page, cursor, next_url)
    - Incremental fetching (modified_since, created_since)
    - Custom request configuration (headers, query params, data path)
    - Sync state tracking for resumable fetches

    Args:
        pool: Database connection pool
        source: Source name
        metrics: Pipeline metrics tracker
        full_refresh: If True, ignore incremental state and fetch all data
    """
    import aiohttp
    import json
    import hashlib
    from datetime import datetime, timedelta
    from urllib.parse import urlencode

    try:
        async with pool.acquire() as conn:
            # Get source configuration
            row = await conn.fetchrow("""
                SELECT source, tier, options
                FROM ops.sync_schedules
                WHERE source = $1
            """, source)

            if not row or not row['options']:
                logger.warning(f"No configuration found for dynamic source: {source}")
                return 0

            options = row['options']
            if isinstance(options, str):
                options = json.loads(options)

            base_url = options.get('base_url')
            target_table = options.get('target_table')
            rate_limit = options.get('rate_limit_per_second', 10)
            timeout_seconds = options.get('timeout_seconds', 60)
            batch_size = options.get('batch_size', 100)

            if not base_url:
                logger.warning(f"No base_url configured for source: {source}")
                return 0

            if not target_table:
                logger.warning(f"No target_table configured for source: {source}")
                return 0

            # Get request configuration
            request_config = options.get('request', {})
            http_method = request_config.get('method', 'GET')
            custom_headers = request_config.get('headers', {})
            query_params = dict(request_config.get('query_params', {}))
            body_template = request_config.get('body_template')
            data_path = request_config.get('data_path')

            # Get pagination configuration
            pagination = options.get('pagination', {})
            pagination_type = pagination.get('type', 'none')
            page_size = pagination.get('page_size', batch_size)
            max_pages = pagination.get('max_pages', 100)

            # Get incremental configuration
            incremental = options.get('incremental', {})
            incremental_type = incremental.get('type', 'none')
            date_field = incremental.get('date_field')
            date_param = incremental.get('date_param')
            date_format = incremental.get('date_format', '%Y-%m-%dT%H:%M:%SZ')
            lookback_hours = incremental.get('lookback_hours', 24)

            # Get sync state
            sync_state = options.get('sync_state', {})
            last_cursor = sync_state.get('last_cursor')
            last_offset = sync_state.get('last_offset', 0)
            last_modified = sync_state.get('last_modified_date')

            # Reset state if full refresh requested
            if full_refresh:
                last_cursor = None
                last_offset = 0
                last_modified = None
                logger.info(f"Full refresh requested for {source}, resetting sync state")

            # Build headers with authentication
            headers = {
                'Accept': 'application/json',
                'User-Agent': 'DK-Data-Platform/1.0',
            }
            headers.update(custom_headers)

            auth_type = options.get('auth_type', 'none')
            credentials = options.get('credentials', {})

            if auth_type != 'none' and credentials.get('configured'):
                cred_key = credentials.get('key', 'api_key')
                source_upper = source.upper().replace('-', '_')

                if auth_type == 'api_key':
                    # Env-var-first: SYNC_APIKEY_{SOURCE} via Doppler, fall back to options dict
                    env_val = os.environ.get(f"SYNC_APIKEY_{source_upper}")
                    value = env_val or credentials.get('value', '')
                    if not env_val and credentials.get('value'):
                        logger.warning(f"Using options-dict credential for {source} — configure SYNC_APIKEY_{source_upper} in Doppler")
                    headers[cred_key] = value
                elif auth_type == 'bearer':
                    env_val = os.environ.get(f"SYNC_TOKEN_{source_upper}")
                    value = env_val or credentials.get('value', '')
                    if not env_val and credentials.get('value'):
                        logger.warning(f"Using options-dict credential for {source} — configure SYNC_TOKEN_{source_upper} in Doppler")
                    headers['Authorization'] = f"Bearer {value}"
                elif auth_type == 'basic':
                    import base64
                    env_val = os.environ.get(f"SYNC_CRED_{source_upper}")
                    value = env_val or credentials.get('value', '')
                    if not env_val and credentials.get('value'):
                        logger.warning(f"Using options-dict credential for {source} — configure SYNC_CRED_{source_upper} in Doppler")
                    encoded = base64.b64encode(value.encode()).decode()
                    headers['Authorization'] = f"Basic {encoded}"

            # Add incremental date filter if configured
            use_incremental = False
            if incremental_type != 'none' and date_param and not full_refresh:
                if last_modified:
                    use_incremental = True
                    # Determine the filter date
                    # Handle different date formats - YYYYMMDD vs ISO
                    try:
                        if len(last_modified) == 8 and last_modified.isdigit():
                            # YYYYMMDD format (e.g., from FDA API)
                            filter_date = datetime.strptime(last_modified, '%Y%m%d')
                        else:
                            # ISO format
                            filter_date = datetime.fromisoformat(last_modified.replace('Z', '+00:00').replace('+00:00', ''))

                        # Apply lookback to catch any missed records
                        filter_date = filter_date - timedelta(hours=lookback_hours)

                        # Check if this is a search-style query (like FDA's search parameter)
                        # FDA format: search=effective_time:[YYYYMMDD TO *]
                        search_template = incremental.get('search_template')
                        if search_template:
                            # Use template like "{date_field}:[{date} TO *]"
                            query_params[date_param] = search_template.format(
                                date_field=date_field,
                                date=filter_date.strftime(date_format)
                            )
                        elif date_param == 'search' and date_field:
                            # Auto-detect FDA-style search query
                            query_params[date_param] = f"{date_field}:[{filter_date.strftime(date_format)} TO *]"
                        else:
                            # Simple date parameter
                            query_params[date_param] = filter_date.strftime(date_format)

                        logger.info(f"Incremental fetch from {filter_date.strftime('%Y-%m-%d')}, query: {date_param}={query_params[date_param]}")
                    except Exception as e:
                        logger.warning(f"Failed to parse last_modified date '{last_modified}': {e}, falling back to full fetch")
                        use_incremental = False

            logger.info(f"Fetching data from dynamic source: {source} ({base_url})")

            total_inserted = 0
            page_count = 0
            # When using incremental date filter, start from offset 0 (fetching different subset)
            # Only resume offset when NOT using incremental (pure pagination resume)
            if use_incremental:
                # Incremental: start fresh, date filter defines the subset
                current_offset = 0
                current_cursor = None
            else:
                # No incremental: resume from where we left off
                current_offset = last_offset if pagination_type == 'offset' and not full_refresh else 0
                current_cursor = last_cursor if pagination_type == 'cursor' and not full_refresh else None
            current_url = base_url
            newest_date = None

            async with aiohttp.ClientSession() as session:
                while page_count < max_pages:
                    # Rate limiting
                    await asyncio.sleep(1.0 / rate_limit)

                    # Build URL with pagination
                    request_params = dict(query_params)

                    if pagination_type == 'offset':
                        request_params[pagination.get('offset_param', 'offset')] = current_offset
                        request_params[pagination.get('limit_param', 'limit')] = page_size
                    elif pagination_type == 'page':
                        request_params[pagination.get('page_param', 'page')] = page_count + 1
                        request_params[pagination.get('page_size_param', 'page_size')] = page_size
                    elif pagination_type == 'cursor':
                        if current_cursor:
                            request_params[pagination.get('cursor_param', 'cursor')] = current_cursor
                        # Always add page size for cursor pagination
                        page_size_param = pagination.get('page_size_param', 'pageSize')
                        if page_size_param:
                            request_params[page_size_param] = page_size

                    # Build final URL
                    if pagination_type == 'next_url' and current_url != base_url:
                        fetch_url = current_url  # Use the next URL directly
                    else:
                        fetch_url = f"{base_url}?{urlencode(request_params)}" if request_params else base_url

                    try:
                        timeout = aiohttp.ClientTimeout(total=timeout_seconds)

                        if http_method == 'POST':
                            async with session.post(
                                fetch_url,
                                headers=headers,
                                data=body_template,
                                timeout=timeout
                            ) as response:
                                if response.status not in (200, 201):
                                    logger.error(f"API request failed for {source}: {response.status}")
                                    metrics.errors.append(f"raw_{source}: HTTP {response.status}")
                                    break
                                data = await response.json()
                        else:
                            async with session.get(
                                fetch_url,
                                headers=headers,
                                timeout=timeout
                            ) as response:
                                if response.status != 200:
                                    logger.error(f"API request failed for {source}: {response.status}")
                                    metrics.errors.append(f"raw_{source}: HTTP {response.status}")
                                    break
                                data = await response.json()

                    except asyncio.TimeoutError:
                        logger.error(f"Request timed out for {source}")
                        metrics.errors.append(f"raw_{source}: timeout")
                        break
                    except aiohttp.ClientError as e:
                        logger.error(f"Request failed for {source}: {e}")
                        metrics.errors.append(f"raw_{source}: {str(e)[:100]}")
                        break

                    # Extract data using data_path
                    records_data = data
                    if data_path and isinstance(data, dict):
                        for key in data_path.split('.'):
                            if isinstance(records_data, dict) and key in records_data:
                                records_data = records_data[key]
                            else:
                                records_data = []
                                break

                    # Handle array or single object
                    if isinstance(records_data, dict):
                        records = [records_data]
                    elif isinstance(records_data, list):
                        records = records_data
                    else:
                        records = []

                    if not records:
                        logger.info(f"No more records from {source} at page {page_count + 1}")
                        break

                    # Insert records (with or without deduplication)
                    page_inserted = 0
                    for record in records:
                        try:
                            # Create hash for deduplication
                            record_hash = hashlib.md5(
                                json.dumps(record, sort_keys=True, default=str).encode()
                            ).hexdigest()

                            # Skip deduplication check if full_refresh is True
                            exists = False
                            if not full_refresh:
                                # Check for duplicate (within last 24 hours)
                                exists = await conn.fetchval(f"""
                                SELECT 1 FROM {target_table}
                                WHERE _raw_payload->>'_hash' = $1
                                AND _ingested_at > NOW() - INTERVAL '24 hours'
                                LIMIT 1
                            """, record_hash)

                            if not exists:
                                # Add metadata to record
                                record['_hash'] = record_hash

                                await conn.execute(f"""
                                    INSERT INTO {target_table} (_raw_payload, _ingested_at)
                                    VALUES ($1, NOW())
                                """, json.dumps(record))
                                page_inserted += 1

                                # Track newest date for incremental state
                                if date_field and date_field in record:
                                    record_date = record[date_field]
                                    if record_date and (not newest_date or record_date > newest_date):
                                        newest_date = record_date

                        except Exception as e:
                            logger.error(f"Failed to insert record for {source}: {e}")
                            metrics.errors.append(f"raw_{source}_insert: {str(e)[:100]}")

                    total_inserted += page_inserted
                    page_count += 1

                    logger.info(f"{source} page {page_count}: {page_inserted} new records (total: {total_inserted})")

                    # Update pagination state for next iteration
                    if pagination_type == 'none':
                        break  # No pagination, single request only
                    elif pagination_type == 'offset':
                        current_offset += len(records)
                        if len(records) < page_size:
                            break  # Last page
                    elif pagination_type == 'page':
                        if len(records) < page_size:
                            break  # Last page
                    elif pagination_type == 'cursor':
                        cursor_path = pagination.get('cursor_path', 'next_cursor')
                        next_cursor = data
                        for key in cursor_path.split('.'):
                            if isinstance(next_cursor, dict) and key in next_cursor:
                                next_cursor = next_cursor[key]
                            else:
                                next_cursor = None
                                break
                        if not next_cursor:
                            break
                        current_cursor = next_cursor
                    elif pagination_type == 'next_url':
                        next_url_path = pagination.get('next_url_path', 'next')
                        next_url = data
                        for key in next_url_path.split('.'):
                            if isinstance(next_url, dict) and key in next_url:
                                next_url = next_url[key]
                            else:
                                next_url = None
                                break
                        if not next_url:
                            break
                        current_url = next_url

            # Update sync state
            new_sync_state = {
                'last_successful_sync': datetime.utcnow().isoformat(),
                'last_cursor': current_cursor if pagination_type == 'cursor' else None,
                'last_offset': current_offset if pagination_type == 'offset' else 0,
                'last_modified_date': newest_date or last_modified,
                'total_records_synced': sync_state.get('total_records_synced', 0) + total_inserted,
                'last_page_count': page_count,
            }

            options['sync_state'] = new_sync_state

            await conn.execute("""
                UPDATE ops.sync_schedules
                SET options = $2, last_run = NOW(), updated_at = NOW()
                WHERE source = $1
            """, source, json.dumps(options))

            logger.info(f"Inserted {total_inserted} records for dynamic source: {source} ({page_count} pages)")
            return total_inserted

    except Exception as e:
        logger.error(f"Dynamic source ingestion failed for {source}: {e}")
        metrics.errors.append(f"raw_{source}: {str(e)}")
        return 0


async def run_raw_ingestion(
    pool,
    sources: List[str],
    metrics: PipelineMetrics,
    drug_name: Optional[str] = None,
) -> Dict[str, int]:
    """Run raw layer ingestion for specified sources."""
    from .raw_ingestion import (
        ClinicalTrialsIngestion,
        OpenFDAIngestion,
        ChEMBLIngestion,
        PubChemIngestion,
        UniProtIngestion,
        OpenAlexIngestion,
        WHOINNIngestion,
        KEGGDrugIngestion,
        TTDIngestion,
        FDADrugsIngestion,
        IMGTIngestion,
        CDCVaccinesIngestion,
        ReactomeIngestion,
        NICEHTAIngestion,
        CMSOpenPaymentsIngestion,
        CMSMedicareIngestion,
        NIHReporterIngestion,
        NPIRegistryIngestion,
        EuropePMCIngestion,
        FDADrugsfdaIngestion,
        EPOPatentsIngestion,
        CochraneReviewsIngestion,
        EMAIngestion,
    )

    results = {}

    for source in sources:
        try:
            logger.info(f"Starting raw ingestion for {source}")

            if source == 'clinicaltrials' or source == 'clinicaltrials_gov':
                service = ClinicalTrialsIngestion(pool)
                count = 0
                if drug_name:
                    # Check if drug_name is a comma-separated list of NCT IDs
                    if drug_name.startswith('NCT'):
                        nct_ids = [n.strip() for n in drug_name.split(',') if n.strip().startswith('NCT')]
                        for nct_id in nct_ids[:10]:  # Limit to 10 per request
                            result = await service.fetch_study_by_nct(nct_id)
                            if result:
                                count += 1
                                # Also run silver refresh for individual study (has full resultsSection)
                                try:
                                    raw_row = await pool.fetchrow(
                                        "SELECT response_body FROM mol_raw.clinicaltrials WHERE api_endpoint LIKE $1 ORDER BY request_timestamp DESC LIMIT 1",
                                        f"%{nct_id}%"
                                    )
                                    if raw_row and raw_row['response_body']:
                                        from ...services.pipeline.silver_gold_refresher import SilverGoldRefresher
                                        refresher = SilverGoldRefresher(pool)
                                        resp = raw_row['response_body']
                                        if isinstance(resp, str):
                                            resp = json.loads(resp)
                                        await refresher.refresh(nct_id, 'clinicaltrials', resp)
                                        logger.info(f"Silver refreshed for individual study {nct_id}")
                                except Exception as e:
                                    logger.warning(f"Silver refresh for {nct_id} failed: {e}")
                    else:
                        # Fetch trials for the specific drug (intervention search)
                        result = await service.fetch_studies(intervention=drug_name, page_size=100)
                        if result:
                            count += 1
                        # Also search by query for broader coverage
                        result = await service.fetch_studies(query=drug_name, page_size=100)
                        if result:
                            count += 1

                    # Also fetch individual studies for trials with results
                    # (search endpoint returns metadata but NOT resultsSection)
                    try:
                        trials_with_results = await pool.fetch(
                            """SELECT DISTINCT nct_id FROM mol_silver.clinical_trials
                               WHERE molecule_id IN (
                                 SELECT molecule_id FROM mol_silver.molecules
                                 WHERE LOWER(canonical_name) LIKE '%' || LOWER($1) || '%'
                               )
                               AND results_outcome_measures IS NULL
                               AND has_results = false
                               ORDER BY nct_id LIMIT 20""",
                            drug_name.split(',')[0].strip() if not drug_name.startswith('NCT') else 'durvalumab'
                        )
                        if trials_with_results:
                            logger.info(f"Fetching {len(trials_with_results)} individual trials for results enrichment")
                            for row in trials_with_results:
                                result = await service.fetch_study_by_nct(row['nct_id'])
                                if result:
                                    count += 1
                    except Exception as e:
                        logger.warning(f"Results enrichment failed (non-fatal): {e}")
                else:
                    # Default: fetch by common conditions
                    for condition in ['cancer', 'diabetes', 'cardiovascular', 'immunology']:
                        result = await service.fetch_studies(condition=condition, page_size=100)
                        if result:
                            count += 1
                results[source] = count

            elif source == 'openfda_faers':
                service = OpenFDAIngestion(pool)
                count = 0
                if drug_name:
                    result = await service.fetch_faers_events(drug_name=drug_name, limit=100)
                    if result:
                        count += 1
                else:
                    for drug in ['aspirin', 'ibuprofen', 'metformin', 'atorvastatin']:
                        result = await service.fetch_faers_events(drug_name=drug, limit=100)
                        if result:
                            count += 1
                results[source] = count

            elif source == 'openfda_labels':
                service = OpenFDAIngestion(pool)
                if drug_name:
                    result = await service.fetch_drug_labels(drug_name=drug_name, limit=100)
                else:
                    result = await service.fetch_drug_labels(limit=100)
                results[source] = 1 if result else 0

            elif source == 'chembl':
                service = ChEMBLIngestion(pool)
                count = 0
                names = [drug_name] if drug_name else ['aspirin', 'imatinib', 'pembrolizumab']
                for name in names:
                    result = await service.fetch_molecule_by_name(name)
                    if result:
                        count += 1
                results[source] = count

            elif source == 'pubchem':
                service = PubChemIngestion(pool)
                count = 0
                names = [drug_name] if drug_name else ['aspirin', 'caffeine', 'glucose']
                for name in names:
                    result = await service.fetch_compound_by_name(name)
                    if result:
                        count += 1
                results[source] = count

            elif source == 'uniprot':
                service = UniProtIngestion(pool)
                query = drug_name if drug_name else "insulin receptor"
                result = await service.search_proteins(query, limit=50)
                results[source] = 1 if result else 0

            elif source == 'openalex':
                service = OpenAlexIngestion(pool)
                query = drug_name if drug_name else "drug development clinical trial"
                result = await service.fetch_works(query, per_page=50)
                results[source] = 1 if result else 0

            elif source == 'sec_edgar':
                import hashlib
                import json as _json
                from ...services.external_apis.sec_edgar_client import SECEdgarClient
                from ...services.pipeline.sec_mda_extractor import extract_mda_from_filing

                # Step 1: Resolve originator company name for CIK lookup.
                # Use mol_silver.clinical_trials lead_sponsor_name (INDUSTRY class, top by trial count).
                manufacturer_name = None
                if drug_name:
                    async with pool.acquire() as conn:
                        row = await conn.fetchrow("""
                            SELECT ct.lead_sponsor_name AS manufacturer, COUNT(*) AS trial_count
                            FROM mol_silver.clinical_trials ct
                            JOIN mol_silver.molecules m ON ct.molecule_id = m.molecule_id
                            WHERE LOWER(m.canonical_name) = LOWER($1)
                              AND ct.lead_sponsor_class = 'INDUSTRY'
                              AND ct.lead_sponsor_name IS NOT NULL
                            GROUP BY ct.lead_sponsor_name
                            HAVING COUNT(*) >= 2
                            ORDER BY COUNT(*) DESC
                            LIMIT 1
                        """, drug_name)
                        if row and row['manufacturer']:
                            manufacturer_name = row['manufacturer']
                            logger.info(f"SEC EDGAR: resolved '{drug_name}' → sponsor '{manufacturer_name}' ({row['trial_count']} trials)")
                        else:
                            fb_row = await conn.fetchrow("""
                                SELECT (dl.manufacturer_name::jsonb->>0) AS manufacturer
                                FROM mol_silver.drug_labels dl
                                JOIN mol_silver.molecules m ON dl.molecule_id = m.molecule_id
                                WHERE LOWER(m.canonical_name) = LOWER($1)
                                  AND dl.manufacturer_name IS NOT NULL
                                LIMIT 1
                            """, drug_name)
                            if fb_row and fb_row['manufacturer']:
                                manufacturer_name = fb_row['manufacturer']
                                logger.info(f"SEC EDGAR: resolved '{drug_name}' → drug_labels manufacturer '{manufacturer_name}' (fallback)")

                # Step 2: Look up CIK via the authoritative company name search.
                count = 0
                target_cik = None
                lookup_name = manufacturer_name or drug_name
                if lookup_name:
                    try:
                        cik_client = SECEdgarClient()
                        target_cik = await cik_client.lookup_cik_by_company_name(lookup_name)
                        if target_cik:
                            logger.info(f"SEC EDGAR: CIK {target_cik} resolved for '{lookup_name}'")
                        else:
                            logger.warning(f"SEC EDGAR: no CIK found for '{lookup_name}'")
                    except Exception as e:
                        logger.warning(f"SEC EDGAR CIK lookup failed: {e}")

                # Step 3: Fetch the latest annual filing and extract the MD&A section.
                # The raw MDA text is stored to mol_raw; SQLMesh transforms it to
                # mol_silver.financial_filings (with molecule entity link). Revenue
                # extraction from the MDA text is handled by xenon's LLM pipeline
                # (processFinancialFilingsWithLLM in assessment-orchestrator.service.ts).
                if target_cik and drug_name:
                    try:
                        extraction = None
                        for filing_type in ('10-K', '20-F'):
                            extraction = await extract_mda_from_filing(
                                target_cik, drug_name, filing_type
                            )
                            if extraction:
                                logger.info(
                                    f"SEC EDGAR: extracted MD&A from {filing_type} "
                                    f"accession={extraction.accession_number} "
                                    f"({len(extraction.mda_text)} chars)"
                                )
                                break

                        if extraction:
                            body = {
                                'cik': target_cik,
                                'company_name': manufacturer_name or drug_name,
                                'drug_name': drug_name,
                                'filing_type': extraction.filing_type,
                                'filing_date': extraction.filing_date,
                                'accession_number': extraction.accession_number,
                                'mda_text': extraction.mda_text or None,
                                'risk_factors_text': extraction.risk_factors_text or None,
                            }
                            body_json = _json.dumps(body, default=str)
                            body_hash = hashlib.sha256(body_json.encode()).hexdigest()[:64]
                            async with pool.acquire() as conn:
                                await conn.execute("""
                                    INSERT INTO mol_raw.sec_edgar
                                        (response_body, response_body_hash, request_timestamp,
                                         api_endpoint, response_status)
                                    VALUES ($1::jsonb, $2, NOW(), 'sec_edgar_mda', 200)
                                    ON CONFLICT (response_body_hash) DO NOTHING
                                """, body_json, body_hash)
                            count = 1
                            logger.info(f"SEC EDGAR: stored MD&A to mol_raw for '{drug_name}'")
                        else:
                            logger.warning(f"SEC EDGAR: no 10-K or 20-F found for CIK {target_cik} ('{drug_name}')")
                    except Exception as e:
                        logger.warning(f"SEC EDGAR MDA extraction failed: {e}")

                results[source] = count

            # New sources for research codes and biologics
            elif source == 'who_inn':
                service = WHOINNIngestion(pool)
                count = 0
                # Fetch synonyms for common research codes
                for code in ['CP-690,550', 'RAD001', 'AIN457', 'BI10773', 'FTY720']:
                    result = await service.search_by_research_code(code)
                    if result:
                        count += 1
                results[source] = count

            elif source == 'kegg_drug':
                service = KEGGDrugIngestion(pool)
                result = await service.fetch_drug_list()
                results[source] = 1 if result else 0

            elif source == 'ttd':
                service = TTDIngestion(pool)
                count = 0
                # Fetch info for common therapeutic targets
                for target in ['EGFR', 'HER2', 'PD-1', 'TNF']:
                    result = await service.fetch_target_info(target)
                    if result:
                        count += 1
                results[source] = count

            elif source == 'fda_drugs':
                service = FDADrugsIngestion(pool)
                result = await service.fetch_approvals(limit=100)
                results[source] = 1 if result else 0

            elif source == 'imgt':
                service = IMGTIngestion(pool)
                count = 0
                # Fetch antibody structures for common biologics
                for ab in ['trastuzumab', 'pembrolizumab', 'adalimumab']:
                    result = await service.fetch_antibody_structures(ab)
                    if result:
                        count += 1
                results[source] = count

            elif source == 'cdc_vaccines':
                service = CDCVaccinesIngestion(pool)
                result = await service.fetch_vaccine_products()
                results[source] = 1 if result else 0

            elif source == 'reactome':
                service = ReactomeIngestion(pool)
                count = 0
                queries = [drug_name] if drug_name else ['PD-L1', 'immune checkpoint']
                for q in queries:
                    result = await service.search_pathways(q)
                    if result:
                        count += 1
                results[source] = count

            elif source == 'nice_hta':
                service = NICEHTAIngestion(pool)
                count = 0
                if drug_name:
                    result = await service.search_guidance(drug_name)
                    if result:
                        count += 1
                    # Extract structured fields from NICE API response into mol_bronze
                    try:
                        raw_rows = await pool.fetch(
                            """SELECT id, response_body FROM mol_raw.nice_hta
                               WHERE processed_to_bronze = FALSE
                               AND response_status = 200
                               AND response_body IS NOT NULL
                               ORDER BY request_timestamp DESC LIMIT 20"""
                        )
                        for raw_row in raw_rows:
                            try:
                                body = raw_row['response_body']
                                if isinstance(body, str):
                                    import json as _json
                                    body = _json.loads(body)
                                # NICE API returns list of guidance items or single item
                                items = body if isinstance(body, list) else body.get('results', body.get('data', [body]))
                                if not isinstance(items, list):
                                    items = [items]
                                for item in items:
                                    if not isinstance(item, dict):
                                        continue
                                    guidance_id = item.get('GuidanceNumber') or item.get('guidanceNumber') or item.get('guidance_id')
                                    if not guidance_id:
                                        continue
                                    title = item.get('Title') or item.get('title') or ''
                                    # Extract decision from GuidanceStatus or PublicationStatus
                                    decision = (item.get('GuidanceStatus') or item.get('guidanceStatus')
                                                or item.get('PublicationStatus') or item.get('publicationStatus'))
                                    # Extract dates
                                    decision_date_str = (item.get('PublishedDate') or item.get('publishedDate')
                                                         or item.get('LastModified') or item.get('lastModified'))
                                    decision_date = None
                                    if decision_date_str:
                                        try:
                                            from datetime import datetime as _dt
                                            # NICE dates can be ISO format or "DD Month YYYY"
                                            for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d %B %Y'):
                                                try:
                                                    decision_date = _dt.strptime(decision_date_str[:19], fmt).date()
                                                    break
                                                except ValueError:
                                                    continue
                                        except Exception:
                                            pass
                                    indication = item.get('Indication') or item.get('indication') or ''
                                    guidance_type = item.get('GuidanceType') or item.get('guidanceType') or 'TA'
                                    url = item.get('Url') or item.get('url') or item.get('GuidanceUrl') or ''
                                    # Extract ICER if present in cost-effectiveness section
                                    icer_value = item.get('ICERValue') or item.get('icer_value') or item.get('costEffectiveness')
                                    await pool.execute("""
                                        INSERT INTO mol_bronze.nice_hta
                                            (raw_id, guidance_id, guidance_type, title, drug_name,
                                             indication, decision, decision_date, url, icer_value)
                                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                                        ON CONFLICT (guidance_id) DO UPDATE SET
                                            decision = COALESCE(EXCLUDED.decision, mol_bronze.nice_hta.decision),
                                            decision_date = COALESCE(EXCLUDED.decision_date, mol_bronze.nice_hta.decision_date),
                                            indication = COALESCE(EXCLUDED.indication, mol_bronze.nice_hta.indication),
                                            icer_value = COALESCE(EXCLUDED.icer_value, mol_bronze.nice_hta.icer_value),
                                            title = COALESCE(EXCLUDED.title, mol_bronze.nice_hta.title)
                                    """,
                                        raw_row['id'], guidance_id, guidance_type, title, drug_name,
                                        indication, decision, decision_date, url,
                                        str(icer_value) if icer_value else None,
                                    )
                                    count += 1
                                # Mark raw record as processed
                                await pool.execute(
                                    "UPDATE mol_raw.nice_hta SET processed_to_bronze = TRUE WHERE id = $1",
                                    raw_row['id']
                                )
                            except Exception as e:
                                logger.debug(f"NICE bronze extraction failed for raw {raw_row['id']}: {e}")
                    except Exception as e:
                        logger.warning(f"NICE bronze extraction failed (non-fatal): {e}")
                    # Also fetch individual guidance pages for existing HTA entries
                    # to get decision/date/ICER that search pages don't return
                    try:
                        existing_hta = await pool.fetch(
                            """SELECT DISTINCT guidance_id FROM mol_bronze.nice_hta
                               WHERE LOWER(drug_name) LIKE '%' || LOWER($1) || '%'
                               AND guidance_id IS NOT NULL
                               AND (decision IS NULL OR decision = '')""",
                            drug_name
                        )
                        for row in existing_hta[:10]:
                            detail = await service.fetch_guidance_detail(row['guidance_id'])
                            if detail:
                                count += 1
                    except Exception as e:
                        logger.warning(f"NICE detail fetch failed (non-fatal): {e}")
                results[source] = count

            elif source == 'cms_open_payments':
                service = CMSOpenPaymentsIngestion(pool)
                if drug_name:
                    result = await service.fetch_payments(drug_name, year=2024)
                    results[source] = 1 if result else 0
                else:
                    results[source] = 0

            elif source == 'cms_medicare':
                service = CMSMedicareIngestion(pool)
                if drug_name:
                    result = await service.fetch_part_b_spending(drug_name)
                    results[source] = 1 if result else 0
                else:
                    results[source] = 0

            elif source == 'nih_reporter':
                service = NIHReporterIngestion(pool)
                if drug_name:
                    result = await service.search_grants(drug_name)
                    results[source] = 1 if result else 0
                else:
                    results[source] = 0

            elif source == 'npi_registry':
                service = NPIRegistryIngestion(pool)
                result = await service.search_providers('Medical Oncology')
                results[source] = 1 if result else 0

            elif source == 'europepmc':
                service = EuropePMCIngestion(pool)
                query = drug_name if drug_name else 'clinical trial oncology'
                result = await service.search_publications(query)
                results[source] = 1 if result else 0

            elif source == 'fda_drugsfda':
                service = FDADrugsfdaIngestion(pool)
                if drug_name:
                    result = await service.fetch_approvals(brand_name=drug_name)
                    if not result:
                        result = await service.fetch_approvals(generic_name=drug_name)
                    results[source] = 1 if result else 0
                else:
                    results[source] = 0

            elif source == 'epo_patents':
                # EPO Open Patent Services — drug-specific patent search
                service = EPOPatentsIngestion(pool)
                count = 0
                if drug_name:
                    result = await service.search_patents(drug_name)
                    if result:
                        count += 1
                else:
                    # Bulk cron: fetch for common pharma applicants
                    for applicant in ['AstraZeneca', 'Pfizer', 'Merck', 'Roche', 'Novartis']:
                        result = await service.search_patents_by_applicant(applicant)
                        if result:
                            count += 1
                results[source] = count

            elif source == 'cochrane_reviews':
                # Cochrane Library — drug-specific systematic review search
                service = CochraneReviewsIngestion(pool)
                count = 0
                if drug_name:
                    result = await service.search_reviews(drug_name)
                    if result:
                        count += 1
                else:
                    # Bulk cron: fetch recent reviews
                    for term in ['cancer immunotherapy', 'checkpoint inhibitor', 'monoclonal antibody']:
                        result = await service.search_reviews(term)
                        if result:
                            count += 1
                results[source] = count

            elif source == 'hta_decisions':
                # Broad HTA decisions — uses NICE HTA ingestion as primary source
                # G-BA, PBAC, SMC access added as separate handlers when APIs stabilize
                service = NICEHTAIngestion(pool)
                count = 0
                if drug_name:
                    result = await service.search_guidance(drug_name)
                    if result:
                        count += 1
                    try:
                        # Bronze extraction (same as nice_hta handler)
                        raw_rows = await pool.fetch(
                            """SELECT id, response_body FROM mol_raw.nice_hta
                               WHERE processed_to_bronze = FALSE
                               AND response_status = 200
                               AND response_body IS NOT NULL
                               ORDER BY request_timestamp DESC LIMIT 20"""
                        )
                        for raw_row in raw_rows:
                            try:
                                body = raw_row['response_body']
                                if isinstance(body, str):
                                    import json as _json
                                    body = _json.loads(body)
                                items = body if isinstance(body, list) else body.get('results', body.get('data', [body]))
                                if not isinstance(items, list):
                                    items = [items]
                                for item in items:
                                    if not isinstance(item, dict):
                                        continue
                                    guidance_id = item.get('GuidanceNumber') or item.get('guidanceNumber') or item.get('guidance_id')
                                    if not guidance_id:
                                        continue
                                    title = item.get('Title') or item.get('title') or ''
                                    decision = (item.get('GuidanceStatus') or item.get('guidanceStatus')
                                                or item.get('PublicationStatus') or item.get('publicationStatus'))
                                    decision_date_str = (item.get('PublishedDate') or item.get('publishedDate')
                                                         or item.get('LastModified') or item.get('lastModified'))
                                    decision_date = None
                                    if decision_date_str:
                                        try:
                                            from datetime import datetime as _dt
                                            for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d %B %Y'):
                                                try:
                                                    decision_date = _dt.strptime(decision_date_str[:19], fmt).date()
                                                    break
                                                except ValueError:
                                                    continue
                                        except Exception:
                                            pass
                                    indication = item.get('Indication') or item.get('indication') or ''
                                    guidance_type = item.get('GuidanceType') or item.get('guidanceType') or 'TA'
                                    url = item.get('Url') or item.get('url') or item.get('GuidanceUrl') or ''
                                    icer_value = item.get('ICERValue') or item.get('icer_value') or item.get('costEffectiveness')
                                    await pool.execute("""
                                        INSERT INTO mol_bronze.nice_hta
                                            (guidance_id, guidance_type, title, drug_name,
                                             indication, decision, decision_date, url, icer_value)
                                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                                        ON CONFLICT (guidance_id) DO UPDATE SET
                                            decision = COALESCE(EXCLUDED.decision, mol_bronze.nice_hta.decision),
                                            decision_date = COALESCE(EXCLUDED.decision_date, mol_bronze.nice_hta.decision_date),
                                            indication = COALESCE(EXCLUDED.indication, mol_bronze.nice_hta.indication),
                                            icer_value = COALESCE(EXCLUDED.icer_value, mol_bronze.nice_hta.icer_value)
                                    """,
                                        guidance_id, guidance_type, title, drug_name,
                                        indication, decision, decision_date, url,
                                        str(icer_value) if icer_value else None,
                                    )
                                    count += 1
                                await pool.execute(
                                    "UPDATE mol_raw.nice_hta SET processed_to_bronze = TRUE WHERE id = $1",
                                    raw_row['id']
                                )
                            except Exception as e:
                                logger.debug(f"HTA bronze extraction failed for raw {raw_row['id']}: {e}")
                    except Exception as e:
                        logger.warning(f"HTA bronze extraction failed (non-fatal): {e}")
                results[source] = count

            elif source == 'ema_regulatory':
                # EMA authorized medicines + European Public Assessment Reports
                service = EMAIngestion(pool)
                count = 0
                if drug_name:
                    result = await service.fetch_medicine_by_name(drug_name)
                    if result:
                        count += 1
                else:
                    # Bulk cron: fetch recent authorized medicines
                    result = await service.fetch_authorized_medicines(limit=100)
                    if result:
                        count += 1
                    result = await service.fetch_epars(limit=100)
                    if result:
                        count += 1
                results[source] = count

            else:
                # Try to handle as dynamically onboarded source
                results[source] = await run_dynamic_source_ingestion(pool, source, metrics)

            metrics.records_fetched += results.get(source, 0)
            logger.info(f"Raw ingestion for {source}: {results.get(source, 0)} records")

        except Exception as e:
            err_msg = str(e) or type(e).__name__
            logger.error(f"Raw ingestion failed for {source} [{type(e).__name__}]: {err_msg}")
            metrics.errors.append(f"raw_{source}: {err_msg}")
            results[source] = 0

    return results



# Mapping: ops.sync_schedules source name → SQLMesh model names for bronze & silver.
# This is the authoritative map — each source must have a corresponding SQLMesh model.
SOURCE_TO_SQLMESH_MODELS: Dict[str, Dict[str, str]] = {
    'clinicaltrials_gov': {
        'bronze': 'mol_bronze.clinicaltrials',
        'silver': 'mol_silver.clinical_trials',
    },
    'openfda_labels': {
        'bronze': 'mol_bronze.openfda_labels',
        'silver': 'mol_silver.drug_labels',
    },
    'openfda_faers': {
        'bronze': 'mol_bronze.faers_events',
        'silver': 'mol_silver.adverse_events',
    },
    'chembl': {
        'bronze': 'mol_bronze.chembl',
        'silver': 'mol_silver.molecules',
    },
    'pubchem': {
        'bronze': 'mol_bronze.pubchem',
        'silver': 'mol_silver.pubchem',  # dedicated compound table; molecule enrichment via inchi_key join
    },
    'sec_edgar': {
        'bronze': 'mol_bronze.sec_edgar',
        'silver': 'mol_silver.financial_filings',
    },
    'uniprot': {
        'bronze': 'mol_bronze.uniprot',
        'silver': 'mol_silver.targets',
    },
    'openalex': {
        'bronze': 'mol_bronze.openalex',
        'silver': 'mol_silver.publications',
    },
    'openalex_ci': {
        'bronze': 'mol_bronze.openalex',
        'silver': 'mol_silver.publications',
    },
    'pubmed': {
        'bronze': 'mol_bronze.pubmed',
        'silver': 'mol_silver.publications',
    },
    'drugbank': {
        'bronze': 'mol_bronze.drugbank',
        'silver': 'mol_silver.drugbank',  # dedicated pharmacology table; molecule enrichment via inchi_key join
    },
    'dailymed': {
        'bronze': 'mol_bronze.dailymed',
        'silver': 'mol_silver.dailymed_labels',
    },
    'cochrane_reviews': {
        'bronze': 'mol_bronze.cochrane_reviews',
        'silver': 'mol_silver.cochrane_reviews',  # was mol_silver.publications (wrong)
    },
    'ema_regulatory': {
        'bronze': 'mol_bronze.ema',
        'silver': 'mol_silver.ema_regulatory',  # dedicated EMA medicine table; hta_decisions → regulatory_decisions
    },
    # europepmc ingests publication data but had no SOURCE_TO_SQLMESH_MODELS entry
    'europepmc': {
        'bronze': 'mol_bronze.europepmc',
        'silver': 'mol_silver.publications',
    },
    'hta_decisions': {
        'bronze': 'mol_bronze.nice_hta',          # hta_decisions feeds into the same nice_hta bronze table
        'silver': 'mol_silver.regulatory_decisions',  # was 'mol_silver.hta_decisions'; actual model is regulatory_decisions.sql
    },
    'purple_book': {
        'bronze': 'mol_bronze.purple_book',
        'silver': 'mol_silver.molecules',
    },
    'epo_patents': {
        'bronze': 'mol_bronze.epo_patents',
        'silver': 'mol_silver.patents',
    },
    'euipo_trademarks': {
        'bronze': 'mol_bronze.euipo_trademarks',
        'silver': 'mol_silver.trademarks',
    },
    'uspto_patents': {
        'bronze': 'mol_bronze.uspto_patents',
        'silver': 'mol_silver.patents',
    },
    'uspto_trademarks': {
        'bronze': 'mol_bronze.uspto_trademarks',
        'silver': 'mol_silver.trademarks',
    },
    'uspto_ci': {
        'bronze': 'mol_bronze.uspto_ci',
        'silver': 'mol_silver.patents',
    },
    'who_gho': {
        'bronze': 'mol_bronze.who_gho',
        # no silver model — bronze-only source
    },
    'hrsa_shortage_areas': {
        'bronze': 'mol_bronze.hrsa',
        # no silver model — bronze-only source
    },
    'acc_tvc_certification': {
        'bronze': 'mol_bronze.acc_tvc',
        # no silver model — bronze-only source
    },
    'journal_rss': {
        'bronze': 'mol_bronze.journal_rss',
        'silver': 'mol_silver.news_signals',
    },
    'medical_news': {
        'bronze': 'mol_bronze.medical_news',
        'silver': 'mol_silver.news_signals',
    },
    # CMS drug spending — fetcher writes to mol_bronze.cms_medicare_spending;
    # silver model joins to mol_silver.drug_spending (molecule-linked rows)
    'cms_medicare': {
        'bronze': 'mol_bronze.cms_medicare_spending',
        'silver': 'mol_silver.drug_spending',
    },
    # CMS Open Payments — fetcher writes to mol_bronze.cms_open_payments;
    # silver model promotes to mol_silver.physician_payments (molecule-linked rows)
    'cms_open_payments': {
        'bronze': 'mol_bronze.cms_open_payments',
        'silver': 'mol_silver.physician_payments',
    },
    # NIH Reporter — fetcher writes to mol_raw.nih_reporter;
    # bronze model extracts JSON fields; silver promotes to mol_silver.research_grants
    'nih_reporter': {
        'bronze': 'mol_bronze.nih_reporter',
        'silver': 'mol_silver.research_grants',
    },
    'ct_gov_indication_stats': {
        'bronze': 'mol_bronze.ct_gov_indication_stats',
        # no silver model — bronze-only source
    },
}

# Gold models run after all silver transforms (order matters for dependencies).
# Independent aggregations first, then models that depend on other gold tables.
GOLD_SQLMESH_MODELS = [
    # Core molecule aggregations — depend only on mol_silver.*
    'mol_gold.molecule_profile',
    'mol_gold.safety_signals',
    'mol_gold.lifecycle_stages',
    'mol_gold.lifecycle_evidence',
    'mol_gold.regulatory_timeline',
    'mol_gold.competitive_landscape',
    'mol_gold.company_pipeline',
    # Financial / market — depend on financial_filings + drug_spending
    'mol_gold.financial_summary',
    'mol_gold.market_summary',
    # Advocacy
    'mol_gold.advocacy_groups',
    'mol_gold.advocacy_sentiment',
    # KOL — depend on publications + physician_payments
    'mol_gold.kol_profiles',
    'mol_gold.kol_drug_associations',
    'mol_gold.kol_network',
]

async def run_bronze_transformation(pool, metrics: PipelineMetrics, sources: Optional[List[str]] = None) -> Dict[str, int]:
    """Transform Raw → Bronze for the given sources using SQLMesh.

    Calls `sqlmesh plan --auto-apply --select-model <model>` for each source.
    All transformation logic lives in SQLMesh SQL models — no Python transforms.
    """
    import asyncio
    from ...ingestion.transform_molecules import transform_model

    results: Dict[str, int] = {}
    target_sources = sources or list(SOURCE_TO_SQLMESH_MODELS.keys())

    for source in target_sources:
        models = SOURCE_TO_SQLMESH_MODELS.get(source, {})
        bronze_model = models.get('bronze')
        if not bronze_model:
            logger.debug(f"No SQLMesh bronze model for source '{source}', skipping")
            continue
        try:
            result = await asyncio.to_thread(transform_model, bronze_model)
            count = result.get('success_count', 0)
            results[source] = count
            metrics.records_bronze += count
            if result.get('status') == 'failed':
                err = result.get('error', 'unknown')[:120]
                metrics.errors.append(f"bronze_{source}: {err}")
                logger.error(f"Bronze SQLMesh failed for '{source}' ({bronze_model}): {err}")
            else:
                logger.info(f"Bronze SQLMesh OK: '{source}' ({bronze_model}) → {count} records")
        except Exception as e:
            logger.error(f"Bronze SQLMesh error for '{source}': {e}")
            metrics.errors.append(f"bronze_{source}: {str(e)[:100]}")

    logger.info(f"Bronze transformation complete: {metrics.records_bronze} total records")
    return results


async def run_silver_transformation(pool, metrics: PipelineMetrics, sources: Optional[List[str]] = None) -> Dict[str, int]:
    """Transform Bronze → Silver for the given sources using SQLMesh.

    Calls `sqlmesh plan --auto-apply --select-model <model>` for each source.
    Entity linking (molecule_id join) is embedded in the SQLMesh silver models.
    """
    import asyncio
    from ...ingestion.transform_molecules import transform_model

    results: Dict[str, int] = {}
    processed_models: set = set()  # deduplicate — multiple sources can share a silver model
    target_sources = sources or list(SOURCE_TO_SQLMESH_MODELS.keys())

    for source in target_sources:
        models = SOURCE_TO_SQLMESH_MODELS.get(source, {})
        silver_model = models.get('silver')
        if not silver_model or silver_model in processed_models:
            continue
        processed_models.add(silver_model)
        try:
            result = await asyncio.to_thread(transform_model, silver_model)
            count = result.get('success_count', 0)
            results[silver_model] = count
            metrics.records_silver += count
            if result.get('status') == 'failed':
                err = result.get('error', 'unknown')[:120]
                metrics.errors.append(f"silver_{source}: {err}")
                logger.error(f"Silver SQLMesh failed for '{source}' ({silver_model}): {err}")
            else:
                logger.info(f"Silver SQLMesh OK: '{source}' ({silver_model}) → {count} records")
        except Exception as e:
            logger.error(f"Silver SQLMesh error for '{source}': {e}")
            metrics.errors.append(f"silver_{source}: {str(e)[:100]}")

    logger.info(f"Silver transformation complete: {metrics.records_silver} total records linked")
    return results


async def run_entity_linking(pool, metrics: PipelineMetrics) -> Dict[str, Any]:
    """
    Run entity linking to connect trials, labels, and other entities to molecules.

    This phase:
    1. Refreshes the drug_name_lookup with synonyms from DrugBank products and ChEMBL
    2. Links clinical trials to molecules using normalized drug names
    3. Links FDA drug labels to molecules

    Uses the database functions created in silver schema.
    """
    results = {}

    try:
        async with pool.acquire() as conn:
            # Check if the legacy silver.run_entity_linking() function still exists.
            # It was deprecated in favour of Python-side SilverTransformation; the
            # silver schema is dropped in migration 121.  Skip silently when absent.
            fn_exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM pg_proc p "
                "JOIN pg_namespace n ON p.pronamespace = n.oid "
                "WHERE n.nspname = 'silver' AND p.proname = 'run_entity_linking')"
            )
            if not fn_exists:
                logger.info("silver.run_entity_linking() not present (schema dropped) — skipping legacy linking")
                return results

            rows = await conn.fetch("SELECT * FROM silver.run_entity_linking()")

            for row in rows:
                step = row['step']
                result_text = row['result']
                results[step] = result_text
                logger.info(f"Entity Linking - {step}: {result_text}")

            # Parse linking stats for metrics
            import re
            for row in rows:
                if 'Trials' in row['step']:
                    match = re.search(r'\+(\d+)', row['result'])
                    if match:
                        metrics.records_silver += int(match.group(1))
                elif 'Labels' in row['step']:
                    match = re.search(r'\+(\d+)', row['result'])
                    if match:
                        metrics.records_silver += int(match.group(1))

        logger.info(f"Entity linking complete: {results}")

    except Exception as e:
        logger.error(f"Entity linking failed: {e}")
        metrics.errors.append(f"entity_linking: {str(e)}")
        results['error'] = str(e)

    return results


async def run_retroactive_linking(pool, metrics: PipelineMetrics) -> Dict[str, int]:
    """
    Re-attempt entity linking for Silver records that have NULL molecule_id.

    This phase runs after entity linking to catch records that:
    1. Were previously unlinked because molecules weren't in the database
    2. Can now be linked because new molecules were just imported
    3. Failed initial linking due to timing issues

    This is particularly important when:
    - A second data source imports molecules that match existing unlinked records
    - The identifier_mappings table is updated with new mappings
    """
    from .dynamic_transformer import DynamicSourceTransformer, get_dynamic_sources

    results = {}

    try:
        dynamic_sources = await get_dynamic_sources(pool)
        if not dynamic_sources:
            logger.info("No dynamic sources found for retroactive linking")
            return results

        transformer = DynamicSourceTransformer(pool)

        for source in dynamic_sources:
            try:
                # Check if this source has entity linking configured
                config = await transformer.get_source_config(source)
                if not config:
                    continue

                entity_linking = config.get('options', {}).get('entity_linking', {})
                if not entity_linking.get('identifier_field'):
                    continue  # No entity linking configured

                # Run retroactive linking
                result = await transformer.relink_unlinked_records(source, batch_size=1000)
                results[source] = result.records_updated

                if result.records_updated > 0:
                    logger.info(
                        f"Retroactive linking for {source}: "
                        f"{result.records_updated}/{result.records_processed} records now linked"
                    )
                    metrics.records_silver += result.records_updated

                if result.errors:
                    metrics.errors.extend(result.errors[:3])

            except Exception as e:
                logger.error(f"Retroactive linking failed for {source}: {e}")
                metrics.errors.append(f"relink_{source}: {str(e)[:100]}")

        logger.info(f"Retroactive linking complete: {sum(results.values())} total records linked")

    except Exception as e:
        logger.error(f"Retroactive linking phase failed: {e}")
        metrics.errors.append(f"retroactive_linking: {str(e)}")

    return results


async def run_gold_aggregation(pool, metrics: PipelineMetrics) -> Dict[str, int]:
    """Run all Gold aggregation models via SQLMesh.

    All gold logic lives in SQL models — no Python aggregation code.
    """
    import asyncio
    from ...ingestion.transform_molecules import transform_model

    results: Dict[str, int] = {}
    for model_name in GOLD_SQLMESH_MODELS:
        try:
            result = await asyncio.to_thread(transform_model, model_name)
            count = result.get('success_count', 0)
            results[model_name] = count
            metrics.records_gold += count
            if result.get('status') == 'failed':
                logger.warning(f"Gold SQLMesh model '{model_name}' failed: {result.get('error', '')[:100]}")
            else:
                logger.info(f"Gold SQLMesh OK: '{model_name}' → {count} records")
        except Exception as e:
            logger.warning(f"Gold SQLMesh error for '{model_name}': {e}")

    logger.info(f"Gold aggregation complete: {metrics.records_gold} total records")
    return results


async def run_sqlmesh_transformation(metrics: PipelineMetrics) -> Dict[str, Any]:
    """
    Run SQLMesh transformations after bronze layer ingestion.

    This integrates SQLMesh as an alternative/additional transformation layer.
    """
    import subprocess
    from pathlib import Path

    results = {}

    try:
        # Locate the SQLMesh project directory
        script_dir = Path(__file__).parent
        sqlmesh_dir = script_dir.parent.parent.parent / "sqlmesh"

        if not sqlmesh_dir.exists():
            logger.warning(f"SQLMesh directory not found: {sqlmesh_dir}")
            return results

        # Get environment from env var
        environment = os.getenv('SQLMESH_ENV', 'prod')

        # Run sqlmesh plan --auto-apply
        cmd = ["sqlmesh", "plan", environment, "--auto-apply", "--no-prompts"]
        logger.info(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            cwd=str(sqlmesh_dir),
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )

        results = {
            "returncode": result.returncode,
            "stdout": result.stdout[:1000] if result.stdout else None,
            "stderr": result.stderr[:500] if result.stderr else None,
        }

        if result.returncode == 0:
            logger.info("SQLMesh transformation complete")
        else:
            logger.error(f"SQLMesh failed with code {result.returncode}")
            if result.stderr:
                metrics.errors.append(f"sqlmesh: {result.stderr[:200]}")

    except subprocess.TimeoutExpired:
        logger.error("SQLMesh transformation timed out")
        metrics.errors.append("sqlmesh: timeout after 600 seconds")
    except FileNotFoundError:
        logger.warning("SQLMesh CLI not found - skipping")
    except Exception as e:
        logger.error(f"SQLMesh transformation failed: {e}")
        metrics.errors.append(f"sqlmesh: {str(e)}")

    return results


async def record_job_execution(
    pool,
    job_id: str,
    tier: str,
    sources: List[str],
    metrics: PipelineMetrics,
    status: str
):
    """Record job execution in database using existing table schema."""
    try:
        # Map our status to the table's allowed statuses
        status_map = {
            'running': 'processing',
            'completed': 'completed',
            'completed_with_errors': 'completed',
            'failed': 'failed',
        }
        db_status = status_map.get(status, 'processing')

        # Calculate total records processed
        total_records = (
            metrics.records_fetched +
            metrics.records_bronze +
            metrics.records_silver +
            metrics.records_gold
        )

        # Build error details
        error_details = {
            'tier': tier,
            'sources': sources,
            'records_fetched': metrics.records_fetched,
            'records_bronze': metrics.records_bronze,
            'records_silver': metrics.records_silver,
            'records_gold': metrics.records_gold,
            'duration_seconds': metrics.elapsed_seconds(),
            'errors': metrics.errors[:20],
        }

        async with pool.acquire() as conn:
            # Check if job exists
            existing = await conn.fetchval(
                "SELECT job_id FROM ops.ingestion_jobs WHERE job_id = $1",
                job_id
            )

            # Serialize error_details to JSON string for JSONB column
            error_details_json = json.dumps(error_details)

            if existing:
                # Update existing job - determine if we should set completed_at
                should_complete = db_status in ('completed', 'failed')

                if should_complete:
                    await conn.execute("""
                        UPDATE ops.ingestion_jobs SET
                            status = $2,
                            completed_at = NOW(),
                            records_processed = $3,
                            error_message = $4,
                            error_details = $5::jsonb
                        WHERE job_id = $1
                    """,
                        job_id,
                        db_status,
                        total_records,
                        metrics.errors[0] if metrics.errors else None,
                        error_details_json
                    )
                else:
                    await conn.execute("""
                        UPDATE ops.ingestion_jobs SET
                            status = $2,
                            records_processed = $3,
                            error_message = $4,
                            error_details = $5::jsonb
                        WHERE job_id = $1
                    """,
                        job_id,
                        db_status,
                        total_records,
                        metrics.errors[0] if metrics.errors else None,
                        error_details_json
                    )
            else:
                # Insert new job (use first source as the source field)
                source_name = sources[0] if sources else tier
                await conn.execute("""
                    INSERT INTO ops.ingestion_jobs (
                        job_id, source, status, priority,
                        started_at, records_processed,
                        error_message, error_details
                    ) VALUES (
                        $1, $2, $3, $4, NOW(), $5, $6, $7::jsonb
                    )
                """,
                    job_id,
                    source_name,
                    db_status,
                    'normal',
                    total_records,
                    metrics.errors[0] if metrics.errors else None,
                    error_details_json
                )

    except Exception as e:
        logger.error(f"Failed to record job execution: {e}")


async def run_pipeline(
    sources: List[str],
    tier: str,
    full_refresh: bool = False,
    skip_raw: bool = False,
    skip_bronze: bool = False,
    skip_silver: bool = False,
    skip_gold: bool = False,
    drug_name: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the full data pipeline.

    Args:
        sources: List of data sources to sync
        tier: Sync tier (daily, weekly, monthly)
        full_refresh: Force full refresh instead of incremental
        skip_raw: Skip raw ingestion
        skip_bronze: Skip bronze transformation
        skip_silver: Skip silver transformation
        skip_gold: Skip gold aggregation
        drug_name: Optional drug name to fetch data for (instead of hardcoded defaults)
        job_id: Optional pre-assigned job UUID string (e.g. from trigger endpoint so
                xenon can poll the same ID via GET /jobs/{job_id})

    Returns:
        Pipeline execution results
    """
    # Use caller-supplied job_id so xenon can poll it, or generate a new one
    if job_id is not None:
        from uuid import UUID as _UUID
        job_id = _UUID(job_id)
    else:
        job_id = uuid4()
    job_id_str = str(job_id)  # For logging
    metrics = PipelineMetrics()

    logger.info(f"Starting pipeline job {job_id_str}")
    logger.info(f"Tier: {tier}, Sources: {sources}, Full refresh: {full_refresh}")

    pool = None
    status = 'completed'

    try:
        pool = await get_db_pool()

        # Record job start
        await record_job_execution(pool, job_id, tier, sources, metrics, 'running')

        # Phase 1: Raw Ingestion
        if not skip_raw:
            logger.info("Phase 1: Raw Ingestion")
            await run_raw_ingestion(pool, sources, metrics, drug_name=drug_name)

        # Phase 2: Bronze Transformation
        if not skip_bronze:
            logger.info("Phase 2: Bronze Transformation")
            await run_bronze_transformation(pool, metrics, sources=sources)

        # Phase 3: Silver Transformation
        if not skip_silver:
            logger.info("Phase 3: Silver Transformation")
            await run_silver_transformation(pool, metrics, sources=sources)

        # Phase 4: Entity Linking (connect trials/labels to molecules)
        if not skip_silver:
            logger.info("Phase 4: Entity Linking")
            await run_entity_linking(pool, metrics)

        # Phase 4b: Retroactive Linking (re-link previously unlinked records)
        if not skip_silver:
            logger.info("Phase 4b: Retroactive Entity Linking")
            await run_retroactive_linking(pool, metrics)

        # Phase 5: Gold Aggregation
        if not skip_gold:
            logger.info("Phase 5: Gold Aggregation")
            await run_gold_aggregation(pool, metrics)

        # Phase 6: SQLMesh Transformation (optional, if configured)
        use_sqlmesh = os.getenv('USE_SQLMESH', 'false').lower() in ('true', '1', 'yes')
        if use_sqlmesh and not skip_bronze:
            logger.info("Phase 5: SQLMesh Transformation")
            await run_sqlmesh_transformation(metrics)

        if metrics.errors:
            status = 'completed_with_errors'

    except Exception as e:
        err_msg = str(e) or type(e).__name__
        logger.error(f"Pipeline failed [{type(e).__name__}]: {err_msg}")
        metrics.errors.append(f"pipeline: {err_msg}")
        status = 'failed'

    finally:
        if pool:
            # Record job completion
            await record_job_execution(pool, job_id, tier, sources, metrics, status)
            await pool.close()

    result = {
        'job_id': job_id_str,  # Return string for JSON serialization
        'status': status,
        'tier': tier,
        'sources': sources,
        'metrics': metrics.to_dict(),
        'completed_at': datetime.utcnow().isoformat(),
    }

    logger.info(f"Pipeline job {job_id_str} completed with status: {status}")
    logger.info(f"Metrics: {metrics.to_dict()}")

    return result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='DK Data Platform Sync Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Daily sync for clinical trials and FDA data
    python -m sync_runner --sources clinicaltrials,openfda_labels --tier daily

    # Weekly sync for FAERS
    python -m sync_runner --sources openfda_faers,openalex --tier weekly

    # Monthly sync for reference databases
    python -m sync_runner --sources chembl,drugbank,pubchem --tier monthly

    # Transform only (skip raw ingestion)
    python -m sync_runner --tier daily --skip-raw

    # Full pipeline refresh
    python -m sync_runner --sources all --tier manual --full-refresh
        """
    )

    parser.add_argument(
        '--sources', '-s',
        type=str,
        default='all',
        help='Comma-separated list of sources (or "all")'
    )

    parser.add_argument(
        '--tier', '-t',
        type=str,
        choices=['daily', 'weekly', 'monthly', 'manual'],
        default='manual',
        help='Sync tier'
    )

    parser.add_argument(
        '--full-refresh', '-f',
        type=str,
        default='false',
        help='Force full refresh (true/false)'
    )

    parser.add_argument(
        '--skip-raw',
        action='store_true',
        help='Skip raw ingestion phase'
    )

    parser.add_argument(
        '--skip-bronze',
        action='store_true',
        help='Skip bronze transformation phase'
    )

    parser.add_argument(
        '--skip-silver',
        action='store_true',
        help='Skip silver transformation phase'
    )

    parser.add_argument(
        '--skip-gold',
        action='store_true',
        help='Skip gold aggregation phase'
    )

    args = parser.parse_args()

    # Parse sources
    if args.sources == 'all':
        sources = [
            # Core sources (daily/weekly)
            'clinicaltrials', 'openfda_faers', 'openfda_labels',
            # Reference databases (monthly)
            'chembl', 'pubchem', 'uniprot', 'openalex',
            # Research codes and biologics (for better entity linking)
            'who_inn', 'kegg_drug', 'ttd', 'fda_drugs',
            'imgt', 'cdc_vaccines'
        ]
    else:
        sources = [s.strip() for s in args.sources.split(',')]

    # Parse full_refresh
    full_refresh = args.full_refresh.lower() in ('true', '1', 'yes')

    # Run pipeline
    result = asyncio.run(run_pipeline(
        sources=sources,
        tier=args.tier,
        full_refresh=full_refresh,
        skip_raw=args.skip_raw,
        skip_bronze=args.skip_bronze,
        skip_silver=args.skip_silver,
        skip_gold=args.skip_gold,
    ))

    # Exit with appropriate code
    if result['status'] == 'failed':
        sys.exit(1)
    elif result['status'] == 'completed_with_errors':
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
