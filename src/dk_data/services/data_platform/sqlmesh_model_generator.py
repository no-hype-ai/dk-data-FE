"""
SQLMesh Model Generator Service

Dynamically generates SQLMesh SQL models from transformation rules stored in the database.
Enables zero-code onboarding of new data sources.

Part of DK Molecule Data Platform
"""

import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass
from uuid import UUID
import logging

from jinja2 import Environment, BaseLoader

logger = logging.getLogger(__name__)


@dataclass
class TransformationRule:
    """Transformation rule from database."""
    id: UUID
    source_name: str
    source_table: str
    target_table: str
    target_type: str
    column_mappings: Dict[str, str]
    computed_columns: Dict[str, str]
    identifier_mappings: Dict[str, str]
    name_mappings: Dict[str, str]
    dedup_strategy: str
    dedup_columns: List[str]
    dedup_confidence_threshold: float
    source_precedence: int
    incremental_column: Optional[str]
    batch_size: int
    where_clause: Optional[str]
    enabled: bool


@dataclass
class GeneratedModel:
    """Result of model generation."""
    model_name: str
    model_sql: str
    model_hash: str
    file_path: str
    rule_id: UUID


class SQLMeshModelGenerator:
    """
    Service for generating SQLMesh models from transformation rules.

    Features:
    - Reads rules from raw.silver_transformation_rules
    - Generates SQLMesh-compatible SQL models
    - Handles molecule, identifier, and name lookup transformations
    - Supports incremental processing
    - Tracks generated models for change detection
    """

    # Base path for generated models (relative to sqlmesh directory)
    MODELS_BASE_PATH = "models/generated"

    # Jinja2 environment for template rendering
    jinja_env = Environment(loader=BaseLoader())

    def __init__(self, db_pool, sqlmesh_root: str = None):
        """
        Initialize the generator.

        Args:
            db_pool: Database connection pool
            sqlmesh_root: Root directory for SQLMesh models
        """
        self.db_pool = db_pool
        self.sqlmesh_root = sqlmesh_root or self._find_sqlmesh_root()

    def _find_sqlmesh_root(self) -> str:
        """Find the SQLMesh root directory."""
        # Look for sqlmesh directory relative to this file
        current = Path(__file__).parent
        for _ in range(5):  # Search up to 5 levels
            sqlmesh_path = current / "sqlmesh"
            if sqlmesh_path.exists():
                return str(sqlmesh_path)
            sqlmesh_path = current.parent / "sqlmesh"
            if sqlmesh_path.exists():
                return str(sqlmesh_path)
            current = current.parent

        # Default fallback for dk-data-FE structure
        return str(Path(__file__).parent.parent.parent / "sqlmesh")

    async def load_transformation_rules(self, source_name: Optional[str] = None) -> List[TransformationRule]:
        """
        Load transformation rules from database.

        Args:
            source_name: Optional filter by source name

        Returns:
            List of TransformationRule objects
        """
        async with self.db_pool.acquire() as conn:
            query = """
                SELECT id, source_name, source_table, target_table, target_type,
                       column_mappings, computed_columns, identifier_mappings, name_mappings,
                       dedup_strategy, dedup_columns, dedup_confidence_threshold,
                       source_precedence, incremental_column, batch_size, where_clause, enabled
                FROM raw.silver_transformation_rules
                WHERE enabled = true
            """
            params = []

            if source_name:
                query += " AND source_name = $1"
                params.append(source_name)

            query += " ORDER BY source_precedence ASC"

            rows = await conn.fetch(query, *params)

            rules = []
            for row in rows:
                rules.append(TransformationRule(
                    id=row['id'],
                    source_name=row['source_name'],
                    source_table=row['source_table'],
                    target_table=row['target_table'],
                    target_type=row['target_type'],
                    column_mappings=row['column_mappings'] or {},
                    computed_columns=row['computed_columns'] or {},
                    identifier_mappings=row['identifier_mappings'] or {},
                    name_mappings=row['name_mappings'] or {},
                    dedup_strategy=row['dedup_strategy'],
                    dedup_columns=row['dedup_columns'] or ['inchi_key'],
                    dedup_confidence_threshold=float(row['dedup_confidence_threshold'] or 0.8),
                    source_precedence=row['source_precedence'],
                    incremental_column=row['incremental_column'],
                    batch_size=row['batch_size'] or 1000,
                    where_clause=row['where_clause'],
                    enabled=row['enabled']
                ))

            return rules

    def generate_molecule_model(self, rule: TransformationRule) -> str:
        """
        Generate SQLMesh model for molecule transformation.

        Args:
            rule: Transformation rule

        Returns:
            Generated SQL model content
        """
        # Build column selections
        column_selections = []
        for bronze_col, silver_col in rule.column_mappings.items():
            if bronze_col == silver_col:
                column_selections.append(f"        {bronze_col}")
            else:
                column_selections.append(f"        {bronze_col} AS {silver_col}")

        # Add computed columns
        for silver_col, expression in rule.computed_columns.items():
            column_selections.append(f"        {expression} AS {silver_col}")

        # Build development status CASE expression if max_phase is mapped
        dev_status_expr = ""
        if 'max_phase' in rule.column_mappings.values():
            dev_status_expr = """
        CASE
            WHEN max_phase = 4 THEN 'approved'
            WHEN max_phase = 3 THEN 'phase_3'
            WHEN max_phase = 2 THEN 'phase_2'
            WHEN max_phase = 1 THEN 'phase_1'
            ELSE 'preclinical'
        END AS development_status,"""

        # Build WHERE clause
        where_parts = ["processed_to_silver = FALSE"]
        if rule.where_clause:
            where_parts.append(f"({rule.where_clause})")

        # Dedup columns
        dedup_cols = rule.dedup_columns if rule.dedup_columns else ['inchi_key']
        primary_dedup = dedup_cols[0]

        model_sql = f'''-- SQLMesh Model: Silver {rule.source_name.title()} Molecules
-- Auto-generated from transformation rules on {datetime.utcnow().isoformat()}
-- Source: {rule.source_table}
-- DO NOT EDIT MANUALLY - Changes will be overwritten

MODEL (
    name silver.{rule.source_name}_molecules,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key {primary_dedup},
        when_matched_update_all TRUE
    ),
    cron '@daily',
    audits (
        not_null(columns := ({primary_dedup}))
    ),
    grain {primary_dedup}
);

-- Source precedence: {rule.source_precedence} (lower = higher priority)

WITH source_data AS (
    SELECT
{chr(10).join(column_selections)}
    FROM {rule.source_table}
    WHERE {' AND '.join(where_parts)}
    {"AND @incremental_time_filter(" + rule.incremental_column + ")" if rule.incremental_column else ""}
),

deduplicated AS (
    SELECT DISTINCT ON ({', '.join(dedup_cols)})
        gen_random_uuid() AS id,
        *,{dev_status_expr}
        {rule.dedup_confidence_threshold} AS resolution_confidence,
        FALSE AS needs_review,
        NULL::TEXT AS review_reason,
        jsonb_build_array('{rule.source_name}') AS data_sources,
        '{rule.source_name}' AS primary_source,
        {rule.source_precedence} AS source_precedence,
        NOW() AS created_at,
        NOW() AS updated_at
    FROM source_data
    WHERE {primary_dedup} IS NOT NULL
    ORDER BY {', '.join(dedup_cols)}, source_updated_at DESC NULLS LAST
)

SELECT * FROM deduplicated;


-- Post-insert: Mark Bronze records as processed
@post_incremental(
    UPDATE {rule.source_table}
    SET processed_to_silver = TRUE
    WHERE processed_to_silver = FALSE
    AND {primary_dedup} IN (SELECT {primary_dedup} FROM silver.{rule.source_name}_molecules)
);
'''
        return model_sql

    def generate_identifier_model(self, rule: TransformationRule) -> str:
        """
        Generate SQLMesh model for identifier extraction.

        Args:
            rule: Transformation rule with identifier_mappings

        Returns:
            Generated SQL model content for identifier_mappings
        """
        if not rule.identifier_mappings:
            return ""

        # Build UNION ALL for each identifier type
        unions = []
        for identifier_type, source_column in rule.identifier_mappings.items():
            union_sql = f'''
-- {identifier_type} from {rule.source_name}
SELECT
    m.id AS molecule_id,
    '{identifier_type}' AS identifier_type,
    s.{source_column}::TEXT AS identifier_value,
    '{rule.source_name}' AS source,
    1.0 AS confidence,
    TRUE AS is_primary,
    s.source_updated_at AS source_date,
    NOW() AS created_at
FROM silver.molecules m
JOIN {rule.source_table} s ON m.inchi_key = s.inchi_key
WHERE s.{source_column} IS NOT NULL
  AND m.needs_review = FALSE'''
            unions.append(union_sql)

        model_sql = f'''-- SQLMesh Model: Silver {rule.source_name.title()} Identifier Mappings
-- Auto-generated from transformation rules on {datetime.utcnow().isoformat()}
-- Source: {rule.source_table}
-- DO NOT EDIT MANUALLY - Changes will be overwritten

MODEL (
    name silver.{rule.source_name}_identifiers,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, identifier_type, identifier_value)
    ),
    cron '@daily',
    audits (
        not_null(columns := (molecule_id, identifier_type, identifier_value))
    ),
    grain (molecule_id, identifier_type, identifier_value)
);

{" UNION ALL ".join(unions)};
'''
        return model_sql

    def generate_name_lookup_model(self, rule: TransformationRule) -> str:
        """
        Generate SQLMesh model for drug name lookup.

        Args:
            rule: Transformation rule with name_mappings

        Returns:
            Generated SQL model content for drug_name_lookup
        """
        if not rule.name_mappings:
            return ""

        unions = []
        for name_type, source_column in rule.name_mappings.items():
            # Check if it's a JSONB array column (for synonyms, brands, etc.)
            if 'synonyms' in source_column.lower() or 'brands' in source_column.lower():
                # Handle JSONB array
                union_sql = f'''
-- {name_type} names from {rule.source_name} (JSONB array)
SELECT
    m.id AS molecule_id,
    name_val AS name,
    '{name_type}' AS name_type,
    LOWER(TRIM(name_val)) AS name_normalized,
    '{rule.source_name}' AS source,
    NOW() AS created_at
FROM silver.molecules m
JOIN {rule.source_table} s ON m.inchi_key = s.inchi_key
CROSS JOIN LATERAL jsonb_array_elements_text(s.{source_column}) AS name_val
WHERE s.{source_column} IS NOT NULL
  AND jsonb_array_length(s.{source_column}) > 0
  AND m.needs_review = FALSE
  AND name_val IS NOT NULL
  AND LENGTH(TRIM(name_val)) > 0'''
            else:
                # Handle scalar column
                union_sql = f'''
-- {name_type} names from {rule.source_name}
SELECT
    m.id AS molecule_id,
    s.{source_column} AS name,
    '{name_type}' AS name_type,
    LOWER(TRIM(s.{source_column})) AS name_normalized,
    '{rule.source_name}' AS source,
    NOW() AS created_at
FROM silver.molecules m
JOIN {rule.source_table} s ON m.inchi_key = s.inchi_key
WHERE s.{source_column} IS NOT NULL
  AND m.needs_review = FALSE'''
            unions.append(union_sql)

        model_sql = f'''-- SQLMesh Model: Silver {rule.source_name.title()} Drug Name Lookup
-- Auto-generated from transformation rules on {datetime.utcnow().isoformat()}
-- Source: {rule.source_table}
-- DO NOT EDIT MANUALLY - Changes will be overwritten

MODEL (
    name silver.{rule.source_name}_names,
    kind INCREMENTAL_BY_UNIQUE_KEY (
        unique_key (molecule_id, name_normalized, source)
    ),
    cron '@daily',
    audits (
        not_null(columns := (molecule_id, name, name_normalized, source))
    ),
    grain (molecule_id, name_normalized, source)
);

{" UNION ALL ".join(unions)};
'''
        return model_sql

    def generate_unified_silver_model(self, rules: List[TransformationRule]) -> str:
        """
        Generate a unified silver.molecules model that merges all sources.

        This model combines molecules from all source-specific models
        using source precedence for deduplication.

        Args:
            rules: List of all transformation rules

        Returns:
            Generated SQL model content
        """
        # Sort by precedence
        sorted_rules = sorted(rules, key=lambda r: r.source_precedence)

        # Build source CTEs
        source_ctes = []
        for rule in sorted_rules:
            cte = f'''
    {rule.source_name}_molecules AS (
        SELECT * FROM silver.{rule.source_name}_molecules
    )'''
            source_ctes.append(cte)

        # Build UNION ALL
        unions = []
        for rule in sorted_rules:
            unions.append(f"    SELECT * FROM {rule.source_name}_molecules")

        model_sql = f'''-- SQLMesh Model: Unified Silver Molecules
-- Auto-generated from transformation rules on {datetime.utcnow().isoformat()}
-- Merges molecules from all sources using precedence-based deduplication
-- DO NOT EDIT MANUALLY - Changes will be overwritten

MODEL (
    name silver.molecules_unified,
    kind FULL,
    cron '@daily',
    audits (
        not_null(columns := (inchi_key, canonical_name)),
        unique_values(columns := (inchi_key))
    ),
    grain inchi_key
);

-- Source precedence (lower = higher priority):
-- {chr(10).join([f"-- {r.source_precedence}: {r.source_name}" for r in sorted_rules])}

WITH
{','.join(source_ctes)},

all_molecules AS (
{chr(10).join([f"    {u}" for i, u in enumerate(unions)])}
),

-- Deduplicate by InChI Key, keeping highest precedence source
deduplicated AS (
    SELECT DISTINCT ON (inchi_key)
        *
    FROM all_molecules
    WHERE inchi_key IS NOT NULL
    ORDER BY inchi_key, source_precedence ASC, updated_at DESC
)

SELECT * FROM deduplicated;
'''
        return model_sql

    async def generate_all_models(
        self,
        source_name: Optional[str] = None,
        write_to_disk: bool = True
    ) -> List[GeneratedModel]:
        """
        Generate all SQLMesh models from transformation rules.

        Args:
            source_name: Optional filter by source name
            write_to_disk: Whether to write models to disk

        Returns:
            List of GeneratedModel objects
        """
        rules = await self.load_transformation_rules(source_name)

        if not rules:
            logger.warning("No transformation rules found")
            return []

        generated_models = []

        for rule in rules:
            # Generate molecule model
            mol_sql = self.generate_molecule_model(rule)
            mol_model = await self._create_model(
                rule, "molecules", mol_sql, write_to_disk
            )
            generated_models.append(mol_model)

            # Generate identifier model (if mappings exist)
            if rule.identifier_mappings:
                id_sql = self.generate_identifier_model(rule)
                id_model = await self._create_model(
                    rule, "identifiers", id_sql, write_to_disk
                )
                generated_models.append(id_model)

            # Generate name lookup model (if mappings exist)
            if rule.name_mappings:
                name_sql = self.generate_name_lookup_model(rule)
                name_model = await self._create_model(
                    rule, "names", name_sql, write_to_disk
                )
                generated_models.append(name_model)

        # Generate unified model if multiple sources
        if len(rules) > 1 and not source_name:
            unified_sql = self.generate_unified_silver_model(rules)
            unified_model = await self._create_unified_model(
                rules, unified_sql, write_to_disk
            )
            generated_models.append(unified_model)

        # Register models in database
        await self._register_models(generated_models)

        logger.info(f"Generated {len(generated_models)} SQLMesh models")
        return generated_models

    async def _create_model(
        self,
        rule: TransformationRule,
        model_type: str,
        sql: str,
        write_to_disk: bool
    ) -> GeneratedModel:
        """Create a GeneratedModel object and optionally write to disk."""
        model_name = f"silver.{rule.source_name}_{model_type}"
        file_name = f"{rule.source_name}_{model_type}.sql"
        file_path = f"{self.MODELS_BASE_PATH}/silver/{file_name}"
        model_hash = hashlib.sha256(sql.encode()).hexdigest()

        if write_to_disk:
            full_path = Path(self.sqlmesh_root) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(sql)
            logger.info(f"Written model to {full_path}")

        return GeneratedModel(
            model_name=model_name,
            model_sql=sql,
            model_hash=model_hash,
            file_path=file_path,
            rule_id=rule.id
        )

    async def _create_unified_model(
        self,
        rules: List[TransformationRule],
        sql: str,
        write_to_disk: bool
    ) -> GeneratedModel:
        """Create unified model."""
        model_name = "silver.molecules_unified"
        file_name = "molecules_unified.sql"
        file_path = f"{self.MODELS_BASE_PATH}/silver/{file_name}"
        model_hash = hashlib.sha256(sql.encode()).hexdigest()

        if write_to_disk:
            full_path = Path(self.sqlmesh_root) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(sql)
            logger.info(f"Written unified model to {full_path}")

        return GeneratedModel(
            model_name=model_name,
            model_sql=sql,
            model_hash=model_hash,
            file_path=file_path,
            rule_id=rules[0].id  # Use first rule's ID for reference
        )

    async def _register_models(self, models: List[GeneratedModel]) -> None:
        """Register generated models in database for tracking."""
        async with self.db_pool.acquire() as conn:
            for model in models:
                await conn.execute("""
                    INSERT INTO raw.generated_sqlmesh_models
                    (model_name, source_rule_id, model_sql, model_hash, file_path,
                     generation_status, last_generated_at)
                    VALUES ($1, $2, $3, $4, $5, 'generated', NOW())
                    ON CONFLICT (model_name) DO UPDATE SET
                        source_rule_id = EXCLUDED.source_rule_id,
                        model_sql = EXCLUDED.model_sql,
                        model_hash = EXCLUDED.model_hash,
                        file_path = EXCLUDED.file_path,
                        generation_status = 'generated',
                        last_generated_at = NOW(),
                        updated_at = NOW()
                """, model.model_name, model.rule_id, model.model_sql,
                    model.model_hash, model.file_path)

    async def check_for_changes(self) -> List[str]:
        """
        Check if any transformation rules have changed since last generation.

        Returns:
            List of source names that need regeneration
        """
        async with self.db_pool.acquire() as conn:
            # Find rules updated after their models were generated
            rows = await conn.fetch("""
                SELECT DISTINCT r.source_name
                FROM raw.silver_transformation_rules r
                LEFT JOIN raw.generated_sqlmesh_models m
                    ON m.source_rule_id = r.id
                WHERE r.enabled = true
                  AND (m.id IS NULL
                       OR r.updated_at > m.last_generated_at)
            """)

            return [row['source_name'] for row in rows]

    async def regenerate_if_needed(self) -> List[GeneratedModel]:
        """
        Regenerate models only for sources that have changed.

        Returns:
            List of regenerated models
        """
        changed_sources = await self.check_for_changes()

        if not changed_sources:
            logger.info("No transformation rule changes detected")
            return []

        logger.info(f"Regenerating models for: {changed_sources}")

        all_models = []
        for source in changed_sources:
            models = await self.generate_all_models(source_name=source)
            all_models.extend(models)

        return all_models


# =============================================================================
# CLI Interface
# =============================================================================

async def main():
    """CLI entry point for model generation."""
    import asyncpg
    import sys

    # Parse arguments
    regenerate_all = "--all" in sys.argv
    source_filter = None
    for i, arg in enumerate(sys.argv):
        if arg == "--source" and i + 1 < len(sys.argv):
            source_filter = sys.argv[i + 1]

    # Connect to database
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5433/dk_data"
    )
    pool = await asyncpg.create_pool(db_url)

    try:
        generator = SQLMeshModelGenerator(pool)

        if regenerate_all or source_filter:
            models = await generator.generate_all_models(source_name=source_filter)
            print(f"Generated {len(models)} models:")
            for m in models:
                print(f"  - {m.model_name} -> {m.file_path}")
        else:
            models = await generator.regenerate_if_needed()
            if models:
                print(f"Regenerated {len(models)} models:")
                for m in models:
                    print(f"  - {m.model_name} -> {m.file_path}")
            else:
                print("No models needed regeneration")

    finally:
        await pool.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
