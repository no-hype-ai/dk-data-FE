"""
Dynamic Source Transformer

Implements Raw → Bronze → Silver → Gold transformations for dynamically
onboarded data sources. Uses schema information stored during onboarding
to automatically transform data through the medallion architecture.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import json
import re
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class TransformResult:
    """Result of a transformation operation."""
    source: str
    layer: str
    records_processed: int
    records_inserted: int
    records_updated: int
    records_failed: int
    errors: List[str]
    duration_seconds: float


class DynamicSourceTransformer:
    """
    Transforms data for dynamically onboarded sources through the
    medallion architecture (Raw → Bronze → Silver → Gold).

    Bronze: Extract typed fields from raw JSON payload
    Silver: Clean, normalize, deduplicate
    Gold: Aggregate into analytics-ready views
    """

    def __init__(self, db_pool):
        self.db_pool = db_pool

    async def get_source_config(self, source: str) -> Optional[Dict[str, Any]]:
        """Get source configuration from sync_schedules."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT source, tier, options
                FROM raw.sync_schedules
                WHERE source = $1
            """, source)

            if not row:
                return None

            options = row['options']
            if isinstance(options, str):
                options = json.loads(options)

            return {
                'source': row['source'],
                'tier': row['tier'],
                'options': options or {}
            }

    async def get_table_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Get column information for a table."""
        # Parse schema and table name
        if '.' in table_name:
            schema, table = table_name.split('.', 1)
        else:
            schema, table = 'raw', table_name

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = $1 AND table_name = $2
                ORDER BY ordinal_position
            """, schema, table)

            return [
                {
                    'name': row['column_name'],
                    'type': row['data_type'],
                    'nullable': row['is_nullable'] == 'YES'
                }
                for row in rows
            ]

    async def _detect_schema_from_payload(
        self,
        raw_table: str,
        sample_size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Auto-detect Bronze schema from response_body samples.

        Analyzes sample records to determine column names and types.
        Handles nested JSON by flattening to appropriate depth.
        """
        async with self.db_pool.acquire() as conn:
            # Get sample payloads
            rows = await conn.fetch(f"""
                SELECT response_body
                FROM {raw_table}
                WHERE response_body IS NOT NULL
                LIMIT $1
            """, sample_size)

            if not rows:
                return []

            # Analyze all samples to build comprehensive schema
            field_types = {}

            def infer_pg_type(value):
                """Infer PostgreSQL type from Python value."""
                if value is None:
                    return 'TEXT'
                if isinstance(value, bool):
                    return 'BOOLEAN'
                if isinstance(value, int):
                    return 'BIGINT' if abs(value) > 2147483647 else 'INTEGER'
                if isinstance(value, float):
                    return 'DOUBLE PRECISION'
                if isinstance(value, (list, dict)):
                    return 'JSONB'
                # String type detection
                str_val = str(value)
                if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', str_val):
                    return 'TIMESTAMPTZ'
                if re.match(r'^\d{4}-\d{2}-\d{2}$', str_val):
                    return 'DATE'
                if len(str_val) > 1000:
                    return 'TEXT'
                return 'TEXT'

            # Reserved column names that conflict with auto-generated columns
            RESERVED_COLUMNS = {
                'id', '_raw_id', '_extra_fields', 'raw_metadata',
                'bronze_hash', 'quality_score', 'processed_at',
                'silver_metadata', 'is_valid', 'validation_errors', 'normalized_at'
            }

            def extract_fields(data, prefix='', depth=0, max_depth=2):
                """Extract fields from nested dict, flattening to max_depth."""
                if not isinstance(data, dict) or depth > max_depth:
                    return

                for key, value in data.items():
                    # Skip internal fields
                    if key.startswith('_'):
                        continue

                    # Create safe column name
                    col_name = f"{prefix}{key}" if prefix else key
                    col_name = re.sub(r'[^a-zA-Z0-9_]', '_', col_name).lower()[:63]

                    # Rename reserved column names to preserve data
                    if col_name in RESERVED_COLUMNS:
                        col_name = f"source_{col_name}"

                    if isinstance(value, dict) and depth < max_depth:
                        # Recurse into nested dicts
                        extract_fields(value, f"{col_name}_", depth + 1, max_depth)
                    elif isinstance(value, list):
                        # Store arrays as JSONB
                        if col_name not in field_types:
                            field_types[col_name] = 'JSONB'
                    else:
                        # Determine type from value
                        pg_type = infer_pg_type(value)
                        if col_name in field_types:
                            # Type coercion - prefer more general types
                            existing = field_types[col_name]
                            if existing != pg_type:
                                # Default to TEXT if types conflict
                                field_types[col_name] = 'TEXT'
                        else:
                            field_types[col_name] = pg_type

            # Process all samples — unwrap API envelope if present
            for row in rows:
                payload = row['response_body']
                if isinstance(payload, str):
                    payload = json.loads(payload)

                # Detect API response envelope: {"results": [...], "meta": {...}}
                # Common in openFDA, ClinicalTrials.gov, OpenAlex, PubChem
                results_array = None
                for envelope_key in ('results', 'studies', 'works', 'data', 'hits'):
                    if isinstance(payload, dict) and envelope_key in payload and isinstance(payload[envelope_key], list):
                        results_array = payload[envelope_key]
                        break

                if results_array and len(results_array) > 0:
                    # Extract schema from the first few items in the results array
                    for item in results_array[:5]:
                        if isinstance(item, dict):
                            extract_fields(item)
                else:
                    # No envelope — extract from the payload directly
                    extract_fields(payload)

            # Convert to column list
            columns = [
                {'name': name, 'type': pg_type, 'nullable': True}
                for name, pg_type in sorted(field_types.items())
            ]

            logger.info(f"Auto-detected {len(columns)} columns from {raw_table}")
            return columns

    # =========================================================================
    # RAW → BRONZE Transformation
    # =========================================================================

    async def transform_raw_to_bronze(
        self,
        source: str,
        batch_size: int = 1000
    ) -> TransformResult:
        """
        Transform raw JSON data to Bronze typed columns.

        FULLY DYNAMIC with SCHEMA EVOLUTION:
        - Auto-detects schema from response_body samples (larger sample size)
        - Dynamically adds columns when new fields are discovered
        - Stores unmapped fields in _extra_fields JSONB column
        """
        import time
        start_time = time.time()

        result = TransformResult(
            source=source,
            layer='bronze',
            records_processed=0,
            records_inserted=0,
            records_updated=0,
            records_failed=0,
            errors=[],
            duration_seconds=0
        )

        try:
            config = await self.get_source_config(source)
            if not config:
                result.errors.append(f"Source {source} not found")
                return result

            options = config['options']
            raw_table = options.get('target_table', f'raw.{source}')
            bronze_table = raw_table.replace('raw.', 'bronze.')

            # AUTO-DETECT schema from larger sample (100 records for better coverage)
            data_columns = await self._detect_schema_from_payload(raw_table, sample_size=100)

            if not data_columns:
                logger.warning(f"Could not detect schema for {source}, using minimal columns")

            async with self.db_pool.acquire() as conn:
                # Ensure bronze schema exists
                await conn.execute("CREATE SCHEMA IF NOT EXISTS bronze")

                # Create bronze table if not exists (adds missing columns)
                await self._create_bronze_table(conn, bronze_table, data_columns, source)

                # Filter auto-detected columns to only those that exist in the table
                # (SQLMesh may have created the table with different columns)
                existing_cols = await conn.fetch(f"""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema || '.' || table_name = $1
                """, bronze_table)
                existing_col_names = {r['column_name'] for r in existing_cols}
                data_columns = [c for c in data_columns if c['name'] in existing_col_names]

                # Get unprocessed raw records
                raw_records = await conn.fetch(f"""
                    SELECT id, response_body, request_timestamp
                    FROM {raw_table}
                    WHERE response_body IS NOT NULL
                    AND id NOT IN (
                        SELECT (raw_metadata->>'raw_id')::uuid
                        FROM {bronze_table}
                        WHERE raw_metadata->>'source' = $1
                    )
                    ORDER BY request_timestamp
                    LIMIT $2
                """, source, batch_size)

                result.records_processed = len(raw_records)

                # Track current column names for schema evolution
                current_columns = {c['name'] for c in data_columns}
                new_fields_discovered = {}

                for record in raw_records:
                    try:
                        payload = record['response_body']
                        if isinstance(payload, str):
                            payload = json.loads(payload)

                        # Detect API response envelope and unwrap results array
                        items_to_process = [payload]
                        for envelope_key in ('results', 'studies', 'works', 'data', 'hits'):
                            if isinstance(payload, dict) and envelope_key in payload and isinstance(payload[envelope_key], list):
                                items_to_process = payload[envelope_key]
                                break

                        for item in items_to_process:
                            if not isinstance(item, dict):
                                continue

                            # Extract typed values and track extra fields
                            values, extra_fields = self._extract_typed_values_with_extras(
                                item, data_columns, current_columns
                            )

                            # Track newly discovered fields for schema evolution
                            for field_name, field_value in extra_fields.items():
                                if field_name not in new_fields_discovered and field_name not in current_columns:
                                    pg_type = self._infer_pg_type(field_value)
                                    new_fields_discovered[field_name] = pg_type

                            # Insert into bronze with extra fields
                            await self._insert_bronze_record(
                                conn, bronze_table, data_columns, values,
                                record['id'], source, record['request_timestamp'],
                                extra_fields=extra_fields
                            )
                            result.records_inserted += 1

                    except Exception as e:
                        result.records_failed += 1
                        if len(result.errors) < 10:
                            result.errors.append(f"Record {record['id']}: {str(e)[:100]}")

                # Schema evolution: add newly discovered columns
                if new_fields_discovered:
                    columns_added = await self._evolve_schema(
                        conn, bronze_table, new_fields_discovered, source
                    )
                    if columns_added > 0:
                        logger.info(f"Schema evolution: added {columns_added} new columns to {bronze_table}")

                logger.info(
                    f"Bronze transform for {source}: "
                    f"{result.records_inserted}/{result.records_processed} records"
                    f"{f', {len(new_fields_discovered)} new fields discovered' if new_fields_discovered else ''}"
                )

        except Exception as e:
            logger.error(f"Bronze transformation failed for {source}: {e}")
            result.errors.append(str(e))

        result.duration_seconds = time.time() - start_time
        return result

    async def _create_bronze_table(
        self,
        conn,
        table_name: str,
        columns: List[Dict[str, Any]],
        source: str
    ):
        """Create bronze table with typed columns plus metadata."""
        # Build column definitions
        col_defs = ["id SERIAL PRIMARY KEY"]

        for col in columns:
            pg_type = self._map_to_postgres_type(col['type'])
            # Quote column names to handle SQL reserved words (like 'references')
            col_defs.append(f'"{col["name"]}" {pg_type}')

        # Add bronze metadata columns
        col_defs.extend([
            "_extra_fields JSONB",   # Catch-all for fields not in schema
            "_raw_id INTEGER",       # Reference to raw record
            "raw_metadata JSONB",    # Links to raw record (legacy)
            "bronze_hash TEXT",      # Hash for deduplication
            "quality_score FLOAT",   # Data quality score
            "processed_at TIMESTAMPTZ DEFAULT NOW()"
        ])

        ddl = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {', '.join(col_defs)}
            )
        """
        await conn.execute(ddl)

        # Create indexes
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{source}_bronze_hash
            ON {table_name} (bronze_hash)
        """)
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{source}_bronze_processed
            ON {table_name} (processed_at)
        """)
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{source}_bronze_raw_id
            ON {table_name} (_raw_id)
        """)

    async def _evolve_schema(
        self,
        conn,
        table_name: str,
        new_fields: Dict[str, str],
        source: str
    ) -> int:
        """
        Add new columns to Bronze table when new fields are discovered.

        Returns number of columns added.
        """
        if not new_fields:
            return 0

        columns_added = 0
        for field_name, pg_type in new_fields.items():
            try:
                # Safely add column if it doesn't exist
                # Quote column names to handle SQL reserved words (like 'references')
                await conn.execute(f"""
                    ALTER TABLE {table_name}
                    ADD COLUMN IF NOT EXISTS "{field_name}" {pg_type}
                """)
                columns_added += 1
                logger.info(f"Schema evolution: added column {field_name} ({pg_type}) to {table_name}")
            except Exception as e:
                logger.warning(f"Could not add column {field_name} to {table_name}: {e}")

        return columns_added

    def _infer_pg_type(self, value: Any) -> str:
        """Infer PostgreSQL type from a Python value."""
        if value is None:
            return 'TEXT'
        if isinstance(value, bool):
            return 'BOOLEAN'
        if isinstance(value, int):
            return 'BIGINT' if abs(value) > 2147483647 else 'INTEGER'
        if isinstance(value, float):
            return 'DOUBLE PRECISION'
        if isinstance(value, (list, dict)):
            return 'JSONB'
        str_val = str(value)
        if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', str_val):
            return 'TIMESTAMPTZ'
        if re.match(r'^\d{4}-\d{2}-\d{2}$', str_val):
            return 'DATE'
        return 'TEXT'

    def _extract_typed_values_with_extras(
        self,
        payload: Dict[str, Any],
        columns: List[Dict[str, Any]],
        known_columns: set
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Extract values for known columns and track extra fields.

        Returns:
            Tuple of (mapped_values, extra_fields)
        """
        # Get mapped values using existing extraction
        values = self._extract_typed_values(payload, columns)

        # Find extra fields not in known columns
        extra_fields = {}

        def collect_fields(data: Dict, prefix: str = '', depth: int = 0):
            """Recursively collect all fields from payload."""
            if not isinstance(data, dict) or depth > 2:
                return
            for key, value in data.items():
                if key.startswith('_'):
                    continue
                field_name = f"{prefix}{key}" if prefix else key
                field_name = re.sub(r'[^a-zA-Z0-9_]', '_', field_name).lower()[:63]

                if field_name not in known_columns and field_name not in values:
                    if isinstance(value, dict) and depth < 2:
                        collect_fields(value, f"{field_name}_", depth + 1)
                    else:
                        extra_fields[field_name] = value

        collect_fields(payload)

        return values, extra_fields

    def _extract_typed_values(
        self,
        payload: Dict[str, Any],
        columns: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract and type-cast values from JSON payload.

        Handles:
        - Direct top-level keys
        - Nested paths (e.g., openfda.brand_name, protocolSection.identificationModule.nctId)
        - Array values (takes first element)
        - Case-insensitive matching
        - CamelCase to snake_case conversion
        - Deep recursive search (up to 5 levels)
        """
        values = {}

        # Known path mappings for specific API structures
        KNOWN_PATHS = {
            # ClinicalTrials.gov API v2 mappings
            'nct_id': ['protocolSection.identificationModule.nctId', 'nctId'],
            'brief_title': ['protocolSection.identificationModule.briefTitle', 'briefTitle'],
            'official_title': ['protocolSection.identificationModule.officialTitle', 'officialTitle'],
            'overall_status': ['protocolSection.statusModule.overallStatus', 'overallStatus'],
            'phase': ['protocolSection.designModule.phases', 'phases'],
            'study_type': ['protocolSection.designModule.studyType', 'studyType'],
            'start_date': ['protocolSection.statusModule.startDateStruct.date', 'startDate'],
            'completion_date': ['protocolSection.statusModule.completionDateStruct.date', 'completionDate'],
            'lead_sponsor': ['protocolSection.sponsorCollaboratorsModule.leadSponsor.name', 'leadSponsor'],
            'conditions': ['protocolSection.conditionsModule.conditions', 'conditions'],
            'interventions': ['protocolSection.armsInterventionsModule.interventions', 'interventions'],
            'has_results': ['hasResults'],
            # FDA FAERS API mappings
            'drugs': ['patient.drug', 'drug'],
            'reactions': ['patient.reaction', 'reaction'],
            'patient_age': ['patient.patientonsetage', 'patientonsetage'],
            'patient_sex': ['patient.patientsex', 'patientsex'],
            'patient_weight': ['patient.patientweight', 'patientweight'],
        }

        def snake_to_camel(name: str) -> str:
            """Convert snake_case to camelCase."""
            components = name.split('_')
            return components[0] + ''.join(x.title() for x in components[1:])

        def camel_to_snake(name: str) -> str:
            """Convert camelCase to snake_case."""
            import re
            return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

        def get_by_path(data: Any, path: str) -> Any:
            """Get value from nested dict using dot notation path."""
            if data is None:
                return None

            parts = path.split('.')
            current = data

            for part in parts:
                if current is None:
                    return None
                if isinstance(current, list):
                    current = current[0] if current else None
                    if current is None:
                        return None
                if isinstance(current, dict):
                    # Try exact match
                    if part in current:
                        current = current[part]
                    # Try case variations
                    else:
                        found = False
                        for k in current.keys():
                            if k.lower() == part.lower():
                                current = current[k]
                                found = True
                                break
                        if not found:
                            return None
                else:
                    return None

            # Handle array result
            if isinstance(current, list) and current:
                return current[0] if len(current) == 1 else current
            return current

        def find_value_deep(data: Any, target_key: str, max_depth: int = 5, current_depth: int = 0) -> Any:
            """Deeply recursive search for a key in nested dicts."""
            if current_depth > max_depth or data is None:
                return None

            if isinstance(data, list):
                if data:
                    return find_value_deep(data[0], target_key, max_depth, current_depth)
                return None

            if not isinstance(data, dict):
                return None

            # Generate key variations to search
            key_variations = [
                target_key,
                snake_to_camel(target_key),
                target_key.replace('_', ''),
                target_key.lower(),
            ]

            # Check current level with all variations
            for key_var in key_variations:
                if key_var in data:
                    val = data[key_var]
                    if isinstance(val, list) and val:
                        return val[0] if len(val) == 1 else val
                    return val
                # Case-insensitive check
                for k, v in data.items():
                    if k.lower() == key_var.lower():
                        if isinstance(v, list) and v:
                            return v[0] if len(v) == 1 else v
                        return v

            # Recurse into nested dicts
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    result = find_value_deep(value, target_key, max_depth, current_depth + 1)
                    if result is not None:
                        return result

            return None

        for col in columns:
            col_name = col['name']
            value = None

            # 1. Try known paths first (for well-known APIs like ClinicalTrials, FDA)
            if col_name in KNOWN_PATHS:
                for path in KNOWN_PATHS[col_name]:
                    value = get_by_path(payload, path)
                    if value is not None:
                        break

            # 2. Convert underscore-separated names to dot paths (e.g., patient_drug → patient.drug)
            if value is None and '_' in col_name:
                # Try various underscore-to-path interpretations
                parts = col_name.split('_')
                for i in range(1, len(parts)):
                    # Try splitting at different positions
                    path = '.'.join(['_'.join(parts[:i]), '_'.join(parts[i:])])
                    value = get_by_path(payload, path)
                    if value is not None:
                        break
                    # Also try camelCase for the second part
                    second_part = parts[i] + ''.join(p.title() for p in parts[i+1:]) if i < len(parts) else ''
                    if second_part:
                        path = '.'.join(['_'.join(parts[:i]), second_part])
                        value = get_by_path(payload, path)
                        if value is not None:
                            break

            # 3. Try deep recursive search with name variations
            if value is None:
                value = find_value_deep(payload, col_name)

            # 4. Try the last part of underscore-separated name (leaf key)
            if value is None and '_' in col_name:
                leaf_key = col_name.split('_')[-1]
                value = find_value_deep(payload, leaf_key)

            # 5. Try without underscores at top level
            if value is None:
                clean_name = col_name.replace('_', '')
                for key in payload.keys():
                    if key.lower().replace('_', '') == clean_name.lower():
                        val = payload[key]
                        value = val[0] if isinstance(val, list) and val else val
                        break

            # 6. Try with source_ prefix removed
            if value is None and col_name.startswith('source_'):
                clean_name = col_name[7:]
                value = find_value_deep(payload, clean_name)

            # Type conversion
            if value is not None:
                try:
                    if 'int' in col['type'].lower():
                        value = int(value) if value != '' else None
                    elif 'float' in col['type'].lower() or 'double' in col['type'].lower():
                        value = float(value) if value != '' else None
                    elif 'bool' in col['type'].lower():
                        value = bool(value)
                    elif 'json' in col['type'].lower():
                        value = json.dumps(value) if not isinstance(value, str) else value
                except (ValueError, TypeError):
                    value = None

            values[col_name] = value

        return values

    async def _insert_bronze_record(
        self,
        conn,
        table_name: str,
        columns: List[Dict[str, Any]],
        values: Dict[str, Any],
        raw_id: Any,  # UUID or int depending on raw table schema
        source: str,
        ingested_at: datetime,
        extra_fields: Optional[Dict[str, Any]] = None
    ):
        """Insert a record into the bronze table with extra fields support."""
        # Calculate hash for deduplication
        hash_input = json.dumps(values, sort_keys=True, default=str)
        bronze_hash = hashlib.md5(hash_input.encode()).hexdigest()

        # Calculate simple quality score (% of non-null fields)
        non_null = sum(1 for v in values.values() if v is not None)
        quality_score = non_null / len(values) if values else 0

        # Build insert query
        # Quote column names to handle SQL reserved words (like 'references')
        col_names = [f'"{c["name"]}"' for c in columns]

        # Add metadata columns including _extra_fields and _raw_id
        col_names.extend(['_extra_fields', '_raw_id', 'raw_metadata', 'bronze_hash', 'quality_score'])

        raw_metadata = json.dumps({
            'raw_id': str(raw_id),  # Convert UUID to string for JSON serialization
            'source': source,
            'ingested_at': ingested_at.isoformat()
        })

        # Prepare extra_fields as JSONB (only if there are extra fields)
        extra_fields_json = json.dumps(extra_fields) if extra_fields else None

        # Build params
        params = [values.get(c['name']) for c in columns]
        params.extend([extra_fields_json, raw_id, raw_metadata, bronze_hash, quality_score])

        placeholders = [f'${i+1}' for i in range(len(params))]

        query = f"""
            INSERT INTO {table_name} ({', '.join(col_names)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT DO NOTHING
        """

        await conn.execute(query, *params)

    def _map_to_postgres_type(self, info_schema_type: str) -> str:
        """Map information_schema type to PostgreSQL type."""
        type_map = {
            'integer': 'INTEGER',
            'bigint': 'BIGINT',
            'smallint': 'SMALLINT',
            'numeric': 'NUMERIC',
            'real': 'REAL',
            'double precision': 'DOUBLE PRECISION',
            'boolean': 'BOOLEAN',
            'text': 'TEXT',
            'character varying': 'TEXT',
            'character': 'TEXT',
            'timestamp with time zone': 'TIMESTAMPTZ',
            'timestamp without time zone': 'TIMESTAMP',
            'date': 'DATE',
            'time': 'TIME',
            'jsonb': 'JSONB',
            'json': 'JSONB',
            'uuid': 'UUID',
        }
        return type_map.get(info_schema_type.lower(), 'TEXT')

    # =========================================================================
    # BRONZE → SILVER Transformation
    # =========================================================================

    async def transform_bronze_to_silver(
        self,
        source: str,
        batch_size: int = 1000
    ) -> TransformResult:
        """
        Transform Bronze data to Silver (cleaned, normalized, deduplicated).

        Silver layer operations:
        - Remove duplicates (using bronze_hash)
        - Normalize text fields
        - Validate data types
        - Apply business rules
        - Perform entity linking to master molecule database (if configured)
        """
        import time
        start_time = time.time()

        result = TransformResult(
            source=source,
            layer='silver',
            records_processed=0,
            records_inserted=0,
            records_updated=0,
            records_failed=0,
            errors=[],
            duration_seconds=0
        )

        try:
            config = await self.get_source_config(source)
            if not config:
                result.errors.append(f"Source {source} not found")
                return result

            options = config['options']
            raw_table = options.get('target_table', f'raw.{source}')
            bronze_table = raw_table.replace('raw.', 'bronze.')
            silver_table = raw_table.replace('raw.', 'silver.')

            # Get entity linking configuration from Phase 3 onboarding
            entity_linking = options.get('entity_linking', {})
            # User-specified identifier from WebUI Phase 3
            user_identifier_field = entity_linking.get('identifier_field')
            user_identifier_type = entity_linking.get('identifier_type')
            has_specific_linking = bool(user_identifier_field and user_identifier_type)

            # Smart linking: auto-detect additional identifiers (enabled by default)
            # This SUPPLEMENTS the user-specified identifier, not replaces it
            use_smart_linking = entity_linking.get('smart_linking', True)

            # Entity linking is enabled if either specific config OR smart linking
            has_entity_linking = has_specific_linking or use_smart_linking

            if has_entity_linking:
                if has_specific_linking:
                    logger.info(f"Entity linking for {source}: PRIMARY={user_identifier_field} ({user_identifier_type})")
                if use_smart_linking:
                    logger.info(f"Smart entity linking also enabled for {source} (auto-detect additional identifiers)")

            # Get columns from bronze table
            columns = await self.get_table_columns(bronze_table)
            data_columns = [
                c for c in columns
                if c['name'] not in ('id', 'raw_metadata', 'bronze_hash', 'quality_score', 'processed_at', '_extra_fields', '_raw_id')
            ]

            async with self.db_pool.acquire() as conn:
                # Ensure silver schema exists
                await conn.execute("CREATE SCHEMA IF NOT EXISTS silver")

                # Create silver table (with molecule_id if entity linking enabled)
                await self._create_silver_table(conn, silver_table, data_columns, source, has_entity_linking)

                # Get unprocessed bronze records (deduplicated)
                bronze_records = await conn.fetch(f"""
                    SELECT DISTINCT ON (bronze_hash) *
                    FROM {bronze_table}
                    WHERE quality_score >= 0.3  -- Minimum quality threshold
                    AND bronze_hash NOT IN (
                        SELECT COALESCE(silver_metadata->>'bronze_hash', '')
                        FROM {silver_table}
                    )
                    ORDER BY bronze_hash, quality_score DESC, processed_at DESC
                    LIMIT $1
                """, batch_size)

                result.records_processed = len(bronze_records)

                # Pre-load identifier mappings for entity linking
                identifier_cache = {}
                smart_cache = {}
                detected_fields = []

                if has_entity_linking:
                    # PRIORITY ORDER:
                    # 1. User-specified identifier from Phase 3 (highest priority)
                    # 2. Smart-detected identifiers (auto-detected from column names)

                    if has_specific_linking:
                        # Load user-specified identifier mappings FIRST (highest priority)
                        identifier_cache = await self._load_identifier_mappings(
                            conn, entity_linking, bronze_records
                        )
                        logger.info(f"Loaded {len(identifier_cache)} mappings for user-specified identifier: {user_identifier_field}")

                    if use_smart_linking:
                        # SMART LINKING: auto-detect additional identifier types
                        smart_cache, detected_fields = await self._smart_load_all_identifiers(
                            conn, [dict(r) for r in bronze_records], data_columns
                        )
                        # Remove user-specified field from smart detection to avoid duplicate lookups
                        if user_identifier_field:
                            detected_fields = [(t, f) for t, f in detected_fields if f != user_identifier_field]

                linked_count = 0
                linked_records = []  # Track records that were successfully linked

                for record in bronze_records:
                    try:
                        # Clean and normalize values
                        cleaned_values = self._clean_values(record, data_columns)

                        # Perform entity linking (PRIORITY: user-specified > smart-detected)
                        molecule_id = None
                        if has_entity_linking:
                            # 1. Try USER-SPECIFIED identifier FIRST (from Phase 3 onboarding)
                            if has_specific_linking:
                                molecule_id = await self._resolve_entity(
                                    cleaned_values, entity_linking, identifier_cache
                                )

                            # 2. If not found, try SMART LINKING (auto-detected identifiers)
                            if molecule_id is None and use_smart_linking and detected_fields:
                                molecule_id = self._smart_resolve_entity(
                                    cleaned_values, detected_fields, smart_cache
                                )

                            if molecule_id:
                                linked_count += 1
                                # Track linked record for adding to identifier_mappings
                                cleaned_values['_linked_molecule_id'] = molecule_id
                                linked_records.append(cleaned_values)

                        # Insert into silver
                        await self._insert_silver_record(
                            conn, silver_table, data_columns, cleaned_values,
                            record['id'], record['bronze_hash'], source,
                            molecule_id=molecule_id
                        )
                        result.records_inserted += 1

                    except Exception as e:
                        result.records_failed += 1
                        if len(result.errors) < 10:
                            result.errors.append(f"Record {record['id']}: {str(e)[:100]}")

                # Log entity linking statistics
                if has_entity_linking:
                    logger.info(
                        f"Entity linking for {source}: {linked_count}/{result.records_inserted} records linked"
                    )
                    if detected_fields:
                        logger.info(f"  Used identifiers: {[f for _, f in detected_fields]}")

                    # ADD NEW IDENTIFIERS TO CROSS-REFERENCE SYSTEM
                    # This grows the identifier knowledge graph with each new data source
                    if linked_records and detected_fields:
                        new_mappings = await self._add_new_identifiers_to_mappings(
                            conn, linked_records, detected_fields, source
                        )
                        if new_mappings > 0:
                            logger.info(f"  Added {new_mappings} new identifier mappings to cross-reference system")

                logger.info(
                    f"Silver transform for {source}: "
                    f"{result.records_inserted}/{result.records_processed} records"
                )

        except Exception as e:
            logger.error(f"Silver transformation failed for {source}: {e}")
            result.errors.append(str(e))

        result.duration_seconds = time.time() - start_time
        return result

    # =========================================================================
    # SMART MULTI-IDENTIFIER ENTITY LINKING
    # =========================================================================

    # Known field name patterns for each identifier type (priority order)
    IDENTIFIER_PATTERNS = {
        'inchi_key': {
            'db_type': 'inchi_key',
            'patterns': ['inchi_key', 'inchikey', 'inchi', 'standard_inchi_key'],
            'regex': r'^[A-Z]{14}-[A-Z]{10}-[A-Z]$',  # InChIKey format
            'priority': 1,  # Highest priority - most specific
        },
        'drugbank_id': {
            'db_type': 'drugbank_id',
            'patterns': ['drugbank_id', 'drugbankid', 'drugbank', 'db_id'],
            'regex': r'^DB\d{5}$',
            'priority': 2,
        },
        'chembl_id': {
            'db_type': 'chembl_id',
            'patterns': ['chembl_id', 'chemblid', 'chembl', 'molecule_chembl_id'],
            'regex': r'^CHEMBL\d+$',
            'priority': 3,
        },
        'pubchem_cid': {
            'db_type': 'pubchem_cid',
            'patterns': ['pubchem_cid', 'pubchemcid', 'pubchem', 'cid', 'compound_cid'],
            'regex': r'^\d+$',
            'priority': 4,
        },
        'cas_number': {
            'db_type': 'cas_number',
            'patterns': ['cas_number', 'cas', 'casrn', 'cas_rn', 'cas_registry'],
            'regex': r'^\d{2,7}-\d{2}-\d$',
            'priority': 5,
        },
        'unii': {
            'db_type': 'unii',
            'patterns': ['unii', 'fda_unii', 'substance_unii'],
            'regex': r'^[A-Z0-9]{10}$',
            'priority': 6,
        },
        'smiles': {
            'db_type': 'smiles',
            'patterns': ['smiles', 'canonical_smiles', 'isomeric_smiles', 'mol_smiles'],
            'regex': None,  # SMILES are complex, detect by field name only
            'priority': 7,
        },
        'drug_name': {
            'db_type': 'drug_name',
            'patterns': ['drug_name', 'drugname', 'generic_name', 'brand_name', 'name',
                        'compound_name', 'molecule_name', 'substance_name', 'medicinal_product',
                        'active_ingredient', 'active_substance', 'inn', 'nonproprietary_name'],
            'regex': None,  # Names are free text
            'priority': 8,  # Lowest priority - least specific
        },
    }

    async def _smart_load_all_identifiers(
        self,
        conn,
        records: List[Dict[str, Any]],
        columns: List[Dict[str, Any]]
    ) -> Tuple[Dict[str, Dict[str, str]], List[Tuple[str, str]]]:
        """
        Smart entity linking: auto-detect ALL identifier fields in the data
        and build a unified cache for multi-identifier resolution.

        Returns:
            - cache: Dict mapping (identifier_type, value) -> molecule_id
            - detected_fields: List of (identifier_type, field_name) tuples found
        """
        # Get column names from schema
        column_names = {c['name'].lower() for c in columns}

        # Detect which identifier fields are present
        detected_fields = []
        for id_type, config in self.IDENTIFIER_PATTERNS.items():
            for pattern in config['patterns']:
                if pattern in column_names:
                    detected_fields.append((id_type, pattern))
                    break  # Found a match for this type, move to next

        # Sort by priority (lowest number = highest priority)
        detected_fields.sort(key=lambda x: self.IDENTIFIER_PATTERNS[x[0]]['priority'])

        if not detected_fields:
            logger.info("No identifier fields detected in schema")
            return {}, []

        logger.info(f"Smart entity linking: detected identifiers {[(t, f) for t, f in detected_fields]}")

        # Build unified cache from all detected identifier types
        cache = {}  # {(id_type, value): molecule_id}

        for id_type, field_name in detected_fields:
            db_type = self.IDENTIFIER_PATTERNS[id_type]['db_type']

            # Extract unique values for this identifier type
            values = set()
            for record in records:
                val = record.get(field_name)
                if val and isinstance(val, (str, int)):
                    val_str = str(val).strip()
                    if val_str:
                        values.add(val_str)

            if not values:
                continue

            # Look up in identifier_mappings
            try:
                # Handle special case for inchi_key which may be stored as 'inchi_key' in DB
                lookup_type = db_type
                if db_type == 'smiles':
                    lookup_type = 'smiles'  # Stored as 'smiles' in identifier_mappings

                rows = await conn.fetch("""
                    SELECT identifier_value, molecule_id::text
                    FROM mol_silver.identifier_mappings
                    WHERE identifier_type = $1
                    AND identifier_value = ANY($2)
                """, lookup_type, list(values))

                for row in rows:
                    cache[(id_type, row['identifier_value'])] = row['molecule_id']

                logger.debug(f"Loaded {len(rows)} mappings for {id_type}")
            except Exception as e:
                logger.warning(f"identifier_mappings lookup failed for {id_type}: {e}")

            # Also try drug_name_lookup for name-based matching
            if id_type == 'drug_name' and values:
                try:
                    rows = await conn.fetch("""
                        SELECT drug_name_lower, molecule_id::text
                        FROM mol_silver.drug_name_lookup
                        WHERE drug_name_lower = ANY($1)
                    """, [v.lower() for v in values])

                    for row in rows:
                        # Store with original case and lowercase
                        cache[(id_type, row['drug_name_lower'])] = row['molecule_id']

                    logger.debug(f"Loaded {len(rows)} drug name lookups")
                except Exception as e:
                    logger.debug(f"drug_name_lookup failed: {e}")

        total_mappings = len(cache)
        logger.info(f"Smart entity linking: loaded {total_mappings} total identifier mappings")

        return cache, detected_fields

    def _smart_resolve_entity(
        self,
        values: Dict[str, Any],
        detected_fields: List[Tuple[str, str]],
        identifier_cache: Dict[Tuple[str, str], str]
    ) -> Optional[str]:
        """
        Resolve a record to molecule_id using ALL available identifiers.
        Tries each identifier in priority order, returns first match.
        """
        for id_type, field_name in detected_fields:
            val = values.get(field_name)
            if not val:
                continue

            val_str = str(val).strip()

            # Try exact match
            cache_key = (id_type, val_str)
            if cache_key in identifier_cache:
                return identifier_cache[cache_key]

            # For drug names, also try lowercase
            if id_type == 'drug_name':
                cache_key_lower = (id_type, val_str.lower())
                if cache_key_lower in identifier_cache:
                    return identifier_cache[cache_key_lower]

        return None

    async def _load_identifier_mappings(
        self,
        conn,
        entity_linking: Dict[str, Any],
        records: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Pre-load identifier mappings for efficient batch lookup.

        Returns a dict mapping identifier values to molecule_id (UUID string).
        """
        identifier_type = entity_linking.get('identifier_type', '').lower()
        identifier_field = entity_linking.get('identifier_field', '')

        # Map user-facing identifier types to database identifier_type values
        # The identifier_mappings table uses underscore versions
        db_identifier_type_map = {
            'inchikey': 'inchi_key',
            'smiles': 'canonical_smiles',
            'cas': 'cas_number',
            'chembl_id': 'chembl_id',
            'pubchem_cid': 'pubchem_cid',
            'drugbank_id': 'drugbank_id',
            'drug_name': 'drug_name',
            'unii': 'unii',
        }

        # Map identifier types to molecule table columns for fallback lookup
        molecule_column_map = {
            'inchikey': 'inchi_key',
            'smiles': 'canonical_smiles',
            'cas': None,  # Not in molecules table
            'chembl_id': None,
            'pubchem_cid': None,
            'drugbank_id': None,
            'drug_name': 'canonical_name',
            'unii': None,
        }

        db_identifier_type = db_identifier_type_map.get(identifier_type)
        lookup_column = molecule_column_map.get(identifier_type)

        if not db_identifier_type:
            logger.warning(f"Unknown identifier type: {identifier_type}")
            return {}

        # Extract unique identifiers from records
        identifiers = set()
        for record in records:
            val = record.get(identifier_field)
            if val and isinstance(val, str):
                identifiers.add(val.strip())

        if not identifiers:
            return {}

        cache = {}

        # Look up in identifier_mappings table (primary lookup)
        try:
            rows = await conn.fetch("""
                SELECT identifier_value, molecule_id::text
                FROM mol_silver.identifier_mappings
                WHERE identifier_type = $1
                AND identifier_value = ANY($2)
            """, db_identifier_type, list(identifiers))

            for row in rows:
                cache[row['identifier_value']] = row['molecule_id']

            logger.info(f"Loaded {len(cache)} identifier mappings for {db_identifier_type}")
        except Exception as e:
            logger.warning(f"identifier_mappings lookup failed: {e}")

        # Fallback: try direct molecule lookup if column exists
        if lookup_column and len(cache) < len(identifiers):
            try:
                remaining = [i for i in identifiers if i not in cache]
                rows = await conn.fetch(f"""
                    SELECT {lookup_column} as identifier, id::text as molecule_id
                    FROM mol_silver.molecules
                    WHERE {lookup_column} = ANY($1)
                """, remaining)

                for row in rows:
                    if row['identifier'] and row['identifier'] not in cache:
                        cache[row['identifier']] = row['molecule_id']

                logger.info(f"Added {len(rows)} molecule mappings from molecules table")
            except Exception as e2:
                logger.warning(f"molecules table lookup failed: {e2}")

        # Also try drug_name_lookup for name-based matching
        if identifier_type == 'drug_name' and identifiers:
            try:
                remaining = [i for i in identifiers if i not in cache and i.lower() not in cache]
                if remaining:
                    rows = await conn.fetch("""
                        SELECT LOWER(name) as name, molecule_id::text
                        FROM mol_silver.drug_name_lookup
                        WHERE LOWER(name) = ANY($1)
                    """, [n.lower() for n in remaining])

                    for row in rows:
                        cache[row['name']] = row['molecule_id']

                    logger.info(f"Added {len(rows)} drug name lookups")
            except Exception as e:
                logger.debug(f"drug_name_lookup table not available: {e}")

        return cache

    def _get_identifier_value(
        self,
        values: Dict[str, Any],
        entity_linking: Dict[str, Any]
    ) -> Optional[str]:
        """Extract the identifier value from a record."""
        primary_field = entity_linking.get('identifier_field', '')
        value = values.get(primary_field)

        if value and isinstance(value, str):
            return value.strip()

        # Try secondary identifier
        secondary_field = entity_linking.get('secondary_identifier_field', '')
        if secondary_field:
            value = values.get(secondary_field)
            if value and isinstance(value, str):
                return value.strip()

        return None

    async def _resolve_entity(
        self,
        values: Dict[str, Any],
        entity_linking: Dict[str, Any],
        identifier_cache: Dict[str, str]
    ) -> Optional[str]:
        """Resolve a record to a molecule_id (UUID) using configured identifiers."""
        # Try primary identifier
        primary_field = entity_linking.get('identifier_field', '')
        primary_value = values.get(primary_field)

        if primary_value and isinstance(primary_value, str):
            primary_value = primary_value.strip()
            if primary_value in identifier_cache:
                return identifier_cache[primary_value]

            # For drug names, also try lowercase
            if entity_linking.get('identifier_type') == 'drug_name':
                if primary_value.lower() in identifier_cache:
                    return identifier_cache[primary_value.lower()]

        # Try secondary identifier
        secondary_field = entity_linking.get('secondary_identifier_field', '')
        if secondary_field:
            secondary_value = values.get(secondary_field)
            if secondary_value and isinstance(secondary_value, str):
                secondary_value = secondary_value.strip()
                if secondary_value in identifier_cache:
                    return identifier_cache[secondary_value]

        return None

    async def _add_new_identifiers_to_mappings(
        self,
        conn,
        records: List[Dict[str, Any]],
        detected_fields: List[Tuple[str, str]],
        source: str
    ) -> int:
        """
        After linking records to molecules, add any NEW identifiers found
        in this data source to identifier_mappings for future cross-referencing.

        This grows the identifier knowledge graph with each new data source.
        """
        if not detected_fields:
            return 0

        added_count = 0

        for id_type, field_name in detected_fields:
            db_type = self.IDENTIFIER_PATTERNS[id_type]['db_type']

            # Collect (value, molecule_id) pairs from successfully linked records
            new_mappings = []
            for record in records:
                molecule_id = record.get('_linked_molecule_id')
                if not molecule_id:
                    continue

                val = record.get(field_name)
                if val and isinstance(val, (str, int)):
                    val_str = str(val).strip()
                    if val_str:
                        new_mappings.append((val_str, molecule_id))

            if not new_mappings:
                continue

            # Insert new mappings (ignore conflicts with existing)
            try:
                # Use COPY for efficiency or batch insert
                for val, mol_id in new_mappings:
                    await conn.execute("""
                        INSERT INTO mol_silver.identifier_mappings
                        (id, molecule_id, identifier_type, identifier_value, source, confidence, is_primary, created_at, updated_at)
                        VALUES (gen_random_uuid(), $1::uuid, $2, $3, $4, 0.8, false, NOW(), NOW())
                        ON CONFLICT (molecule_id, identifier_type, identifier_value) DO NOTHING
                    """, mol_id, db_type, val, source)

                added_count += len(new_mappings)
                logger.info(f"Added {len(new_mappings)} {id_type} mappings from {source} to identifier_mappings")

            except Exception as e:
                logger.warning(f"Failed to add {id_type} mappings: {e}")

        # Also add drug names to drug_name_lookup
        name_fields = [f for t, f in detected_fields if t == 'drug_name']
        for field_name in name_fields:
            try:
                for record in records:
                    molecule_id = record.get('_linked_molecule_id')
                    name = record.get(field_name)
                    if molecule_id and name and isinstance(name, str):
                        await conn.execute("""
                            INSERT INTO mol_silver.drug_name_lookup (drug_name_lower, molecule_id)
                            VALUES ($1, $2::uuid)
                            ON CONFLICT DO NOTHING
                        """, name.lower().strip(), molecule_id)
            except Exception as e:
                logger.debug(f"Failed to add drug names to lookup: {e}")

        return added_count

    async def _create_silver_table(
        self,
        conn,
        table_name: str,
        columns: List[Dict[str, Any]],
        source: str,
        has_entity_linking: bool = False
    ):
        """Create silver table with cleaned columns plus metadata."""
        col_defs = ["id SERIAL PRIMARY KEY"]

        for col in columns:
            pg_type = self._map_to_postgres_type(col['type'])
            # Quote column names to handle SQL reserved words
            col_defs.append(f'"{col["name"]}" {pg_type}')

        # Add silver metadata columns
        col_defs.extend([
            "silver_metadata JSONB",
            "is_valid BOOLEAN DEFAULT TRUE",
            "validation_errors JSONB",
            "normalized_at TIMESTAMPTZ DEFAULT NOW()"
        ])

        # Add molecule_id column for entity linking (UUID stored as TEXT)
        if has_entity_linking:
            col_defs.append("molecule_id TEXT")  # Links to silver.molecules (UUID)

        ddl = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {', '.join(col_defs)}
            )
        """
        await conn.execute(ddl)

        # Create indexes
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{source}_silver_valid
            ON {table_name} (is_valid)
        """)

        # Create index on molecule_id for entity linking
        if has_entity_linking:
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{source}_silver_molecule
                ON {table_name} (molecule_id) WHERE molecule_id IS NOT NULL
            """)

    def _clean_values(
        self,
        record: Dict[str, Any],
        columns: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Clean and normalize values."""
        cleaned = {}

        for col in columns:
            col_name = col['name']
            value = record.get(col_name)

            if value is None:
                cleaned[col_name] = None
                continue

            # Text cleaning
            if isinstance(value, str):
                # Trim whitespace
                value = value.strip()
                # Normalize unicode
                value = value.replace('\x00', '')
                # Empty string to None
                if value == '':
                    value = None

            cleaned[col_name] = value

        return cleaned

    async def _insert_silver_record(
        self,
        conn,
        table_name: str,
        columns: List[Dict[str, Any]],
        values: Dict[str, Any],
        bronze_id: int,
        bronze_hash: str,
        source: str,
        molecule_id: Optional[str] = None
    ):
        """Insert a record into the silver table."""
        # Validate record
        validation_errors = []
        is_valid = True

        # Basic validation - check required fields have values
        for col in columns:
            if not col.get('nullable', True) and values.get(col['name']) is None:
                validation_errors.append(f"Missing required field: {col['name']}")
                is_valid = False

        # Build insert query
        # Quote column names to handle SQL reserved words
        col_names = [f'"{c["name"]}"' for c in columns]
        placeholders = [f'${i+1}' for i in range(len(col_names))]

        col_names.extend(['silver_metadata', 'is_valid', 'validation_errors'])
        next_idx = len(col_names)
        placeholders.extend([f'${next_idx-2}', f'${next_idx-1}', f'${next_idx}'])

        silver_metadata = json.dumps({
            'bronze_id': bronze_id,
            'bronze_hash': bronze_hash,
            'source': source,
            'processed_at': datetime.utcnow().isoformat(),
            'molecule_id': molecule_id  # Track if linking was successful
        })

        params = [values.get(c['name']) for c in columns]
        params.extend([
            silver_metadata,
            is_valid,
            json.dumps(validation_errors) if validation_errors else None
        ])

        # Add molecule_id if provided
        if molecule_id is not None:
            col_names.append('molecule_id')
            placeholders.append(f'${len(params)+1}')
            params.append(molecule_id)

        query = f"""
            INSERT INTO {table_name} ({', '.join(col_names)})
            VALUES ({', '.join(placeholders)})
        """

        await conn.execute(query, *params)

    # =========================================================================
    # SILVER → GOLD Transformation
    # =========================================================================

    async def transform_silver_to_gold(
        self,
        source: str
    ) -> TransformResult:
        """
        Transform Silver data to Gold (aggregated, analytics-ready).

        Gold layer creates:
        - Summary statistics
        - Aggregated views by common dimensions
        - Pre-computed metrics
        """
        import time
        start_time = time.time()

        result = TransformResult(
            source=source,
            layer='gold',
            records_processed=0,
            records_inserted=0,
            records_updated=0,
            records_failed=0,
            errors=[],
            duration_seconds=0
        )

        try:
            config = await self.get_source_config(source)
            if not config:
                result.errors.append(f"Source {source} not found")
                return result

            options = config['options']
            raw_table = options.get('target_table', f'raw.{source}')
            silver_table = raw_table.replace('raw.', 'silver.')
            gold_table = raw_table.replace('raw.', 'gold.')

            # Get columns from silver table
            columns = await self.get_table_columns(silver_table)
            data_columns = [
                c for c in columns
                if c['name'] not in ('id', 'silver_metadata', 'is_valid', 'validation_errors', 'normalized_at')
            ]

            async with self.db_pool.acquire() as conn:
                # Ensure gold schema exists
                await conn.execute("CREATE SCHEMA IF NOT EXISTS gold")

                # Create gold summary table
                await self._create_gold_table(conn, gold_table, data_columns, source)

                # Count valid silver records
                silver_count = await conn.fetchval(f"""
                    SELECT COUNT(*) FROM {silver_table} WHERE is_valid = TRUE
                """)
                result.records_processed = silver_count or 0

                # Generate aggregations
                await self._generate_gold_aggregations(
                    conn, silver_table, gold_table, data_columns, source
                )

                # Count gold records
                gold_count = await conn.fetchval(f"""
                    SELECT COUNT(*) FROM {gold_table}
                """)
                result.records_inserted = gold_count or 0

                logger.info(
                    f"Gold transform for {source}: "
                    f"{result.records_inserted} aggregations from {result.records_processed} records"
                )

        except Exception as e:
            logger.error(f"Gold transformation failed for {source}: {e}")
            result.errors.append(str(e))

        result.duration_seconds = time.time() - start_time
        return result

    async def _create_gold_table(
        self,
        conn,
        table_name: str,
        columns: List[Dict[str, Any]],
        source: str
    ):
        """Create gold aggregation table."""
        ddl = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id SERIAL PRIMARY KEY,
                source TEXT NOT NULL DEFAULT '{source}',
                aggregation_type TEXT NOT NULL,
                dimension_name TEXT,
                dimension_value TEXT,
                record_count INTEGER,
                metrics JSONB,
                computed_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(source, aggregation_type, dimension_name, dimension_value)
            )
        """
        await conn.execute(ddl)

        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{source}_gold_agg
            ON {table_name} (aggregation_type, dimension_name)
        """)

    async def _generate_gold_aggregations(
        self,
        conn,
        silver_table: str,
        gold_table: str,
        columns: List[Dict[str, Any]],
        source: str
    ):
        """Generate various aggregations for the gold layer."""

        # Check if molecule_id column exists (entity linking enabled)
        has_molecule_id = any(c['name'] == 'molecule_id' for c in columns)

        # 1. Overall summary
        if has_molecule_id:
            summary = await conn.fetchrow(f"""
                SELECT
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE is_valid) as valid_records,
                    COUNT(molecule_id) as linked_records,
                    COUNT(DISTINCT molecule_id) as unique_molecules,
                    MIN(normalized_at) as first_record,
                    MAX(normalized_at) as last_record
                FROM {silver_table}
            """)
        else:
            summary = await conn.fetchrow(f"""
                SELECT
                    COUNT(*) as total_records,
                    COUNT(*) FILTER (WHERE is_valid) as valid_records,
                    0 as linked_records,
                    0 as unique_molecules,
                    MIN(normalized_at) as first_record,
                    MAX(normalized_at) as last_record
                FROM {silver_table}
            """)

        metrics = {
            'valid_records': summary['valid_records'],
            'first_record': summary['first_record'].isoformat() if summary['first_record'] else None,
            'last_record': summary['last_record'].isoformat() if summary['last_record'] else None,
            'validity_rate': summary['valid_records'] / summary['total_records'] if summary['total_records'] else 0
        }

        # Add entity linking statistics
        if has_molecule_id:
            metrics['linked_records'] = summary['linked_records']
            metrics['unique_molecules'] = summary['unique_molecules']
            metrics['linking_rate'] = summary['linked_records'] / summary['total_records'] if summary['total_records'] else 0

        await conn.execute(f"""
            INSERT INTO {gold_table} (source, aggregation_type, dimension_name, dimension_value, record_count, metrics)
            VALUES ($1, 'summary', 'overall', 'all', $2, $3)
            ON CONFLICT (source, aggregation_type, dimension_name, dimension_value)
            DO UPDATE SET record_count = $2, metrics = $3, computed_at = NOW()
        """, source, summary['total_records'], json.dumps(metrics))

        # 1b. Entity linking summary (if enabled)
        if has_molecule_id and summary['linked_records'] > 0:
            await conn.execute(f"""
                INSERT INTO {gold_table} (source, aggregation_type, dimension_name, dimension_value, record_count, metrics)
                VALUES ($1, 'entity_linking', 'status', 'linked', $2, $3)
                ON CONFLICT (source, aggregation_type, dimension_name, dimension_value)
                DO UPDATE SET record_count = $2, metrics = $3, computed_at = NOW()
            """, source, summary['linked_records'], json.dumps({
                'unique_molecules': summary['unique_molecules'],
                'records_per_molecule': summary['linked_records'] / summary['unique_molecules'] if summary['unique_molecules'] else 0
            }))

            await conn.execute(f"""
                INSERT INTO {gold_table} (source, aggregation_type, dimension_name, dimension_value, record_count, metrics)
                VALUES ($1, 'entity_linking', 'status', 'unlinked', $2, $3)
                ON CONFLICT (source, aggregation_type, dimension_name, dimension_value)
                DO UPDATE SET record_count = $2, metrics = $3, computed_at = NOW()
            """, source, summary['total_records'] - summary['linked_records'], json.dumps({
                'percentage': (summary['total_records'] - summary['linked_records']) / summary['total_records'] if summary['total_records'] else 0
            }))

        # 2. Aggregations by text columns (top values)
        text_columns = [c for c in columns if c['type'] in ('text', 'character varying')]

        for col in text_columns[:5]:  # Limit to first 5 text columns
            col_name = col['name']
            try:
                top_values = await conn.fetch(f"""
                    SELECT {col_name} as value, COUNT(*) as cnt
                    FROM {silver_table}
                    WHERE is_valid = TRUE AND {col_name} IS NOT NULL
                    GROUP BY {col_name}
                    ORDER BY cnt DESC
                    LIMIT 10
                """)

                for row in top_values:
                    if row['value']:
                        await conn.execute(f"""
                            INSERT INTO {gold_table}
                            (source, aggregation_type, dimension_name, dimension_value, record_count, metrics)
                            VALUES ($1, 'top_values', $2, $3, $4, $5)
                            ON CONFLICT (source, aggregation_type, dimension_name, dimension_value)
                            DO UPDATE SET record_count = $4, metrics = $5, computed_at = NOW()
                        """, source, col_name, str(row['value'])[:255], row['cnt'], json.dumps({
                            'percentage': row['cnt'] / summary['total_records'] if summary['total_records'] else 0
                        }))
            except Exception as e:
                logger.warning(f"Could not aggregate column {col_name}: {e}")

        # 3. Numeric column statistics
        numeric_columns = [c for c in columns if c['type'] in ('integer', 'bigint', 'numeric', 'real', 'double precision')]

        for col in numeric_columns[:5]:
            col_name = col['name']
            try:
                stats = await conn.fetchrow(f"""
                    SELECT
                        COUNT({col_name}) as count,
                        AVG({col_name}::numeric) as avg,
                        MIN({col_name}) as min,
                        MAX({col_name}) as max,
                        STDDEV({col_name}::numeric) as stddev
                    FROM {silver_table}
                    WHERE is_valid = TRUE
                """)

                await conn.execute(f"""
                    INSERT INTO {gold_table}
                    (source, aggregation_type, dimension_name, dimension_value, record_count, metrics)
                    VALUES ($1, 'numeric_stats', $2, 'statistics', $3, $4)
                    ON CONFLICT (source, aggregation_type, dimension_name, dimension_value)
                    DO UPDATE SET record_count = $3, metrics = $4, computed_at = NOW()
                """, source, col_name, stats['count'], json.dumps({
                    'avg': float(stats['avg']) if stats['avg'] else None,
                    'min': float(stats['min']) if stats['min'] else None,
                    'max': float(stats['max']) if stats['max'] else None,
                    'stddev': float(stats['stddev']) if stats['stddev'] else None,
                }))
            except Exception as e:
                logger.warning(f"Could not compute stats for column {col_name}: {e}")

    # =========================================================================
    # Retroactive Entity Linking
    # =========================================================================

    async def relink_unlinked_records(
        self,
        source: str,
        batch_size: int = 1000
    ) -> TransformResult:
        """
        Re-attempt entity linking for Silver records that have NULL molecule_id.

        This is useful when:
        1. A second data source adds new molecules to the master database
        2. The identifier_mappings table is updated with new mappings
        3. Initial linking failed due to missing data

        Records that were previously unlinked will be checked again against
        the current state of the molecule database.
        """
        import time
        start_time = time.time()

        result = TransformResult(
            source=source,
            layer='relink',
            records_processed=0,
            records_inserted=0,
            records_updated=0,
            records_failed=0,
            errors=[],
            duration_seconds=0
        )

        try:
            config = await self.get_source_config(source)
            if not config:
                result.errors.append(f"Source {source} not found")
                return result

            options = config['options']
            entity_linking = options.get('entity_linking', {})

            if not entity_linking.get('identifier_field') or not entity_linking.get('identifier_type'):
                result.errors.append(f"Entity linking not configured for {source}")
                return result

            raw_table = options.get('target_table', f'raw.{source}')
            silver_table = raw_table.replace('raw.', 'silver.')

            # Get columns from silver table
            columns = await self.get_table_columns(silver_table)
            data_columns = [
                c for c in columns
                if c['name'] not in ('id', 'silver_metadata', 'is_valid', 'validation_errors', 'normalized_at', 'molecule_id')
            ]

            async with self.db_pool.acquire() as conn:
                # Check if molecule_id column exists
                has_molecule_id = any(c['name'] == 'molecule_id' for c in columns)
                if not has_molecule_id:
                    result.errors.append(f"Silver table {silver_table} does not have molecule_id column")
                    return result

                # Get unlinked silver records
                unlinked_records = await conn.fetch(f"""
                    SELECT *
                    FROM {silver_table}
                    WHERE is_valid = TRUE
                    AND (molecule_id IS NULL OR molecule_id = '')
                    ORDER BY normalized_at
                    LIMIT $1
                """, batch_size)

                result.records_processed = len(unlinked_records)

                if result.records_processed == 0:
                    logger.info(f"No unlinked records to relink for {source}")
                    return result

                # Load fresh identifier mappings
                identifier_cache = await self._load_identifier_mappings(
                    conn, entity_linking, unlinked_records
                )

                for record in unlinked_records:
                    try:
                        # Extract cleaned values
                        cleaned_values = {c['name']: record.get(c['name']) for c in data_columns}

                        # Try to resolve entity with fresh cache
                        molecule_id = await self._resolve_entity(
                            cleaned_values, entity_linking, identifier_cache
                        )

                        if molecule_id:
                            # Update the record with the new molecule_id
                            await conn.execute(f"""
                                UPDATE {silver_table}
                                SET molecule_id = $1,
                                    silver_metadata = silver_metadata || $2
                                WHERE id = $3
                            """, molecule_id, json.dumps({
                                'relinked_at': datetime.utcnow().isoformat()
                            }), record['id'])
                            result.records_updated += 1

                    except Exception as e:
                        result.records_failed += 1
                        if len(result.errors) < 10:
                            result.errors.append(f"Record {record['id']}: {str(e)[:100]}")

                logger.info(
                    f"Retroactive linking for {source}: "
                    f"{result.records_updated}/{result.records_processed} records now linked"
                )

        except Exception as e:
            logger.error(f"Retroactive linking failed for {source}: {e}")
            result.errors.append(str(e))

        result.duration_seconds = time.time() - start_time
        return result

    async def relink_all_sources(self, batch_size: int = 1000) -> Dict[str, TransformResult]:
        """
        Re-attempt entity linking for all dynamic sources that have unlinked records.

        Call this after importing new molecules to the master database.
        """
        results = {}
        sources = await get_dynamic_sources(self.db_pool)

        for source in sources:
            config = await self.get_source_config(source)
            if config and config['options'].get('entity_linking', {}).get('identifier_field'):
                results[source] = await self.relink_unlinked_records(source, batch_size)

        return results

    # =========================================================================
    # Full Pipeline
    # =========================================================================

    async def run_full_pipeline(
        self,
        source: str,
        batch_size: int = 1000
    ) -> Dict[str, TransformResult]:
        """
        Run the full Raw → Bronze → Silver → Gold pipeline for a source.
        """
        results = {}

        logger.info(f"Starting full medallion pipeline for dynamic source: {source}")

        # Raw → Bronze
        results['bronze'] = await self.transform_raw_to_bronze(source, batch_size)
        if results['bronze'].errors and results['bronze'].records_inserted == 0:
            logger.error(f"Bronze transformation failed for {source}, stopping pipeline")
            return results

        # Bronze → Silver
        results['silver'] = await self.transform_bronze_to_silver(source, batch_size)
        if results['silver'].errors and results['silver'].records_inserted == 0:
            logger.error(f"Silver transformation failed for {source}, stopping pipeline")
            return results

        # Silver → Gold
        results['gold'] = await self.transform_silver_to_gold(source)

        logger.info(
            f"Completed medallion pipeline for {source}: "
            f"Bronze={results['bronze'].records_inserted}, "
            f"Silver={results['silver'].records_inserted}, "
            f"Gold={results['gold'].records_inserted}"
        )

        return results


async def get_dynamic_sources(pool) -> List[str]:
    """Get list of dynamically onboarded sources (not built-in)."""
    builtin_sources = {
        'clinicaltrials', 'openfda_faers', 'openfda_labels',
        'chembl', 'pubchem', 'drugbank', 'uniprot', 'openalex',
        'clinicaltrials_gov', 'who_inn', 'kegg_drug', 'ttd',
        'fda_drugs', 'imgt', 'cdc_vaccines'
    }

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT source FROM raw.sync_schedules
            WHERE options->>'target_table' IS NOT NULL
        """)

        return [
            row['source'] for row in rows
            if row['source'] not in builtin_sources
        ]
