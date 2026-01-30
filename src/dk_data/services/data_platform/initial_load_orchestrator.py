"""
Initial Load Orchestrator - Full Data Platform Bootstrap (Bulletproof Edition)

Implements Option A (Layer-by-Layer) loading with:
- Checkpoint/resume capability (survives restarts)
- Disk space monitoring (stops before filling disk)
- Retry logic with exponential backoff
- Graceful shutdown handling (SIGTERM/SIGINT)
- Batch inserts for performance
- Progress persistence to database

Usage:
    python -m services.data_platform.initial_load_orchestrator --all
    python -m services.data_platform.initial_load_orchestrator --source fda_labels
    python -m services.data_platform.initial_load_orchestrator --resume
    python -m services.data_platform.initial_load_orchestrator --status
    python -m services.data_platform.initial_load_orchestrator --reset-all

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import asyncio
import aiohttp
import io
import json
import os
import sys
import time
import signal
import shutil
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging
import argparse
import traceback

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

class LoadConfig:
    """Configuration for the initial load process."""

    # Disk space thresholds (in GB)
    MIN_DISK_SPACE_GB: float = float(os.getenv('MIN_DISK_SPACE_GB', '10'))
    WARN_DISK_SPACE_GB: float = float(os.getenv('WARN_DISK_SPACE_GB', '20'))

    # Retry settings
    MAX_RETRIES: int = int(os.getenv('MAX_RETRIES', '5'))
    INITIAL_RETRY_DELAY: float = float(os.getenv('INITIAL_RETRY_DELAY', '1.0'))
    MAX_RETRY_DELAY: float = float(os.getenv('MAX_RETRY_DELAY', '60.0'))
    RETRY_BACKOFF_FACTOR: float = float(os.getenv('RETRY_BACKOFF_FACTOR', '2.0'))

    # Batch settings
    BATCH_SIZE: int = int(os.getenv('BATCH_SIZE', '500'))
    CHECKPOINT_INTERVAL: int = int(os.getenv('CHECKPOINT_INTERVAL', '1000'))

    # Connection settings
    DB_POOL_MIN: int = int(os.getenv('DB_POOL_MIN', '2'))
    DB_POOL_MAX: int = int(os.getenv('DB_POOL_MAX', '10'))
    HTTP_TIMEOUT: int = int(os.getenv('HTTP_TIMEOUT', '120'))

    # Progress check interval (seconds)
    PROGRESS_LOG_INTERVAL: int = int(os.getenv('PROGRESS_LOG_INTERVAL', '60'))


# =============================================================================
# Data Source Configurations
# =============================================================================

DATA_SOURCES = {
    'fda_labels': {
        'name': 'FDA Drug Labels',
        'api_type': 'rest',
        'base_url': 'https://api.fda.gov/drug/label.json',
        'tier': 'daily',
        'total_records_endpoint': 'https://api.fda.gov/drug/label.json?limit=1',
        'total_path': 'meta.results.total',
        'pagination': {
            'type': 'skip',
            'page_size': 1000,
            'skip_param': 'skip',
            'limit_param': 'limit',
            'max_skip': 25000,
        },
        'data_path': 'results',
        'rate_limit': 4,
        'entity_linking': {
            'identifier_field': 'openfda.unii',
            'identifier_type': 'unii',
            'secondary_fields': ['openfda.brand_name', 'openfda.generic_name'],
        },
    },
    'fda_faers': {
        'name': 'FDA Adverse Event Reports',
        'api_type': 'rest',
        'base_url': 'https://api.fda.gov/drug/event.json',
        'tier': 'daily',
        'total_records_endpoint': 'https://api.fda.gov/drug/event.json?limit=1',
        'total_path': 'meta.results.total',
        'pagination': {
            'type': 'skip',
            'page_size': 1000,
            'skip_param': 'skip',
            'limit_param': 'limit',
            'max_skip': 25000,
        },
        'data_path': 'results',
        'rate_limit': 4,
        'entity_linking': {
            'identifier_field': 'patient.drug.medicinalproduct',
            'identifier_type': 'drug_name',
        },
    },
    'fda_orange_book': {
        'name': 'FDA Orange Book',
        'api_type': 'file',
        'base_url': 'https://www.fda.gov/media/76860/download',
        'tier': 'monthly',
        'file_format': 'tsv',
        'delimiter': '~',
        'entity_linking': {
            'identifier_field': 'Ingredient',
            'identifier_type': 'drug_name',
        },
    },
    'clinicaltrials': {
        'name': 'ClinicalTrials.gov Studies',
        'api_type': 'rest',
        'base_url': 'https://clinicaltrials.gov/api/v2/studies',
        'tier': 'daily',
        'total_records_endpoint': 'https://clinicaltrials.gov/api/v2/stats/size',
        'total_path': 'totalCount',
        'pagination': {
            'type': 'token',
            'page_size': 100,
            'page_size_param': 'pageSize',
            'token_param': 'pageToken',
            'token_response_path': 'nextPageToken',
        },
        'data_path': 'studies',
        'rate_limit': 3,
        'query_params': {
            'format': 'json',
            'countTotal': 'true',
        },
        'entity_linking': {
            'identifier_field': 'protocolSection.armsInterventionsModule.interventions',
            'identifier_type': 'drug_name',
        },
    },
    'chembl_molecules': {
        'name': 'ChEMBL Molecules',
        'api_type': 'rest',
        'base_url': 'https://www.ebi.ac.uk/chembl/api/data/molecule.json',
        'tier': 'weekly',
        'total_records_endpoint': 'https://www.ebi.ac.uk/chembl/api/data/molecule.json?limit=1',
        'total_path': 'page_meta.total_count',
        'pagination': {
            'type': 'offset',
            'page_size': 1000,
            'offset_param': 'offset',
            'limit_param': 'limit',
        },
        'data_path': 'molecules',
        'rate_limit': 5,
        'entity_linking': {
            'identifier_field': 'molecule_chembl_id',
            'identifier_type': 'chembl_id',
            'secondary_fields': ['molecule_structures.standard_inchi_key'],
        },
    },
    'pubchem_compounds': {
        'name': 'PubChem Compounds',
        'api_type': 'bulk_ftp',
        'base_url': 'https://ftp.ncbi.nlm.nih.gov/pubchem/Compound/CURRENT-Full/SDF/',
        'tier': 'monthly',
        'bulk_download': True,
        'file_pattern': 'Compound_*.sdf.gz',
        'entity_linking': {
            'identifier_field': 'PUBCHEM_COMPOUND_CID',
            'identifier_type': 'pubchem_cid',
            'secondary_fields': ['PUBCHEM_IUPAC_INCHIKEY'],
        },
    },
    'drugbank': {
        'name': 'DrugBank',
        'api_type': 'file',
        'base_url': None,
        'tier': 'weekly',
        'file_format': 'xml',
        'requires_license': True,
        'entity_linking': {
            'identifier_field': 'drugbank-id',
            'identifier_type': 'drugbank_id',
            'secondary_fields': ['inchikey', 'cas-number'],
        },
    },
    'ema_medicines': {
        'name': 'EMA Authorized Medicines',
        'api_type': 'file',
        'base_url': 'https://www.ema.europa.eu/sites/default/files/Medicines_output_european_public_assessment_reports.xlsx',
        'tier': 'weekly',
        'file_format': 'xlsx',
        'entity_linking': {
            'identifier_field': 'Active substance',
            'identifier_type': 'drug_name',
            'secondary_fields': ['Medicine name'],
        },
    },
    'uniprot_targets': {
        'name': 'UniProt Drug Targets',
        'api_type': 'rest',
        'base_url': 'https://rest.uniprot.org/uniprotkb/stream',
        'tier': 'monthly',
        'query_params': {
            'query': '(cc_interaction_type:drug)',
            'format': 'json',
            'size': 500,
        },
        'pagination': {
            'type': 'link',
            'link_header': 'Link',
        },
        'rate_limit': 1,
        'entity_linking': {
            'identifier_field': 'primaryAccession',
            'identifier_type': 'uniprot_id',
        },
    },
    'sider': {
        'name': 'SIDER Side Effects',
        'api_type': 'file',
        'base_url': 'http://sideeffects.embl.de/media/download/meddra_all_se.tsv.gz',
        'tier': 'monthly',
        'file_format': 'tsv',
        'compressed': True,
        'entity_linking': {
            'identifier_field': 'stitch_compound_id',
            'identifier_type': 'pubchem_cid',
        },
    },
    'bindingdb': {
        'name': 'BindingDB Affinities',
        'api_type': 'file',
        'base_url': None,  # Local file - set BINDINGDB_FILE env var
        'tier': 'monthly',
        'file_format': 'tsv',
        'compressed': True,
        'compression_type': 'zip',
        'requires_local_file': True,
        'file_env_var': 'BINDINGDB_FILE',
        'entity_linking': {
            'identifier_field': 'Ligand InChI Key',
            'identifier_type': 'inchi_key',
            'secondary_fields': ['PubChem CID', 'ChEMBL ID of Ligand', 'DrugBank ID of Ligand'],
        },
    },
    'openalex': {
        'name': 'OpenAlex Publications',
        'api_type': 'rest',
        'base_url': 'https://api.openalex.org/works',
        'tier': 'weekly',
        'pagination': {
            'type': 'cursor',
            'page_size': 200,
            'cursor_param': 'cursor',
        },
        'data_path': 'results',
        'rate_limit': 10,  # Polite pool allows 10/sec
        'query_params': {
            'filter': 'concepts.id:C71924100|C203014093|C185592680|C126322002',  # Medicine, Pharmacology, Drug discovery, Clinical trial
            'select': 'id,title,publication_year,doi,concepts,authorships,cited_by_count,abstract_inverted_index',
        },
        'requires_api_key': False,  # Optional but recommended
        'api_key_env': 'OPENALEX_API_KEY',
        'entity_linking': {
            'identifier_field': 'id',
            'identifier_type': 'openalex_id',
        },
    },
    'pdb': {
        'name': 'RCSB PDB Structures',
        'api_type': 'rest',
        'base_url': 'https://search.rcsb.org/rcsbsearch/v2/query',
        'tier': 'monthly',
        'pagination': {
            'type': 'offset',
            'page_size': 1000,
            'offset_param': 'start',
        },
        'rate_limit': 5,
        'query_params': {
            'query': {
                'type': 'terminal',
                'service': 'text',
                'parameters': {
                    'attribute': 'rcsb_entry_info.selected_polymer_entity_types',
                    'operator': 'contains_phrase',
                    'value': 'Protein'
                }
            },
            'return_type': 'entry',
            'request_options': {
                'results_content_type': ['experimental'],
                'sort': [{'sort_by': 'rcsb_accession_info.initial_release_date', 'direction': 'desc'}],
            }
        },
        'entity_linking': {
            'identifier_field': 'identifier',
            'identifier_type': 'pdb_id',
        },
    },
    'pubchem_bioassay': {
        'name': 'PubChem BioAssay (Drug-like compounds)',
        'api_type': 'rest',
        'base_url': 'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid',
        'tier': 'monthly',
        'rate_limit': 5,  # NCBI limit
        'requires_api_key': False,
        'api_key_env': 'NCBI_API_KEY',  # Optional for higher rate
        'entity_linking': {
            'identifier_field': 'CID',
            'identifier_type': 'pubchem_cid',
            'secondary_fields': ['InChIKey'],
        },
        # Note: PubChem is loaded via compound list batches, not pagination
        'batch_mode': True,
    },
    'uspto_patents': {
        'name': 'USPTO PatentsView',
        'api_type': 'rest',
        'base_url': 'https://api.patentsview.org/patents/query',
        'tier': 'weekly',
        'pagination': {
            'type': 'offset',
            'page_size': 1000,
            'offset_param': 'o',
        },
        'rate_limit': 45,  # 45 requests per minute
        'requires_api_key': True,
        'api_key_env': 'PATENTSVIEW_API_KEY',
        'entity_linking': {
            'identifier_field': 'patent_number',
            'identifier_type': 'patent_number',
        },
    },
}


# =============================================================================
# Enums and Data Classes
# =============================================================================

class LoadStatus(str, Enum):
    PENDING = 'pending'
    LOADING_RAW = 'loading_raw'
    LOADING_BRONZE = 'loading_bronze'
    LOADING_SILVER = 'loading_silver'
    COMPLETE = 'complete'
    ERROR = 'error'
    PAUSED = 'paused'


@dataclass
class SourceProgress:
    """Track loading progress for each source - serializable to DB."""
    source: str
    status: str = LoadStatus.PENDING.value
    raw_records: int = 0
    raw_expected: int = 0
    bronze_records: int = 0
    silver_records: int = 0
    linked_records: int = 0
    last_checkpoint: Optional[str] = None  # JSON with pagination state
    errors: List[str] = field(default_factory=list)
    retries: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SourceProgress':
        return cls(**data)


@dataclass
class LoadState:
    """Overall load state - persisted to database."""
    run_id: str
    status: str = 'running'
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    sources: Dict[str, SourceProgress] = field(default_factory=dict)
    current_phase: str = 'init'
    disk_space_gb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'run_id': self.run_id,
            'status': self.status,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'sources': {k: v.to_dict() for k, v in self.sources.items()},
            'current_phase': self.current_phase,
            'disk_space_gb': self.disk_space_gb,
        }


# =============================================================================
# Utility Functions
# =============================================================================

def get_disk_space_gb(path: str = '/') -> float:
    """Get available disk space in GB."""
    try:
        total, used, free = shutil.disk_usage(path)
        return free / (1024 ** 3)
    except Exception as e:
        logger.warning(f"Could not check disk space: {e}")
        return float('inf')  # Assume infinite if we can't check


def utc_now_str() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


async def retry_with_backoff(
    func: Callable,
    *args,
    max_retries: int = LoadConfig.MAX_RETRIES,
    initial_delay: float = LoadConfig.INITIAL_RETRY_DELAY,
    max_delay: float = LoadConfig.MAX_RETRY_DELAY,
    backoff_factor: float = LoadConfig.RETRY_BACKOFF_FACTOR,
    **kwargs
) -> Any:
    """Execute async function with exponential backoff retry."""
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
            last_exception = e
            if attempt < max_retries:
                logger.warning(f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
                delay = min(delay * backoff_factor, max_delay)
            else:
                logger.error(f"All {max_retries + 1} attempts failed: {e}")

    raise last_exception


# =============================================================================
# Initial Load Orchestrator
# =============================================================================

class InitialLoadOrchestrator:
    """
    Orchestrates full data platform initial load with bulletproof features.
    """

    def __init__(self, db_pool, run_id: Optional[str] = None):
        self.db_pool = db_pool
        self.run_id = run_id or f"load_{int(time.time())}"
        self.state: Optional[LoadState] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self._shutdown_requested = False
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers."""
        def signal_handler(signum, frame):
            logger.warning(f"Received signal {signum}, initiating graceful shutdown...")
            self._shutdown_requested = True

        try:
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        except Exception as e:
            logger.warning(f"Could not setup signal handlers: {e}")

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=LoadConfig.HTTP_TIMEOUT)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    # =========================================================================
    # State Persistence
    # =========================================================================

    async def _ensure_state_table(self):
        """Create state tracking table if it doesn't exist."""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS raw.initial_load_state (
                    run_id TEXT PRIMARY KEY,
                    state JSONB NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_initial_load_state_updated
                ON raw.initial_load_state(updated_at DESC)
            """)

    async def _save_state(self):
        """Persist current state to database."""
        if not self.state:
            return

        self.state.disk_space_gb = get_disk_space_gb()

        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO raw.initial_load_state (run_id, state, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (run_id) DO UPDATE SET
                    state = $2,
                    updated_at = NOW()
            """, self.run_id, json.dumps(self.state.to_dict()))

    async def _load_state(self, run_id: Optional[str] = None) -> Optional[LoadState]:
        """Load state from database."""
        await self._ensure_state_table()

        async with self.db_pool.acquire() as conn:
            if run_id:
                row = await conn.fetchrow("""
                    SELECT state FROM raw.initial_load_state WHERE run_id = $1
                """, run_id)
            else:
                # Get most recent incomplete run
                row = await conn.fetchrow("""
                    SELECT state FROM raw.initial_load_state
                    WHERE state->>'status' IN ('running', 'paused')
                    ORDER BY updated_at DESC LIMIT 1
                """)

            if row:
                data = json.loads(row['state']) if isinstance(row['state'], str) else row['state']
                state = LoadState(
                    run_id=data['run_id'],
                    status=data.get('status', 'running'),
                    started_at=data.get('started_at'),
                    completed_at=data.get('completed_at'),
                    current_phase=data.get('current_phase', 'init'),
                    disk_space_gb=data.get('disk_space_gb', 0),
                )
                for source_id, progress_data in data.get('sources', {}).items():
                    state.sources[source_id] = SourceProgress.from_dict(progress_data)
                return state

        return None

    async def _update_source_progress(self, source: str, **kwargs):
        """Update progress for a specific source and save state."""
        if source not in self.state.sources:
            self.state.sources[source] = SourceProgress(source=source)

        progress = self.state.sources[source]
        progress.last_updated = utc_now_str()

        for key, value in kwargs.items():
            if hasattr(progress, key):
                setattr(progress, key, value)

        await self._save_state()

    # =========================================================================
    # Disk Space Monitoring
    # =========================================================================

    def _check_disk_space(self) -> Tuple[bool, float]:
        """Check if we have enough disk space to continue."""
        free_gb = get_disk_space_gb()

        if free_gb < LoadConfig.MIN_DISK_SPACE_GB:
            logger.error(f"CRITICAL: Only {free_gb:.1f}GB disk space remaining! Minimum: {LoadConfig.MIN_DISK_SPACE_GB}GB")
            return False, free_gb

        if free_gb < LoadConfig.WARN_DISK_SPACE_GB:
            logger.warning(f"LOW DISK SPACE: {free_gb:.1f}GB remaining")

        return True, free_gb

    # =========================================================================
    # External API Count Checking
    # =========================================================================

    async def check_external_counts(self) -> Dict[str, int]:
        """Query each external API to get total available records."""
        counts = {}

        for source_id, config in DATA_SOURCES.items():
            if config.get('bulk_download') or config.get('requires_license'):
                counts[source_id] = -1
                continue

            endpoint = config.get('total_records_endpoint')
            if not endpoint:
                counts[source_id] = -1
                continue

            try:
                headers = {}
                if config.get('requires_api_key'):
                    api_key = os.getenv(config.get('api_key_env', ''))
                    if api_key:
                        headers['X-Api-Key'] = api_key

                async with self.session.get(endpoint, headers=headers, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        path = config.get('total_path', '')
                        value = data
                        for key in path.split('.'):
                            if isinstance(value, dict):
                                value = value.get(key)
                            else:
                                value = None
                                break
                        counts[source_id] = int(value) if value else -1
                    else:
                        counts[source_id] = -1
            except Exception as e:
                counts[source_id] = -1
                logger.debug(f"Could not get count for {source_id}: {e}")

        return counts

    # =========================================================================
    # Source Registration
    # =========================================================================

    async def register_all_sources(self):
        """Register all data sources in sync_schedules."""
        async with self.db_pool.acquire() as conn:
            # Ensure sync_schedules table exists
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS raw.sync_schedules (
                    id SERIAL PRIMARY KEY,
                    source TEXT UNIQUE NOT NULL,
                    tier TEXT DEFAULT 'weekly',
                    cron_expression TEXT DEFAULT '0 0 * * *',
                    priority INTEGER DEFAULT 1,
                    enabled BOOLEAN DEFAULT true,
                    options JSONB DEFAULT '{}',
                    last_run_at TIMESTAMPTZ,
                    next_run_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            for source_id, config in DATA_SOURCES.items():
                options = {
                    'api_type': config.get('api_type'),
                    'base_url': config.get('base_url'),
                    'pagination': config.get('pagination'),
                    'data_path': config.get('data_path'),
                    'rate_limit_per_second': config.get('rate_limit', 5),
                    'query_params': config.get('query_params', {}),
                    'entity_linking': config.get('entity_linking'),
                    'target_table': f"raw.{source_id.replace('-', '_')}_data",
                }

                await conn.execute("""
                    INSERT INTO raw.sync_schedules (source, tier, cron_expression, priority, enabled, options)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (source) DO UPDATE SET
                        options = $6,
                        updated_at = NOW()
                """,
                    source_id,
                    config.get('tier', 'weekly'),
                    '0 0 * * *',
                    1,
                    True,
                    json.dumps(options)
                )

        logger.info(f"Registered {len(DATA_SOURCES)} data sources")

    # =========================================================================
    # Raw Layer Loaders
    # =========================================================================

    async def _create_raw_table(self, table_name: str, unique_source_id: bool = False):
        """Create raw table with standard schema."""
        async with self.db_pool.acquire() as conn:
            unique_constraint = "UNIQUE" if unique_source_id else ""
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS raw.{table_name} (
                    id SERIAL PRIMARY KEY,
                    _source_id TEXT {unique_constraint},
                    _ingested_at TIMESTAMPTZ DEFAULT NOW(),
                    _raw_payload JSONB
                )
            """)
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{table_name}_source_id
                ON raw.{table_name}(_source_id)
            """)

    async def _batch_insert_raw(
        self,
        table_name: str,
        records: List[Tuple[str, str]],
        upsert: bool = False
    ) -> int:
        """Batch insert records to raw table."""
        if not records:
            return 0

        async with self.db_pool.acquire() as conn:
            if upsert:
                # Use INSERT ... ON CONFLICT for upsert
                await conn.executemany(f"""
                    INSERT INTO raw.{table_name} (_source_id, _raw_payload)
                    VALUES ($1, $2)
                    ON CONFLICT (_source_id) DO UPDATE SET
                        _raw_payload = EXCLUDED._raw_payload,
                        _ingested_at = NOW()
                """, records)
            else:
                await conn.executemany(f"""
                    INSERT INTO raw.{table_name} (_source_id, _raw_payload)
                    VALUES ($1, $2)
                """, records)

        return len(records)

    async def load_raw_fda_labels(self, max_records: Optional[int] = None) -> int:
        """Load FDA drug labels to raw layer with checkpointing."""
        source = 'fda_labels'
        config = DATA_SOURCES[source]
        table_name = 'fda_labels_data'

        await self._create_raw_table(table_name)

        # Check for checkpoint
        progress = self.state.sources.get(source, SourceProgress(source=source))
        checkpoint = json.loads(progress.last_checkpoint) if progress.last_checkpoint else {}
        skip = checkpoint.get('skip', 0)
        total_loaded = checkpoint.get('total_loaded', 0)

        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        page_size = config['pagination']['page_size']
        max_skip = config['pagination'].get('max_skip', 25000)
        rate_limit = config.get('rate_limit', 4)
        api_key = os.getenv('OPENFDA_API_KEY', '')

        batch = []

        while not self._shutdown_requested:
            # Check disk space periodically
            ok, _ = self._check_disk_space()
            if not ok:
                await self._update_source_progress(source, status=LoadStatus.PAUSED.value,
                    last_checkpoint=json.dumps({'skip': skip, 'total_loaded': total_loaded}))
                return total_loaded

            if max_records and total_loaded >= max_records:
                break

            if skip >= max_skip:
                logger.warning(f"Reached OpenFDA skip limit ({max_skip})")
                break

            url = f"{config['base_url']}?limit={page_size}&skip={skip}"
            if api_key:
                url += f"&api_key={api_key}"

            try:
                async def fetch_page():
                    async with self.session.get(url) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 429:
                            raise aiohttp.ClientError("Rate limited")
                        else:
                            raise aiohttp.ClientError(f"HTTP {resp.status}")

                data = await retry_with_backoff(fetch_page)
                results = data.get('results', [])

                if not results:
                    break

                for record in results:
                    source_id = record.get('id') or record.get('set_id')
                    batch.append((source_id, json.dumps(record)))
                    total_loaded += 1

                    if len(batch) >= LoadConfig.BATCH_SIZE:
                        await self._batch_insert_raw(table_name, batch)
                        batch = []

                # Checkpoint periodically
                if total_loaded % LoadConfig.CHECKPOINT_INTERVAL == 0:
                    await self._update_source_progress(
                        source,
                        raw_records=total_loaded,
                        last_checkpoint=json.dumps({'skip': skip + page_size, 'total_loaded': total_loaded})
                    )
                    logger.info(f"FDA Labels: {total_loaded:,} records (checkpoint at skip={skip})")

                skip += page_size
                await asyncio.sleep(1 / rate_limit)

            except Exception as e:
                logger.error(f"FDA Labels error at skip={skip}: {e}")
                progress.errors.append(f"{utc_now_str()}: {str(e)}")
                await self._update_source_progress(
                    source,
                    errors=progress.errors,
                    last_checkpoint=json.dumps({'skip': skip, 'total_loaded': total_loaded})
                )
                break

        # Insert remaining batch
        if batch:
            await self._batch_insert_raw(table_name, batch)

        final_status = LoadStatus.PAUSED.value if self._shutdown_requested else LoadStatus.COMPLETE.value
        await self._update_source_progress(
            source,
            status=final_status,
            raw_records=total_loaded,
            completed_at=utc_now_str() if not self._shutdown_requested else None,
            last_checkpoint=json.dumps({'skip': skip, 'total_loaded': total_loaded})
        )

        logger.info(f"FDA Labels: completed with {total_loaded:,} records")
        return total_loaded

    async def load_raw_clinicaltrials(self, max_records: Optional[int] = None) -> int:
        """Load ClinicalTrials.gov studies with checkpointing."""
        source = 'clinicaltrials'
        config = DATA_SOURCES[source]
        table_name = 'clinicaltrials_data'

        await self._create_raw_table(table_name, unique_source_id=True)

        # Check for checkpoint
        progress = self.state.sources.get(source, SourceProgress(source=source))
        checkpoint = json.loads(progress.last_checkpoint) if progress.last_checkpoint else {}
        page_token = checkpoint.get('page_token')
        total_loaded = checkpoint.get('total_loaded', 0)

        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        page_size = config['pagination']['page_size']
        rate_limit = config.get('rate_limit', 3)
        batch = []

        while not self._shutdown_requested:
            ok, _ = self._check_disk_space()
            if not ok:
                await self._update_source_progress(source, status=LoadStatus.PAUSED.value,
                    last_checkpoint=json.dumps({'page_token': page_token, 'total_loaded': total_loaded}))
                return total_loaded

            if max_records and total_loaded >= max_records:
                break

            params = {'format': 'json', 'pageSize': page_size, 'countTotal': 'true'}
            if page_token:
                params['pageToken'] = page_token

            try:
                async def fetch_page():
                    async with self.session.get(config['base_url'], params=params) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        raise aiohttp.ClientError(f"HTTP {resp.status}")

                data = await retry_with_backoff(fetch_page)
                studies = data.get('studies', [])

                if not studies:
                    break

                for study in studies:
                    nct_id = study.get('protocolSection', {}).get('identificationModule', {}).get('nctId')
                    if nct_id:
                        batch.append((nct_id, json.dumps(study)))
                        total_loaded += 1

                        if len(batch) >= LoadConfig.BATCH_SIZE:
                            await self._batch_insert_raw(table_name, batch, upsert=True)
                            batch = []

                page_token = data.get('nextPageToken')

                if total_loaded % LoadConfig.CHECKPOINT_INTERVAL == 0:
                    await self._update_source_progress(
                        source,
                        raw_records=total_loaded,
                        last_checkpoint=json.dumps({'page_token': page_token, 'total_loaded': total_loaded})
                    )
                    logger.info(f"ClinicalTrials: {total_loaded:,} records")

                if not page_token:
                    break

                await asyncio.sleep(1 / rate_limit)

            except Exception as e:
                logger.error(f"ClinicalTrials error: {e}")
                progress.errors.append(f"{utc_now_str()}: {str(e)}")
                await self._update_source_progress(
                    source,
                    errors=progress.errors,
                    last_checkpoint=json.dumps({'page_token': page_token, 'total_loaded': total_loaded})
                )
                break

        if batch:
            await self._batch_insert_raw(table_name, batch, upsert=True)

        final_status = LoadStatus.PAUSED.value if self._shutdown_requested else LoadStatus.COMPLETE.value
        await self._update_source_progress(
            source,
            status=final_status,
            raw_records=total_loaded,
            completed_at=utc_now_str() if not self._shutdown_requested else None
        )

        logger.info(f"ClinicalTrials: completed with {total_loaded:,} records")
        return total_loaded

    async def load_raw_chembl(self, max_records: Optional[int] = None) -> int:
        """Load ChEMBL molecules with checkpointing."""
        source = 'chembl_molecules'
        config = DATA_SOURCES[source]
        table_name = 'chembl_molecules_data'

        await self._create_raw_table(table_name, unique_source_id=True)

        progress = self.state.sources.get(source, SourceProgress(source=source))
        checkpoint = json.loads(progress.last_checkpoint) if progress.last_checkpoint else {}
        offset = checkpoint.get('offset', 0)
        total_loaded = checkpoint.get('total_loaded', 0)

        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        page_size = config['pagination']['page_size']
        rate_limit = config.get('rate_limit', 5)
        batch = []

        while not self._shutdown_requested:
            ok, _ = self._check_disk_space()
            if not ok:
                await self._update_source_progress(source, status=LoadStatus.PAUSED.value,
                    last_checkpoint=json.dumps({'offset': offset, 'total_loaded': total_loaded}))
                return total_loaded

            if max_records and total_loaded >= max_records:
                break

            url = f"{config['base_url']}?limit={page_size}&offset={offset}"

            try:
                async def fetch_page():
                    async with self.session.get(url) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        raise aiohttp.ClientError(f"HTTP {resp.status}")

                data = await retry_with_backoff(fetch_page)
                molecules = data.get('molecules', [])

                if not molecules:
                    break

                for mol in molecules:
                    chembl_id = mol.get('molecule_chembl_id')
                    if chembl_id:
                        batch.append((chembl_id, json.dumps(mol)))
                        total_loaded += 1

                        if len(batch) >= LoadConfig.BATCH_SIZE:
                            await self._batch_insert_raw(table_name, batch, upsert=True)
                            batch = []

                offset += page_size

                if total_loaded % LoadConfig.CHECKPOINT_INTERVAL == 0:
                    await self._update_source_progress(
                        source,
                        raw_records=total_loaded,
                        last_checkpoint=json.dumps({'offset': offset, 'total_loaded': total_loaded})
                    )
                    logger.info(f"ChEMBL: {total_loaded:,} records (offset={offset})")

                await asyncio.sleep(1 / rate_limit)

            except Exception as e:
                logger.error(f"ChEMBL error at offset={offset}: {e}")
                progress.errors.append(f"{utc_now_str()}: {str(e)}")
                await self._update_source_progress(
                    source,
                    errors=progress.errors,
                    last_checkpoint=json.dumps({'offset': offset, 'total_loaded': total_loaded})
                )
                break

        if batch:
            await self._batch_insert_raw(table_name, batch, upsert=True)

        final_status = LoadStatus.PAUSED.value if self._shutdown_requested else LoadStatus.COMPLETE.value
        await self._update_source_progress(
            source,
            status=final_status,
            raw_records=total_loaded,
            completed_at=utc_now_str() if not self._shutdown_requested else None
        )

        logger.info(f"ChEMBL: completed with {total_loaded:,} records")
        return total_loaded

    async def load_raw_ema(self) -> int:
        """Load EMA authorized medicines."""
        source = 'ema_medicines'
        config = DATA_SOURCES[source]
        table_name = 'ema_medicines_data'
        total_loaded = 0

        await self._create_raw_table(table_name)
        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        try:
            async def fetch_file():
                async with self.session.get(config['base_url']) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    raise aiohttp.ClientError(f"HTTP {resp.status}")

            content = await retry_with_backoff(fetch_file)

            import io
            try:
                import pandas as pd
                df = pd.read_excel(io.BytesIO(content))
                batch = []

                for idx, row in df.iterrows():
                    record = row.to_dict()
                    record = {k: (None if pd.isna(v) else v) for k, v in record.items()}
                    source_id = str(record.get('Medicine name', f'ema_{idx}'))
                    batch.append((source_id, json.dumps(record, default=str)))
                    total_loaded += 1

                    if len(batch) >= LoadConfig.BATCH_SIZE:
                        await self._batch_insert_raw(table_name, batch)
                        batch = []

                if batch:
                    await self._batch_insert_raw(table_name, batch)

                logger.info(f"EMA: loaded {total_loaded:,} records")

            except ImportError:
                logger.error("pandas/openpyxl required for EMA Excel parsing")

        except Exception as e:
            logger.error(f"EMA fetch error: {e}")
            progress = self.state.sources.get(source, SourceProgress(source=source))
            progress.errors.append(f"{utc_now_str()}: {str(e)}")

        await self._update_source_progress(
            source,
            status=LoadStatus.COMPLETE.value,
            raw_records=total_loaded,
            completed_at=utc_now_str()
        )

        return total_loaded

    async def load_raw_orange_book(self) -> int:
        """Load FDA Orange Book."""
        source = 'fda_orange_book'
        config = DATA_SOURCES[source]
        table_name = 'orange_book_data'
        total_loaded = 0

        await self._create_raw_table(table_name)
        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        try:
            async def fetch_file():
                async with self.session.get(config['base_url']) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    raise aiohttp.ClientError(f"HTTP {resp.status}")

            content = await retry_with_backoff(fetch_file)
            lines = content.strip().split('\n')

            if lines:
                headers = lines[0].split('~')
                batch = []

                for line in lines[1:]:
                    values = line.split('~')
                    record = dict(zip(headers, values))
                    source_id = str(record.get('Appl_No', f'ob_{total_loaded}'))
                    batch.append((source_id, json.dumps(record)))
                    total_loaded += 1

                    if len(batch) >= LoadConfig.BATCH_SIZE:
                        await self._batch_insert_raw(table_name, batch)
                        batch = []

                if batch:
                    await self._batch_insert_raw(table_name, batch)

                logger.info(f"Orange Book: loaded {total_loaded:,} records")

        except Exception as e:
            logger.error(f"Orange Book fetch error: {e}")

        await self._update_source_progress(
            source,
            status=LoadStatus.COMPLETE.value,
            raw_records=total_loaded,
            completed_at=utc_now_str()
        )

        return total_loaded

    async def load_raw_uniprot(self, max_records: Optional[int] = 50000) -> int:
        """Load UniProt drug targets with checkpointing."""
        source = 'uniprot_targets'
        config = DATA_SOURCES[source]
        table_name = 'uniprot_targets_data'

        await self._create_raw_table(table_name, unique_source_id=True)

        progress = self.state.sources.get(source, SourceProgress(source=source))
        checkpoint = json.loads(progress.last_checkpoint) if progress.last_checkpoint else {}
        url = checkpoint.get('next_url') or f"{config['base_url']}?query=(cc_interaction_type:drug)&format=json&size=500"
        total_loaded = checkpoint.get('total_loaded', 0)

        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        batch = []

        while url and not self._shutdown_requested:
            ok, _ = self._check_disk_space()
            if not ok:
                await self._update_source_progress(source, status=LoadStatus.PAUSED.value,
                    last_checkpoint=json.dumps({'next_url': url, 'total_loaded': total_loaded}))
                return total_loaded

            if max_records and total_loaded >= max_records:
                break

            try:
                async def fetch_page():
                    async with self.session.get(url) as resp:
                        if resp.status == 200:
                            return await resp.json(), resp.headers.get('Link', '')
                        raise aiohttp.ClientError(f"HTTP {resp.status}")

                data, link_header = await retry_with_backoff(fetch_page)
                results = data.get('results', [])

                if not results:
                    break

                for entry in results:
                    accession = entry.get('primaryAccession')
                    if accession:
                        batch.append((accession, json.dumps(entry)))
                        total_loaded += 1

                        if len(batch) >= LoadConfig.BATCH_SIZE:
                            await self._batch_insert_raw(table_name, batch, upsert=True)
                            batch = []

                # Get next page URL
                url = None
                for link in link_header.split(','):
                    if 'rel="next"' in link:
                        url = link.split(';')[0].strip('<> ')
                        break

                if total_loaded % LoadConfig.CHECKPOINT_INTERVAL == 0:
                    await self._update_source_progress(
                        source,
                        raw_records=total_loaded,
                        last_checkpoint=json.dumps({'next_url': url, 'total_loaded': total_loaded})
                    )
                    logger.info(f"UniProt: {total_loaded:,} records")

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"UniProt error: {e}")
                progress.errors.append(f"{utc_now_str()}: {str(e)}")
                await self._update_source_progress(
                    source,
                    errors=progress.errors,
                    last_checkpoint=json.dumps({'next_url': url, 'total_loaded': total_loaded})
                )
                break

        if batch:
            await self._batch_insert_raw(table_name, batch, upsert=True)

        final_status = LoadStatus.PAUSED.value if self._shutdown_requested else LoadStatus.COMPLETE.value
        await self._update_source_progress(
            source,
            status=final_status,
            raw_records=total_loaded,
            completed_at=utc_now_str() if not self._shutdown_requested else None
        )

        logger.info(f"UniProt: completed with {total_loaded:,} records")
        return total_loaded

    async def load_raw_fda_faers(self, max_records: Optional[int] = None) -> int:
        """
        Load FDA FAERS adverse events using weekly date batches.

        FAERS has 20M+ records but OpenFDA API limits skip to 25k.
        Strategy: Query week-by-week using receivedate ranges to partition data.
        Each week typically has <25k records, allowing full pagination.
        """
        source = 'fda_faers'
        config = DATA_SOURCES[source]
        table_name = 'fda_faers_data'

        await self._create_raw_table(table_name, unique_source_id=True)

        # Check for checkpoint
        progress = self.state.sources.get(source, SourceProgress(source=source))
        checkpoint = json.loads(progress.last_checkpoint) if progress.last_checkpoint else {}

        # FAERS data starts around 2004, but most useful data is recent
        # Default: start from 2012-01-01 for comprehensive coverage
        from datetime import date, timedelta

        start_date_str = checkpoint.get('current_week_start', '2012-01-01')
        current_week_start = date.fromisoformat(start_date_str)
        week_skip = checkpoint.get('week_skip', 0)
        total_loaded = checkpoint.get('total_loaded', 0)

        today = date.today()

        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        page_size = config['pagination']['page_size']
        max_skip = config['pagination'].get('max_skip', 25000)
        rate_limit = config.get('rate_limit', 4)
        api_key = os.getenv('OPENFDA_API_KEY', '')

        batch = []
        weeks_processed = 0

        while current_week_start < today and not self._shutdown_requested:
            # Check disk space
            ok, _ = self._check_disk_space()
            if not ok:
                await self._update_source_progress(source, status=LoadStatus.PAUSED.value,
                    last_checkpoint=json.dumps({
                        'current_week_start': current_week_start.isoformat(),
                        'week_skip': week_skip,
                        'total_loaded': total_loaded
                    }))
                return total_loaded

            if max_records and total_loaded >= max_records:
                break

            # Calculate week end (7 days from start)
            week_end = current_week_start + timedelta(days=6)

            # Build date range query
            # Format: receivedate:[20120101+TO+20120107]
            date_start = current_week_start.strftime('%Y%m%d')
            date_end = week_end.strftime('%Y%m%d')
            search_query = f"receivedate:[{date_start}+TO+{date_end}]"

            # Paginate within this week
            skip = week_skip
            week_records = 0

            while skip < max_skip and not self._shutdown_requested:
                if max_records and total_loaded >= max_records:
                    break

                url = f"{config['base_url']}?search={search_query}&limit={page_size}&skip={skip}"
                if api_key:
                    url += f"&api_key={api_key}"

                try:
                    async def fetch_page():
                        async with self.session.get(url) as resp:
                            if resp.status == 200:
                                return await resp.json()
                            elif resp.status == 404:
                                # No results for this query - not an error
                                return {'results': []}
                            elif resp.status == 429:
                                raise aiohttp.ClientError("Rate limited")
                            else:
                                raise aiohttp.ClientError(f"HTTP {resp.status}")

                    data = await retry_with_backoff(fetch_page)
                    results = data.get('results', [])

                    if not results:
                        # No more records for this week
                        break

                    for record in results:
                        # Create unique ID from safetyreportid + version
                        safety_id = record.get('safetyreportid', '')
                        version = record.get('safetyreportversion', '1')
                        source_id = f"{safety_id}_v{version}"

                        batch.append((source_id, json.dumps(record)))
                        total_loaded += 1
                        week_records += 1

                        if len(batch) >= LoadConfig.BATCH_SIZE:
                            await self._batch_insert_raw(table_name, batch, upsert=True)
                            batch = []

                    skip += page_size

                    # Checkpoint every interval
                    if total_loaded % LoadConfig.CHECKPOINT_INTERVAL == 0:
                        await self._update_source_progress(
                            source,
                            raw_records=total_loaded,
                            last_checkpoint=json.dumps({
                                'current_week_start': current_week_start.isoformat(),
                                'week_skip': skip,
                                'total_loaded': total_loaded
                            })
                        )
                        logger.info(f"FAERS: {total_loaded:,} records (week of {current_week_start})")

                    await asyncio.sleep(1 / rate_limit)

                except Exception as e:
                    logger.error(f"FAERS error for week {current_week_start}: {e}")
                    progress.errors.append(f"{utc_now_str()}: Week {current_week_start}: {str(e)}")
                    await self._update_source_progress(
                        source,
                        errors=progress.errors,
                        last_checkpoint=json.dumps({
                            'current_week_start': current_week_start.isoformat(),
                            'week_skip': skip,
                            'total_loaded': total_loaded
                        })
                    )
                    # Continue to next week instead of stopping completely
                    break

            # Move to next week
            current_week_start = current_week_start + timedelta(days=7)
            week_skip = 0  # Reset skip for new week
            weeks_processed += 1

            # Log progress every 10 weeks
            if weeks_processed % 10 == 0:
                logger.info(f"FAERS: Processed {weeks_processed} weeks, {total_loaded:,} total records")

        # Insert remaining batch
        if batch:
            await self._batch_insert_raw(table_name, batch, upsert=True)

        final_status = LoadStatus.PAUSED.value if self._shutdown_requested else LoadStatus.COMPLETE.value
        await self._update_source_progress(
            source,
            status=final_status,
            raw_records=total_loaded,
            completed_at=utc_now_str() if not self._shutdown_requested else None,
            last_checkpoint=json.dumps({
                'current_week_start': current_week_start.isoformat(),
                'week_skip': 0,
                'total_loaded': total_loaded
            })
        )

        logger.info(f"FAERS: completed with {total_loaded:,} records ({weeks_processed} weeks processed)")
        return total_loaded

    async def load_raw_sider(self) -> int:
        """Load SIDER side effects data from gzipped TSV."""
        source = 'sider'
        config = DATA_SOURCES[source]
        table_name = 'sider_data'
        total_loaded = 0

        await self._create_raw_table(table_name)
        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        try:
            import gzip

            async def fetch_file():
                async with self.session.get(config['base_url']) as resp:
                    if resp.status == 200:
                        return await resp.read()
                    raise aiohttp.ClientError(f"HTTP {resp.status}")

            compressed_data = await retry_with_backoff(fetch_file)
            content = gzip.decompress(compressed_data).decode('utf-8')
            lines = content.strip().split('\n')

            # SIDER TSV format: compound_id, side_effect_id, side_effect_name, etc.
            # No header - known columns
            headers = ['stitch_compound_id_flat', 'stitch_compound_id_stereo', 'umls_cui_label',
                      'meddra_type', 'umls_cui_meddra', 'side_effect_name']

            batch = []
            for line in lines:
                values = line.split('\t')
                if len(values) >= len(headers):
                    record = dict(zip(headers, values[:len(headers)]))
                    source_id = f"{record.get('stitch_compound_id_stereo', '')}_{record.get('umls_cui_meddra', '')}"
                    batch.append((source_id, json.dumps(record)))
                    total_loaded += 1

                    if len(batch) >= LoadConfig.BATCH_SIZE:
                        await self._batch_insert_raw(table_name, batch)
                        batch = []

            if batch:
                await self._batch_insert_raw(table_name, batch)

            logger.info(f"SIDER: loaded {total_loaded:,} records")

        except Exception as e:
            logger.error(f"SIDER fetch error: {e}")
            progress = self.state.sources.get(source, SourceProgress(source=source))
            progress.errors.append(f"{utc_now_str()}: {str(e)}")

        await self._update_source_progress(
            source,
            status=LoadStatus.COMPLETE.value,
            raw_records=total_loaded,
            completed_at=utc_now_str()
        )

        return total_loaded

    async def load_raw_bindingdb(self, bindingdb_file: Optional[str] = None, max_records: Optional[int] = None) -> int:
        """
        Load BindingDB binding affinities from local ZIP file.

        BindingDB provides TSV data in a ZIP archive (~2.5GB uncompressed).
        Contains ~3M binding affinity records.

        Download from: https://www.bindingdb.org/rwd/bind/chemsearch/marvin/SDFdownload.jsp?all_download=yes
        Set BINDINGDB_FILE env var or pass bindingdb_file parameter.
        """
        source = 'bindingdb'
        table_name = 'bindingdb_data'
        total_loaded = 0

        # Check for BindingDB file
        bindingdb_path = bindingdb_file or os.getenv('BINDINGDB_FILE')
        if not bindingdb_path:
            logger.warning("BindingDB: BINDINGDB_FILE not set.")
            logger.warning("BindingDB: Download from https://www.bindingdb.org/rwd/bind/chemsearch/marvin/SDFdownload.jsp?all_download=yes")
            logger.warning("BindingDB: Set BINDINGDB_FILE=/path/to/BindingDB_All.tsv.zip")
            return 0

        if not os.path.exists(bindingdb_path):
            logger.error(f"BindingDB: File not found: {bindingdb_path}")
            return 0

        await self._create_raw_table(table_name, unique_source_id=True)

        # Check for checkpoint
        progress = self.state.sources.get(source, SourceProgress(source=source))
        checkpoint = json.loads(progress.last_checkpoint) if progress.last_checkpoint else {}
        start_line = checkpoint.get('start_line', 0)
        total_loaded = checkpoint.get('total_loaded', 0)

        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        try:
            import zipfile

            logger.info(f"BindingDB: Loading from {bindingdb_path}")

            # Open local ZIP file
            with zipfile.ZipFile(bindingdb_path, 'r') as zf:
                # Find the TSV file inside
                tsv_files = [f for f in zf.namelist() if f.endswith('.tsv')]
                if not tsv_files:
                    raise ValueError("No TSV file found in BindingDB ZIP")

                tsv_filename = tsv_files[0]
                logger.info(f"BindingDB: Extracting {tsv_filename}")

                with zf.open(tsv_filename) as tsv_file:
                    # Read as text
                    content = io.TextIOWrapper(tsv_file, encoding='utf-8', errors='replace')
                    lines = content.readlines()

                    if not lines:
                        raise ValueError("Empty TSV file")

                    # First line is header
                    headers = lines[0].strip().split('\t')
                    logger.info(f"BindingDB: {len(lines)-1} data rows, {len(headers)} columns")

                    batch = []
                    line_num = 0

                    for line in lines[1:]:
                        line_num += 1

                        # Skip already processed lines (resume)
                        if line_num <= start_line:
                            continue

                        if self._shutdown_requested:
                            break

                        # Check disk space periodically
                        if line_num % 100000 == 0:
                            ok, _ = self._check_disk_space()
                            if not ok:
                                await self._update_source_progress(source, status=LoadStatus.PAUSED.value,
                                    last_checkpoint=json.dumps({'start_line': line_num, 'total_loaded': total_loaded}))
                                return total_loaded

                        if max_records and total_loaded >= max_records:
                            break

                        values = line.strip().split('\t')
                        if len(values) >= 10:  # Ensure minimum columns
                            record = dict(zip(headers[:len(values)], values))
                            # Create unique ID from ligand + target
                            ligand_id = record.get('Ligand InChI Key', '') or record.get('PubChem CID', f'row_{line_num}')
                            target_id = record.get('Target Name', '') or record.get('UniProt (SwissProt) Primary ID of Target Chain', '')
                            source_id = f"{ligand_id}_{hash(target_id) % 10**8}"

                            batch.append((source_id, json.dumps(record)))
                            total_loaded += 1

                            if len(batch) >= LoadConfig.BATCH_SIZE:
                                await self._batch_insert_raw(table_name, batch, upsert=True)
                                batch = []

                        # Checkpoint periodically
                        if total_loaded % LoadConfig.CHECKPOINT_INTERVAL == 0 and total_loaded > 0:
                            await self._update_source_progress(
                                source,
                                raw_records=total_loaded,
                                last_checkpoint=json.dumps({'start_line': line_num, 'total_loaded': total_loaded})
                            )
                            logger.info(f"BindingDB: {total_loaded:,} records loaded")

                    if batch:
                        await self._batch_insert_raw(table_name, batch, upsert=True)

            logger.info(f"BindingDB: completed with {total_loaded:,} records")

        except Exception as e:
            logger.error(f"BindingDB error: {e}")
            import traceback
            traceback.print_exc()
            progress = self.state.sources.get(source, SourceProgress(source=source))
            progress.errors.append(f"{utc_now_str()}: {str(e)}")

        final_status = LoadStatus.PAUSED.value if self._shutdown_requested else LoadStatus.COMPLETE.value
        await self._update_source_progress(
            source,
            status=final_status,
            raw_records=total_loaded,
            completed_at=utc_now_str() if not self._shutdown_requested else None
        )

        return total_loaded

    async def load_raw_drugbank(self, drugbank_file: Optional[str] = None) -> int:
        """
        Load DrugBank from local XML file (requires license).

        DrugBank requires a license. Download from https://go.drugbank.com/releases
        Set DRUGBANK_FILE env var or pass drugbank_file parameter.
        Expected file: drugbank_all_full_database.xml.zip
        """
        source = 'drugbank'
        table_name = 'drugbank_data'
        total_loaded = 0

        # Check for DrugBank file
        drugbank_path = drugbank_file or os.getenv('DRUGBANK_FILE')
        if not drugbank_path:
            logger.warning("DrugBank: DRUGBANK_FILE not set. Download from https://go.drugbank.com/releases")
            logger.warning("DrugBank: Set DRUGBANK_FILE=/path/to/drugbank_all_full_database.xml.zip")
            return 0

        if not os.path.exists(drugbank_path):
            logger.error(f"DrugBank: File not found: {drugbank_path}")
            return 0

        await self._create_raw_table(table_name, unique_source_id=True)
        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        try:
            import zipfile
            import xml.etree.ElementTree as ET

            logger.info(f"DrugBank: Loading from {drugbank_path}")

            # Open ZIP and parse XML
            with zipfile.ZipFile(drugbank_path, 'r') as zf:
                xml_files = [f for f in zf.namelist() if f.endswith('.xml')]
                if not xml_files:
                    raise ValueError("No XML file found in DrugBank ZIP")

                xml_filename = xml_files[0]
                logger.info(f"DrugBank: Parsing {xml_filename}")

                with zf.open(xml_filename) as xml_file:
                    # Parse incrementally for memory efficiency
                    batch = []
                    ns = {'db': 'http://www.drugbank.ca'}

                    for event, elem in ET.iterparse(xml_file, events=['end']):
                        if elem.tag == '{http://www.drugbank.ca}drug':
                            # Extract key fields
                            drugbank_id = None
                            for db_id in elem.findall('.//db:drugbank-id', ns):
                                if db_id.get('primary') == 'true':
                                    drugbank_id = db_id.text
                                    break
                            if not drugbank_id:
                                db_ids = elem.findall('.//db:drugbank-id', ns)
                                if db_ids:
                                    drugbank_id = db_ids[0].text

                            if drugbank_id:
                                # Build record from key fields
                                record = {
                                    'drugbank_id': drugbank_id,
                                    'name': elem.findtext('.//db:name', '', ns),
                                    'type': elem.get('type', ''),
                                    'description': elem.findtext('.//db:description', '', ns)[:2000] if elem.findtext('.//db:description', '', ns) else '',
                                    'cas_number': elem.findtext('.//db:cas-number', '', ns),
                                    'unii': elem.findtext('.//db:unii', '', ns),
                                    'state': elem.findtext('.//db:state', '', ns),
                                    'indication': elem.findtext('.//db:indication', '', ns)[:2000] if elem.findtext('.//db:indication', '', ns) else '',
                                    'pharmacodynamics': elem.findtext('.//db:pharmacodynamics', '', ns)[:2000] if elem.findtext('.//db:pharmacodynamics', '', ns) else '',
                                    'mechanism_of_action': elem.findtext('.//db:mechanism-of-action', '', ns)[:2000] if elem.findtext('.//db:mechanism-of-action', '', ns) else '',
                                    'groups': [g.text for g in elem.findall('.//db:group', ns)],
                                    'categories': [c.findtext('db:category', '', ns) for c in elem.findall('.//db:category', ns)][:20],
                                }

                                # Get identifiers
                                for prop in elem.findall('.//db:calculated-properties/db:property', ns):
                                    kind = prop.findtext('db:kind', '', ns)
                                    if kind in ['InChIKey', 'InChI', 'SMILES']:
                                        record[kind.lower().replace(' ', '_')] = prop.findtext('db:value', '', ns)

                                batch.append((drugbank_id, json.dumps(record)))
                                total_loaded += 1

                                if len(batch) >= LoadConfig.BATCH_SIZE:
                                    await self._batch_insert_raw(table_name, batch, upsert=True)
                                    batch = []

                                if total_loaded % 1000 == 0:
                                    logger.info(f"DrugBank: {total_loaded:,} drugs loaded")

                            # Clear element to save memory
                            elem.clear()

                    if batch:
                        await self._batch_insert_raw(table_name, batch, upsert=True)

            logger.info(f"DrugBank: completed with {total_loaded:,} drugs")

        except Exception as e:
            logger.error(f"DrugBank error: {e}")
            import traceback
            traceback.print_exc()

        await self._update_source_progress(
            source,
            status=LoadStatus.COMPLETE.value,
            raw_records=total_loaded,
            completed_at=utc_now_str()
        )

        return total_loaded

    async def load_raw_openalex(self, max_records: Optional[int] = 500000) -> int:
        """
        Load OpenAlex publications related to drug discovery/pharmacology.

        Uses cursor-based pagination. Filters for relevant concepts:
        - Medicine, Pharmacology, Drug discovery, Clinical trial
        """
        source = 'openalex'
        config = DATA_SOURCES[source]
        table_name = 'openalex_data'

        await self._create_raw_table(table_name, unique_source_id=True)

        progress = self.state.sources.get(source, SourceProgress(source=source))
        checkpoint = json.loads(progress.last_checkpoint) if progress.last_checkpoint else {}
        cursor = checkpoint.get('cursor', '*')
        total_loaded = checkpoint.get('total_loaded', 0)

        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        rate_limit = config.get('rate_limit', 10)
        batch = []

        # Add email for polite pool (higher rate limit)
        email = os.getenv('OPENALEX_EMAIL', '')
        api_key = os.getenv('OPENALEX_API_KEY', '')

        while cursor and not self._shutdown_requested:
            ok, _ = self._check_disk_space()
            if not ok:
                await self._update_source_progress(source, status=LoadStatus.PAUSED.value,
                    last_checkpoint=json.dumps({'cursor': cursor, 'total_loaded': total_loaded}))
                return total_loaded

            if max_records and total_loaded >= max_records:
                break

            # Build URL
            params = {
                'filter': config['query_params']['filter'],
                'select': config['query_params']['select'],
                'per-page': 200,
                'cursor': cursor,
            }
            if email:
                params['mailto'] = email
            if api_key:
                params['api_key'] = api_key

            try:
                async def fetch_page():
                    async with self.session.get(config['base_url'], params=params) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 429:
                            raise aiohttp.ClientError("Rate limited")
                        raise aiohttp.ClientError(f"HTTP {resp.status}")

                data = await retry_with_backoff(fetch_page)
                results = data.get('results', [])

                if not results:
                    break

                for work in results:
                    openalex_id = work.get('id', '').replace('https://openalex.org/', '')
                    if openalex_id:
                        batch.append((openalex_id, json.dumps(work)))
                        total_loaded += 1

                        if len(batch) >= LoadConfig.BATCH_SIZE:
                            await self._batch_insert_raw(table_name, batch, upsert=True)
                            batch = []

                # Get next cursor
                meta = data.get('meta', {})
                cursor = meta.get('next_cursor')

                if total_loaded % LoadConfig.CHECKPOINT_INTERVAL == 0:
                    await self._update_source_progress(
                        source,
                        raw_records=total_loaded,
                        last_checkpoint=json.dumps({'cursor': cursor, 'total_loaded': total_loaded})
                    )
                    logger.info(f"OpenAlex: {total_loaded:,} publications loaded")

                if not cursor:
                    break

                await asyncio.sleep(1 / rate_limit)

            except Exception as e:
                logger.error(f"OpenAlex error: {e}")
                progress.errors.append(f"{utc_now_str()}: {str(e)}")
                await self._update_source_progress(
                    source,
                    errors=progress.errors,
                    last_checkpoint=json.dumps({'cursor': cursor, 'total_loaded': total_loaded})
                )
                break

        if batch:
            await self._batch_insert_raw(table_name, batch, upsert=True)

        final_status = LoadStatus.PAUSED.value if self._shutdown_requested else LoadStatus.COMPLETE.value
        await self._update_source_progress(
            source,
            status=final_status,
            raw_records=total_loaded,
            completed_at=utc_now_str() if not self._shutdown_requested else None
        )

        logger.info(f"OpenAlex: completed with {total_loaded:,} publications")
        return total_loaded

    async def load_raw_pdb(self, max_records: Optional[int] = None) -> int:
        """
        Load PDB protein structures relevant to drug targets.

        Uses RCSB search API to find protein structures with drug-like ligands.
        """
        source = 'pdb'
        table_name = 'pdb_data'

        await self._create_raw_table(table_name, unique_source_id=True)

        progress = self.state.sources.get(source, SourceProgress(source=source))
        checkpoint = json.loads(progress.last_checkpoint) if progress.last_checkpoint else {}
        start_offset = checkpoint.get('offset', 0)
        total_loaded = checkpoint.get('total_loaded', 0)

        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        # Search for structures with drug-like ligands
        search_url = 'https://search.rcsb.org/rcsbsearch/v2/query'
        data_url = 'https://data.rcsb.org/rest/v1/core/entry'

        # Query for protein structures with ligands
        search_query = {
            'query': {
                'type': 'group',
                'logical_operator': 'and',
                'nodes': [
                    {
                        'type': 'terminal',
                        'service': 'text',
                        'parameters': {
                            'attribute': 'rcsb_entry_info.selected_polymer_entity_types',
                            'operator': 'contains_phrase',
                            'value': 'Protein (only)'
                        }
                    },
                    {
                        'type': 'terminal',
                        'service': 'text',
                        'parameters': {
                            'attribute': 'rcsb_entry_info.nonpolymer_entity_count',
                            'operator': 'greater',
                            'value': 0
                        }
                    }
                ]
            },
            'return_type': 'entry',
            'request_options': {
                'paginate': {
                    'start': start_offset,
                    'rows': 1000
                },
                'results_content_type': ['experimental'],
                'sort': [{'sort_by': 'rcsb_accession_info.initial_release_date', 'direction': 'desc'}]
            }
        }

        batch = []
        offset = start_offset

        while not self._shutdown_requested:
            ok, _ = self._check_disk_space()
            if not ok:
                await self._update_source_progress(source, status=LoadStatus.PAUSED.value,
                    last_checkpoint=json.dumps({'offset': offset, 'total_loaded': total_loaded}))
                return total_loaded

            if max_records and total_loaded >= max_records:
                break

            search_query['request_options']['paginate']['start'] = offset

            try:
                async def fetch_search():
                    async with self.session.post(search_url, json=search_query) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        raise aiohttp.ClientError(f"HTTP {resp.status}")

                results = await retry_with_backoff(fetch_search)
                result_set = results.get('result_set', [])

                if not result_set:
                    break

                # Fetch details for each PDB entry
                for entry in result_set:
                    pdb_id = entry.get('identifier')
                    if not pdb_id:
                        continue

                    # Get full entry data
                    try:
                        async def fetch_entry():
                            async with self.session.get(f"{data_url}/{pdb_id}") as resp:
                                if resp.status == 200:
                                    return await resp.json()
                                return None

                        entry_data = await fetch_entry()
                        if entry_data:
                            batch.append((pdb_id, json.dumps(entry_data)))
                            total_loaded += 1

                            if len(batch) >= LoadConfig.BATCH_SIZE:
                                await self._batch_insert_raw(table_name, batch, upsert=True)
                                batch = []

                    except Exception as e:
                        logger.debug(f"PDB entry {pdb_id} fetch error: {e}")

                    await asyncio.sleep(0.1)  # Rate limit individual fetches

                offset += len(result_set)

                if total_loaded % LoadConfig.CHECKPOINT_INTERVAL == 0:
                    await self._update_source_progress(
                        source,
                        raw_records=total_loaded,
                        last_checkpoint=json.dumps({'offset': offset, 'total_loaded': total_loaded})
                    )
                    logger.info(f"PDB: {total_loaded:,} structures loaded")

                # Check if we've reached the end
                total_count = results.get('total_count', 0)
                if offset >= total_count:
                    break

            except Exception as e:
                logger.error(f"PDB error: {e}")
                progress.errors.append(f"{utc_now_str()}: {str(e)}")
                break

        if batch:
            await self._batch_insert_raw(table_name, batch, upsert=True)

        final_status = LoadStatus.PAUSED.value if self._shutdown_requested else LoadStatus.COMPLETE.value
        await self._update_source_progress(
            source,
            status=final_status,
            raw_records=total_loaded,
            completed_at=utc_now_str() if not self._shutdown_requested else None
        )

        logger.info(f"PDB: completed with {total_loaded:,} structures")
        return total_loaded

    async def load_raw_pubchem(self, max_records: Optional[int] = 100000) -> int:
        """
        Load PubChem compounds that are drug-like or have bioactivity data.

        Uses the PUG REST API with strategic filters for drug-relevant compounds.
        Full PubChem has 119M+ compounds - we filter to drug-like subset.
        """
        source = 'pubchem_bioassay'
        table_name = 'pubchem_compounds_data'
        total_loaded = 0

        await self._create_raw_table(table_name, unique_source_id=True)

        progress = self.state.sources.get(source, SourceProgress(source=source))
        checkpoint = json.loads(progress.last_checkpoint) if progress.last_checkpoint else {}
        list_offset = checkpoint.get('list_offset', 0)
        total_loaded = checkpoint.get('total_loaded', 0)

        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        # Strategy: Get compounds with DrugBank cross-references (these are drug-like)
        # Also can use: /compound/substructure for drug scaffolds
        list_url = 'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/xref/RegistryID/DrugBank/cids/JSON'

        try:
            # First get list of CIDs that have DrugBank references
            logger.info("PubChem: Fetching drug-like compound list...")

            async def fetch_cid_list():
                async with self.session.get(list_url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    raise aiohttp.ClientError(f"HTTP {resp.status}")

            cid_data = await retry_with_backoff(fetch_cid_list)
            cids = cid_data.get('IdentifierList', {}).get('CID', [])

            logger.info(f"PubChem: Found {len(cids):,} drug-like compounds")

            # Limit if max_records specified
            if max_records:
                cids = cids[:max_records]

            # Fetch details in batches
            batch_size = 100  # PubChem allows up to 100 CIDs per request
            batch = []

            for i in range(list_offset, len(cids), batch_size):
                if self._shutdown_requested:
                    break

                ok, _ = self._check_disk_space()
                if not ok:
                    await self._update_source_progress(source, status=LoadStatus.PAUSED.value,
                        last_checkpoint=json.dumps({'list_offset': i, 'total_loaded': total_loaded}))
                    return total_loaded

                cid_batch = cids[i:i+batch_size]
                cid_str = ','.join(str(c) for c in cid_batch)

                # Fetch compound properties
                props_url = f'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid_str}/property/MolecularFormula,MolecularWeight,InChIKey,CanonicalSMILES,IUPACName/JSON'

                try:
                    async def fetch_props():
                        async with self.session.get(props_url) as resp:
                            if resp.status == 200:
                                return await resp.json()
                            return None

                    props_data = await fetch_props()
                    if props_data and 'PropertyTable' in props_data:
                        for compound in props_data['PropertyTable'].get('Properties', []):
                            cid = compound.get('CID')
                            if cid:
                                batch.append((str(cid), json.dumps(compound)))
                                total_loaded += 1

                                if len(batch) >= LoadConfig.BATCH_SIZE:
                                    await self._batch_insert_raw(table_name, batch, upsert=True)
                                    batch = []

                except Exception as e:
                    logger.debug(f"PubChem batch error: {e}")

                if total_loaded % LoadConfig.CHECKPOINT_INTERVAL == 0 and total_loaded > 0:
                    await self._update_source_progress(
                        source,
                        raw_records=total_loaded,
                        last_checkpoint=json.dumps({'list_offset': i, 'total_loaded': total_loaded})
                    )
                    logger.info(f"PubChem: {total_loaded:,} compounds loaded")

                await asyncio.sleep(0.2)  # Rate limit

            if batch:
                await self._batch_insert_raw(table_name, batch, upsert=True)

        except Exception as e:
            logger.error(f"PubChem error: {e}")
            import traceback
            traceback.print_exc()

        final_status = LoadStatus.PAUSED.value if self._shutdown_requested else LoadStatus.COMPLETE.value
        await self._update_source_progress(
            source,
            status=final_status,
            raw_records=total_loaded,
            completed_at=utc_now_str() if not self._shutdown_requested else None
        )

        logger.info(f"PubChem: completed with {total_loaded:,} compounds")
        return total_loaded

    async def load_raw_uspto_patents(self, max_records: Optional[int] = 100000) -> int:
        """
        Load USPTO patents related to pharmaceuticals/drugs.

        Uses PatentsView API with filters for drug-related CPC codes.
        Requires PATENTSVIEW_API_KEY env var.
        """
        source = 'uspto_patents'
        config = DATA_SOURCES[source]
        table_name = 'uspto_patents_data'

        # Check for API key
        api_key = os.getenv('PATENTSVIEW_API_KEY')
        if not api_key:
            logger.warning("USPTO Patents: PATENTSVIEW_API_KEY not set")
            logger.warning("USPTO Patents: Get API key from https://patentsview.org/apis/keyrequest")
            return 0

        await self._create_raw_table(table_name, unique_source_id=True)

        progress = self.state.sources.get(source, SourceProgress(source=source))
        checkpoint = json.loads(progress.last_checkpoint) if progress.last_checkpoint else {}
        offset = checkpoint.get('offset', 0)
        total_loaded = checkpoint.get('total_loaded', 0)

        await self._update_source_progress(source, status=LoadStatus.LOADING_RAW.value, started_at=utc_now_str())

        # CPC codes for pharmaceuticals/drugs:
        # A61K - Preparations for medical, dental, or toilet purposes
        # A61P - Specific therapeutic activity of chemical compounds
        # C07D - Heterocyclic compounds (many drugs)
        # C07K - Peptides
        query = {
            'q': {'_or': [
                {'_begins': {'cpc_subgroup_id': 'A61K'}},
                {'_begins': {'cpc_subgroup_id': 'A61P'}},
                {'_begins': {'cpc_subgroup_id': 'C07D'}},
                {'_begins': {'cpc_subgroup_id': 'C07K'}},
            ]},
            'f': ['patent_number', 'patent_title', 'patent_date', 'patent_abstract',
                  'assignee_organization', 'inventor_first_name', 'inventor_last_name',
                  'cpc_group_id', 'cpc_subgroup_id'],
            'o': {'per_page': 1000},
            's': [{'patent_date': 'desc'}]
        }

        headers = {'X-Api-Key': api_key}
        batch = []

        while not self._shutdown_requested:
            ok, _ = self._check_disk_space()
            if not ok:
                await self._update_source_progress(source, status=LoadStatus.PAUSED.value,
                    last_checkpoint=json.dumps({'offset': offset, 'total_loaded': total_loaded}))
                return total_loaded

            if max_records and total_loaded >= max_records:
                break

            query['o']['page'] = (offset // 1000) + 1

            try:
                async def fetch_page():
                    async with self.session.post(
                        config['base_url'],
                        json=query,
                        headers=headers
                    ) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 429:
                            raise aiohttp.ClientError("Rate limited")
                        raise aiohttp.ClientError(f"HTTP {resp.status}")

                data = await retry_with_backoff(fetch_page)
                patents = data.get('patents', [])

                if not patents:
                    break

                for patent in patents:
                    patent_number = patent.get('patent_number')
                    if patent_number:
                        batch.append((patent_number, json.dumps(patent)))
                        total_loaded += 1

                        if len(batch) >= LoadConfig.BATCH_SIZE:
                            await self._batch_insert_raw(table_name, batch, upsert=True)
                            batch = []

                offset += len(patents)

                if total_loaded % LoadConfig.CHECKPOINT_INTERVAL == 0:
                    await self._update_source_progress(
                        source,
                        raw_records=total_loaded,
                        last_checkpoint=json.dumps({'offset': offset, 'total_loaded': total_loaded})
                    )
                    logger.info(f"USPTO Patents: {total_loaded:,} patents loaded")

                # Check if we've reached the end
                total_count = data.get('total_patent_count', 0)
                if offset >= total_count:
                    break

                # Rate limit: 45 requests per minute
                await asyncio.sleep(60 / 45)

            except Exception as e:
                logger.error(f"USPTO Patents error: {e}")
                progress.errors.append(f"{utc_now_str()}: {str(e)}")
                break

        if batch:
            await self._batch_insert_raw(table_name, batch, upsert=True)

        final_status = LoadStatus.PAUSED.value if self._shutdown_requested else LoadStatus.COMPLETE.value
        await self._update_source_progress(
            source,
            status=final_status,
            raw_records=total_loaded,
            completed_at=utc_now_str() if not self._shutdown_requested else None
        )

        logger.info(f"USPTO Patents: completed with {total_loaded:,} patents")
        return total_loaded

    # =========================================================================
    # Bronze and Silver Processing (using BulletproofTransformer)
    # =========================================================================

    async def _get_transformer(self):
        """Get or create the bulletproof transformer instance."""
        if not hasattr(self, '_transformer'):
            try:
                from .bulletproof_transformer import BulletproofTransformer
                self._transformer = BulletproofTransformer(self.db_pool)
                await self._transformer.initialize()
                logger.info("Initialized BulletproofTransformer")
            except ImportError as e:
                logger.warning(f"BulletproofTransformer not available: {e}")
                # Fall back to dynamic transformer
                try:
                    from .dynamic_transformer import DynamicSourceTransformer
                    self._transformer = DynamicSourceTransformer(self.db_pool)
                    logger.info("Falling back to DynamicSourceTransformer")
                except ImportError:
                    self._transformer = None
        return self._transformer

    async def process_all_bronze(self):
        """Process all Raw tables to Bronze using bulletproof transformer."""
        self.state.current_phase = 'bronze'
        await self._save_state()

        transformer = await self._get_transformer()
        if not transformer:
            logger.warning("No transformer available, skipping bronze processing")
            return

        async with self.db_pool.acquire() as conn:
            raw_tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'raw' AND table_name LIKE '%_data'
                AND table_name NOT IN ('sync_schedules', 'initial_load_state', 'transformation_state', 'transformation_config')
            """)

        for row in raw_tables:
            if self._shutdown_requested:
                break

            table_name = row['table_name']
            source = table_name.replace('_data', '')

            try:
                logger.info(f"Processing Raw→Bronze: {source}")
                await self._update_source_progress(source, status=LoadStatus.LOADING_BRONZE.value)

                result = await transformer.transform_raw_to_bronze(source, resume=True)

                await self._update_source_progress(
                    source,
                    bronze_records=result.records_inserted,
                    status=LoadStatus.LOADING_SILVER.value
                )
                logger.info(f"Bronze complete for {source}: {result.records_inserted:,} records ({result.records_failed} failed)")

                if result.errors:
                    logger.warning(f"  Errors: {result.errors[:3]}...")

            except Exception as e:
                logger.error(f"Bronze transform error for {source}: {e}")
                import traceback
                traceback.print_exc()
                progress = self.state.sources.get(source, SourceProgress(source=source))
                progress.errors.append(f"Bronze: {e}")
                await self._update_source_progress(source, errors=progress.errors, status=LoadStatus.ERROR.value)

    async def process_all_silver(self):
        """Process all Bronze tables to Silver with entity linking."""
        self.state.current_phase = 'silver'
        await self._save_state()

        transformer = await self._get_transformer()
        if not transformer:
            logger.warning("No transformer available, skipping silver processing")
            return

        async with self.db_pool.acquire() as conn:
            bronze_tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'bronze' AND table_type = 'BASE TABLE'
            """)

        for row in bronze_tables:
            if self._shutdown_requested:
                break

            table_name = row['table_name']
            source = table_name.replace('_data', '')

            try:
                logger.info(f"Processing Bronze→Silver: {source}")
                await self._update_source_progress(source, status=LoadStatus.LOADING_SILVER.value)

                result = await transformer.transform_bronze_to_silver(source, resume=True)

                # Use records_linked from bulletproof transformer, fall back to records_inserted
                linked = getattr(result, 'records_linked', 0) or result.records_inserted

                await self._update_source_progress(
                    source,
                    silver_records=linked,
                    linked_records=linked,
                    status=LoadStatus.COMPLETE.value,
                    completed_at=utc_now_str()
                )
                logger.info(f"Silver complete for {source}: {linked:,} records linked ({result.records_failed} failed)")

                if result.errors:
                    logger.warning(f"  Errors: {result.errors[:3]}...")

            except Exception as e:
                logger.error(f"Silver transform error for {source}: {e}")
                import traceback
                traceback.print_exc()
                progress = self.state.sources.get(source, SourceProgress(source=source))
                progress.errors.append(f"Silver: {e}")
                await self._update_source_progress(source, errors=progress.errors, status=LoadStatus.ERROR.value)

    async def run_sqlmesh_transformations(self, environment: str = 'prod') -> bool:
        """
        Run SQLMesh Gold layer transformations.

        HYBRID APPROACH:
        - Raw → Bronze → Silver: Python BulletproofTransformer (dynamic schema detection)
        - Silver → Gold: SQLMesh (declarative SQL analytics)

        SQLMesh creates Gold layer views on top of Python-created Silver tables:
        - gold.molecule_profiles: Comprehensive drug profiles
        - gold.trial_analytics: Clinical trial success rates
        - gold.safety_signals: Adverse event signal detection
        - gold.research_landscape: Publication analytics

        Args:
            environment: SQLMesh environment ('prod' or 'dev')

        Returns:
            True if successful, False otherwise
        """
        import subprocess
        import shlex

        sqlmesh_project_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'sqlmesh_project'
        )

        if not os.path.exists(sqlmesh_project_path):
            logger.error(f"SQLMesh project not found at {sqlmesh_project_path}")
            return False

        logger.info("=" * 70)
        logger.info("RUNNING SQLMESH TRANSFORMATIONS")
        logger.info("=" * 70)
        logger.info(f"Project path: {sqlmesh_project_path}")
        logger.info(f"Environment: {environment}")

        try:
            # Step 1: Run SQLMesh plan (non-interactive)
            logger.info("\n--- Phase 1: Planning SQLMesh changes ---")
            plan_cmd = f"sqlmesh plan --environment {environment} --auto-apply"

            result = subprocess.run(
                shlex.split(plan_cmd),
                cwd=sqlmesh_project_path,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            if result.returncode != 0:
                logger.error(f"SQLMesh plan failed: {result.stderr}")
                # Try to continue anyway - might just be "nothing to do"
                if "Nothing to do" not in result.stdout:
                    logger.warning("Continuing despite plan error...")
            else:
                logger.info(result.stdout)

            # Step 2: Run SQLMesh (executes all models)
            logger.info("\n--- Phase 2: Running SQLMesh models ---")
            run_cmd = f"sqlmesh run --environment {environment}"

            result = subprocess.run(
                shlex.split(run_cmd),
                cwd=sqlmesh_project_path,
                capture_output=True,
                text=True,
                timeout=7200  # 2 hour timeout for large datasets
            )

            if result.returncode != 0:
                logger.error(f"SQLMesh run failed: {result.stderr}")
                return False

            logger.info(result.stdout)

            # Step 3: Run audits
            logger.info("\n--- Phase 3: Running data quality audits ---")
            audit_cmd = "sqlmesh audit"

            result = subprocess.run(
                shlex.split(audit_cmd),
                cwd=sqlmesh_project_path,
                capture_output=True,
                text=True,
                timeout=1800  # 30 min timeout
            )

            if result.returncode != 0:
                logger.warning(f"SQLMesh audit warnings: {result.stderr}")
                # Audits failing is a warning, not a failure

            if result.stdout:
                logger.info(result.stdout)

            logger.info("\n" + "=" * 70)
            logger.info("SQLMESH TRANSFORMATIONS COMPLETE")
            logger.info("=" * 70)

            # Update state to reflect SQLMesh completion
            self.state.current_phase = 'complete'
            await self._save_state()

            return True

        except subprocess.TimeoutExpired:
            logger.error("SQLMesh transformation timed out")
            return False
        except FileNotFoundError:
            logger.error("SQLMesh not found. Install with: pip install sqlmesh")
            return False
        except Exception as e:
            logger.error(f"SQLMesh transformation error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # =========================================================================
    # Reset Functions
    # =========================================================================

    async def reset_all(self):
        """Complete reset of all data and state."""
        logger.warning("RESETTING ALL DATA AND STATE!")

        async with self.db_pool.acquire() as conn:
            # Clear state table
            await conn.execute("TRUNCATE raw.initial_load_state")

            # Get and truncate all raw tables
            raw_tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'raw' AND table_type = 'BASE TABLE'
                AND table_name NOT IN ('sync_schedules')
            """)
            for row in raw_tables:
                try:
                    await conn.execute(f"TRUNCATE raw.{row['table_name']} RESTART IDENTITY CASCADE")
                    logger.info(f"Truncated raw.{row['table_name']}")
                except Exception as e:
                    logger.warning(f"Could not truncate raw.{row['table_name']}: {e}")

            # Truncate bronze tables
            bronze_tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'bronze' AND table_type = 'BASE TABLE'
            """)
            for row in bronze_tables:
                try:
                    await conn.execute(f"TRUNCATE bronze.{row['table_name']} RESTART IDENTITY CASCADE")
                    logger.info(f"Truncated bronze.{row['table_name']}")
                except Exception as e:
                    logger.warning(f"Could not truncate bronze.{row['table_name']}: {e}")

            # Truncate silver tables
            silver_tables = await conn.fetch("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'silver' AND table_type = 'BASE TABLE'
            """)
            for row in silver_tables:
                try:
                    await conn.execute(f"TRUNCATE silver.{row['table_name']} RESTART IDENTITY CASCADE")
                    logger.info(f"Truncated silver.{row['table_name']}")
                except Exception as e:
                    logger.warning(f"Could not truncate silver.{row['table_name']}: {e}")

        logger.info("Reset complete")

    # =========================================================================
    # Status Display
    # =========================================================================

    async def show_status(self):
        """Display current load status."""
        state = await self._load_state()

        if not state:
            print("\nNo active or recent load found.")
            return

        print(f"\n{'='*70}")
        print(f"INITIAL LOAD STATUS - Run ID: {state.run_id}")
        print(f"{'='*70}")
        print(f"Status: {state.status}")
        print(f"Phase: {state.current_phase}")
        print(f"Started: {state.started_at}")
        print(f"Disk Space: {state.disk_space_gb:.1f} GB")
        print("\nSources:")
        print(f"{'-'*70}")

        for source_id, progress in state.sources.items():
            status_icon = {
                'pending': '⏳',
                'loading_raw': '📥',
                'loading_bronze': '🔶',
                'loading_silver': '🔷',
                'complete': '✅',
                'error': '❌',
                'paused': '⏸️',
            }.get(progress.status, '❓')

            print(f"  {status_icon} {source_id}:")
            print(f"      Status: {progress.status}")
            print(f"      Raw: {progress.raw_records:,}")
            print(f"      Bronze: {progress.bronze_records:,}")
            print(f"      Silver: {progress.silver_records:,}")
            if progress.errors:
                print(f"      Errors: {len(progress.errors)}")

    # =========================================================================
    # Main Orchestration
    # =========================================================================

    async def run_full_initial_load(
        self,
        sources: Optional[List[str]] = None,
        max_records_per_source: Optional[int] = None,
        skip_raw: bool = False,
        skip_bronze: bool = False,
        skip_silver: bool = False,
        resume: bool = False,
        use_sqlmesh: bool = False,
        sqlmesh_environment: str = 'prod',
    ):
        """Run full initial load with checkpointing and resume capability.

        Args:
            sources: List of sources to load (None = all)
            max_records_per_source: Limit records per source (for testing)
            skip_raw: Skip raw layer loading
            skip_bronze: Skip bronze layer transformation
            skip_silver: Skip silver layer transformation
            resume: Resume from previous checkpoint
            use_sqlmesh: Use SQLMesh for transformations instead of Python transformer
            sqlmesh_environment: SQLMesh environment ('prod' or 'dev')
        """
        start_time = time.time()

        # Check disk space before starting
        ok, free_gb = self._check_disk_space()
        if not ok:
            logger.error("Insufficient disk space to start load")
            return

        # Initialize or resume state
        await self._ensure_state_table()

        if resume:
            self.state = await self._load_state()
            if self.state:
                self.run_id = self.state.run_id
                logger.info(f"Resuming load run: {self.run_id}")
            else:
                logger.info("No previous run to resume, starting fresh")
                resume = False

        if not self.state:
            self.state = LoadState(
                run_id=self.run_id,
                started_at=utc_now_str(),
                disk_space_gb=free_gb,
            )

        self.state.status = 'running'
        await self._save_state()

        sources_to_load = sources or list(DATA_SOURCES.keys())

        logger.info("=" * 70)
        logger.info("INITIAL LOAD ORCHESTRATOR - Bulletproof Edition")
        logger.info("=" * 70)
        logger.info(f"Run ID: {self.run_id}")
        logger.info(f"Resume mode: {resume}")
        logger.info(f"Sources: {sources_to_load}")
        logger.info(f"Max records per source: {max_records_per_source or 'unlimited'}")
        logger.info(f"Available disk space: {free_gb:.1f} GB")
        logger.info(f"Min required: {LoadConfig.MIN_DISK_SPACE_GB} GB")

        # Phase 1: Register all sources
        logger.info("\n--- Phase 1: Registering data sources ---")
        await self.register_all_sources()

        # Phase 2: Load to Raw
        if not skip_raw:
            self.state.current_phase = 'raw'
            await self._save_state()
            logger.info("\n--- Phase 2: Loading to Raw layer ---")

            raw_loaders = {
                # Core regulatory sources (high priority)
                'fda_labels': self.load_raw_fda_labels,
                'fda_faers': self.load_raw_fda_faers,
                'fda_orange_book': self.load_raw_orange_book,
                'ema_medicines': self.load_raw_ema,
                # Clinical trials
                'clinicaltrials': self.load_raw_clinicaltrials,
                # Chemical/molecular databases
                'chembl_molecules': self.load_raw_chembl,
                'pubchem_bioassay': self.load_raw_pubchem,
                'drugbank': self.load_raw_drugbank,  # Requires DRUGBANK_FILE env var
                'bindingdb': self.load_raw_bindingdb,  # Requires BINDINGDB_FILE env var
                'sider': self.load_raw_sider,
                # Protein/target databases
                'uniprot_targets': self.load_raw_uniprot,
                'pdb': self.load_raw_pdb,
                # Publications & IP
                'openalex': self.load_raw_openalex,
                'uspto_patents': self.load_raw_uspto_patents,  # Requires PATENTSVIEW_API_KEY
            }

            for source in sources_to_load:
                if self._shutdown_requested:
                    logger.warning("Shutdown requested, saving state and exiting...")
                    break

                if source in raw_loaders:
                    # Check if already complete (resume mode)
                    progress = self.state.sources.get(source)
                    if resume and progress and progress.status == LoadStatus.COMPLETE.value:
                        logger.info(f"Skipping {source} (already complete)")
                        continue

                    loader = raw_loaders[source]
                    try:
                        if max_records_per_source:
                            await loader(max_records=max_records_per_source)
                        else:
                            await loader()
                    except Exception as e:
                        logger.error(f"Error loading {source}: {e}")
                        traceback.print_exc()

        # Phase 3 & 4: Bronze & Silver (either via SQLMesh or custom Python transformer)
        if use_sqlmesh:
            # Use SQLMesh for all transformations (Bronze + Silver + Gold)
            if not (skip_bronze and skip_silver) and not self._shutdown_requested:
                logger.info("\n--- Phase 3+4: Running SQLMesh transformations ---")
                success = await self.run_sqlmesh_transformations(environment=sqlmesh_environment)
                if not success:
                    logger.error("SQLMesh transformations failed")
        else:
            # Use custom Python transformer
            # Phase 3: Bronze
            if not skip_bronze and not self._shutdown_requested:
                logger.info("\n--- Phase 3: Processing to Bronze layer ---")
                await self.process_all_bronze()

            # Phase 4: Silver
            if not skip_silver and not self._shutdown_requested:
                logger.info("\n--- Phase 4: Processing to Silver layer ---")
                await self.process_all_silver()

        # Final status
        elapsed = time.time() - start_time
        self.state.status = 'paused' if self._shutdown_requested else 'complete'
        self.state.completed_at = utc_now_str() if not self._shutdown_requested else None
        await self._save_state()

        logger.info("\n" + "=" * 70)
        logger.info("INITIAL LOAD " + ("PAUSED" if self._shutdown_requested else "COMPLETE"))
        logger.info("=" * 70)
        logger.info(f"Duration: {elapsed/60:.1f} minutes")
        logger.info(f"Run ID: {self.run_id}")
        if self._shutdown_requested:
            logger.info("To resume: python -m services.data_platform.initial_load_orchestrator --resume")

        for source, progress in self.state.sources.items():
            logger.info(f"  {source}:")
            logger.info(f"    Status: {progress.status}")
            logger.info(f"    Raw: {progress.raw_records:,}")
            logger.info(f"    Bronze: {progress.bronze_records:,}")
            logger.info(f"    Silver: {progress.silver_records:,}")
            if progress.errors:
                logger.warning(f"    Errors: {len(progress.errors)}")


# =============================================================================
# CLI Entry Point
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(
        description='Initial Load Orchestrator - Bulletproof Edition',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full load of all sources
  python -m services.data_platform.initial_load_orchestrator --all

  # Load specific source
  python -m services.data_platform.initial_load_orchestrator --source clinicaltrials

  # Resume interrupted load
  python -m services.data_platform.initial_load_orchestrator --resume

  # Check status of current/last load
  python -m services.data_platform.initial_load_orchestrator --status

  # Reset everything and start fresh
  python -m services.data_platform.initial_load_orchestrator --reset-all

  # Test with limited records
  python -m services.data_platform.initial_load_orchestrator --all --max-records 1000

  # Use SQLMesh for transformations (recommended)
  python -m services.data_platform.initial_load_orchestrator --all --sqlmesh

  # Raw only, then run SQLMesh separately
  python -m services.data_platform.initial_load_orchestrator --all --layer raw
  python -m services.data_platform.initial_load_orchestrator --sqlmesh-only

Environment Variables:
  DATABASE_URL          Database connection string
  MIN_DISK_SPACE_GB     Minimum disk space to continue (default: 10)
  MAX_RETRIES           Maximum retry attempts (default: 5)
  BATCH_SIZE            Records per batch insert (default: 500)
  OPENFDA_API_KEY       FDA API key for higher rate limits
        """
    )
    parser.add_argument('--all', action='store_true', help='Load all sources')
    parser.add_argument('--source', type=str, help='Load specific source')
    parser.add_argument('--sources', type=str, help='Comma-separated list of sources')
    parser.add_argument('--resume', action='store_true', help='Resume previous interrupted load')
    parser.add_argument('--status', action='store_true', help='Show current load status')
    parser.add_argument('--reset-all', action='store_true', help='Reset ALL data and state')
    parser.add_argument('--check-counts', action='store_true', help='Check external API counts')
    parser.add_argument('--register-only', action='store_true', help='Only register sources')
    parser.add_argument('--layer', choices=['raw', 'bronze', 'silver'], help='Only process specific layer')
    parser.add_argument('--max-records', type=int, help='Max records per source (for testing)')
    parser.add_argument('--run-id', type=str, help='Specify run ID (for resume)')

    # SQLMesh options
    parser.add_argument('--sqlmesh', action='store_true',
                        help='Use SQLMesh for transformations (Bronze/Silver/Gold)')
    parser.add_argument('--sqlmesh-only', action='store_true',
                        help='Only run SQLMesh transformations (skip raw loading)')
    parser.add_argument('--sqlmesh-env', type=str, default='prod',
                        choices=['prod', 'dev'],
                        help='SQLMesh environment (default: prod)')

    args = parser.parse_args()

    # Database connection
    import asyncpg
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5433/edwards_tavr')

    try:
        pool = await asyncpg.create_pool(
            db_url,
            min_size=LoadConfig.DB_POOL_MIN,
            max_size=LoadConfig.DB_POOL_MAX
        )
    except Exception as e:
        logger.error(f"Could not connect to database: {e}")
        logger.error("Make sure the database is running and DATABASE_URL is correct")
        sys.exit(1)

    try:
        async with InitialLoadOrchestrator(pool, run_id=args.run_id) as orchestrator:
            if args.status:
                await orchestrator.show_status()
                return

            if args.reset_all:
                confirm = input("This will DELETE ALL DATA. Type 'yes' to confirm: ")
                if confirm.lower() == 'yes':
                    await orchestrator.reset_all()
                else:
                    print("Aborted")
                return

            if args.check_counts:
                counts = await orchestrator.check_external_counts()
                print("\nExternal API Record Counts:")
                print("-" * 50)
                for source, count in counts.items():
                    print(f"  {source}: {count:,}" if count > 0 else f"  {source}: unknown")
                return

            if args.register_only:
                await orchestrator.register_all_sources()
                return

            sources = None
            if args.source:
                sources = [args.source]
            elif args.sources:
                sources = [s.strip() for s in args.sources.split(',')]
            elif args.all or args.resume:
                sources = None

            # Handle SQLMesh-only mode
            if args.sqlmesh_only:
                logger.info("Running SQLMesh transformations only (no raw loading)")
                success = await orchestrator.run_sqlmesh_transformations(
                    environment=args.sqlmesh_env
                )
                if not success:
                    logger.error("SQLMesh transformations failed")
                    sys.exit(1)
                return

            if not args.all and not args.resume and not args.source and not args.sources:
                parser.print_help()
                print("\nSpecify --all, --source, --sources, --resume, or --sqlmesh-only to start loading")
                return

            skip_raw = args.layer in ['bronze', 'silver']
            skip_bronze = args.layer == 'silver'
            skip_silver = args.layer in ['raw', 'bronze']

            await orchestrator.run_full_initial_load(
                sources=sources,
                max_records_per_source=args.max_records,
                skip_raw=skip_raw,
                skip_bronze=skip_bronze,
                skip_silver=skip_silver,
                resume=args.resume,
                use_sqlmesh=args.sqlmesh,
                sqlmesh_environment=args.sqlmesh_env,
            )
    finally:
        await pool.close()


if __name__ == '__main__':
    asyncio.run(main())
