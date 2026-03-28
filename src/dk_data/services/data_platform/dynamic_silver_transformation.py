"""
Dynamic Silver Transformation Service

Provides a configuration-driven approach to Bronze -> Silver transformation.
Reads rules from database and executes transformations without hardcoded logic.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from uuid import UUID
import logging
import json

from .sqlmesh_model_generator import SQLMeshModelGenerator, TransformationRule

logger = logging.getLogger(__name__)


@dataclass
class TransformationResult:
    """Result of a transformation run."""
    source_name: str
    records_processed: int
    records_inserted: int
    records_updated: int
    records_linked: int
    identifiers_extracted: int
    names_extracted: int
    duration_seconds: float
    errors: List[str]
    success: bool


@dataclass
class EntityLinkResult:
    """Result of entity linking."""
    molecule_id: UUID
    source_record_id: UUID
    link_type: str  # new, matched_inchi, matched_identifier, matched_name
    confidence: float
    matched_by: Optional[str]


class DynamicSilverTransformation:
    """
    Service for dynamically transforming Bronze data to Silver layer.

    This service:
    1. Reads transformation rules from raw.silver_transformation_rules
    2. Executes transformations using SQL (no hardcoded Python logic)
    3. Links new entities to existing mol_silver.molecules
    4. Extracts identifiers to mol_silver.identifier_mappings
    5. Extracts names to mol_silver.drug_name_lookup
    """

    def __init__(self, db_pool):
        """
        Initialize the transformation service.

        Args:
            db_pool: Database connection pool
        """
        self.db_pool = db_pool
        self.model_generator = SQLMeshModelGenerator(db_pool)

    async def transform_source(
        self,
        source_name: str,
        batch_size: Optional[int] = None,
        dry_run: bool = False
    ) -> TransformationResult:
        """
        Transform a single source from Bronze to Silver.

        Args:
            source_name: Name of the source to transform
            batch_size: Override batch size from config
            dry_run: If True, don't commit changes

        Returns:
            TransformationResult with statistics
        """
        start_time = datetime.utcnow()
        errors = []
        mol_result = {'processed': 0, 'inserted': 0, 'updated': 0, 'processed_ids': []}
        link_result = {'linked': 0}
        id_result = {'extracted': 0}
        name_result = {'extracted': 0}

        # Load rule
        rules = await self.model_generator.load_transformation_rules(source_name)
        if not rules:
            return TransformationResult(
                source_name=source_name,
                records_processed=0,
                records_inserted=0,
                records_updated=0,
                records_linked=0,
                identifiers_extracted=0,
                names_extracted=0,
                duration_seconds=0,
                errors=[f"No transformation rule found for source: {source_name}"],
                success=False
            )

        rule = rules[0]
        batch_size = batch_size or rule.batch_size

        try:
            async with self.db_pool.acquire() as conn:
                # Start transaction
                if not dry_run:
                    await conn.execute("BEGIN")

                # Step 1: Transform molecules
                mol_result = await self._transform_molecules(conn, rule, batch_size)

                # Step 2: Link to existing molecules
                link_result = await self._link_entities(conn, rule)

                # Step 3: Extract identifiers
                id_result = await self._extract_identifiers(conn, rule)

                # Step 4: Extract names
                name_result = await self._extract_names(conn, rule)

                # Step 5: Mark processed
                await self._mark_processed(conn, rule, mol_result['processed_ids'])

                # Update last run stats
                await conn.execute("""
                    UPDATE raw.silver_transformation_rules
                    SET last_run_at = NOW(),
                        last_run_records = $1
                    WHERE source_name = $2
                """, mol_result['inserted'], source_name)

                if dry_run:
                    await conn.execute("ROLLBACK")
                    logger.info(f"Dry run completed for {source_name}")
                else:
                    await conn.execute("COMMIT")
                    logger.info(f"Transformation committed for {source_name}")

        except Exception as e:
            errors.append(str(e))
            logger.error(f"Transformation failed for {source_name}: {e}")
            if not dry_run:
                async with self.db_pool.acquire() as conn:
                    await conn.execute("ROLLBACK")

        duration = (datetime.utcnow() - start_time).total_seconds()

        return TransformationResult(
            source_name=source_name,
            records_processed=mol_result.get('processed', 0),
            records_inserted=mol_result.get('inserted', 0),
            records_updated=mol_result.get('updated', 0),
            records_linked=link_result.get('linked', 0),
            identifiers_extracted=id_result.get('extracted', 0),
            names_extracted=name_result.get('extracted', 0),
            duration_seconds=duration,
            errors=errors,
            success=len(errors) == 0
        )

    async def _transform_molecules(
        self,
        conn,
        rule: TransformationRule,
        batch_size: int
    ) -> Dict[str, Any]:
        """Execute molecule transformation using dynamic SQL."""
        # Build column mappings
        select_cols = []
        for bronze_col, silver_col in rule.column_mappings.items():
            if bronze_col == silver_col:
                select_cols.append(bronze_col)
            else:
                select_cols.append(f"{bronze_col} AS {silver_col}")

        # Add computed columns
        for silver_col, expr in rule.computed_columns.items():
            select_cols.append(f"({expr}) AS {silver_col}")

        # Build WHERE clause
        where_parts = ["processed_to_silver = FALSE"]
        if rule.where_clause:
            where_parts.append(f"({rule.where_clause})")

        # Primary dedup column
        dedup_col = rule.dedup_columns[0] if rule.dedup_columns else 'inchi_key'

        # Build transformation SQL
        transform_sql = f"""
            WITH source_batch AS (
                SELECT
                    {', '.join(select_cols)},
                    source_updated_at,
                    id AS bronze_id
                FROM {rule.source_table}
                WHERE {' AND '.join(where_parts)}
                ORDER BY source_updated_at ASC
                LIMIT {batch_size}
            ),
            deduplicated AS (
                SELECT DISTINCT ON ({dedup_col})
                    gen_random_uuid() AS id,
                    *,
                    {rule.dedup_confidence_threshold} AS resolution_confidence,
                    FALSE AS needs_review,
                    jsonb_build_array('{rule.source_name}') AS data_sources,
                    '{rule.source_name}' AS primary_source,
                    NOW() AS created_at,
                    NOW() AS updated_at
                FROM source_batch
                WHERE {dedup_col} IS NOT NULL
                ORDER BY {dedup_col}, source_updated_at DESC
            )
            INSERT INTO mol_silver.molecules (
                id, {', '.join([c.split(' AS ')[-1] if ' AS ' in c else c for c in select_cols])},
                resolution_confidence, needs_review, data_sources, primary_source, created_at, updated_at
            )
            SELECT
                id, {', '.join([c.split(' AS ')[-1] if ' AS ' in c else c for c in select_cols])},
                resolution_confidence, needs_review, data_sources, primary_source, created_at, updated_at
            FROM deduplicated d
            WHERE NOT EXISTS (
                SELECT 1 FROM mol_silver.molecules m WHERE m.{dedup_col} = d.{dedup_col}
            )
            ON CONFLICT ({dedup_col}) DO UPDATE SET
                data_sources = mol_silver.molecules.data_sources || EXCLUDED.data_sources,
                updated_at = NOW()
            RETURNING id, {dedup_col}
        """

        try:
            result = await conn.fetch(transform_sql)
            processed_ids = [row['id'] for row in result]

            return {
                'processed': len(result),
                'inserted': len(result),
                'updated': 0,  # Would need separate tracking
                'processed_ids': processed_ids
            }
        except Exception as e:
            logger.error(f"Molecule transformation error: {e}")
            logger.error(f"SQL: {transform_sql[:500]}...")
            raise

    async def _link_entities(
        self,
        conn,
        rule: TransformationRule
    ) -> Dict[str, Any]:
        """Link new entities to existing molecules using configured strategy."""
        linked = 0

        if rule.dedup_strategy == 'inchi_key':
            # InChI key matching is handled by the INSERT ... ON CONFLICT
            pass

        elif rule.dedup_strategy == 'identifier_match':
            # Match by identifiers
            for id_type, source_col in rule.identifier_mappings.items():
                link_sql = f"""
                    UPDATE mol_silver.molecules m
                    SET data_sources = m.data_sources || '"{rule.source_name}"',
                        updated_at = NOW()
                    FROM {rule.source_table} s
                    WHERE s.{source_col} IS NOT NULL
                      AND EXISTS (
                          SELECT 1 FROM mol_silver.identifier_mappings im
                          WHERE im.identifier_type = '{id_type}'
                            AND im.identifier_value = s.{source_col}::TEXT
                            AND im.molecule_id = m.id
                      )
                      AND NOT (m.data_sources ? '{rule.source_name}')
                """
                result = await conn.execute(link_sql)
                linked += int(result.split()[-1]) if result else 0

        elif rule.dedup_strategy == 'name_fuzzy':
            # Fuzzy name matching
            name_col = rule.name_mappings.get('generic') or list(rule.column_mappings.keys())[0]
            link_sql = f"""
                UPDATE mol_silver.molecules m
                SET data_sources = m.data_sources || '"{rule.source_name}"',
                    updated_at = NOW()
                FROM {rule.source_table} s
                WHERE s.{name_col} IS NOT NULL
                  AND similarity(LOWER(s.{name_col}), LOWER(m.canonical_name)) > {rule.dedup_confidence_threshold}
                  AND NOT (m.data_sources ? '{rule.source_name}')
            """
            result = await conn.execute(link_sql)
            linked += int(result.split()[-1]) if result else 0

        return {'linked': linked}

    async def _extract_identifiers(
        self,
        conn,
        rule: TransformationRule
    ) -> Dict[str, Any]:
        """Extract identifiers from source to mol_silver.identifier_mappings."""
        if not rule.identifier_mappings:
            return {'extracted': 0}

        extracted = 0

        for id_type, source_col in rule.identifier_mappings.items():
            extract_sql = f"""
                INSERT INTO mol_silver.identifier_mappings (
                    molecule_id, identifier_type, identifier_value, source,
                    confidence, is_primary, source_date, created_at
                )
                SELECT
                    m.id,
                    '{id_type}',
                    s.{source_col}::TEXT,
                    '{rule.source_name}',
                    1.0,
                    TRUE,
                    s.source_updated_at,
                    NOW()
                FROM mol_silver.molecules m
                JOIN {rule.source_table} s ON m.inchi_key = s.inchi_key
                WHERE s.{source_col} IS NOT NULL
                  AND m.needs_review = FALSE
                ON CONFLICT (molecule_id, identifier_type, identifier_value) DO NOTHING
            """
            try:
                result = await conn.execute(extract_sql)
                count = int(result.split()[-1]) if result and 'INSERT' in result else 0
                extracted += count
            except Exception as e:
                logger.warning(f"Identifier extraction error for {id_type}: {e}")

        return {'extracted': extracted}

    async def _extract_names(
        self,
        conn,
        rule: TransformationRule
    ) -> Dict[str, Any]:
        """Extract drug names from source to mol_silver.drug_name_lookup."""
        if not rule.name_mappings:
            return {'extracted': 0}

        extracted = 0

        for name_type, source_col in rule.name_mappings.items():
            # Check if JSONB array or scalar
            is_array = 'synonyms' in source_col.lower() or 'brands' in source_col.lower()

            if is_array:
                extract_sql = f"""
                    INSERT INTO mol_silver.drug_name_lookup (
                        molecule_id, name, name_type, name_normalized, source, created_at
                    )
                    SELECT
                        m.id,
                        name_val,
                        '{name_type}',
                        LOWER(TRIM(name_val)),
                        '{rule.source_name}',
                        NOW()
                    FROM mol_silver.molecules m
                    JOIN {rule.source_table} s ON m.inchi_key = s.inchi_key
                    CROSS JOIN LATERAL jsonb_array_elements_text(s.{source_col}) AS name_val
                    WHERE s.{source_col} IS NOT NULL
                      AND jsonb_array_length(s.{source_col}) > 0
                      AND m.needs_review = FALSE
                      AND name_val IS NOT NULL
                      AND LENGTH(TRIM(name_val)) > 0
                    ON CONFLICT (molecule_id, name_normalized, source) DO NOTHING
                """
            else:
                extract_sql = f"""
                    INSERT INTO mol_silver.drug_name_lookup (
                        molecule_id, name, name_type, name_normalized, source, created_at
                    )
                    SELECT
                        m.id,
                        s.{source_col},
                        '{name_type}',
                        LOWER(TRIM(s.{source_col})),
                        '{rule.source_name}',
                        NOW()
                    FROM mol_silver.molecules m
                    JOIN {rule.source_table} s ON m.inchi_key = s.inchi_key
                    WHERE s.{source_col} IS NOT NULL
                      AND m.needs_review = FALSE
                    ON CONFLICT (molecule_id, name_normalized, source) DO NOTHING
                """

            try:
                result = await conn.execute(extract_sql)
                count = int(result.split()[-1]) if result and 'INSERT' in result else 0
                extracted += count
            except Exception as e:
                logger.warning(f"Name extraction error for {name_type}: {e}")

        return {'extracted': extracted}

    async def _mark_processed(
        self,
        conn,
        rule: TransformationRule,
        processed_ids: List[UUID]
    ) -> None:
        """Mark Bronze records as processed."""
        if not processed_ids:
            return

        dedup_col = rule.dedup_columns[0] if rule.dedup_columns else 'inchi_key'

        mark_sql = f"""
            UPDATE {rule.source_table}
            SET processed_to_silver = TRUE
            WHERE {dedup_col} IN (
                SELECT {dedup_col} FROM mol_silver.molecules WHERE id = ANY($1::uuid[])
            )
        """
        await conn.execute(mark_sql, processed_ids)

    async def transform_all_sources(
        self,
        dry_run: bool = False
    ) -> List[TransformationResult]:
        """
        Transform all enabled sources.

        Args:
            dry_run: If True, don't commit changes

        Returns:
            List of TransformationResult for each source
        """
        rules = await self.model_generator.load_transformation_rules()
        results = []

        # Sort by precedence
        rules.sort(key=lambda r: r.source_precedence)

        for rule in rules:
            logger.info(f"Transforming source: {rule.source_name}")
            result = await self.transform_source(rule.source_name, dry_run=dry_run)
            results.append(result)

        return results

    async def register_new_source(
        self,
        source_name: str,
        source_table: str,
        column_mappings: Dict[str, str],
        identifier_mappings: Optional[Dict[str, str]] = None,
        name_mappings: Optional[Dict[str, str]] = None,
        source_precedence: int = 10,
        dedup_strategy: str = 'inchi_key',
        generate_models: bool = True
    ) -> Tuple[bool, str]:
        """
        Register a new data source for transformation.

        This is the main entry point for onboarding new sources.

        Args:
            source_name: Unique name for the source
            source_table: Bronze table name (e.g., 'mol_bronze.new_source')
            column_mappings: Bronze -> Silver column mappings
            identifier_mappings: Identifier extraction rules
            name_mappings: Name extraction rules
            source_precedence: Priority (lower = higher)
            dedup_strategy: Deduplication strategy
            generate_models: Whether to generate SQLMesh models

        Returns:
            Tuple of (success, message)
        """
        try:
            async with self.db_pool.acquire() as conn:
                # Insert transformation rule
                await conn.execute("""
                    INSERT INTO raw.silver_transformation_rules (
                        source_name, source_table, target_table, target_type,
                        column_mappings, identifier_mappings, name_mappings,
                        dedup_strategy, source_precedence, enabled
                    ) VALUES ($1, $2, 'mol_silver.molecules', 'molecule', $3, $4, $5, $6, $7, true)
                    ON CONFLICT (source_name) DO UPDATE SET
                        source_table = EXCLUDED.source_table,
                        column_mappings = EXCLUDED.column_mappings,
                        identifier_mappings = EXCLUDED.identifier_mappings,
                        name_mappings = EXCLUDED.name_mappings,
                        dedup_strategy = EXCLUDED.dedup_strategy,
                        source_precedence = EXCLUDED.source_precedence,
                        updated_at = NOW()
                """,
                    source_name,
                    source_table,
                    json.dumps(column_mappings),
                    json.dumps(identifier_mappings or {}),
                    json.dumps(name_mappings or {}),
                    dedup_strategy,
                    source_precedence
                )

            # Generate SQLMesh models
            if generate_models:
                models = await self.model_generator.generate_all_models(source_name)
                model_paths = [m.file_path for m in models]
                return True, f"Registered source '{source_name}' with {len(models)} models: {model_paths}"

            return True, f"Registered source '{source_name}' (models not generated)"

        except Exception as e:
            logger.error(f"Failed to register source {source_name}: {e}")
            return False, str(e)


# =============================================================================
# Convenience Functions
# =============================================================================

async def register_source(
    db_pool,
    source_name: str,
    source_table: str,
    column_mappings: Dict[str, str],
    **kwargs
) -> Tuple[bool, str]:
    """
    Quick registration of a new data source.

    Example:
        success, msg = await register_source(
            pool,
            source_name='new_pharma_db',
            source_table='mol_bronze.new_pharma_db',
            column_mappings={
                'inchi_key': 'inchi_key',
                'drug_name': 'canonical_name',
                'smiles': 'canonical_smiles'
            },
            identifier_mappings={
                'internal_id': 'new_pharma_id'
            }
        )
    """
    service = DynamicSilverTransformation(db_pool)
    return await service.register_new_source(
        source_name, source_table, column_mappings, **kwargs
    )


async def transform_source(db_pool, source_name: str) -> TransformationResult:
    """Quick transformation of a single source."""
    service = DynamicSilverTransformation(db_pool)
    return await service.transform_source(source_name)
