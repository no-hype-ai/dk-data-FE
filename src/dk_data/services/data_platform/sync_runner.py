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
    level=os.getenv('LOG_LEVEL', 'INFO'),
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

    return await asyncpg.create_pool(db_url, min_size=2, max_size=10)


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
                FROM raw.sync_schedules
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
                UPDATE raw.sync_schedules
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
    )

    results = {}

    for source in sources:
        try:
            logger.info(f"Starting raw ingestion for {source}")

            if source == 'clinicaltrials' or source == 'clinicaltrials_gov':
                service = ClinicalTrialsIngestion(pool)
                count = 0
                if drug_name:
                    # Fetch trials for the specific drug (intervention search)
                    result = await service.fetch_studies(intervention=drug_name, page_size=100)
                    if result:
                        count += 1
                    # Also search by query for broader coverage
                    result = await service.fetch_studies(query=drug_name, page_size=100)
                    if result:
                        count += 1
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
                from datetime import date as date_type
                from ...ingestion.fetchers.sec_edgar import SECEdgarFetcher

                # Step 1: Fetch filing metadata from EDGAR search index
                fetcher = SECEdgarFetcher()
                search_terms = [drug_name] if drug_name else None
                fetch_result = fetcher.fetch(
                    search_terms=search_terms,
                    days_back=365,
                )
                count = 0
                target_cik = None
                if fetch_result.get("status") == "success" and fetch_result.get("records"):
                    async with pool.acquire() as conn:
                        for rec in fetch_result["records"]:
                            try:
                                fd = rec.get("filing_date")
                                filing_date = None
                                if fd:
                                    try:
                                        filing_date = date_type.fromisoformat(str(fd)[:10])
                                    except (ValueError, TypeError):
                                        filing_date = None
                                await conn.execute("""
                                    INSERT INTO raw.sec_edgar
                                        (accession_number, company_name, cik, filing_type, filing_date, document_url, description)
                                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                                    ON CONFLICT (accession_number) DO UPDATE SET
                                        company_name = EXCLUDED.company_name,
                                        filing_date = EXCLUDED.filing_date,
                                        document_url = EXCLUDED.document_url
                                """,
                                    rec.get("accession_number"),
                                    rec.get("company_name"),
                                    rec.get("cik"),
                                    rec.get("filing_type"),
                                    filing_date,
                                    rec.get("document_url"),
                                    rec.get("description"),
                                )
                                count += 1
                                # Track the target company's CIK for revenue extraction
                                # Handle formatted names like "ASTRAZENECA PLC  (AZN)  (CIK 0000901832)"
                                cn = (rec.get("company_name") or "").lower()
                                if drug_name and cn and drug_name.lower().split()[0] in cn:
                                    target_cik = rec.get("cik")
                                    logger.info(f"SEC EDGAR: matched CIK {target_cik} for company '{rec.get('company_name')}'")

                            except Exception as e:
                                logger.debug(f"SEC EDGAR insert failed: {e}")
                    logger.info(f"SEC EDGAR: loaded {count} filings for '{drug_name}' (CIK: {target_cik})")

                # Step 2: Extract product-level revenue from the filing content
                # Uses the SECEdgarClient which parses FilingSummary.xml and XBRL data
                if target_cik and drug_name:
                    try:
                        from ...services.external_apis.sec_edgar_client import SECEdgarClient
                        client = SECEdgarClient()
                        current_year = date_type.today().year
                        revenues = await client.extract_product_revenues(
                            target_cik, years=[current_year, current_year - 1, current_year - 2]
                        )
                        if revenues:
                            async with pool.acquire() as conn:
                                for rev in revenues:
                                    try:
                                        await conn.execute("""
                                            INSERT INTO silver.financial_filings
                                                (id, company_name, filing_type, period, revenue, product_name, source, created_at)
                                            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, 'sec_edgar', NOW())
                                        """,
                                            drug_name,
                                            rev.source_filing or '20-F',
                                            f"{rev.period}_{rev.year}" if rev.year else rev.period,
                                            rev.revenue_usd,
                                            rev.product_name,
                                        )
                                    except Exception as e:
                                        logger.debug(f"SEC EDGAR revenue insert failed: {e}")
                            logger.info(f"SEC EDGAR: extracted {len(revenues)} product revenues for '{drug_name}'")
                    except Exception as e:
                        logger.warning(f"SEC EDGAR revenue extraction failed: {e}")

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

            else:
                # Try to handle as dynamically onboarded source
                results[source] = await run_dynamic_source_ingestion(pool, source, metrics)

            metrics.records_fetched += results.get(source, 0)
            logger.info(f"Raw ingestion for {source}: {results.get(source, 0)} records")

        except Exception as e:
            logger.error(f"Raw ingestion failed for {source}: {e}")
            metrics.errors.append(f"raw_{source}: {str(e)}")
            results[source] = 0

    return results


async def run_bronze_transformation(pool, metrics: PipelineMetrics) -> Dict[str, int]:
    """Transform Raw layer data to Bronze using BulletproofTransformer.

    Uses dynamic schema detection - no hardcoded column mappings.
    """
    results = {}

    try:
        # Try to use BulletproofTransformer (preferred - dynamic schema detection)
        from .bulletproof_transformer import BulletproofTransformer
        transformer = BulletproofTransformer(pool)
        await transformer.initialize()
        logger.info("Using BulletproofTransformer for Bronze layer")
    except ImportError:
        # Fallback to DynamicSourceTransformer
        from .dynamic_transformer import DynamicSourceTransformer
        transformer = DynamicSourceTransformer(pool)
        logger.warning("BulletproofTransformer not available, using DynamicSourceTransformer")

    # Get all raw tables and transform them
    # Raw tables are named directly (e.g., raw.clinicaltrials, raw.openfda_faers)
    # Exclude system/config tables
    SYSTEM_TABLES = {'sync_schedules', 'initial_load_state', 'transformation_state',
                     'transformation_config', 'data_sources', 'refresh_log'}
    async with pool.acquire() as conn:
        raw_tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'raw'
            AND table_type = 'BASE TABLE'
            AND table_name NOT IN ('sync_schedules', 'initial_load_state',
                'transformation_state', 'transformation_config',
                'data_sources', 'refresh_log')
        """)

    for row in raw_tables:
        source = row['table_name']
        try:
            result = await transformer.transform_raw_to_bronze(source)
            results[source] = result.records_inserted
            metrics.records_bronze += result.records_inserted
            if result.errors:
                metrics.errors.extend(result.errors[:3])
            logger.info(f"Bronze transform {source}: {result.records_inserted} records")
        except Exception as e:
            logger.error(f"Bronze transform failed for {source}: {e}")
            metrics.errors.append(f"bronze_{source}: {str(e)[:100]}")

    logger.info(f"Bronze transformation complete: {metrics.records_bronze} total records")
    return results


async def run_silver_transformation(pool, metrics: PipelineMetrics) -> Dict[str, int]:
    """Transform Bronze layer data to Silver using BulletproofTransformer.

    Uses 5-level entity linking:
    1. InChI Key (exact match)
    2. Other identifiers (DrugBank, ChEMBL, etc.)
    3. SMILES → InChI conversion (RDKit)
    4. Fuzzy name matching
    5. Create new molecule
    """
    results = {}

    try:
        # Try to use BulletproofTransformer (preferred - dynamic entity linking)
        from .bulletproof_transformer import BulletproofTransformer
        transformer = BulletproofTransformer(pool)
        await transformer.initialize()
        logger.info("Using BulletproofTransformer for Silver layer")
    except ImportError:
        # Fallback to DynamicSourceTransformer
        from .dynamic_transformer import DynamicSourceTransformer
        transformer = DynamicSourceTransformer(pool)
        logger.warning("BulletproofTransformer not available, using DynamicSourceTransformer")

    # Get all bronze tables and transform them to silver
    async with pool.acquire() as conn:
        bronze_tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'bronze' AND table_type = 'BASE TABLE'
        """)

    for row in bronze_tables:
        source = row['table_name']
        try:
            result = await transformer.transform_bronze_to_silver(source)
            linked = getattr(result, 'records_linked', 0) or result.records_inserted
            results[source] = linked
            metrics.records_silver += linked
            if result.errors:
                metrics.errors.extend(result.errors[:3])
            logger.info(f"Silver transform {source}: {linked} records linked")
        except Exception as e:
            logger.error(f"Silver transform failed for {source}: {e}")
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
            # Run the master entity linking function
            rows = await conn.fetch("SELECT * FROM silver.run_entity_linking()")

            for row in rows:
                step = row['step']
                result_text = row['result']
                results[step] = result_text
                logger.info(f"Entity Linking - {step}: {result_text}")

            # Parse linking stats for metrics
            for row in rows:
                if 'Trials' in row['step']:
                    # Extract number from result like "+31 new, 46178 total (48.2%)"
                    import re
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
    """Aggregate Silver layer data to Gold views."""
    from .gold_aggregation import GoldAggregationService

    service = GoldAggregationService(pool)
    results = {}

    try:
        # Refresh all Gold aggregations (built-in sources)
        agg_results = await service.refresh_all()

        for name, result in agg_results.items():
            results[name] = result.rows_affected
            metrics.records_gold += result.rows_affected
            if not result.success and result.error:
                metrics.errors.append(f"gold_{name}: {result.error}")

        logger.info(f"Gold aggregation (built-in): {metrics.records_gold} records")

    except Exception as e:
        logger.error(f"Gold aggregation failed: {e}")
        metrics.errors.append(f"gold: {str(e)}")

    # Process dynamic sources
    try:
        from .dynamic_transformer import DynamicSourceTransformer, get_dynamic_sources

        dynamic_sources = await get_dynamic_sources(pool)
        if dynamic_sources:
            logger.info(f"Processing {len(dynamic_sources)} dynamic sources for Gold")
            transformer = DynamicSourceTransformer(pool)

            for source in dynamic_sources:
                try:
                    result = await transformer.transform_silver_to_gold(source)
                    results[f"dynamic_{source}"] = result.records_inserted
                    metrics.records_gold += result.records_inserted
                    if result.errors:
                        metrics.errors.extend(result.errors[:3])
                except Exception as e:
                    logger.error(f"Dynamic gold transform failed for {source}: {e}")
                    metrics.errors.append(f"gold_dynamic_{source}: {str(e)[:100]}")

            logger.info(f"Gold aggregation (dynamic): processed {len(dynamic_sources)} sources")

    except Exception as e:
        logger.error(f"Dynamic gold aggregation failed: {e}")
        metrics.errors.append(f"gold_dynamic: {str(e)}")

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
                "SELECT job_id FROM raw.ingestion_jobs WHERE job_id = $1",
                job_id
            )

            # Serialize error_details to JSON string for JSONB column
            error_details_json = json.dumps(error_details)

            if existing:
                # Update existing job - determine if we should set completed_at
                should_complete = db_status in ('completed', 'failed')

                if should_complete:
                    await conn.execute("""
                        UPDATE raw.ingestion_jobs SET
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
                        UPDATE raw.ingestion_jobs SET
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
                    INSERT INTO raw.ingestion_jobs (
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

    Returns:
        Pipeline execution results
    """
    # Use UUID object for PostgreSQL UUID column
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
            await run_bronze_transformation(pool, metrics)

        # Phase 3: Silver Transformation
        if not skip_silver:
            logger.info("Phase 3: Silver Transformation")
            await run_silver_transformation(pool, metrics)

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
        logger.error(f"Pipeline failed: {e}")
        metrics.errors.append(f"pipeline: {str(e)}")
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
