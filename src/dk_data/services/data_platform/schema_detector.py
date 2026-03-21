"""
Schema Detector Service

Auto-detects JSON schema from API responses and infers PostgreSQL types.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import re
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class PostgresType(str, Enum):
    """PostgreSQL column types."""
    TEXT = "TEXT"
    INTEGER = "INTEGER"
    BIGINT = "BIGINT"
    NUMERIC = "NUMERIC"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    TIMESTAMP = "TIMESTAMP"
    TIMESTAMPTZ = "TIMESTAMPTZ"
    JSONB = "JSONB"
    UUID = "UUID"


@dataclass
class ColumnSchema:
    """Schema definition for a single column."""
    name: str
    postgres_type: PostgresType
    nullable: bool = True
    is_array: bool = False
    json_path: str = ""
    sample_values: List[Any] = field(default_factory=list)
    description: str = ""


@dataclass
class TableSchema:
    """Complete table schema definition."""
    table_name: str
    columns: List[ColumnSchema]
    primary_key: Optional[str] = None
    unique_columns: List[str] = field(default_factory=list)
    indexes: List[str] = field(default_factory=list)
    source_api: str = ""
    detected_at: datetime = field(default_factory=datetime.utcnow)


class SchemaDetector:
    """
    Service for detecting JSON schema and inferring PostgreSQL types.

    Features:
    - Analyze JSON samples to infer types
    - Detect nested structures
    - Identify potential primary keys
    - Generate column mappings
    """

    # Patterns for type detection
    DATE_PATTERNS = [
        r'^\d{4}-\d{2}-\d{2}$',  # ISO date
        r'^\d{4}\d{2}\d{2}$',    # YYYYMMDD
        r'^\d{2}/\d{2}/\d{4}$',  # MM/DD/YYYY
    ]

    TIMESTAMP_PATTERNS = [
        r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # ISO timestamp
        r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',  # SQL timestamp
    ]

    UUID_PATTERN = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'

    # Common identifier field names
    ID_FIELD_PATTERNS = [
        r'^id$',
        r'^.*_id$',
        r'^.*Id$',
        r'^nct_id$',
        r'^drugbank_id$',
        r'^chembl_id$',
        r'^set_id$',
        r'^safety_report_id$',
    ]

    def __init__(self, max_samples: int = 100):
        """
        Initialize schema detector.

        Args:
            max_samples: Maximum samples to analyze for type inference
        """
        self.max_samples = max_samples

    def detect_schema(
        self,
        json_samples: List[Dict[str, Any]],
        table_name: str,
        source_api: str = ""
    ) -> TableSchema:
        """
        Detect schema from JSON samples.

        Args:
            json_samples: List of JSON objects to analyze
            table_name: Name for the resulting table
            source_api: Source API identifier

        Returns:
            TableSchema with detected columns and types
        """
        if not json_samples:
            raise ValueError("No samples provided for schema detection")

        # Limit samples
        samples = json_samples[:self.max_samples]

        # Collect all fields and their values
        field_values: Dict[str, List[Any]] = defaultdict(list)
        field_paths: Dict[str, str] = {}

        for sample in samples:
            self._collect_fields(sample, field_values, field_paths)

        # Infer types for each field
        columns = []
        for field_name, values in field_values.items():
            column = self._infer_column_schema(
                field_name,
                values,
                field_paths.get(field_name, field_name)
            )
            columns.append(column)

        # Sort columns by name
        columns.sort(key=lambda c: c.name)

        # Detect primary key
        primary_key = self._detect_primary_key(columns)

        # Detect unique columns
        unique_columns = self._detect_unique_columns(columns, field_values)

        # Suggest indexes
        indexes = self._suggest_indexes(columns)

        return TableSchema(
            table_name=table_name,
            columns=columns,
            primary_key=primary_key,
            unique_columns=unique_columns,
            indexes=indexes,
            source_api=source_api,
        )

    def _collect_fields(
        self,
        obj: Any,
        field_values: Dict[str, List[Any]],
        field_paths: Dict[str, str],
        prefix: str = "",
        path: str = ""
    ):
        """Recursively collect fields and their values from JSON."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                field_name = f"{prefix}{key}" if prefix else key
                json_path = f"{path}->'{key}'" if path else f"->'{key}'"

                if isinstance(value, dict):
                    # Nested object - flatten or store as JSONB
                    if len(value) > 5:
                        # Complex nested object -> JSONB
                        field_values[field_name].append(value)
                        field_paths[field_name] = json_path
                    else:
                        # Simple nested object -> flatten
                        self._collect_fields(
                            value, field_values, field_paths,
                            f"{field_name}_", json_path
                        )
                elif isinstance(value, list):
                    # Array - store as JSONB
                    field_values[field_name].append(value)
                    field_paths[field_name] = json_path
                else:
                    field_values[field_name].append(value)
                    field_paths[field_name] = json_path

    def _infer_column_schema(
        self,
        field_name: str,
        values: List[Any],
        json_path: str
    ) -> ColumnSchema:
        """Infer column schema from collected values."""
        # Filter out None values
        non_null = [v for v in values if v is not None]
        nullable = len(non_null) < len(values)

        if not non_null:
            # All null - default to TEXT
            return ColumnSchema(
                name=self._sanitize_column_name(field_name),
                postgres_type=PostgresType.TEXT,
                nullable=True,
                json_path=json_path,
            )

        # Check for arrays
        if all(isinstance(v, list) for v in non_null):
            return ColumnSchema(
                name=self._sanitize_column_name(field_name),
                postgres_type=PostgresType.JSONB,
                nullable=nullable,
                is_array=True,
                json_path=json_path,
                sample_values=non_null[:3],
            )

        # Check for nested objects
        if all(isinstance(v, dict) for v in non_null):
            return ColumnSchema(
                name=self._sanitize_column_name(field_name),
                postgres_type=PostgresType.JSONB,
                nullable=nullable,
                json_path=json_path,
                sample_values=non_null[:3],
            )

        # Infer scalar type
        postgres_type = self._infer_scalar_type(non_null)

        return ColumnSchema(
            name=self._sanitize_column_name(field_name),
            postgres_type=postgres_type,
            nullable=nullable,
            json_path=json_path,
            sample_values=non_null[:5],
        )

    def _infer_scalar_type(self, values: List[Any]) -> PostgresType:
        """Infer PostgreSQL type from scalar values."""
        # Check boolean first
        if all(isinstance(v, bool) for v in values):
            return PostgresType.BOOLEAN

        # Check numeric types
        if all(isinstance(v, int) for v in values):
            max_val = max(abs(v) for v in values)
            if max_val > 2147483647:
                return PostgresType.BIGINT
            return PostgresType.INTEGER

        if all(isinstance(v, (int, float)) for v in values):
            return PostgresType.NUMERIC

        # Check string patterns
        str_values = [str(v) for v in values if v is not None]

        if str_values:
            # Check UUID
            if all(re.match(self.UUID_PATTERN, v, re.I) for v in str_values):
                return PostgresType.UUID

            # Check timestamps
            if all(any(re.match(p, v) for p in self.TIMESTAMP_PATTERNS) for v in str_values):
                return PostgresType.TIMESTAMPTZ

            # Check dates
            if all(any(re.match(p, v) for p in self.DATE_PATTERNS) for v in str_values):
                return PostgresType.DATE

        return PostgresType.TEXT

    def _sanitize_column_name(self, name: str) -> str:
        """Sanitize field name for PostgreSQL column."""
        # Replace dots and dashes with underscores
        sanitized = re.sub(r'[.\-\s]', '_', name)
        # Remove other special characters
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '', sanitized)
        # Ensure doesn't start with number
        if sanitized and sanitized[0].isdigit():
            sanitized = f"col_{sanitized}"
        # Lowercase
        sanitized = sanitized.lower()
        return sanitized or "unnamed"

    def _detect_primary_key(self, columns: List[ColumnSchema]) -> Optional[str]:
        """Detect likely primary key column."""
        for column in columns:
            for pattern in self.ID_FIELD_PATTERNS:
                if re.match(pattern, column.name, re.I):
                    return column.name
        return None

    def _detect_unique_columns(
        self,
        columns: List[ColumnSchema],
        field_values: Dict[str, List[Any]]
    ) -> List[str]:
        """Detect columns with unique values."""
        unique = []
        for column in columns:
            values = field_values.get(column.name, [])
            non_null = [v for v in values if v is not None]
            if len(non_null) > 10 and len(set(str(v) for v in non_null)) == len(non_null):
                unique.append(column.name)
        return unique

    def _suggest_indexes(self, columns: List[ColumnSchema]) -> List[str]:
        """Suggest columns to index."""
        indexes = []
        for column in columns:
            # Index ID-like columns
            if any(re.match(p, column.name, re.I) for p in self.ID_FIELD_PATTERNS):
                indexes.append(column.name)
            # Index date columns
            elif column.postgres_type in (PostgresType.DATE, PostgresType.TIMESTAMP, PostgresType.TIMESTAMPTZ):
                indexes.append(column.name)
        return indexes

    def generate_create_table_sql(
        self,
        schema: TableSchema,
        schema_name: str = "mol_bronze"
    ) -> str:
        """
        Generate CREATE TABLE SQL from detected schema.

        Args:
            schema: TableSchema from detect_schema
            schema_name: PostgreSQL schema name

        Returns:
            CREATE TABLE SQL statement
        """
        lines = [f"CREATE TABLE IF NOT EXISTS {schema_name}.{schema.table_name} ("]
        lines.append("    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),")

        for column in schema.columns:
            null_clause = "" if column.nullable else " NOT NULL"
            lines.append(f"    {column.name} {column.postgres_type.value}{null_clause},")

        # Add metadata columns
        lines.append("    raw_json JSONB,")
        lines.append("    raw_source_id UUID,")
        lines.append("    source TEXT NOT NULL,")
        lines.append("    source_updated_at TIMESTAMPTZ,")
        lines.append("    processed_to_silver BOOLEAN DEFAULT FALSE,")
        lines.append("    created_at TIMESTAMPTZ DEFAULT NOW()")
        lines.append(");")

        # Add indexes
        for idx_col in schema.indexes:
            lines.append(
                f"\nCREATE INDEX IF NOT EXISTS idx_{schema.table_name}_{idx_col} "
                f"ON {schema_name}.{schema.table_name} ({idx_col});"
            )

        # Add JSONB GIN index
        lines.append(
            f"\nCREATE INDEX IF NOT EXISTS idx_{schema.table_name}_raw_json "
            f"ON {schema_name}.{schema.table_name} USING GIN (raw_json);"
        )

        return "\n".join(lines)

    def generate_sqlmesh_model(
        self,
        schema: TableSchema,
        raw_table: str,
        cron_schedule: str = "@daily",
        schema_name: str = "mol_bronze"
    ) -> str:
        """
        Generate SQLMesh model SQL from detected schema.

        Args:
            schema: TableSchema from detect_schema
            raw_table: Name of the raw source table
            cron_schedule: SQLMesh cron schedule
            schema_name: Target bronze schema (mol_bronze or hcs_bronze)

        Returns:
            SQLMesh model SQL
        """
        grain_col = schema.primary_key or schema.columns[0].name if schema.columns else "id"

        lines = [
            f"-- SQLMesh Model: Bronze {schema.table_name.title()}",
            f"-- Auto-generated from {schema.source_api}",
            f"-- Generated at: {schema.detected_at.isoformat()}",
            "",
            "MODEL (",
            f"    name {schema_name}.{schema.table_name},",
            "    kind INCREMENTAL_BY_TIME_RANGE (",
            "        time_column request_timestamp,",
            "        batch_size 500",
            "    ),",
            f"    cron '{cron_schedule}',",
            "    audits (",
            f"        not_null(columns := ({grain_col}))",
            "    ),",
            f"    grain {grain_col}",
            ");",
            "",
            "SELECT",
            "    gen_random_uuid() AS id,",
        ]

        # Add column extractions
        for column in schema.columns:
            cast = ""
            if column.postgres_type == PostgresType.INTEGER:
                cast = "::INTEGER"
            elif column.postgres_type == PostgresType.BIGINT:
                cast = "::BIGINT"
            elif column.postgres_type == PostgresType.NUMERIC:
                cast = "::NUMERIC"
            elif column.postgres_type == PostgresType.BOOLEAN:
                cast = "::BOOLEAN"
            elif column.postgres_type == PostgresType.DATE:
                cast = "::DATE"
            elif column.postgres_type == PostgresType.TIMESTAMPTZ:
                cast = "::TIMESTAMPTZ"

            if column.postgres_type == PostgresType.JSONB:
                lines.append(f"    response_body{column.json_path} AS {column.name},")
            else:
                lines.append(f"    (response_body{column.json_path}){cast} AS {column.name},")

        # Add standard columns
        lines.extend([
            "",
            "    response_body AS raw_json,",
            "    id AS raw_source_id,",
            f"    '{schema.source_api}' AS source,",
            "    request_timestamp AS source_updated_at,",
            "    FALSE AS processed_to_silver,",
            "    NOW() AS created_at",
            "",
            f"FROM mol_raw.{raw_table}",
            "WHERE",
            "    response_status = 200",
            "    AND processed_to_bronze = FALSE",
            "    AND request_timestamp BETWEEN @start_dt AND @end_dt;",
        ])

        return "\n".join(lines)
