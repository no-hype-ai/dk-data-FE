"""
Transformation Configuration - Single Source of Truth

All configuration for the medallion architecture stored in database tables.
No hardcoded values - everything is database-driven and dynamically loaded.

Tables:
- ops.transformation_config: Global transformation settings
- raw.source_config: Per-source configuration
- raw.identifier_types: Identifier patterns and priorities
- raw.field_mappings: Field extraction rules per source
- raw.linking_rules: Entity linking configuration

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import json
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes (no hardcoded values - all loaded from DB)
# =============================================================================

@dataclass
class IdentifierTypeConfig:
    """Configuration for an identifier type."""
    type_id: str
    name: str
    regex_pattern: str
    priority: int  # Lower = higher priority for linking
    preferred_source: str
    is_structural: bool = False  # InChI Key, SMILES, etc.
    validation_func: Optional[str] = None  # Python function name for validation

    def matches(self, value: str) -> bool:
        """Check if value matches this identifier pattern."""
        if not value or not self.regex_pattern:
            return False
        try:
            return bool(re.match(self.regex_pattern, str(value).strip()))
        except re.error:
            return False


@dataclass
class SourceConfig:
    """Configuration for a data source."""
    source_id: str
    name: str
    precedence: int  # Lower = more trusted
    tier: str  # daily, weekly, monthly
    api_type: str  # rest, file, local_file

    # Field extraction
    identifier_fields: Dict[str, str] = field(default_factory=dict)  # field_path -> identifier_type
    name_fields: List[str] = field(default_factory=list)  # Fields containing drug names
    date_fields: List[str] = field(default_factory=list)  # Fields containing dates

    # Transformation settings
    flatten_depth: int = 2
    batch_size: int = 500

    # Entity linking
    primary_identifier: Optional[str] = None  # Which identifier to use for linking
    secondary_identifiers: List[str] = field(default_factory=list)


@dataclass
class TransformationSettings:
    """Global transformation settings."""
    # Thresholds
    confidence_threshold: float = 0.8
    quality_threshold: float = 0.3
    fuzzy_match_threshold: float = 0.85

    # Batch sizes
    raw_to_bronze_batch: int = 1000
    bronze_to_silver_batch: int = 500
    silver_to_gold_batch: int = 100

    # Checkpointing
    checkpoint_interval: int = 1000

    # Schema detection
    schema_sample_size: int = 100
    max_flatten_depth: int = 2

    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


# =============================================================================
# Configuration Manager - Loads everything from Database
# =============================================================================

class TransformationConfigManager:
    """
    Manages all transformation configuration from database.

    Single source of truth - no hardcoded values.
    Configuration is cached and refreshed periodically.
    """

    def __init__(self, db_pool):
        self.db_pool = db_pool
        self._settings: Optional[TransformationSettings] = None
        self._identifier_types: Dict[str, IdentifierTypeConfig] = {}
        self._source_configs: Dict[str, SourceConfig] = {}
        self._field_mappings: Dict[str, Dict[str, str]] = {}
        self._last_refresh: Optional[datetime] = None
        self._cache_ttl_seconds = 300  # 5 minutes

    async def initialize(self):
        """Initialize configuration tables if they don't exist."""
        async with self.db_pool.acquire() as conn:
            # Create configuration tables
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS ops.transformation_config (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL,
                    description TEXT,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS raw.identifier_types (
                    type_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    regex_pattern TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 100,
                    preferred_source TEXT,
                    is_structural BOOLEAN DEFAULT FALSE,
                    validation_func TEXT,
                    examples TEXT[],
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS raw.source_config (
                    source_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    precedence INTEGER NOT NULL DEFAULT 100,
                    tier TEXT DEFAULT 'weekly',
                    api_type TEXT DEFAULT 'rest',
                    identifier_fields JSONB DEFAULT '{}',
                    name_fields TEXT[] DEFAULT '{}',
                    date_fields TEXT[] DEFAULT '{}',
                    flatten_depth INTEGER DEFAULT 2,
                    batch_size INTEGER DEFAULT 500,
                    primary_identifier TEXT,
                    secondary_identifiers TEXT[] DEFAULT '{}',
                    transformation_rules JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS raw.field_mappings (
                    id SERIAL PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES raw.source_config(source_id),
                    source_field TEXT NOT NULL,
                    target_field TEXT NOT NULL,
                    target_type TEXT DEFAULT 'TEXT',
                    transformation TEXT,  -- SQL expression or function name
                    is_identifier BOOLEAN DEFAULT FALSE,
                    identifier_type TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(source_id, source_field)
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_field_mappings_source
                ON raw.field_mappings(source_id)
            """)

            # Seed default configuration if empty
            await self._seed_defaults(conn)

    async def _seed_defaults(self, conn):
        """Seed default configuration values."""
        # Check if already seeded
        count = await conn.fetchval("SELECT COUNT(*) FROM mol_raw.identifier_types")
        if count > 0:
            return

        logger.info("Seeding default transformation configuration...")

        # Default transformation settings
        default_settings = {
            'confidence_threshold': 0.8,
            'quality_threshold': 0.3,
            'fuzzy_match_threshold': 0.85,
            'raw_to_bronze_batch': 1000,
            'bronze_to_silver_batch': 500,
            'silver_to_gold_batch': 100,
            'checkpoint_interval': 1000,
            'schema_sample_size': 100,
            'max_flatten_depth': 2,
            'max_retries': 3,
            'retry_delay_seconds': 1.0,
        }

        for key, value in default_settings.items():
            await conn.execute("""
                INSERT INTO ops.transformation_config (key, value, description)
                VALUES ($1, $2, $3)
                ON CONFLICT (key) DO NOTHING
            """, key, json.dumps(value), f"Default {key}")

        # Default identifier types (comprehensive list)
        identifier_types = [
            # Structural identifiers (highest priority for linking)
            ('inchi_key', 'InChI Key', r'^[A-Z]{14}-[A-Z]{10}-[A-Z]$', 1, None, True, ['BSYNRYMUTXBXSQ-UHFFFAOYSA-N']),
            ('inchi', 'InChI', r'^InChI=1S?/', 2, None, True, ['InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)']),
            ('smiles', 'SMILES', r'^[A-Za-z0-9@+\-\[\]()\\\\/#=%$\.]+$', 3, None, True, ['CC(=O)Oc1ccccc1C(=O)O']),

            # Database identifiers (ordered by source quality)
            ('drugbank_id', 'DrugBank ID', r'^DB\d{5}$', 10, 'drugbank', False, ['DB00945']),
            ('chembl_id', 'ChEMBL ID', r'^CHEMBL\d+$', 11, 'chembl', False, ['CHEMBL25']),
            ('rxcui', 'RxNorm CUI', r'^(?!NCT)\d{4,8}$', 12, 'rxnorm', False, ['1191']),
            ('pubchem_cid', 'PubChem CID', r'^\d{1,10}$', 13, 'pubchem', False, ['2244']),
            ('pubchem_sid', 'PubChem SID', r'^\d{1,12}$', 14, 'pubchem', False, ['144206486']),
            ('kegg_id', 'KEGG Drug ID', r'^D\d{5}$', 15, 'kegg', False, ['D00109']),
            ('pharmgkb_id', 'PharmGKB ID', r'^PA\d+$', 16, 'pharmgkb', False, ['PA449015']),
            ('bindingdb_id', 'BindingDB ID', r'^BDBM\d+$', 17, 'bindingdb', False, ['BDBM50000001']),

            # Regulatory identifiers
            ('unii', 'FDA UNII', r'^[A-Z0-9]{10}$', 20, 'fda_labels', False, ['R16CO5Y76E']),
            ('cas_number', 'CAS Number', r'^\d{2,7}-\d{2}-\d$', 21, 'pubchem', False, ['50-78-2']),
            ('ndc_code', 'NDC Code', r'^\d{4,5}-\d{3,4}-\d{1,2}$', 22, 'dailymed', False, ['0069-2587-10']),
            ('atc_code', 'ATC Code', r'^[A-Z]\d{2}[A-Z]{2}\d{2}$', 23, 'who_inn', False, ['N02BE01']),
            ('ema_number', 'EMA Number', r'^EMEA/H/C/\d+$', 24, 'ema', False, ['EMEA/H/C/000471']),

            # Clinical/research identifiers
            ('nct_id', 'ClinicalTrials.gov ID', r'^NCT\d{8}$', 30, 'clinicaltrials', False, ['NCT00000001']),
            ('research_code', 'Research Code', r'^[A-Z]{2,4}[-\s]?\d{2,6}(,\d+)?$', 31, 'who_inn', False, ['CP-690,550']),

            # Protein/structural identifiers
            ('uniprot_id', 'UniProt ID', r'^[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$', 40, 'uniprot', False, ['P00533']),
            ('pdb_id', 'PDB ID', r'^[0-9][A-Z0-9]{3}$', 41, 'pdb', False, ['1ABC']),

            # Other identifiers
            ('stitch_id', 'STITCH ID', r'^CID[ms]?\d+$', 50, 'sider', False, ['CIDs00000001']),
            ('dailymed_set_id', 'DailyMed Set ID', r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 51, 'dailymed', False, ['a1b2c3d4-e5f6-7890-abcd-ef1234567890']),

            # Generic name (lowest priority)
            ('drug_name', 'Drug Name', r'^.{2,200}$', 100, None, False, ['Aspirin']),
        ]

        for type_id, name, pattern, priority, source, is_structural, examples in identifier_types:
            await conn.execute("""
                INSERT INTO mol_raw.identifier_types
                (type_id, name, regex_pattern, priority, preferred_source, is_structural, examples)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (type_id) DO NOTHING
            """, type_id, name, pattern, priority, source, is_structural, examples)

        # Default source configurations
        source_configs = [
            # Tier 1: Curated authoritative sources
            ('drugbank', 'DrugBank', 1, 'weekly', 'local_file',
             {'drugbank-id': 'drugbank_id', 'inchikey': 'inchi_key', 'cas-number': 'cas_number', 'unii': 'unii'},
             ['name', 'generic_name'], ['created', 'updated'], 'drugbank_id'),

            ('chembl', 'ChEMBL', 2, 'weekly', 'rest',
             {'molecule_chembl_id': 'chembl_id', 'molecule_structures.standard_inchi_key': 'inchi_key'},
             ['pref_name'], [], 'chembl_id'),

            # Tier 2: Regulatory sources
            ('fda_labels', 'FDA Drug Labels', 3, 'daily', 'rest',
             {'openfda.unii': 'unii', 'openfda.rxcui': 'rxcui', 'openfda.ndc': 'ndc_code'},
             ['openfda.brand_name', 'openfda.generic_name'], ['effective_time'], 'unii'),

            ('fda_faers', 'FDA FAERS', 4, 'daily', 'rest',
             {'patient.drug.openfda.unii': 'unii'},
             ['patient.drug.medicinalproduct'], ['receivedate'], 'drug_name'),

            ('fda_orange_book', 'FDA Orange Book', 5, 'weekly', 'file',
             {'Appl_No': 'nda_number'},
             ['Ingredient', 'Trade_Name'], ['Approval_Date'], 'drug_name'),

            ('ema', 'European Medicines Agency', 6, 'weekly', 'file',
             {},
             ['Active substance', 'Medicine name'], ['Marketing authorisation date'], 'drug_name'),

            # Tier 3: Large compound databases
            ('pubchem', 'PubChem', 7, 'monthly', 'rest',
             {'CID': 'pubchem_cid', 'InChIKey': 'inchi_key'},
             ['IUPACName'], [], 'pubchem_cid'),

            ('bindingdb', 'BindingDB', 8, 'monthly', 'local_file',
             {'Ligand InChI Key': 'inchi_key', 'PubChem CID': 'pubchem_cid', 'ChEMBL ID of Ligand': 'chembl_id', 'DrugBank ID of Ligand': 'drugbank_id'},
             ['Ligand Name'], [], 'inchi_key'),

            ('sider', 'SIDER', 9, 'monthly', 'file',
             {'stitch_compound_id_stereo': 'stitch_id'},
             [], [], 'stitch_id'),

            # Tier 4: Clinical & Publications
            ('clinicaltrials', 'ClinicalTrials.gov', 10, 'daily', 'rest',
             {'protocolSection.identificationModule.nctId': 'nct_id'},
             ['protocolSection.armsInterventionsModule.interventions.interventionName'],
             ['protocolSection.statusModule.startDateStruct.date'], 'nct_id'),

            ('openalex', 'OpenAlex', 11, 'weekly', 'rest',
             {'id': 'openalex_id'},
             ['title'], ['publication_year'], 'openalex_id'),

            # Tier 5: Protein/Target databases
            ('uniprot', 'UniProt', 12, 'monthly', 'rest',
             {'primaryAccession': 'uniprot_id'},
             ['proteinDescription.recommendedName.fullName.value'], [], 'uniprot_id'),

            ('pdb', 'RCSB PDB', 13, 'monthly', 'rest',
             {'rcsb_id': 'pdb_id'},
             ['struct.title'], ['rcsb_accession_info.initial_release_date'], 'pdb_id'),

            # Tier 6: Patent data
            ('uspto_patents', 'USPTO PatentsView', 14, 'weekly', 'rest',
             {'patent_number': 'patent_number'},
             ['patent_title'], ['patent_date'], 'patent_number'),
        ]

        for source_id, name, precedence, tier, api_type, id_fields, name_fields, date_fields, primary_id in source_configs:
            await conn.execute("""
                INSERT INTO mol_raw.source_config
                (source_id, name, precedence, tier, api_type, identifier_fields, name_fields, date_fields, primary_identifier)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (source_id) DO NOTHING
            """, source_id, name, precedence, tier, api_type, json.dumps(id_fields), name_fields, date_fields, primary_id)

        logger.info(f"Seeded {len(identifier_types)} identifier types and {len(source_configs)} source configs")

    async def refresh(self, force: bool = False):
        """Refresh configuration from database."""
        now = datetime.now(timezone.utc)

        if not force and self._last_refresh:
            elapsed = (now - self._last_refresh).total_seconds()
            if elapsed < self._cache_ttl_seconds:
                return

        async with self.db_pool.acquire() as conn:
            # Load transformation settings
            settings_dict = {}
            rows = await conn.fetch("SELECT key, value FROM ops.transformation_config")
            for row in rows:
                val = row['value']
                if isinstance(val, str):
                    val = json.loads(val)
                settings_dict[row['key']] = val

            self._settings = TransformationSettings(
                confidence_threshold=settings_dict.get('confidence_threshold', 0.8),
                quality_threshold=settings_dict.get('quality_threshold', 0.3),
                fuzzy_match_threshold=settings_dict.get('fuzzy_match_threshold', 0.85),
                raw_to_bronze_batch=settings_dict.get('raw_to_bronze_batch', 1000),
                bronze_to_silver_batch=settings_dict.get('bronze_to_silver_batch', 500),
                silver_to_gold_batch=settings_dict.get('silver_to_gold_batch', 100),
                checkpoint_interval=settings_dict.get('checkpoint_interval', 1000),
                schema_sample_size=settings_dict.get('schema_sample_size', 100),
                max_flatten_depth=settings_dict.get('max_flatten_depth', 2),
                max_retries=settings_dict.get('max_retries', 3),
                retry_delay_seconds=settings_dict.get('retry_delay_seconds', 1.0),
            )

            # Load identifier types
            self._identifier_types = {}
            rows = await conn.fetch("""
                SELECT type_id, name, regex_pattern, priority, preferred_source, is_structural, validation_func
                FROM mol_raw.identifier_types
                ORDER BY priority
            """)
            for row in rows:
                self._identifier_types[row['type_id']] = IdentifierTypeConfig(
                    type_id=row['type_id'],
                    name=row['name'],
                    regex_pattern=row['regex_pattern'],
                    priority=row['priority'],
                    preferred_source=row['preferred_source'],
                    is_structural=row['is_structural'],
                    validation_func=row['validation_func'],
                )

            # Load source configs
            self._source_configs = {}
            rows = await conn.fetch("""
                SELECT source_id, name, precedence, tier, api_type, identifier_fields,
                       name_fields, date_fields, flatten_depth, batch_size,
                       primary_identifier, secondary_identifiers
                FROM mol_raw.source_config
                ORDER BY precedence
            """)
            for row in rows:
                id_fields = row['identifier_fields']
                if isinstance(id_fields, str):
                    id_fields = json.loads(id_fields)

                self._source_configs[row['source_id']] = SourceConfig(
                    source_id=row['source_id'],
                    name=row['name'],
                    precedence=row['precedence'],
                    tier=row['tier'],
                    api_type=row['api_type'],
                    identifier_fields=id_fields or {},
                    name_fields=row['name_fields'] or [],
                    date_fields=row['date_fields'] or [],
                    flatten_depth=row['flatten_depth'] or 2,
                    batch_size=row['batch_size'] or 500,
                    primary_identifier=row['primary_identifier'],
                    secondary_identifiers=row['secondary_identifiers'] or [],
                )

            # Load field mappings
            self._field_mappings = {}
            rows = await conn.fetch("""
                SELECT source_id, source_field, target_field, target_type, transformation,
                       is_identifier, identifier_type
                FROM mol_raw.field_mappings
            """)
            for row in rows:
                source_id = row['source_id']
                if source_id not in self._field_mappings:
                    self._field_mappings[source_id] = {}
                self._field_mappings[source_id][row['source_field']] = {
                    'target_field': row['target_field'],
                    'target_type': row['target_type'],
                    'transformation': row['transformation'],
                    'is_identifier': row['is_identifier'],
                    'identifier_type': row['identifier_type'],
                }

        self._last_refresh = now
        logger.debug(f"Refreshed config: {len(self._identifier_types)} identifier types, {len(self._source_configs)} sources")

    @property
    def settings(self) -> TransformationSettings:
        """Get transformation settings."""
        if not self._settings:
            raise RuntimeError("Configuration not loaded. Call refresh() first.")
        return self._settings

    @property
    def identifier_types(self) -> Dict[str, IdentifierTypeConfig]:
        """Get identifier type configurations."""
        return self._identifier_types

    @property
    def source_configs(self) -> Dict[str, SourceConfig]:
        """Get source configurations."""
        return self._source_configs

    def get_source_config(self, source_id: str) -> Optional[SourceConfig]:
        """Get configuration for a specific source."""
        return self._source_configs.get(source_id)

    def get_field_mappings(self, source_id: str) -> Dict[str, Dict]:
        """Get field mappings for a source."""
        return self._field_mappings.get(source_id, {})

    def detect_identifier_type(self, value: str) -> Optional[IdentifierTypeConfig]:
        """
        Detect the identifier type from a value.

        Returns the highest priority (lowest number) matching type.
        """
        if not value:
            return None

        value = str(value).strip()

        # Check all identifier types in priority order
        for type_id, config in sorted(self._identifier_types.items(), key=lambda x: x[1].priority):
            if config.matches(value):
                return config

        return None

    def get_source_precedence(self, source_id: str) -> int:
        """Get precedence for a source (lower = more trusted)."""
        config = self._source_configs.get(source_id)
        return config.precedence if config else 999

    async def add_source_config(self, config: SourceConfig):
        """Add or update a source configuration."""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO mol_raw.source_config
                (source_id, name, precedence, tier, api_type, identifier_fields,
                 name_fields, date_fields, flatten_depth, batch_size,
                 primary_identifier, secondary_identifiers)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (source_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    precedence = EXCLUDED.precedence,
                    tier = EXCLUDED.tier,
                    api_type = EXCLUDED.api_type,
                    identifier_fields = EXCLUDED.identifier_fields,
                    name_fields = EXCLUDED.name_fields,
                    date_fields = EXCLUDED.date_fields,
                    flatten_depth = EXCLUDED.flatten_depth,
                    batch_size = EXCLUDED.batch_size,
                    primary_identifier = EXCLUDED.primary_identifier,
                    secondary_identifiers = EXCLUDED.secondary_identifiers,
                    updated_at = NOW()
            """,
                config.source_id,
                config.name,
                config.precedence,
                config.tier,
                config.api_type,
                json.dumps(config.identifier_fields),
                config.name_fields,
                config.date_fields,
                config.flatten_depth,
                config.batch_size,
                config.primary_identifier,
                config.secondary_identifiers
            )

        # Refresh cache
        await self.refresh(force=True)

    async def update_setting(self, key: str, value: Any, description: str = None):
        """Update a transformation setting."""
        async with self.db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ops.transformation_config (key, value, description, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value = $2,
                    description = COALESCE($3, ops.transformation_config.description),
                    updated_at = NOW()
            """, key, json.dumps(value), description)

        await self.refresh(force=True)
